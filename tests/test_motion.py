"""Motion graphics tests: expressions, filtergraph order, and learned presets.

Renders here are checked by *measuring pixels over time*, not by ffmpeg's exit code.
That distinction is the whole point of this file: every motion bug found while building
this module produced a render that succeeded and simply did not move.

The filtergraph-order tests are regressions for that exact class of failure. On
ffmpeg 6.1 an animated `scale` changes the frame size every frame, and a `format` or
`pad` placed after it silently freezes the size at frame one — measured as a card
stuck at 40px while its track climbed to 520px.
"""

from __future__ import annotations

import itertools
import json
import re
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from forgecast.motion import (
    LIBRARY,
    ImageCard,
    MotionPreset,
    Scene,
    Text,
    Track,
    by_intensity,
    derive_from_profile,
    fade_in_out,
    get,
    learn,
)
from forgecast.motion.presets import derive_intensity, slug
from forgecast.vision import analyse_file

FPS = 25
WIDTH, HEIGHT = 320, 180


def _run(args: list[str]) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-500:])


def _frames(path: Path, width: int = WIDTH, height: int = HEIGHT) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    data = np.frombuffer(proc.stdout, dtype=np.uint8)
    count = data.size // (width * height * 3)
    return data[: count * width * height * 3].reshape(
        count, height, width, 3).astype(np.float32)


def _red_area(frame: np.ndarray) -> int:
    """Pixel count of the red test card, used to measure scale over time."""
    red, green, blue = frame[..., 0], frame[..., 1], frame[..., 2]
    return int(((red > 110) & (red > green * 1.5) & (red > blue * 1.5)).sum())


