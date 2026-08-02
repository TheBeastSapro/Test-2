"""Geography for the map renderer: a land mask, a projection, and great circles.

## Why a raster mask and not the coastline vectors

The obvious thing to ship is the coastline polygons and stroke them. The documentary
map look is not a stroked coastline, though — it is a *dot grid*, land rendered as
thousands of small dots on a dark field, because that reads at a glance, survives
compression, and does not turn into a tangle of hairlines at 720p. Answering "is this
grid cell land?" a hundred thousand times per frame is a raster question, so the data
is a raster: one bit per cell, 1024x512, from Natural Earth 110m.

That is 64 KB raw, 6.7 KB deflated, and it ships in the package. No download at
runtime, no network dependency in a tool that is supposed to work on a plane.

Natural Earth is public domain (CC0). The mask was rasterised from `ne_110m_land`.

## The two things that are easy to get wrong

**Great circles.** The short path between two points on a sphere is not a straight
line on an equirectangular map. Interpolating longitude and latitude linearly draws a
line that is visibly, embarrassingly wrong for any long route — a New York-to-Tokyo
arc drawn that way passes over the mid-Pacific instead of over the Arctic. So
`great_circle` slerps on the unit sphere and projects each sample.

**The antimeridian.** A route that crosses ±180 degrees projects to two points at
opposite edges of the map, and naively connecting them draws a line straight back
across the entire frame. Every polyline this module produces is therefore returned as
a *list of segments*, already split at the seam. Callers draw each segment separately.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MASK_WIDTH = 1024
MASK_HEIGHT = 512
MASK_FILE = Path(__file__).resolve().parent / "data" / "land_110m.bin"

# A point this far from its neighbour in projected x is a seam crossing, not a move.
# Half the map is the only threshold that cannot be confused with a legitimate step,
# because no single great-circle sample step spans more than a quarter of the globe.
_SEAM_FRACTION = 0.5


@lru_cache(maxsize=1)
def land_mask() -> bytes:
    """The packed land bitmap, one bit per cell, row-major from 90N/180W."""
    return zlib.decompress(MASK_FILE.read_bytes())


def is_land(lat: float, lon: float) -> bool:
    """Whether a coordinate falls on land, to the resolution of the mask (~0.35 deg)."""
    mask = land_mask()
    x = int((lon + 180.0) / 360.0 * MASK_WIDTH)
    y = int((90.0 - lat) / 180.0 * MASK_HEIGHT)
    x = min(max(x, 0), MASK_WIDTH - 1)
    y = min(max(y, 0), MASK_HEIGHT - 1)
    index = y * MASK_WIDTH + x
    # Pillow packs 1-bit rows MSB first, and the row stride is padded to whole bytes.
    # MASK_WIDTH is a multiple of 8, so the stride is exactly MASK_WIDTH // 8.
    return bool(mask[index >> 3] & (0x80 >> (index & 7)))


def wrap_lon(value: float) -> float:
    """Fold a longitude into [-180, 180)."""
    return (value + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class Bounds:
    """A longitude/latitude window, which may cross the antimeridian.

    When it does, `east` is numerically less than `west` — the window runs eastward off
    the right edge of the map and back on at the left. Every method here is written to
    survive that, because the alternative is a map that cannot frame the Pacific, and
    the Pacific is where the trade routes and flight paths are.
    """

    west: float = -180.0
    east: float = 180.0
    south: float = -85.0
    north: float = 85.0

    @property
    def lon_span(self) -> float:
        span = self.east - self.west
        return span + 360.0 if span <= 0 else span

    @property
    def lat_span(self) -> float:
        return self.north - self.south

    @property
    def lon_centre(self) -> float:
        return wrap_lon(self.west + self.lon_span / 2)

    @property
    def straddles(self) -> bool:
        """Whether this window crosses the antimeridian (east is 'less than' west)."""
        return self.east < self.west

    def with_lon_span(self, span: float, centre: float | None = None) -> Bounds:
        """A window of the given longitude span, keeping (or moving) the centre.

        Works in centre-and-span rather than west-and-east because a window that
        crosses the antimeridian has `east < west`, and every clamp written in terms of
        the two edges gets that case wrong.
        """
        span = max(0.001, min(360.0, span))
        middle = self.lon_centre if centre is None else wrap_lon(centre)
        # A full turn is *not* special-cased to (-180, 180). Coverage is identical
        # either way, but the centre is what a push-in interpolates towards, and
        # throwing it away here silently pinned every opening world view to Greenwich —
        # which is how a Pacific route ended up panning across the seam. At span 360
        # west and east coincide, and `lon_span` reads that as a full turn.
        return Bounds(
            wrap_lon(middle - span / 2), wrap_lon(middle + span / 2),
            self.south, self.north,
        )

    def padded(self, fraction: float = 0.18) -> Bounds:
        """Widen by a fraction of the current span.

        Framing a set of markers exactly to their extent puts them on the frame edge,
        which reads as a crop rather than a view. Padding is what makes it a shot.
        """
        lat_pad = self.lat_span * fraction
        widened = self.with_lon_span(self.lon_span * (1 + 2 * fraction))
        return Bounds(
            west=widened.west, east=widened.east,
            south=max(-85.0, self.south - lat_pad),
            north=min(85.0, self.north + lat_pad),
        )

    def with_aspect(self, aspect: float) -> Bounds:
        """Grow the narrow axis until the window matches the frame's aspect ratio.

        Equirectangular pixels are square exactly when `lon_span / lat_span` equals the
        frame's aspect. Anything else stretches the map, and a stretched coastline is
        the single most obvious tell that a map was generated rather than designed.

        ## Why latitude is allowed past the poles

        The whole world is 360 by 180 degrees — an aspect of 2.0. To show all of it in
        a 16:9 frame with square pixels you need 202 degrees of latitude, and to show
        it in a 9:16 frame you need 640. Neither exists.

        There are three ways out, and only one is right. Cropping longitude throws away
        the Pacific, and takes New Zealand and half of Alaska with it. Stretching is
        the thing this method exists to prevent — measured before this was fixed, the
        default world view was 1.19x tall at 16:9 and **3.77x** at 9:16, which is not a
        subtle artefact, it is a different map.

        The third way is to let the window extend beyond the poles. There is nothing
        above 90N to draw, so those rows render as plain ocean — and since the ocean is
        already the background colour, the padding is invisible. The map keeps its true
        proportions and the frame stays full. That is why the clamp here is generous
        rather than at the pole; `padded` still clamps to real latitudes, because that
        one is about framing content the viewer is meant to look at.
        """
        lon, lat = self.lon_span, self.lat_span
        if lat <= 0 or lon <= 0:
            return self
        current = lon / lat
        if abs(current - aspect) < 1e-6:
            return self

        if current < aspect:
            # Too tall: widen. Longitude has a hard limit at one full turn, past which
            # the window would show the same meridian twice.
            wanted = min(360.0, lat * aspect)
            if wanted > lon:
                widened = self.with_lon_span(wanted)
                if abs(widened.lon_span / lat - aspect) < 1e-6:
                    return widened
                # Longitude hit the full turn before the ratio was satisfied, so the
                # remainder has to come out of latitude instead.
                return widened._grow_latitude(aspect)
            return self._grow_latitude(aspect)

        return self._grow_latitude(aspect)

    def _grow_latitude(self, aspect: float) -> Bounds:
        """Set the latitude span so the ratio matches, centred on the current window."""
        wanted = self.lon_span / aspect
        if wanted <= self.lat_span:
            return self
        centre = (self.north + self.south) / 2
        half = wanted / 2
        south, north = centre - half, centre + half
        # Off-globe rows draw as ocean, so overshooting the poles is free — but keep it
        # bounded so an extreme aspect cannot produce a degenerate window.
        return Bounds(self.west, self.east, max(south, -400.0), min(north, 400.0))

    def lerp(self, other: Bounds, amount: float) -> Bounds:
        """Interpolate towards another window — how a map push-in is animated.

        Longitude is interpolated as centre-and-span along the shorter way round. The
        obvious version, blending `west` and `east` independently, sends a push-in from
        a world view to a Pacific view sweeping the long way across Eurasia, because
        the two edges cross the antimeridian at different moments.
        """
        t = max(0.0, min(1.0, amount))
        blend = lambda a, b: a + (b - a) * t  # noqa: E731

        delta = wrap_lon(other.lon_centre - self.lon_centre)
        centre = self.lon_centre + delta * t
        span = blend(self.lon_span, other.lon_span)

        latitudes = Bounds(
            -180.0, 180.0,
            blend(self.south, other.south), blend(self.north, other.north),
        )
        return latitudes.with_lon_span(span, centre)


def _enclosing_lon(lons: list[float]) -> tuple[float, float]:
    """The narrowest longitude arc containing every value, as (centre, span).

    Found by taking the *complement of the largest gap*. Using plain min and max
    instead is the bug that makes a Los Angeles-to-Tokyo map show the whole world:
    those two are 257 degrees apart the way min/max measures, and 103 degrees apart
    across the Pacific, which is the way anyone drawing that route means it.

    Returns centre and span rather than west and east because those two are ambiguous
    at the extremes — `west == east` reads as a zero-degree arc and as a full turn, and
    which one it means decides whether a lone marker gets a continent or a hemisphere.
    """
    ordered = sorted(wrap_lon(value) for value in lons)
    if len(ordered) == 1:
        return ordered[0], 0.0

    widest, seam = -1.0, 0
    for index in range(len(ordered)):
        gap = ordered[(index + 1) % len(ordered)] - ordered[index]
        if index == len(ordered) - 1:
            gap += 360.0
        if gap > widest:
            widest, seam = gap, index

    # The arc is everything the widest gap is not: it starts just after the gap and
    # runs round to the point that opened it.
    span = 360.0 - widest
    west = ordered[(seam + 1) % len(ordered)]
    return wrap_lon(west + span / 2), span


def bounds_for(points: list[tuple[float, float]], *, pad: float = 0.25) -> Bounds:
    """The narrowest window containing every (lat, lon), padded."""
    if not points:
        return Bounds()
    lats = [lat for lat, _ in points]
    centre, span = _enclosing_lon([lon for _, lon in points])

    # A lone point, or a tight cluster, has no meaningful span and would divide by
    # zero downstream. Give it a continent-sized view rather than an undefined one.
    lat_south, lat_north = min(lats), max(lats)
    if span < 1.0 or (lat_north - lat_south) < 1.0:
        span = max(span, 40.0)
        middle = (lat_south + lat_north) / 2
        lat_south, lat_north = middle - 14.0, middle + 14.0

    raw = Bounds(-180.0, 180.0, lat_south, lat_north).with_lon_span(span, centre)
    return raw.padded(pad)


@dataclass(frozen=True)
class Projection:
    """Equirectangular projection of a window onto a pixel frame.

    Equirectangular rather than something prettier because it is the projection the
    documentary-map look actually uses: it is what a dot grid reads as, it makes the
    inverse trivial, and every sample is a linear scale rather than a transcendental
    per point — which matters at a hundred thousand dots a frame.
    """

    bounds: Bounds
    width: int
    height: int

    def to_px(self, lat: float, lon: float) -> tuple[float, float]:
        west = self.bounds.west
        # Unwrap eastward so a window that straddles the antimeridian still increases.
        delta = lon - west
        if delta < 0:
            delta += 360.0
        x = delta / self.bounds.lon_span * self.width
        y = (self.bounds.north - lat) / self.bounds.lat_span * self.height
        return x, y

    def contains(self, lat: float, lon: float) -> bool:
        x, y = self.to_px(lat, lon)
        return 0 <= x <= self.width and 0 <= y <= self.height


# ----------------------------------------------------------------- great circles


def _to_vector(lat: float, lon: float) -> tuple[float, float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    return (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))


def _to_latlon(vector: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = vector
    return math.degrees(math.asin(z)), math.degrees(math.atan2(y, x))


def great_circle(
    start: tuple[float, float], end: tuple[float, float], *, samples: int = 96
) -> list[tuple[float, float]]:
    """The shorter great-circle path between two (lat, lon) points.

    Spherical linear interpolation, not interpolation of the coordinates. The
    difference is not subtle: linear lon/lat from New York to Tokyo draws a line across
    the mid-Pacific, while the real short route goes over the Arctic. Any viewer who
    has seen a flight map notices immediately.
    """
    a, b = _to_vector(*start), _to_vector(*end)
    dot = max(-1.0, min(1.0, sum(p * q for p, q in zip(a, b, strict=True))))
    omega = math.acos(dot)

    if omega < 1e-9:
        return [start, end]
    # Antipodal points have no unique short path; any meridian is equally correct, so
    # returning the straight interpolation is as good an answer as exists.
    if abs(omega - math.pi) < 1e-6:
        return [start, end]

    sin_omega = math.sin(omega)
    path = []
    for index in range(samples + 1):
        t = index / samples
        scale_a = math.sin((1 - t) * omega) / sin_omega
        scale_b = math.sin(t * omega) / sin_omega
        point = tuple(scale_a * p + scale_b * q for p, q in zip(a, b, strict=True))
        path.append(_to_latlon(point))  # type: ignore[arg-type]
    return path


def split_at_seam(
    points: list[tuple[float, float]], projection: Projection
) -> list[list[tuple[float, float]]]:
    """Break a projected polyline wherever it wraps around the antimeridian.

    Two consecutive samples on either side of the seam project to opposite edges of
    the frame. Drawing between them lays a line straight back across the whole map —
    the classic broken world-map artefact. Splitting there costs one comparison per
    sample and removes the artefact entirely.
    """
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    limit = projection.width * _SEAM_FRACTION
    previous_x: float | None = None

    for lat, lon in points:
        x, y = projection.to_px(lat, lon)
        if previous_x is not None and abs(x - previous_x) > limit:
            if len(current) > 1:
                segments.append(current)
            current = []
        current.append((x, y))
        previous_x = x

    if len(current) > 1:
        segments.append(current)
    return segments


# ------------------------------------------------------------------- a gazetteer
#
# Enough well-known places that a script can say "Rotterdam" and get a marker without
# the operator looking up coordinates. Deliberately small: this is a convenience, not
# a geocoder, and an unknown name is an error the caller can see rather than a silent
# guess at the wrong continent.

PLACES: dict[str, tuple[float, float]] = {
    "london": (51.51, -0.13), "paris": (48.86, 2.35), "berlin": (52.52, 13.40),
    "madrid": (40.42, -3.70), "rome": (41.90, 12.50), "amsterdam": (52.37, 4.90),
    "rotterdam": (51.92, 4.48), "moscow": (55.76, 37.62), "istanbul": (41.01, 28.98),
    "cairo": (30.04, 31.24), "lagos": (6.52, 3.38), "nairobi": (-1.29, 36.82),
    "johannesburg": (-26.20, 28.05), "dubai": (25.20, 55.27), "mumbai": (19.08, 72.88),
    "delhi": (28.61, 77.21), "singapore": (1.35, 103.82), "bangkok": (13.76, 100.50),
    "hong kong": (22.32, 114.17), "shanghai": (31.23, 121.47), "beijing": (39.90, 116.41),
    "seoul": (37.57, 126.98), "tokyo": (35.68, 139.69), "sydney": (-33.87, 151.21),
    "auckland": (-36.85, 174.76), "jakarta": (-6.21, 106.85),
    "new york": (40.71, -74.01), "washington": (38.91, -77.04),
    "los angeles": (34.05, -118.24), "san francisco": (37.77, -122.42),
    "chicago": (41.88, -87.63), "houston": (29.76, -95.37), "toronto": (43.65, -79.38),
    "vancouver": (49.28, -123.12), "mexico city": (19.43, -99.13),
    "panama canal": (9.08, -79.68), "sao paulo": (-23.55, -46.63),
    "rio de janeiro": (-22.91, -43.17), "buenos aires": (-34.60, -58.38),
    "lima": (-12.05, -77.04), "suez canal": (30.03, 32.55),
    "strait of hormuz": (26.57, 56.25), "strait of malacca": (2.50, 101.00),
    "gibraltar": (36.14, -5.35), "bab el-mandeb": (12.58, 43.33),
    "reykjavik": (64.15, -21.94), "svalbard": (78.22, 15.65),
}


def place(name: str) -> tuple[float, float]:
    """Look up a known place. Raises rather than guessing at an unknown one."""
    key = " ".join(str(name).lower().split())
    if key not in PLACES:
        raise KeyError(
            f"unknown place {name!r} — give (lat, lon) explicitly, or pick from "
            f"{len(PLACES)} known places"
        )
    return PLACES[key]


def resolve(value) -> tuple[float, float]:
    """Accept either a name or an explicit (lat, lon) pair."""
    if isinstance(value, str):
        return place(value)
    lat, lon = value
    return float(lat), float(lon)
