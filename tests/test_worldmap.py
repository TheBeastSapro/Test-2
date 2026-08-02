"""The animated world map, checked against geography rather than against itself.

Every assertion here has an answer that exists outside the code: New York to Tokyo
really does go over the Arctic, Los Angeles and Tokyo really are 103 degrees apart the
short way, the Sahara really is land and the mid-Pacific really is not. A map test
that only compares the renderer to itself would have passed at every stage of the four
geometry bugs this suite now guards.
"""

from __future__ import annotations

import math

import pytest

from forgecast.motion.geo import (
    Bounds,
    Projection,
    bounds_for,
    great_circle,
    is_land,
    place,
    resolve,
    split_at_seam,
    wrap_lon,
)
from forgecast.motion.worldmap import (
    MAP_LIBRARY,
    Arc,
    MapSpec,
    Marker,
    render_frame,
    spec_from,
)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = (math.radians(v) for v in (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(h))


# --------------------------------------------------------------------- land mask


@pytest.mark.parametrize("name,lat,lon,land", [
    ("London", 51.5, -0.1, True),
    ("Sahara", 23.0, 13.0, True),
    ("Kansas", 38.5, -98.0, True),
    ("Amazon", -3.5, -62.0, True),
    ("Siberia", 62.0, 100.0, True),
    ("Australia", -25.0, 133.0, True),
    ("Antarctica", -80.0, 0.0, True),
    ("mid Pacific", 0.0, -160.0, False),
    ("mid Atlantic", 30.0, -40.0, False),
    ("Southern Ocean", -55.0, 20.0, False),
    ("Bay of Bengal", 15.0, 88.0, False),
    ("Arctic Ocean", 88.0, 0.0, False),
])
def test_the_land_mask_agrees_with_the_world(name, lat, lon, land):
    assert is_land(lat, lon) is land, name


def test_the_mask_covers_a_believable_share_of_the_map():
    """A sanity bound on the data itself, in case the packed file is ever rebuilt.

    Land is 29% of the sphere but more of an equirectangular rectangle, because the
    projection stretches the high latitudes where Antarctica and Siberia are.
    """
    from forgecast.motion.geo import MASK_HEIGHT, MASK_WIDTH, land_mask

    ones = sum(bin(byte).count("1") for byte in land_mask())
    assert 0.28 < ones / (MASK_WIDTH * MASK_HEIGHT) < 0.42


# ------------------------------------------------------------------ great circles


def test_new_york_to_tokyo_goes_over_the_arctic():
    """Regression for the most visible possible error in a route map.

    Interpolating longitude and latitude linearly draws the New York-Tokyo route
    across the mid-Pacific, peaking at 40N. The real short path crosses the Arctic
    near Alaska, above 65N. Anyone who has seen a flight map spots the wrong one.
    """
    path = great_circle(place("new york"), place("tokyo"))
    peak = max(path, key=lambda point: point[0])
    assert peak[0] > 65.0, f"peaked at only {peak[0]:.1f}N"
    assert -170 < peak[1] < -120, "the high point should be over Alaska"


def test_a_great_circle_is_the_length_the_haversine_formula_says():
    for origin, destination in (("new york", "tokyo"), ("london", "sydney"),
                                ("lima", "cairo")):
        path = great_circle(place(origin), place(destination))
        walked = sum(haversine_km(path[i], path[i + 1]) for i in range(len(path) - 1))
        direct = haversine_km(place(origin), place(destination))
        assert abs(walked - direct) / direct < 0.001, f"{origin}->{destination}"


def test_a_great_circle_keeps_its_endpoints():
    start, end = place("paris"), place("lagos")
    path = great_circle(start, end)
    assert path[0] == pytest.approx(start, abs=1e-6)
    assert path[-1] == pytest.approx(end, abs=1e-6)


def test_identical_and_antipodal_points_do_not_blow_up():
    same = great_circle((10.0, 20.0), (10.0, 20.0))
    assert len(same) >= 2
    antipodal = great_circle((0.0, 0.0), (0.0, 180.0))
    assert len(antipodal) >= 2


# ------------------------------------------------------------------ the seam


def test_a_route_across_the_antimeridian_is_split():
    """Regression: without this the polyline is drawn straight back across the map.

    Two consecutive samples either side of the seam project to opposite frame edges.
    Joining them is the classic broken world-map artefact.
    """
    projection = Projection(Bounds(), 1280, 720)
    path = great_circle(place("tokyo"), place("los angeles"))
    segments = split_at_seam(path, projection)

    assert len(segments) == 2
    biggest = max(abs(segment[i + 1][0] - segment[i][0])
                  for segment in segments for i in range(len(segment) - 1))
    assert biggest < 640, "a segment jumped across the frame"


def test_a_route_that_stays_put_is_not_split():
    projection = Projection(Bounds(), 1280, 720)
    segments = split_at_seam(great_circle(place("london"), place("cairo")), projection)
    assert len(segments) == 1


# ------------------------------------------------------------------- framing


def test_the_enclosing_window_takes_the_short_way_round():
    """Regression: min/max longitude frames LA-to-Tokyo the wrong way.

    Measured, min and max put them 257 degrees apart — the long way across Eurasia,
    which shows the whole world and pushes in on nothing. Across the Pacific they are
    103 degrees apart, which is what anyone drawing that route means.
    """
    window = bounds_for([place("los angeles"), place("tokyo")], pad=0.0)
    assert window.lon_span < 120.0
    assert window.straddles
    assert -180 < window.lon_centre < -150


def test_an_ordinary_pair_is_framed_the_ordinary_way():
    window = bounds_for([place("rotterdam"), place("shanghai")], pad=0.0)
    assert not window.straddles
    assert window.lon_span == pytest.approx(117.0, abs=1.0)


def test_a_single_place_gets_a_region_not_a_hemisphere():
    """Regression: `west == east` reads both as a zero arc and as a full turn.

    Taking the wrong reading centred a lone marker's view on its antipode, and the
    marker then left the frame partway through the push-in.
    """
    window = bounds_for([place("london")], pad=0.0)
    assert 20.0 < window.lon_span < 90.0
    assert abs(wrap_lon(window.lon_centre - place("london")[1])) < 2.0


@pytest.mark.parametrize("width,height", [(1280, 720), (1080, 1920), (1000, 1000)])
def test_pixels_are_square_at_every_aspect(width, height):
    """Regression: the world view was 1.19x tall at 16:9 and 3.77x at 9:16.

    A stretched coastline is the most obvious tell that a map was generated rather
    than designed, and at 9:16 it was not a subtle artefact — it was a different map.
    """
    window = MapSpec(width=width, height=height, push_in=False).window_at(0.0)
    stretch = (height / window.lat_span) / (width / window.lon_span)
    assert stretch == pytest.approx(1.0, abs=0.001)


@pytest.mark.parametrize("places,width,height,seconds", [
    (["Los Angeles", "Tokyo"], 1080, 1920, 6.0),
    (["Rotterdam", "Suez Canal", "Singapore", "Shanghai"], 1280, 720, 9.0),
    (["Sydney", "Lima", "Auckland"], 1280, 720, 8.0),
    (["London"], 1280, 720, 5.0),
    (["Reykjavik", "Svalbard"], 1280, 720, 6.0),
    (["Auckland", "Vancouver"], 1280, 720, 7.0),
])
def test_a_marker_never_leaves_the_frame_after_it_lands(places, width, height, seconds):
    """The push-in must not lose what it is pushing in on.

    Two separate bugs did exactly that: a centre interpolated the short way round swept
    across the seam and dropped Tokyo for 1.3 seconds, and a full-turn window silently
    discarded its centre and pinned every opening view to Greenwich.
    """
    spec = spec_from(places, seconds=seconds, width=width, height=height)
    for step in range(int(seconds * 10) + 1):
        time = step / 10
        window = spec.window_at(time)
        stretch = (height / window.lat_span) / (width / window.lon_span)
        assert stretch == pytest.approx(1.0, abs=0.001), f"stretched at t={time}"

        projection = Projection(window, width, height)
        for marker in spec.markers:
            if time >= marker.at:
                assert projection.contains(marker.lat, marker.lon), (
                    f"{marker.label} left the frame at t={time}"
                )


# ------------------------------------------------------------------- staging


def test_markers_are_staged_rather_than_landing_together():
    spec = spec_from(["Rotterdam", "Suez Canal", "Singapore"], seconds=9.0)
    times = [marker.at for marker in spec.markers]
    assert times == sorted(times)
    assert times[0] > 0.2, "the first marker should wait for the reveal"
    assert times[-1] < 9.0 - 0.5, "the last marker needs a beat to rest on"
    assert len({round(t, 2) for t in times}) == 3, "they must not stack"


def test_each_arc_lands_with_its_destination():
    spec = spec_from(["Rotterdam", "Singapore", "Shanghai"], seconds=9.0)
    assert len(spec.arcs) == 2
    for arc, destination in zip(spec.arcs, spec.markers[1:], strict=True):
        assert arc.at + arc.duration == pytest.approx(destination.at, abs=0.05)


def test_no_places_means_no_push_and_no_crash():
    spec = spec_from([], seconds=5.0)
    assert spec.markers == [] and spec.arcs == []
    assert spec.window_at(2.5).lon_span == pytest.approx(360.0, abs=1.0)


# ------------------------------------------------------------------- rendering


def _totals(colour: str) -> int:
    text = colour.lstrip("#")
    return sum(int(text[i:i + 2], 16) for i in (0, 2, 4))


def test_a_rendered_frame_puts_land_where_land_is():
    style = MAP_LIBRARY["documentary_dark"]
    spec = MapSpec(width=640, height=360, push_in=False, style=style)
    frame = render_frame(spec, spec.seconds)
    pixels = frame.load()
    projection = Projection(spec.window_at(spec.seconds), 640, 360)
    threshold = _totals(style.land) - 10

    def peak(lat: float, lon: float, radius: int = 6) -> int:
        x, y = projection.to_px(lat, lon)
        return max(
            sum(pixels[int(x + dx), int(y + dy)])
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if 0 <= int(x + dx) < 640 and 0 <= int(y + dy) < 360
        )

    for lat, lon in ((23.0, 13.0), (38.5, -98.0), (-25.0, 133.0)):
        assert peak(lat, lon) >= threshold, f"expected land at {lat},{lon}"
    for lat, lon in ((30.0, -40.0), (-20.0, 80.0)):
        assert peak(lat, lon) < threshold, f"expected ocean at {lat},{lon}"


def test_the_reveal_wipe_moves_across_the_frame():
    style = MAP_LIBRARY["documentary_dark"]
    spec = MapSpec(seconds=6.0, width=640, height=360, push_in=False, style=style)
    threshold = _totals(style.land) - 10

    def lit(time: float, x0: int, x1: int) -> int:
        pixels = render_frame(spec, time).load()
        return sum(1 for x in range(x0, x1) for y in range(0, 360, 3)
                   if sum(pixels[x, y]) >= threshold)

    assert lit(0.0, 0, 640) == 0, "nothing should be drawn on the first frame"
    assert lit(0.45, 0, 96) > 0, "the left edge should come in first"
    assert lit(0.45, 544, 640) == 0, "the right edge should still be waiting"
    assert lit(2.5, 544, 640) > 0, "the wipe should have finished by then"


def test_markers_accumulate_as_they_land():
    spec = spec_from(["Cairo", "Mumbai", "Singapore"], seconds=8.0,
                     width=640, height=360)
    marker = MAP_LIBRARY["documentary_dark"].marker

    def amber(time: float) -> int:
        pixels = render_frame(spec, time).load()
        return sum(1 for y in range(0, 360, 2) for x in range(0, 640, 2)
                   if pixels[x, y][0] > 200 and pixels[x, y][2] < 140)

    assert marker  # the style defines one
    counts = [amber(t) for t in (0.2, 3.0, 5.5, 7.8)]
    assert counts[0] == 0, "no marker before the first lands"
    assert counts == sorted(counts), f"markers should accumulate, got {counts}"
    assert counts[-1] > counts[1] > 0


def test_every_style_renders():
    for name in MAP_LIBRARY:
        spec = MapSpec(seconds=3.0, width=320, height=180, style=MAP_LIBRARY[name],
                       markers=[Marker.of("london", label="London", at=0.0)])
        frame = render_frame(spec, 1.5)
        assert frame.size == (320, 180)
        assert len(frame.getbands()) == 3, f"{name} must render opaque RGB"


def test_a_label_near_the_right_edge_flips_rather_than_clipping():
    """Regression: a route's destination usually ends up near the right edge, and its
    name was drawn straight off the frame."""
    spec = MapSpec(seconds=2.0, width=400, height=300, push_in=False,
                   view=Bounds(west=-10, east=10, south=-8, north=8),
                   markers=[Marker(lat=0.0, lon=9.5, label="Somewhere Long", at=0.0)])
    frame = render_frame(spec, 1.0)
    pixels = frame.load()
    # The label must have put ink to the left of the marker, not past the edge.
    marker_x = Projection(spec.window_at(1.0), 400, 300).to_px(0.0, 9.5)[0]
    left_ink = sum(1 for x in range(max(0, int(marker_x) - 160), int(marker_x))
                   for y in range(120, 180) if sum(pixels[x, y]) > 400)
    assert left_ink > 0, "the label should have flipped to the left of the marker"


# ------------------------------------------------------------------- gazetteer


def test_places_resolve_and_unknown_ones_raise():
    assert resolve("Tokyo") == pytest.approx(place("tokyo"))
    assert resolve((12.0, 34.0)) == (12.0, 34.0)
    with pytest.raises(KeyError):
        place("Atlantis")


def test_every_gazetteer_entry_is_a_real_coordinate():
    from forgecast.motion.geo import PLACES

    for name, (lat, lon) in PLACES.items():
        assert -90 <= lat <= 90 and -180 <= lon <= 180, name
        # Every entry is a city, port or strait — none of them is in open ocean far
        # from any coast, so each should be on or beside land in the mask.
        near = any(
            is_land(lat + dy, lon + dx)
            for dy in (-0.7, 0, 0.7) for dx in (-0.7, 0, 0.7)
        )
        assert near, f"{name} is nowhere near land"


def test_arcs_and_markers_can_be_built_from_names_or_coordinates():
    assert Marker.of("Tokyo", at=1.0).label == "Tokyo"
    assert Marker.of((1.0, 2.0)).lat == 1.0
    arc = Arc.between("London", (0.0, 0.0), at=0.5, duration=1.0)
    assert arc.start == pytest.approx(place("london"))


# ------------------------------------------------------------------- pipeline


def test_the_planner_keeps_only_places_it_can_actually_mark():
    from forgecast.nodes.media import MAX_MAP_MARKERS, known_places

    assert known_places(["Rotterdam", "Atlantis", "SINGAPORE", "  suez canal  "]) == [
        "rotterdam", "singapore", "suez canal",
    ]
    assert known_places(["tokyo", "tokyo"]) == ["tokyo"], "duplicates collapse"
    assert len(known_places(["tokyo", "london", "paris", "cairo", "lima", "delhi"])) \
        == MAX_MAP_MARKERS
    assert known_places(None) == [] and known_places(["Narnia"]) == []


def test_the_documentary_unveil_preset_is_the_slowest_in_the_library():
    """It exists to be the restrained end of the range, so its numbers have to be it.

    Asserted as relationships rather than exact values: the point is that this preset
    holds longer and enters slower than everything else, and that survives tuning.
    """
    from forgecast.motion.presets import LIBRARY, by_intensity

    preset = LIBRARY["documentary_unveil"]
    others = [p for p in LIBRARY.values() if p.name != preset.name]

    assert preset.intensity < min(p.intensity for p in others)
    assert preset.entry_duration > max(p.entry_duration for p in others)
    assert preset.hold > max(p.hold for p in others)
    # No band behind the type: a documentary title sits on the image, not on a slab.
    assert preset.caption_style == "plain" and preset.band_opacity == 0.0
    # And it is what a very calm reference resolves to.
    assert by_intensity(0.15).name == "documentary_unveil"


def test_the_land_mask_ships_with_the_package():
    """A non-editable install must carry the data file, not just the code.

    Without the package-data entry the failure is a missing file at render time, a
    long way from the install that caused it.
    """
    import tomllib
    from pathlib import Path

    from forgecast.motion.geo import MASK_FILE

    assert MASK_FILE.exists()
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"]["package-data"]
    assert any("bin" in pattern for pattern in package_data["forgecast.motion"])
