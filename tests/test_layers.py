"""Cutting the subject out, and putting things behind it.

A still is one flat image and nothing can be behind anything in it. Lift the subject
onto its own layer and everything behind it becomes addressable — which is most of what
separates a composite from a photograph with a camera move on it.

The matting model is not exercised here: it is a 176 MB download and these tests must
run offline. What is exercised is the judgement around it — the quality gate, which is
the part that decides whether a fringed cutout reaches a finished video — and the
compositor, which needs no model at all.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from forgecast.layers import compose, matte


def _cutout(path, *, coverage=0.25, soft=True):
    """A transparent PNG shaped like a matte, without running a model."""
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    drawn = ImageDraw.Draw(image)
    side = int((coverage * 400 * 400) ** 0.5)
    box = [200 - side // 2, 200 - side // 2, 200 + side // 2, 200 + side // 2]
    drawn.rectangle(box, fill=(200, 120, 90, 255))
    if soft:
        # A real boundary is anti-aliased. Without this the matte is a hard threshold,
        # which is exactly what the quality gate refuses.
        drawn.rectangle(box, outline=(200, 120, 90, 128), width=3)
    image.save(path)
    return path


# ------------------------------------------------------------------ the quality gate


def test_a_matte_that_selected_almost_nothing_is_refused():
    """A speck the model latched onto is not a small subject. Composited, it produces a
    frame with a title floating over an unchanged photograph."""
    assert matte._verdict(0.001, 0.01)
    assert "no clear subject" in matte._verdict(0.001, 0.01)


def test_a_matte_that_selected_the_whole_frame_is_refused():
    """There is nothing left to put anything behind, so the effect cannot happen — and
    the composite would be indistinguishable from the original."""
    assert "no background" in matte._verdict(0.98, 0.01)


def test_a_hard_edged_matte_is_refused():
    """The failure that matters. A real subject boundary is anti-aliased; one with
    almost no partial alpha was cut with a threshold, and that is the jagged fringe the
    eye catches instantly. A fringed cutout is more obviously automatic than no cutout."""
    assert "jagged fringe" in matte._verdict(0.3, 0.0)


def test_a_matte_that_is_soft_everywhere_is_refused():
    assert "haze" in matte._verdict(0.3, 0.6)


def test_a_good_matte_is_not_refused():
    assert matte._verdict(0.25, 0.02) == ""


def test_the_refusal_says_what_happened_rather_than_naming_a_threshold():
    """The operator cannot act on "soft_edge 0.0004 < 0.0008"."""
    for coverage, soft in ((0.001, 0.01), (0.98, 0.01), (0.3, 0.0), (0.3, 0.6)):
        why = matte._verdict(coverage, soft)
        assert why and "0." not in why, f"{why!r} quotes a threshold"


def test_measurement_reads_the_alpha_channel(tmp_path):
    import numpy as np

    path = _cutout(tmp_path / "m.png", coverage=0.25)
    alpha = np.array(Image.open(path))[:, :, 3]
    coverage, soft_edge = matte._measure(alpha)
    assert 0.2 < coverage < 0.3
    assert soft_edge > 0


# -------------------------------------------------------------------- the composite


def test_the_subject_occludes_the_text(tmp_path):
    """The whole effect. If the text draws over the subject it is a caption, which is
    the thing this exists to not be."""
    import numpy as np

    cut = _cutout(tmp_path / "subject.png", coverage=0.3)
    out = compose.text_behind(cut, tmp_path / "out.png", "BEHIND")

    result = np.array(Image.open(out.path).convert("RGBA"))
    subject_alpha = np.array(Image.open(cut))[:, :, 3]
    opaque = subject_alpha > 250
    assert opaque.sum() > 0

    # Every pixel the subject fully covers shows the subject's colour, not the text's.
    covered = result[opaque][:, :3]
    assert (covered == [200, 120, 90]).all(axis=1).mean() > 0.98


def test_the_layers_are_stacked_in_the_order_that_makes_the_effect(tmp_path):
    cut = _cutout(tmp_path / "subject.png")
    out = compose.text_behind(cut, tmp_path / "out.png", "TITLE")
    assert out.layers.index("text") < out.layers.index("subject")
    assert "shadow" in out.layers


def test_the_shadow_can_be_turned_off(tmp_path):
    cut = _cutout(tmp_path / "subject.png")
    out = compose.text_behind(cut, tmp_path / "out.png", "TITLE", shadow=False)
    assert "shadow" not in out.layers


def test_a_background_is_composited_under_everything(tmp_path):
    plate = tmp_path / "plate.png"
    Image.new("RGB", (400, 400), (20, 40, 60)).save(plate)
    cut = _cutout(tmp_path / "subject.png")
    out = compose.text_behind(cut, tmp_path / "out.png", "TITLE", background=plate)
    assert out.layers[0] == "background"

    import numpy as np
    result = np.array(Image.open(out.path).convert("RGB"))
    corner = result[5, 5]
    assert tuple(corner) == (20, 40, 60), "the plate is not underneath"


def test_with_no_background_the_subject_sits_on_transparency(tmp_path):
    """What a caller compositing over generated video wants — an opaque frame there
    would cover the video it is meant to sit on."""
    cut = _cutout(tmp_path / "subject.png")
    out = compose.text_behind(cut, tmp_path / "out.png", "TITLE")
    assert out.layers[0] == "transparent"
    assert Image.open(out.path).mode == "RGBA"


def test_the_output_is_a_png_whatever_was_asked_for(tmp_path):
    """Alpha does not survive a JPEG, and a composite that silently loses its
    transparency is a black box over the video underneath."""
    cut = _cutout(tmp_path / "subject.png")
    out = compose.text_behind(cut, tmp_path / "out.jpg", "TITLE")
    assert out.path.endswith(".png")


# ------------------------------------------------------------- installing the tools


def test_the_missing_tools_message_does_not_hand_out_homework():
    """The app installs them. Printing a pip command is the homework the toolchain
    module exists to remove, and it was reported as exactly that for a CLI already."""
    from forgecast.ingest import shots, transcript

    for reporter in (matte.available, shots.available, transcript.available):
        ok, why = reporter()
        if not ok:
            assert "pip install" not in why, f"{why!r} tells the operator to run pip"


def test_the_edit_extra_is_installable_from_inside_the_app():
    from forgecast.desktop import toolchain

    assert "edit" in toolchain.EXTRAS
    spec = toolchain.EXTRAS["edit"]
    # The size is stated, because it is the number that decides whether somebody starts
    # a 400 MB download now or later.
    assert spec["megabytes"] > 0
    assert spec["gives"].strip()
    assert callable(toolchain.install_python_extra)


def test_the_extras_are_not_in_the_mandatory_install():
    """`missing()` drives an install every operator sits through on first run. 400 MB
    of editing tools in there would make everyone pay for a direction most never use."""
    from forgecast.desktop import toolchain

    keys = {tool.key for tool in toolchain.inventory(__import__("pathlib").Path("/nowhere"))}
    assert "edit" not in keys
    assert "rembg" not in keys


# ------------------------------------------------- the app installs what it needs


def test_the_motion_renderer_can_install_itself():
    """It never could, and that was the quietest kind of dead feature.

    `RemotionBackend.available()` checks for `node_modules/remotion`, finds nothing,
    and `backend_for` silently downgrades to ffmpeg — so the layered motion-graphics
    engine shipped in every archive, could not run on any machine, and never produced
    an error saying why.
    """
    from forgecast.desktop import toolchain

    assert "motion" in toolchain.EXTRAS
    assert toolchain.EXTRAS["motion"]["kind"] == "npm"
    assert callable(toolchain.install_remotion)


def test_an_extra_is_verified_by_loading_it_not_by_a_package_manager_exit_code():
    """A resolver that succeeded while leaving the thing unimportable is the failure
    this check exists for, and reporting success for it sends the operator back to a
    feature that still does not work."""
    from pathlib import Path

    from forgecast.desktop import toolchain

    body = Path(toolchain.__file__).read_text(encoding="utf-8")
    assert "extra_installed(name)" in body or "extra_installed(\"motion\", root)" in body

    # And the motion check looks for the resolved package rather than the lockfile.
    ok, absent = toolchain.extra_installed("motion", Path("/nowhere"))
    assert ok is False
    assert absent


def test_node_modules_can_never_reach_the_archive():
    """355 MB of dependencies, and they are rebuilt by the installer on the machine
    that needs them."""
    from tools.package import excluded, files_to_ship

    assert excluded("remotion/node_modules/remotion/index.js")
    assert not any("node_modules" in member for _path, member in files_to_ship())


def test_the_banner_offers_the_extras_rather_than_only_reporting_tools():
    """Optional must not mean "print a command and give up" — which is the homework
    this codebase already removed once for a CLI."""
    from pathlib import Path

    from forgecast import layers

    chat_js = (Path(layers.__file__).resolve().parents[1] / "web" / "static"
               / "chat.js").read_text(encoding="utf-8")
    assert "/api/setup/extras" in chat_js
    assert "installExtra" in chat_js