def _reference(path: Path, *, cuts: int, duration: float, captions: bool,
               accent: str) -> Path:
    """A clip with a known cut rate and known burned-in captions.

    The greys are deliberately luma-separated. An isoluminant palette sits in
    scdet's documented blind spot, and an earlier version of this fixture lost 9 of
    16 cuts that way — a broken fixture reading as a broken detector.
    """
    seconds = duration / cuts
    colours = ["0x0d0d0d", accent, "0xe8e8e8", "0x4a4a4a", "0xb0b0b0", "0x262626"]
    inputs: list[str] = []
    chains: list[str] = []
    for index in range(cuts):
        colour = colours[index % len(colours)]
        inputs += ["-f", "lavfi", "-i",
                   f"color=c={colour}:s={WIDTH}x{HEIGHT}:r={FPS}:d={seconds:.3f}"]
        chain = f"[{index}:v]setsar=1"
        if captions:
            chain += (f",drawtext=text='Caption line {index}':fontsize=16"
                      ":fontcolor=white:x=(w-text_w)/2:y=h-34")
        chains.append(f"{chain}[s{index}]")
    graph = (";".join(chains) + ";"
             + "".join(f"[s{index}]" for index in range(cuts))
             + f"concat=n={cuts}:v=1:a=0[o]")
    _run([*inputs, "-filter_complex", graph, "-map", "[o]",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    return path


@pytest.fixture(scope="module")
def card_image(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("motion") / "card.png"
    _run(["-f", "lavfi", "-i", "color=c=0xE04030:s=200x150:d=1",
          "-frames:v", "1", str(path)])
    return path


@pytest.fixture(scope="module")
def profiles(tmp_path_factory) -> dict[str, dict]:
    """Measured style profiles for a fast-cut and a slow-cut reference."""
    directory = tmp_path_factory.mktemp("refs")
    fast = _reference(directory / "fast.mp4", cuts=12, duration=8.0,
                      captions=True, accent="0xd94f2b")
    slow = _reference(directory / "slow.mp4", cuts=2, duration=8.0,
                      captions=False, accent="0x2b4fd9")
    return {
        "fast": analyse_file(fast).as_dict(include_shots=False),
        "slow": analyse_file(slow).as_dict(include_shots=False),
    }


# ------------------------------------------------------------------- keyframes


def test_track_expression_matches_python_evaluation():
    track = Track("x").at(0.0, 0.0, "linear").at(1.0, 100.0, "ease_out")
    # ease_out at the quarter point: 1-(1-0.25)^2 = 0.4375
    assert track.evaluate(0.25) == pytest.approx(43.75)
    expression = track.expression()
    assert "if(lt(t," in expression
    assert "pow" in expression


def test_constant_track_collapses_to_a_literal():
    track = Track("alpha").at(0.0, 1.0).at(3.0, 1.0)
    assert track.constant == 1.0
    assert track.expression() == "1"
    # Scaling still applies, or a 0..1 track could not drive a pixel dimension.
    assert track.expression(scale=720) == "720"


def test_expressions_never_use_scientific_notation():
    """ffmpeg's parser rejects `1e-05`, so tiny values must stay in fixed form."""
    track = Track("x").at(0.0, 0.000012).at(1.0, 0.5)
    assert "e-" not in track.expression()


# ------------------------------------------------------- filtergraph ordering


def test_format_precedes_animated_scale(card_image):
    """Regression: format after an animated scale freezes the card at frame one."""
    growth = Track("scale").at(0.0, 0.2).at(2.0, 0.7)
    scene = Scene(duration=2.0, width=WIDTH, height=HEIGHT, fps=FPS)
    scene.add(ImageCard(path=card_image, scale=growth, duration=2.0))
    graph = " ".join(scene.command(Path("/dev/null")))
    chain = graph[graph.index("[1:v]"):]
    assert chain.index("format=rgba") < chain.index("scale=w="), chain[:200]


def test_rotation_canvas_is_literal_and_sized_for_the_largest_scale(card_image):
    """hypot(iw,ih) is evaluated once, against the *smallest* frame."""
    growth = Track("scale").at(0.0, 0.2).at(2.0, 0.8)
    tilt = Track("rotation").at(0.0, 0.2).at(1.0, 0.0)
    card = ImageCard(path=card_image, scale=growth, rotation=tilt, duration=2.0)
    fragments, _ = card.compile([1, 2], WIDTH, HEIGHT, "bg", "v1")
    rotate = next(part for part in fragments if "rotate=" in part)
    assert "hypot(iw,ih)" not in rotate
    canvas = int(rotate.split("ow=")[1].split(":")[0])
    # 0.8 * 320 = 256px wide, 4:3 source -> 192 tall, diagonal 320.
    assert canvas >= 320, rotate


def test_shadow_avoids_geq(card_image):
    """geq is ~100x the cost of colorchannelmixer for the same picture."""
    card = ImageCard(path=card_image, shadow=True, duration=1.0)
    fragments, _ = card.compile([1, 2], WIDTH, HEIGHT, "bg", "v1")
    joined = " ".join(fragments)
    assert "geq" not in joined
    assert "colorchannelmixer" in joined


def test_text_escaping_neutralises_filtergraph_metacharacters():
    element = Text(text="Cost: $5, 100% [sic]; it's fine", duration=1.0)
    compiled = element.compile(WIDTH, HEIGHT)
    body = compiled.split("text='")[1].split("'")[0]
    # Colons and commas separate filter options, so they must be escaped, not bare.
    assert re.search(r"(?<!\\)[:,]", body) is None, body
    # These have no escape that ffmpeg honours inside drawtext, so they are replaced.
    assert "%" not in body
    assert "[" not in body and "]" not in body
    assert "'" not in body


def test_shadowed_card_claims_two_inputs(card_image):
    """The shadow is a second decode, not a split — so the input count must match."""
    scene = Scene(duration=1.0, width=WIDTH, height=HEIGHT, fps=FPS)
    scene.add(ImageCard(path=card_image, shadow=True, duration=1.0))
    args = scene.command(Path("/dev/null"))
    assert args.count(str(card_image)) == 2
    graph = " ".join(args)
    assert "split" not in graph
    # Both copies must carry the same geometry, or the shadow drifts off the card.
    assert graph.count("scale=w=") == 2


# ------------------------------------------------------------------- rendering


def test_animated_card_actually_grows(tmp_path, card_image):
    growth = Track("scale").at(0.0, 0.2).at(1.6, 0.75, "ease_in_out")
    scene = Scene(duration=2.0, width=WIDTH, height=HEIGHT, fps=FPS)
    scene.add(ImageCard(path=card_image, scale=growth, duration=2.0,
                        fade_in=0.2, shadow=True, border=4))
    out = scene.render(tmp_path / "grow.mp4", timeout=180)

    frames = _frames(out)
    early = _red_area(frames[int(0.4 * FPS)])
    late = _red_area(frames[int(1.7 * FPS)])
    assert early > 0, "card never appeared"
    assert late > early * 3, f"card did not grow: {early} -> {late}"


def test_elements_are_confined_to_their_window(tmp_path):
    scene = Scene(duration=3.0, width=WIDTH, height=HEIGHT, fps=FPS)
    scene.add(Text(start=1.0, duration=1.0, text="MIDDLE ONLY", size=24,
                   alpha=fade_in_out(1.0, rise=0.2, fall=0.2)))
    out = scene.render(tmp_path / "window.mp4", timeout=180)

    frames = _frames(out)
    lit = np.array([(frame.min(axis=2) > 150).sum() for frame in frames])
    assert lit[int(0.3 * FPS)] == 0, "text drawn before its start"
    assert lit[int(1.5 * FPS)] > 100, "text never drawn"
    assert lit[int(2.7 * FPS)] == 0, "text outlived its window"


# --------------------------------------------------------------------- presets


def test_derived_presets_follow_the_measured_pacing(profiles):
    fast = derive_from_profile(profiles["fast"], name="fast_ref")
    slow = derive_from_profile(profiles["slow"], name="slow_ref")

    assert fast.intensity > slow.intensity
    assert fast.entry_duration < slow.entry_duration
    assert fast.stagger < slow.stagger
    assert fast.hold < slow.hold
    assert fast.text_height_ratio > slow.text_height_ratio
    # Entries must fit inside a shot or the move is still arriving at the cut.
    fast_median = profiles["fast"]["shot_rhythm"]["shot_length"]["median"]
    assert fast.entry_duration <= fast_median * 0.45 + 1e-6


def test_accent_comes_from_the_reference_palette(profiles):
    fast = derive_from_profile(profiles["fast"])
    slow = derive_from_profile(profiles["slow"])
    assert fast.accent_colour != slow.accent_colour
    for preset in (fast, slow):
        red, green, blue = (int(preset.accent_colour[i:i + 2], 16)
                            for i in (1, 3, 5))
        assert max(red, green, blue) >= 160, "accent too dark to read"


def test_intensity_components_are_reported(profiles):
    intensity, components = derive_intensity(profiles["fast"])
    assert 0.0 <= intensity <= 1.0
    assert components["cuts_per_minute"] > 40
    assert set(components) >= {"pace_component", "motion_component",
                               "graphics_component"}


def test_preset_round_trips_through_disk(tmp_path, profiles):
    preset, path = learn(profiles["fast"], name="Fast Ref",
                         reference="ref://fast", directory=tmp_path)
    assert path.name == "fast_ref.json"
    payload = json.loads(path.read_text())
    assert payload["provenance"]["origin"] == "reference"
    assert payload["provenance"]["reference"] == "ref://fast"
    assert payload["provenance"]["measured"]["cuts_per_minute"] > 40
    assert MotionPreset.load(path).as_dict() == preset.as_dict()


def test_a_learned_preset_shadows_a_builtin_of_the_same_name(tmp_path, profiles):
    assert get("kinetic_type", directory=tmp_path).provenance["origin"] == "built_in"
    derive_from_profile(profiles["slow"]).variant("kinetic_type").save(tmp_path)
    assert get("kinetic_type", directory=tmp_path).provenance["origin"] == "reference"


def test_unknown_preset_names_fail_loudly(tmp_path):
    with pytest.raises(KeyError):
        get("no_such_look", directory=tmp_path)


def test_builtin_library_spans_the_intensity_range():
    """The library must cover calm to frantic, and pick the nearest to what is asked.

    Written against the library's own extremes rather than against two preset names.
    Naming them made this fail the moment a calmer preset was added — which is the
    library improving, not a regression, and a test that cannot tell those apart is
    noise.
    """
    presets = sorted(LIBRARY.values(), key=lambda item: item.intensity)
    calmest, busiest = presets[0], presets[-1]

    assert calmest.intensity < 0.4 < busiest.intensity
    assert by_intensity(1.0).name == busiest.name
    assert by_intensity(0.0).name == calmest.name

    # And an intensity between two presets resolves to whichever is nearer.
    for lower, higher in itertools.pairwise(presets):
        midpoint = (lower.intensity + higher.intensity) / 2
        assert by_intensity(midpoint - 0.01).name == lower.name
        assert by_intensity(midpoint + 0.01).name == higher.name


def test_slug_is_filesystem_safe():
    assert slug("Kalla's Fast Cuts!") == "kalla_s_fast_cuts"
    assert slug("///") == "preset"


def test_kinetic_windows_do_not_overlap():
    """Two lines at one position during a crossfade read as a smear, not a swap."""
    preset = LIBRARY["kinetic_type"]
    lines = preset.kinetic(["one", "two", "three"], start=0.0,
                           width=WIDTH, height=HEIGHT)
    texts = sorted((item for item in lines if isinstance(item, Text)),
                   key=lambda item: item.start)
    for current, following in pairwise(texts):
        assert current.end <= following.start + 1e-6


def test_learned_preset_renders_staged_type(tmp_path, profiles):
    preset = derive_from_profile(profiles["fast"], name="fast_ref")
    scene = Scene(duration=3.0, width=WIDTH, height=HEIGHT, fps=FPS)
    scene.add(*preset.kinetic(["First", "Second", "Third"], start=0.2,
                              width=WIDTH, height=HEIGHT))
    out = scene.render(tmp_path / "staged.mp4", timeout=180)

    frames = _frames(out)
    present = np.array([(frame.min(axis=2) > 150).sum() for frame in frames]) > 40
    appearances = int((present[1:] & ~present[:-1]).sum()) + int(present[0])
    assert appearances >= 3, f"staging collapsed into {appearances} appearance(s)"
