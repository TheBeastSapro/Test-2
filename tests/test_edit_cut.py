"""Actually cutting the video an approved plan describes.

`ingest` measured, `edit` decided, the gate recorded an operator agreeing — and then
nothing happened. The approval said so out loud: "the kept spans are the plan a cutting
stage would execute; nothing has been cut yet". Nothing in `render/` consumed an
`EditPlan`, so the one thing the whole direction existed to produce was the one thing it
could not produce.

These tests are about the file coming out. They render for real: ffmpeg is a hard
dependency of this app and a cutter proved with a mock is a cutter proved against the
mock. The two that matter most are the ones that measure the finished file rather than
the arguments that made it — a cut whose arithmetic is right and whose sound has walked
away from its picture is worse than no cut at all, and only the file can say which.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast import ingest
from forgecast.agent.studio import Studio
from forgecast.api.main import create_app
from forgecast.edit import EditPlan, tighten
from forgecast.edit.plan import Decision
from forgecast.render import cut
from forgecast.render.ffmpeg import RenderError, vcodec

# testsrc2 sits at a steady luma of ~121 and `color=black` at 16, so anything between
# them separates the two without a tolerance argument. Loud is a 440 Hz tone at full
# scale; silent is silent.
BRIGHT = 60.0
LOUD_DB = -60.0


# ------------------------------------------------------------------ building a source


def _striped(path: Path, pattern: list[tuple[float, bool]], *, fps: int = 30,
             size: str = "320x180") -> Path:
    """A file whose picture and sound change at exactly the same moments.

    That coincidence is the whole measuring instrument. Duration alone cannot tell a
    correct cut from one that kept the right amount of each stream and put them out of
    step, and this is a source where "out of step" is directly readable off the file: if
    the tone still starts on the frame the pattern brightens, the cut held sync.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for index, (seconds, loud) in enumerate(pattern):
        piece = path.parent / f"{path.stem}-{index:02d}.mp4"
        video = (f"testsrc2=s={size}:r={fps}:d={seconds}" if loud
                 else f"color=c=black:s={size}:r={fps}:d={seconds}")
        audio = (f"sine=frequency=440:sample_rate=48000:duration={seconds}" if loud
                 else f"anullsrc=channel_layout=stereo:sample_rate=48000:d={seconds}")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", video, "-f", "lavfi", "-i", audio,
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-ac", "2", "-shortest", str(piece)],
            check=True, capture_output=True)
        parts.append(piece)

    listing = path.parent / f"{path.stem}-list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", str(listing), "-c", "copy", str(path)],
        check=True, capture_output=True)
    return path


def _silent(path: Path, seconds: float = 6.0, *, fps: int = 30) -> Path:
    """A video with no audio stream at all — a screen capture, in other words."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=s=320x180:r={fps}:d={seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-r", str(fps), "-an", str(path)],
        check=True, capture_output=True)
    return path


# ---------------------------------------------------------------- reading one back


def _probe(path: Path) -> dict:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
         "-show_streams", str(path)], capture_output=True, text=True, check=True)
    payload = json.loads(done.stdout)
    out = {"seconds": float(payload["format"]["duration"])}
    for stream in payload["streams"]:
        out[stream["codec_type"]] = float(stream.get("duration") or 0.0)
        if stream["codec_type"] == "video":
            out["frames"] = int(stream.get("nb_frames") or 0)
    return out


def _series(path: Path, *, audio: bool) -> list[tuple[float, float]]:
    """Per-frame loudness or per-frame brightness, with its timestamp."""
    if audio:
        source = f"amovie={path},astats=metadata=1:reset=1"
        tag = "lavfi.astats.Overall.RMS_level"
    else:
        source = f"movie={path},signalstats"
        tag = "lavfi.signalstats.YAVG"
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi", "-i", source, "-show_entries",
         f"frame=pts_time:frame_tags={tag}", "-print_format", "json"],
        capture_output=True, text=True, check=True)
    rows = []
    for frame in json.loads(done.stdout or "{}").get("frames", []):
        value = (frame.get("tags") or {}).get(tag)
        if value is None:
            continue
        try:
            rows.append((float(frame["pts_time"]), float(value)))
        except ValueError:
            # astats writes "-inf" for a frame of digital silence.
            rows.append((float(frame["pts_time"]), -120.0))
    return rows


def _seams(rows: list[tuple[float, float]], threshold: float) -> list[float]:
    """Where the series crosses the threshold — the moments the file changes state.

    The first frame is skipped: RMS starts from nothing, so a file that opens loud reads
    as a transition the picture has no twin for.
    """
    out, previous = [], None
    for at, value in rows:
        state = value > threshold
        if previous is not None and state != previous and at > 0.2:
            out.append(round(at, 4))
        previous = state
    return out


# ------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def no_transcription(monkeypatch):
    """The transcript reading, off: loading it downloads a model on first use.

    It also exercises the case that matters — a plan built from silence alone, which is
    what a machine without the edit extra actually produces.
    """
    from forgecast.ingest import transcript

    monkeypatch.setattr(transcript, "available",
                        lambda: (False, "transcription needs the video editing tools"))


@pytest.fixture(autouse=True)
def quiet_cutting_slot():
    """No test may start while another one's cut is still encoding.

    The job slot is process-wide — deliberately, because it is one machine's ffmpeg — so
    a test that starts a cut and returns before it finishes would make the next test's
    409 depend on how fast this one's encode was.
    """
    from forgecast.api import routes_edit

    yield
    for _ in range(600):
        if not routes_edit.CUT["running"]:
            break
        time.sleep(0.1)
    routes_edit.CUT.update(running=False, done=False, ok=False, log=[], result={},
                           plan_id="", user_id=0, started=0.0)


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


# ------------------------------------------------------- the file, measured for real


def test_the_cut_file_is_the_length_the_plan_predicted(storage_dir):
    """The whole point, end to end, against a real file and a real plan.

    Measured, planned and executed rather than asserted against numbers written by hand:
    a test that fed the cutter spans it had chosen itself would pass against a cutter
    that agreed with the test and disagreed with `edit.tighten`.
    """
    source = _striped(storage_dir / "predicted.mp4", [(2.0, True), (2.0, False)] * 4)

    measured = ingest.read(source, want_shots=False)
    plan = tighten(measured)
    assert plan.kept, "nothing to cut — the source was not read as speech and silence"
    assert plan.removed_seconds > 4.0, "the four silent blocks were not found"

    made = cut.execute(plan, storage_dir / "cuts" / "predicted-cut.mp4")
    seen = _probe(Path(made.path))

    # The arithmetic the plan quoted, against the file that came out of it.
    # `final_seconds` is the number the operator was shown before they agreed, and
    # snapping every span to the frame grid can move each edge by at most half a frame —
    # so the two may differ by up to one frame per keep and by nothing else. Measured on
    # this source: 13.18s planned, 13.10s delivered, over six keeps.
    slack = (len(plan.kept) + 1) / measured.media.fps
    assert abs(seen["seconds"] - plan.final_seconds) < slack, (
        f"plan said {plan.final_seconds}s, file is {seen['seconds']}s")
    # And the cutter's own arithmetic agrees with the file it wrote — the check that
    # catches a snapping bug the plan's rounder numbers could absorb. Measured: 0.000s.
    assert abs(made.drift) <= 2.0 / made.fps
    assert seen["frames"] == pytest.approx(made.seconds * made.fps, abs=2)
    assert made.original_seconds > made.seconds


def test_the_sound_still_lands_on_the_picture_after_every_cut(storage_dir):
    """The failure a duration check cannot see, and the one this design exists for.

    A cut list applied to video and audio separately drifts: video is selected by whole
    frames and audio by whole 1024-sample packets, so each cut keeps about 21 ms more of
    one than the other. Measured with `aselect` over these same seams, the sound finished
    175 ms ahead of the picture — a fifth of a second of lip sync out of a command that
    looks entirely reasonable.

    This source changes brightness and loudness at the same instant, so the two can be
    read off the finished file and compared.
    """
    source = _striped(storage_dir / "sync.mp4", [(2.0, True), (2.0, False)] * 6)

    starts = [index * 4.0 for index in range(6)]
    plan = EditPlan(source=str(source), original_seconds=24.0, decisions=[
        Decision("keep", max(0.0, at - 0.12), at + 2.12, "speech", "speech")
        for at in starts])
    made = cut.execute(plan, storage_dir / "cuts" / "sync-cut.mp4")

    picture = _seams(_series(Path(made.path), audio=False), BRIGHT)
    sound = _seams(_series(Path(made.path), audio=True), LOUD_DB)
    assert len(picture) == len(sound) > 8, (
        f"the two streams do not describe the same edit: "
        f"{len(picture)} picture seams, {len(sound)} sound seams")

    worst = max(abs(a - b) for a, b in zip(picture, sound, strict=True))
    # One audio packet is 21 ms and one video frame is 33 ms. Inside that is the
    # granularity of the two formats; outside it is drift, and drift grows with the
    # number of cuts — which is why this plan has eleven seams in it. Measured here:
    # 24 ms, flat across all eleven, against 175 ms and rising for `aselect`.
    assert worst < 0.034, f"sound and picture are {worst * 1000:.0f} ms apart"


def test_the_cut_is_re_encoded_rather_than_stream_copied(storage_dir, monkeypatch):
    """The tempting optimisation, and why it is refused.

    `-c copy` cannot start a segment anywhere but a keyframe, so every cut point moves to
    the nearest one behind it. Measured on a 16-second file whose plan asked for 8.84s
    out, the stream copy produced 14.93s — it kept most of what the plan removed. This
    test is here so that "make the cut faster" cannot quietly become that.
    """
    seen: list[list[str]] = []
    monkeypatch.setattr(cut, "run_ffmpeg", lambda args, **kw: seen.append(args))
    monkeypatch.setattr(cut, "ffprobe_duration", lambda path: 4.0)

    source = _striped(storage_dir / "encoded.mp4", [(2.0, True), (2.0, False)])
    plan = EditPlan(source=str(source), original_seconds=4.0,
                    decisions=[Decision("keep", 0.0, 2.0, "speech", "speech")])
    cut.execute(plan, storage_dir / "cuts" / "encoded-cut.mp4")

    args = seen[0]
    assert "copy" not in args, "a stream copy lands on the wrong frame"
    # And through the pipeline's own encoder settings rather than a second opinion about
    # them, because `concat_clips` stream-copies: pieces from two encoders, or at two
    # frame rates, join into a file whose timestamps drift against its audio.
    settings = vcodec(30)
    windows = [args[index:index + len(settings)] for index in range(len(args))]
    assert settings in windows, f"the cut did not encode with {settings}: {args}"


# ------------------------------------------------------------------- the awkward spans


def test_a_quarter_second_keep_survives_the_cut(storage_dir):
    """`edit.MIN_KEEP_SECONDS` is 0.25s, so this is the shortest span a plan can contain.

    Seven and a half frames at 30fps. Short enough that a cutter which rounded spans the
    wrong way would drop it and produce a video missing a shot the plan promised.
    """
    source = _striped(storage_dir / "sliver.mp4", [(4.0, True)])
    plan = EditPlan(source=str(source), original_seconds=4.0, decisions=[
        Decision("keep", 0.5, 0.75, "speech", "speech"),
        Decision("keep", 2.0, 2.25, "speech", "speech"),
    ])
    made = cut.execute(plan, storage_dir / "cuts" / "sliver-cut.mp4")

    assert made.dropped == []
    assert len(made.spans) == 2
    seen = _probe(Path(made.path))
    assert seen["frames"] == 16          # eight frames each, snapped to the grid
    assert abs(seen["seconds"] - 0.533) < 0.02


def test_a_keep_too_short_to_hold_a_frame_is_dropped_and_named(storage_dir):
    """The failure that reads as a success.

    An 8 ms keep produced a file with **no video stream at all**, and ffmpeg exited 0
    while doing it. A plan can be written by hand or by a model, so a span the format
    cannot express has to be refused here and reported — not passed through to produce a
    playable-looking file with nothing in it.
    """
    source = _striped(storage_dir / "flash.mp4", [(4.0, True)])
    plan = EditPlan(source=str(source), original_seconds=4.0, decisions=[
        Decision("keep", 1.001, 1.009, "speech", "speech"),
        Decision("keep", 2.0, 3.0, "speech", "speech"),
    ])
    made = cut.execute(plan, storage_dir / "cuts" / "flash-cut.mp4")

    assert len(made.dropped) == 1
    assert "shorter than one frame" in made.dropped[0]
    assert len(made.spans) == 1
    assert _probe(Path(made.path))["frames"] == 30


def test_spans_are_ordered_and_merged_before_the_filtergraph_sees_them():
    """Two failures at once, neither of which ffmpeg reports.

    Descending spans still produce a file, of the right length, with the shots in the
    wrong order — and they make the encode buffer decoded frames for every keep waiting
    its turn, which at 1080p is 3 MB a frame until the process is killed. Overlapping
    spans play the overlap twice.
    """
    plan = EditPlan(source="x", original_seconds=10.0, decisions=[
        Decision("keep", 6.0, 8.0, "speech", "speech"),
        Decision("keep", 1.0, 4.0, "speech", "speech"),
        Decision("keep", 3.0, 5.0, "speech", "speech"),
    ])
    spans, dropped = cut.spans_for(plan, fps=30, duration=10.0)

    assert dropped == []
    assert spans == sorted(spans)
    assert spans == [(1.0, 5.0), (6.0, 8.0)]


def test_a_span_past_the_end_of_the_file_is_clamped_rather_than_asked_for():
    """ffmpeg truncates it silently, so the plan and the file disagree with no complaint
    from either — and the drift then reads as a cutting bug rather than as a plan built
    against a longer version of the source."""
    plan = EditPlan(source="x", original_seconds=30.0, decisions=[
        Decision("keep", 2.0, 30.0, "speech", "speech")])
    spans, _dropped = cut.spans_for(plan, fps=30, duration=6.0)
    assert spans == [(2.0, 6.0)]


def test_a_plan_that_keeps_nothing_is_refused(storage_dir):
    """Rather than an empty file, or an ffmpeg error about a filtergraph nobody wrote."""
    source = _striped(storage_dir / "empty.mp4", [(2.0, False)])
    plan = EditPlan(source=str(source), original_seconds=2.0, decisions=[
        Decision("drop", 0.0, 2.0, "dead air", "silence")])

    with pytest.raises(RenderError, match="keeps nothing"):
        cut.execute(plan, storage_dir / "cuts" / "empty-cut.mp4")


def test_a_source_with_no_sound_is_cut_without_an_audio_graph(storage_dir):
    """A screen capture has no audio stream, and a graph that asks for one fails outright
    with "Error initializing complex filters" — an ffmpeg message that names nothing an
    operator could act on."""
    source = _silent(storage_dir / "mute.mp4")
    plan = EditPlan(source=str(source), original_seconds=6.0, decisions=[
        Decision("keep", 0.0, 2.0, "speech", "speech"),
        Decision("keep", 4.0, 6.0, "speech", "speech"),
    ])
    made = cut.execute(plan, storage_dir / "cuts" / "mute-cut.mp4")

    assert made.has_audio is False
    seen = _probe(Path(made.path))
    assert "audio" not in seen
    assert abs(seen["seconds"] - 4.0) < 0.05


def test_a_missing_source_is_refused_before_anything_is_encoded(storage_dir):
    plan = EditPlan(source=str(storage_dir / "never-existed.mp4"), original_seconds=4.0,
                    decisions=[Decision("keep", 0.0, 2.0, "speech", "speech")])
    with pytest.raises(RenderError, match="not there any more"):
        cut.execute(plan, storage_dir / "cuts" / "nothing.mp4")


# --------------------------------------------------------------- the plan, round trip


def test_a_plan_read_back_off_disk_is_the_plan_that_was_written(storage_dir):
    """The plan is written down precisely so somebody can go away and read it, which
    means whatever executes it is loading JSON rather than holding the object. A round
    trip that lost the keeps would cut a different video from the one approved."""
    source = _striped(storage_dir / "roundtrip.mp4", [(2.0, True), (2.0, False)] * 2)
    original = tighten(ingest.read(source, want_shots=False))

    again = EditPlan.from_dict(json.loads(json.dumps(original.as_dict())))
    assert [(d.action, d.start, d.end) for d in again.decisions] == \
           [(d.action, d.start, d.end) for d in original.decisions]
    assert again.final_seconds == original.final_seconds
    assert again.unknown == original.unknown


# --------------------------------------------------------------------------- the gate


def test_an_unapproved_plan_is_not_cut(user, storage_dir):
    """The property that keeps `approve_edit` a gate rather than a formality.

    Anything that can reach the studio can reach `cut_plan` — the chat's tools included —
    and it must not act on a plan the operator has not agreed to.
    """
    source = _striped(storage_dir / "ungated.mp4", [(2.0, True), (2.0, False)] * 2)
    studio = Studio(user_id=user.id)
    drafted = studio.plan_edit(source)

    refused = studio.cut_plan(drafted["plan_id"])
    assert "error" in refused
    assert "not approved" in refused["error"]
    assert not list((storage_dir / "cuts").glob("*.mp4")) or \
        not (storage_dir / "cuts" / f"{drafted['plan_id']}.mp4").exists()

    # And a rejected one is no more cuttable than a drafted one.
    studio.approve_edit(drafted["plan_id"], approve=False, note="that pause was the joke")
    assert "not approved" in studio.cut_plan(drafted["plan_id"])["error"]


def test_approving_releases_the_cut_and_cutting_produces_the_file(user, storage_dir):
    """The open loop, closed: approve, cut, and the plan carries what it made."""
    source = _striped(storage_dir / "released.mp4", [(2.0, True), (2.0, False)] * 3)
    studio = Studio(user_id=user.id)
    drafted = studio.plan_edit(source)

    agreed = studio.approve_edit(drafted["plan_id"])
    assert agreed["released"] is True
    # No longer claiming the work is done, and no longer claiming it never will be.
    assert "cut_plan" in agreed["note_to_reader"]

    notes: list[str] = []
    made = studio.cut_plan(drafted["plan_id"], on_note=notes.append)
    assert "error" not in made
    assert Path(made["path"]).exists()
    assert made["relative"] == f"cuts/{drafted['plan_id']}.mp4"
    assert made["seconds"] < made["original_seconds"]
    assert any("cutting" in line for line in notes)

    # The result is on the plan, so the thing that reports it does not have to go
    # looking in a folder and guess which file belongs to which edit.
    reread = studio.edit_plans(drafted["plan_id"])
    assert reread["cut"]["path"] == made["path"]
    assert reread["cut"]["seconds"] == made["seconds"]
    assert studio.edit_plans()["plans"][0]["cut"] == made["path"]


def test_a_plan_whose_source_points_outside_the_install_is_refused(user, storage_dir):
    """A plan is a JSON file on disk, and a JSON file whose `source` is `/etc/hostname`
    is a plausible thing to be handed. The cut re-checks it rather than trusting that it
    was checked when the plan was drafted."""
    source = _striped(storage_dir / "escape.mp4", [(2.0, True), (2.0, False)])
    studio = Studio(user_id=user.id)
    drafted = studio.plan_edit(source)
    studio.approve_edit(drafted["plan_id"])

    from forgecast.agent.studio import edits_dir

    record_path = edits_dir() / f"{drafted['plan_id']}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["plan"]["source"] = "/etc/hostname"
    record["source"] = "/etc/hostname"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    refused = studio.cut_plan(drafted["plan_id"])
    assert "outside this install" in refused["error"]


# ---------------------------------------------------------------------------- the door


def test_the_cutting_endpoints_need_an_account():
    with TestClient(create_app()) as anon:
        assert anon.get("/api/edit/cut").status_code == 401
        assert anon.post("/api/edit/plans/anything/cut").status_code == 401


def test_approving_starts_the_cut_without_waiting_for_it(client, storage_dir):
    """Cutting a twenty-minute source is minutes of encoding, and most proxies close a
    request after sixty seconds. An approval that waited for the encode would be an
    operator's decision that could fail because ffmpeg was busy."""
    source = _striped(storage_dir / "decided.mp4", [(2.0, True), (2.0, False)] * 3)
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]

    answered = client.post(f"/api/edit/plans/{plan_id}/decision",
                           json={"approve": True, "note": "yes"})
    body = answered.json()
    assert body["state"] == "approved"
    assert body["cut"]["running"] is True
    assert body["cut"]["stream"] == f"POST /api/edit/plans/{plan_id}/cut"

    for _ in range(600):
        state = client.get("/api/edit/cut").json()
        if state["done"]:
            break
        time.sleep(0.1)
    assert state["ok"] is True, state
    assert state["plan_id"] == plan_id
    assert Path(state["result"]["path"]).exists()


def test_approving_can_record_the_decision_without_starting_an_encode(client,
                                                                     storage_dir):
    """An operator working through several plans wants the decisions recorded now and
    the machine time taken one at a time afterwards."""
    source = _striped(storage_dir / "later.mp4", [(2.0, True), (2.0, False)])
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]

    body = client.post(f"/api/edit/plans/{plan_id}/decision",
                       json={"approve": True, "cut": False}).json()
    assert body["state"] == "approved"
    assert body["cut"]["running"] is False
    assert client.get("/api/edit/cut").json()["running"] is False


def test_rejecting_starts_nothing(client, storage_dir):
    source = _striped(storage_dir / "refused.mp4", [(2.0, True), (2.0, False)])
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]

    body = client.post(f"/api/edit/plans/{plan_id}/decision",
                       json={"approve": False, "note": "no"}).json()
    assert body["state"] == "rejected"
    assert body["cut"]["running"] is False
    assert client.get("/api/edit/cut").json()["running"] is False


def test_the_cut_streams_its_progress_and_ends_with_the_finished_file(client,
                                                                     storage_dir):
    """NDJSON over a worker thread, the shape the style shelf and the setup page use.

    The heartbeat matters as much as the log lines: the encode is one ffmpeg call with
    nothing to say in the middle of it, and a stream that goes quiet for four minutes is
    a stream an intermediary closes.
    """
    source = _striped(storage_dir / "streamed.mp4", [(2.0, True), (2.0, False)] * 3)
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]
    client.post(f"/api/edit/plans/{plan_id}/decision", json={"approve": True,
                                                             "cut": False})

    answered = client.post(f"/api/edit/plans/{plan_id}/cut")
    assert answered.status_code == 200
    lines = [json.loads(line) for line in answered.text.splitlines() if line.strip()]
    kinds = {line["type"] for line in lines}
    assert "log" in kinds
    assert lines[-1]["type"] == "done"
    assert lines[-1]["ok"] is True

    result = lines[-1]["result"]
    assert Path(result["path"]).exists()
    assert result["seconds"] < result["original_seconds"]
    # Reachable, not merely written: a path on the server's disk is not a video anybody
    # can watch, so the answer carries a signed link the browser can open.
    assert result["media_url"]
    fetched = client.get(result["media_url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "video/mp4"
    assert len(fetched.content) == Path(result["path"]).stat().st_size


def test_an_unapproved_plan_is_refused_by_the_endpoint_too(client, storage_dir):
    """The refusal lives in the studio, so the chat's tools and this endpoint cannot
    disagree about what the gate means."""
    source = _striped(storage_dir / "nogate.mp4", [(2.0, True), (2.0, False)])
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]

    answered = client.post(f"/api/edit/plans/{plan_id}/cut")
    lines = [json.loads(line) for line in answered.text.splitlines() if line.strip()]
    assert lines[-1]["ok"] is False
    assert "not approved" in lines[-1]["result"]["error"]


def test_cutting_a_plan_that_does_not_exist_is_a_404(client):
    assert client.post("/api/edit/plans/nothing-here/cut").status_code == 404


def test_the_finished_cut_is_visible_in_the_files_browser(client, storage_dir):
    """The operator needs the file. `storage/cuts/` is inside the browsable tree and
    beside the run folders, so "did the approval produce anything" is answered by opening
    a directory rather than by reading a JSON field."""
    source = _striped(storage_dir / "browsable.mp4", [(2.0, True), (2.0, False)] * 2)
    plan_id = client.post("/api/edit/plan", json={"path": str(source)}).json()["plan_id"]
    client.post(f"/api/edit/plans/{plan_id}/decision", json={"approve": True,
                                                             "cut": False})
    client.post(f"/api/edit/plans/{plan_id}/cut")

    listing = client.get("/api/files/list", params={"path": "cuts"}).json()
    assert f"{plan_id}.mp4" in [row["name"] for row in listing["entries"]]

    plan = client.get(f"/api/edit/plans/{plan_id}").json()
    assert plan["cut"]["media_url"]
    assert plan["cut"]["files"] == f"/files?path=cuts/{plan_id}.mp4"


# ------------------------------------------------------------------- the chat's end


def test_the_agent_may_execute_an_approved_plan_and_may_not_approve_one():
    """Approving is the operator agreeing to the edit; executing is carrying out a
    decision that has already been taken. `cut_plan` refuses anything unapproved, so it
    cannot be a way around the gate — and keeping it out would mean approving an edit in
    the chat and then being sent somewhere else to receive the file."""
    from forgecast.agent import tools

    assert "mcp__forgecast__cut_plan" in tools.ALLOWED
    assert "cut_plan" in tools._WRITES
    assert "mcp__forgecast__approve_edit" not in tools.ALLOWED
    assert "approve_edit" in tools.ALL_TOOLS


def test_the_stdio_transport_offers_the_cut_and_not_the_approval():
    """`codex exec` has nobody to ask, so the gate must not be reachable from it."""
    from forgecast.agent import mcp_stdio

    served = mcp_stdio.served_tools()
    assert "cut_plan" in served
    assert "approve_edit" not in served
