#!/usr/bin/env python3
"""
Script -> raw stitched voiceover, via the ElevenLabs API.

Same generation semantics as Voiceover Studio, so a section produced here is
interchangeable with one produced in the browser tool:

  * one request per section, ~450 chars
  * previous_text / next_text conditioning, 300 chars each way
  * previous_request_ids from the last 3 sections, for request stitching
  * conditioning is DROPPED right after a chapter announcement, so the narration
    starts fresh instead of continuing the heading's sentence
  * exact digital silence inserted around chapter announcements and CTAs

Unlike the browser, the stitch lands in a 48 kHz WAV rather than a re-encoded
MP3 — mastering runs on the un-degraded audio and only the delivered file is
encoded once.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pronounce  # noqa: E402
from script_prep import (CONTEXT_CHARS, build_sections, chapter_gaps,  # noqa: E402
                         master_script_lines)

SR = 48000
OUTPUT_FORMAT = "mp3_44100_128"

DEFAULT_SETTINGS = {
    "stability": 0.50,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
    "speed": 1.0,
}
DEFAULT_MODEL = "eleven_multilingual_v2"


def log(m):
    print(f"[voiceover] {m}", flush=True)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} failed:\n{p.stderr[-2000:]}")
    return p.stdout


# ------------------------------------------------------------------ profile
def load_profile(path=None):
    """Voice id + calibrated settings. Same shape as the studio's voiceover_profile.json,
    so that file can be dropped in unchanged.

    Also returns `source`: key -> "env" | "profile" | "default" | "unset", i.e. where
    each effective value actually came from. The spend gate prints it, because a value
    the profile omits is a value nobody chose. That is not a hypothetical distinction:
    a rebuilt profile left `similarity_boost` to fall back to DEFAULT_SETTINGS' 0.75
    when Sapro's locked-in number is 0.80, and the plan output could not show it
    because it only printed the four settings the profile happened to name.
    """
    prof = {}
    if path and os.path.isfile(path):
        prof = json.load(open(path, encoding="utf-8"))
    cal = prof.get("calibration") or {}
    src = {}

    env_key, env_voice = (os.environ.get("ELEVENLABS_API_KEY"),
                          os.environ.get("ELEVENLABS_VOICE_ID"))
    env_model = os.environ.get("ELEVENLABS_MODEL")
    key = env_key or prof.get("api_key") or ""
    src["api_key"] = "env" if env_key else "profile" if prof.get("api_key") else "unset"
    voice = env_voice or cal.get("voice") or prof.get("voice_id") or ""
    src["voice_id"] = ("env" if env_voice
                       else "profile" if (cal.get("voice") or prof.get("voice_id"))
                       else "unset")
    model = env_model or cal.get("model") or prof.get("model") or DEFAULT_MODEL
    src["model"] = ("env" if env_model
                    else "profile" if (cal.get("model") or prof.get("model"))
                    else "default")

    settings = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        src[k] = "default"
    for k in ("stability", "similarity_boost", "style", "speed"):
        v = cal.get(k, prof.get(k))
        if v is not None:
            settings[k] = float(v)
            src[k] = "profile"
    if cal.get("use_speaker_boost") is not None:
        settings["use_speaker_boost"] = bool(cal["use_speaker_boost"])
        src["use_speaker_boost"] = "profile"

    def _opt(key, cal_key, prof_key, default, cast):
        """One profile-or-default value, remembering which it was."""
        v = cal.get(cal_key, prof.get(prof_key, None))
        src[key] = "profile" if v is not None else "default"
        return cast(default if v is None else v)

    return {"api_key": key, "voice_id": voice, "model": model, "settings": settings,
            "source": src,
            "collapse_breaks": _opt("collapse_breaks", "collapseBreaks",
                                    "collapse_breaks", False, bool),
            "chapter_pause": _opt("chapter_pause", "chapterPause",
                                  "chapter_pause", "natural", str),
            "skip_headings": _opt("skip_headings", "skipHeadings",
                                  "skip_headings", False, bool),
            "chunk_size": _opt("chunk_size", "chunkSize", "chunk_size", 0,
                               lambda v: int(v or 0)),
            # the studio reads the title aloud by default; this pipeline follows the
            # profile rather than deciding for itself
            "read_title": _opt("read_title", "readTitle", "read_title", True, bool)}


def check_profile(prof):
    missing = []
    if not prof["api_key"]:
        missing.append("ELEVENLABS_API_KEY (env var, or api_key in the profile)")
    if not prof["voice_id"]:
        missing.append("ELEVENLABS_VOICE_ID (env var, or calibration.voice in the profile)")
    if missing:
        raise SystemExit("Cannot generate — missing:\n  " + "\n  ".join(missing) +
                         "\n\nExport your settings from Voiceover Studio (the profile lives at "
                         "voiceover_profile.json next to voiceover_studio.py) and pass it with "
                         "--profile, or set the environment variables.")


# ------------------------------------------------------------------ tts
def client(prof):
    return ElevenLabs(api_key=prof["api_key"], timeout=180)


def tts(client, prof, sections, index, prev_ids):
    """One section -> (mp3 bytes, request id). Retries 429/5xx with backoff."""
    sec = sections[index]
    prev = sections[index - 1] if index else None
    nxt = sections[index + 1] if index + 1 < len(sections) else None
    fresh_start = bool(prev and prev["is_heading"])

    kw = dict(
        voice_id=prof["voice_id"],
        text=sec["send_text"],
        model_id=prof["model"],
        output_format=OUTPUT_FORMAT,
        voice_settings=VoiceSettings(**prof["settings"]),
    )
    if prev and not fresh_start:
        kw["previous_text"] = prev["send_text"][-CONTEXT_CHARS:]
    if nxt:
        kw["next_text"] = nxt["send_text"][:CONTEXT_CHARS]
    if not fresh_start and prev_ids:
        kw["previous_request_ids"] = prev_ids[-3:]

    backoff = 2
    for attempt in range(4):
        try:
            # raw response so the request id header survives — it is what makes the
            # next section continue this one's delivery instead of restarting it.
            # convert() is a context manager streaming chunks; it is not an object
            # with a .data attribute.
            with client.text_to_speech.with_raw_response.convert(**kw) as raw:
                audio = b"".join(raw.data)
                headers = raw.headers or {}
            rid = headers.get("request-id") or headers.get("x-request-id")
            return audio, rid
        except ApiError as e:
            status = e.status_code or 0
            msg = str(getattr(e, "body", "") or e)
            if status == 401:
                raise RuntimeError("Invalid or expired ElevenLabs API key.")
            if status == 402 or "quota" in msg.lower():
                raise RuntimeError(f"Not enough ElevenLabs credits for section {index+1}: {msg}")
            if status in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"section {index+1}: {msg}")
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"section {index+1}: {e}")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(f"section {index+1}: gave up after retries")


# ------------------------------------------------------------------ spend ledger
# The budget has to survive across invocations, not just inside one.
#
# The read-check loop re-invokes this script once per redo round, and it does it by
# appending --regen to the SAME command line — so --approve-spend 12926 arrived
# again, intact, on every round. A ceiling that is handed out fresh to each call is
# not a ceiling: the number shown at the gate was the cost of one call, and the true
# worst case was that number times (1 + max_redos). The ledger makes the approval a
# quantity for the whole run, spent down section by section.
def spend_so_far(path):
    """Characters already sent by earlier invocations sharing this ledger."""
    if not path or not os.path.isfile(path):
        return 0
    try:
        return int(json.load(open(path, encoding="utf-8")).get("spent", 0))
    except (ValueError, OSError, AttributeError):
        # An unreadable ledger must not read as "nothing spent yet" — that is the
        # failure it exists to prevent — but it must not wedge the run either. Say so
        # and treat the budget as exhausted; --approve-spend can raise it deliberately.
        log(f"WARNING: spend ledger {path} is unreadable — treating it as exhausted")
        return -1


def record_spend(path, chars, index=None):
    """Debit `chars` from the run-wide ledger, immediately after they were SENT.

    Written per section rather than per invocation on purpose: a run that dies on
    section 30 of 52 has still been billed for 30, and a ledger that only records
    completed invocations would hand that budget out a second time.
    """
    if not path:
        return
    led = {"spent": 0, "calls": []}
    if os.path.isfile(path):
        try:
            led = json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError):
            led = {"spent": 0, "calls": []}
    led["spent"] = int(led.get("spent", 0)) + int(chars)
    led.setdefault("calls", []).append(
        {"pid": os.getpid(), "section": index, "chars": int(chars),
         "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    tmp = path + ".tmp"
    json.dump(led, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, path)                 # never leave a half-written ledger behind


def generate_sections(prof, sections, parts_dir, only=None, on_spend=None):
    """Render sections to parts_dir/sec_NNN.mp3. `only` = iterable of indexes to
    (re)generate; everything else is reused from disk. Returns request ids.

    `on_spend(chars, index)` is called after each section is actually sent, so the
    run-wide ledger is accurate even if the run dies part-way through."""
    os.makedirs(parts_dir, exist_ok=True)
    cl = client(prof)
    ids_path = os.path.join(parts_dir, "request_ids.json")
    ids = json.load(open(ids_path)) if os.path.isfile(ids_path) else {}

    todo = set(range(len(sections))) if only is None else set(only)
    prev_ids = []
    for i, sec in enumerate(sections):
        path = os.path.join(parts_dir, f"sec_{i:03d}.mp3")
        if i in todo or not os.path.isfile(path):
            kind = "chapter" if sec["is_heading"] else "CTA" if sec["is_cta"] else "section"
            log(f"  {i+1}/{len(sections)} {kind}, {sec['chars']} chars")
            audio, rid = tts(cl, prof, sections, i, prev_ids)
            if on_spend:
                on_spend(sec["chars"], i)
            open(path, "wb").write(audio)
            ids[str(i)] = rid
        rid = ids.get(str(i))
        if rid:
            prev_ids.append(rid)
    json.dump(ids, open(ids_path, "w"), indent=1)
    return ids


# ------------------------------------------------------------------ stitch
def _decode(src, rate=SR, tempo=1.0):
    """-> headerless s16le mono bytes. Byte concatenation of these is sample-exact."""
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        tmp = f.name
    cmd = ["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", str(rate)]
    if abs(tempo - 1.0) > 1e-3:
        cmd += ["-filter:a", f"atempo={tempo:.4f}"]
    run(cmd + ["-f", "s16le", tmp, "-y"])
    data = open(tmp, "rb").read()
    os.unlink(tmp)
    return data


def _syllables(text):
    """Rough syllable count — vowel groups, with the usual silent-e correction.

    Approximate on any single word and accurate enough in aggregate, which is all
    a rate needs.
    """
    n = 0
    for tok in re.findall(r"[A-Za-z']+|\d+", text.lower()):
        if tok.isdigit():
            n += _digit_syllables(tok)
            continue
        if tok.upper() == tok.upper() and not re.search(r"[aeiouy]", tok):
            n += sum(_LETTER_SYL.get(c, 1) for c in tok)   # 'M' in M16 -> 'em'
            continue
        groups = len(re.findall(r"[aeiouy]+", tok))
        if tok.endswith("e") and not tok.endswith(("le", "ee", "ye")) and groups > 1:
            groups -= 1                      # silent e: 'bombard' vs 'bombarde'
        n += max(1, groups)
    return n


# Spoken length of a single letter, for initialisms: 'M16' is said "em sixteen",
# three syllables, not the one a vowel-group count finds in "M".
_LETTER_SYL = {"w": 3, "m": 1, "n": 1, "l": 1, "s": 1, "f": 1, "x": 2, "h": 2}

_ONES = [0, 1, 1, 1, 1, 1, 1, 2, 1, 1]                      # zero..nine
_TEENS = [1, 3, 1, 2, 2, 2, 2, 3, 2, 2]                     # ten..nineteen
_TENS = [0, 0, 2, 2, 2, 2, 2, 3, 2, 2]                      # twenty..ninety


def _digit_syllables(d):
    """Syllables in a run of digits, said the way a narrator says it.

    Numerals were being dropped from the count entirely, which is why "M16"
    measured 1 syllable and "Mark 14 Torpedo" measured 4 instead of 6 — and a
    heading whose length is under-counted looks slow, so the leveller stretched
    it further. Four-digit runs are read year-style ("fourteen sixty") because
    that is what these scripts contain.
    """
    n = int(d)
    if len(d) == 4 and 1100 <= n <= 1999:
        return _digit_syllables(d[:2]) + _digit_syllables(d[2:])
    if n < 10:
        return _ONES[n]
    if n < 20:
        return _TEENS[n - 10]
    if n < 100:
        return _TENS[n // 10] + (_ONES[n % 10] if n % 10 else 0)
    if n < 1000:
        return _ONES[n // 100] + 2 + (_digit_syllables(str(n % 100)) if n % 100 else 0)
    return sum(_ONES[int(c)] for c in d)     # long runs get read digit by digit


def _speech_rate(path, text):
    """Syllables per second over the SPOKEN span only, plus that span.

    Two corrections, and the second one was a real defect in a delivered file.

    Edges: a chapter announcement is 1-4 words wrapped in ~0.2 s of model silence
    at each end. Divide by the whole file and that padding dominates, so a short
    heading looks slow however it was read.

    Units: this used to be WORDS per minute, which is not comparable across
    headings of different lengths — a word is not a fixed amount of speech. In one
    delivered master "Chauchat" (1 word) measured 66 wpm and "James the Second's
    Bombard" (4 words) measured 129, against a median of 99 set by the 2-word
    headings. Nothing was wrong with either read: the long heading was slowed 15%
    and the short one sped up 18% to correct an artifact of counting words. Sapro
    heard the result as "this header is quite slow, especially Bombard".
    Syllables per second is length-independent, so headings of different word
    counts can actually be compared.
    """
    import readcheck as rc
    m = rc.measure(path)
    dur = m["duration"]
    if dur <= 0.2:
        return 0.0, dur
    lead = next((e for s, e in m["silences"] if s <= 0.05), 0.0)
    tail = next((dur - s for s, e in m["silences"] if e >= dur - 0.05), 0.0)
    speech = max(0.2, dur - lead - tail)
    return _syllables(text) / speech, speech


def level_headings(parts_dir, sections, tol=0.12, floor=0.85, ceil=1.18):
    """-> {index: tempo factor} evening out chapter announcements against each other.

    The first chapter announcement is the section with the least conditioning behind
    it — no previous_text, no previous_request_ids — so the model starts cold and
    reads it faster than the ones that follow, which inherit up to three prior
    request ids. It is a real, repeatable difference and it is audible.

    Regenerating does not reliably fix it, because the cause is structural rather
    than a bad roll of the dice. Retiming does, exactly and for free: measure every
    heading, take the median of the others as the target, and stretch any heading
    that sits more than `tol` away from it.
    """
    heads = [s for s in sections if s["is_heading"]]
    if len(heads) < 3:
        # with fewer than three there is no majority to level against, and
        # levelling to a single other heading would just copy its errors
        return {}

    rates = {}
    for s in heads:
        rate, _ = _speech_rate(os.path.join(parts_dir, f"sec_{s['index']:03d}.mp3"),
                               s["send_text"])
        if rate > 0:
            rates[s["index"]] = rate

    factors = {}
    for idx, rate in rates.items():
        others = sorted(v for k, v in rates.items() if k != idx)
        if len(others) < 2:
            continue
        mid = len(others) // 2
        target = others[mid] if len(others) % 2 else (others[mid - 1] + others[mid]) / 2
        if not target or abs(rate - target) / target <= tol:
            continue
        want = target / rate                      # >1 speeds up, <1 slows down
        f = max(floor, min(ceil, want))
        if abs(f - 1.0) <= 1e-3:
            continue
        factors[idx] = f
        note = (f"  heading {idx+1}: {rate:.2f} syl/s vs {target:.2f} median"
                f" — retiming x{f:.3f}")
        # Only warn when the clamp actually leaves the heading short of the target.
        # Rounding both sides to 2 dp printed "lands near 4.20, not 4.20" —
        # a warning about a miss of less than one word per minute, which reads as a
        # problem and is not one.
        landed = rate * f
        if abs(want - f) > 1e-3 and abs(landed - target) >= 1.0:
            # past ~15% the stretch itself becomes audible, so the correction stops
            # short rather than trading one artefact for another. Say so.
            note += (f" (clamped from x{want:.3f}; lands near {landed:.2f} syl/s, "
                     f"not {target:.0f} — listen)")
        log(note)
    return factors


# Each section is a separate render, butt-joined to the next. Whatever sample the
# encoder happens to end on meets whatever sample the next one starts on, and the
# step between them is a click. Sapro heard two of these -- 2:31 and 3:28 in a
# delivered file -- and both landed within a second of a section join.
#
# A click cannot be found reliably after the fact: a sample-step detector tuned to
# catch all three he reported also flagged several hundred ordinary plosives, which
# is the same wall explaintory-vo-master hit. So it is prevented instead. Three
# milliseconds of fade at each section edge takes the join to zero and back; it is
# far shorter than any phoneme, and it cannot click because there is no step left
# to click on.
SPLICE_FADE = 0.003


def _edge_fade(pcm_bytes, rate, dur=SPLICE_FADE):
    """Ramp the first and last few ms of a section to zero so joins cannot step."""
    import array
    a = array.array("h")
    a.frombytes(pcm_bytes)
    n = int(dur * rate)
    if len(a) < 2 * n or n < 1:
        return pcm_bytes
    for k in range(n):
        g = k / n
        a[k] = int(a[k] * g)
        a[len(a) - 1 - k] = int(a[len(a) - 1 - k] * g)
    return a.tobytes()


def stitch(parts_dir, sections, out_path, preset="natural", rate=SR, level=True):
    """Concatenate the sections with exact digital silence between them.
    Returns [{index, start, end}] so a flagged section maps back to a timestamp."""
    gaps = chapter_gaps(sections, preset)
    factors = level_headings(parts_dir, sections) if level else {}
    pcm = bytearray()
    marks = []
    for i, sec in enumerate(sections):
        if gaps[i] > 0:
            pcm += b"\x00\x00" * int(round(gaps[i] * rate))
        start = len(pcm) / 2 / rate
        pcm += _edge_fade(
            _decode(os.path.join(parts_dir, f"sec_{i:03d}.mp3"), rate,
                    factors.get(i, 1.0)), rate)
        marks.append({"index": i, "start": round(start, 3),
                      "end": round(len(pcm) / 2 / rate, 3),
                      "retimed": round(factors.get(i, 1.0), 4)})

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        raw = f.name
    open(raw, "wb").write(bytes(pcm))
    run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1",
         "-i", raw, out_path, "-y"])
    os.unlink(raw)
    return marks


# ------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser(description="Generate a raw voiceover from a script.")
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True, help="stitched raw VO, .wav recommended")
    ap.add_argument("--profile", help="voiceover_profile.json from Voiceover Studio")
    ap.add_argument("--parts-dir", help="where section takes live (default: alongside --out)")
    ap.add_argument("--run-on", action="store_true",
                    help="chapter name leads the first sentence in the same request")
    ap.add_argument("--skip-headings", action="store_true",
                    help="do not read chapter names aloud (studio default is to read them)")
    ap.add_argument("--max-chunk", type=int, default=450)
    ap.add_argument("--chapter-pause", choices=["tight", "natural", "wide"])
    ap.add_argument("--regen", help="comma-separated 1-based sections to re-render")
    ap.add_argument("--budget", type=int, default=2000,
                    help="hard ceiling on characters this invocation may SEND. "
                         "Above it the run stops and prints what it wanted to spend, "
                         "so nobody discovers the bill afterwards. Raise it "
                         "deliberately with --approve-spend.")
    ap.add_argument("--approve-spend", type=int, default=0,
                    help="raise --budget to this many characters for this run")
    ap.add_argument("--spend-log",
                    help="JSON ledger of characters already sent by this RUN. The "
                         "ceiling is debited against it rather than reset, so a redo "
                         "round spends what is left of the approval instead of "
                         "receiving a fresh copy of it.")
    ap.add_argument("--stability", type=float,
                    help="override the profile's stability for this run. Raising it "
                         "slightly is the studio's fix for false mid-sentence pauses.")
    ap.add_argument("--stitch-only", action="store_true")
    ap.add_argument("--no-level-headings", action="store_true",
                    help="leave chapter announcements at whatever rate they rendered")
    ap.add_argument("--lexicon", help="pronunciation lexicon JSON — names respelled so "
                                      "the voice reads them right")
    ap.add_argument("--sections-json", help="write the section manifest here")
    a = ap.parse_args()

    prof = load_profile(a.profile)
    if a.stability is not None:
        prof["settings"]["stability"] = max(0.0, min(1.0, a.stability))
    preset = a.chapter_pause or prof["chapter_pause"]
    raw_script = open(a.script, encoding="utf-8").read()
    sections = build_sections(raw_script, a.skip_headings, a.max_chunk, a.run_on)
    if not sections:
        raise SystemExit("Nothing to narrate — the script is empty after removing headings.")

    # Respell before anything measures character counts, and before the API sees the
    # text — but only in send_text, so the read-check and the mastering alignment
    # still work against the spelling in the script.
    lex = pronounce.load_lexicon(a.lexicon)
    if lex:
        pronounce.check_lexicon(lex, prof["model"])
        used = pronounce.apply_to_sections(sections, lex)
        if used:
            log("respelled for the voice: " +
                ", ".join(f"{w}→{lex[w]} (x{n})" for w, n in sorted(used.items())))

    parts_dir = a.parts_dir or os.path.splitext(a.out)[0] + "_parts"
    chars = sum(s["chars"] for s in sections)
    log(f"{len(sections)} sections · {chars} chars · ~{chars} credits")

    if not a.stitch_only:
        check_profile(prof)
        only = None
        if a.regen:
            only = [int(x) - 1 for x in a.regen.split(",") if x.strip()]
            log(f"re-rendering sections {', '.join(str(i+1) for i in only)}")

        # Count what is actually about to be SENT — sections already on disk are
        # free. A redo pass is where a bill quietly doubles, so it is checked by
        # the same ceiling as a first render.
        todo = range(len(sections)) if only is None else only
        due = sum(sections[i]["chars"] for i in todo
                  if only is None or not os.path.isfile(
                      os.path.join(parts_dir, f"sec_{i:03d}.mp3")) or i in set(only))
        ceiling = max(a.budget, a.approve_spend)
        already = spend_so_far(a.spend_log)
        remaining = ceiling - already if already >= 0 else 0
        if due > remaining:
            raise SystemExit(
                f"\nSTOPPED before spending. This step would send {due:,} characters, "
                f"over the {remaining:,} left of the {ceiling:,} approved for this run"
                + (f" ({already:,} already sent).\n" if already > 0 else ".\n")
                + f"  {len(list(todo))} section(s): "
                f"{', '.join(str(i+1) for i in list(todo)[:12])}"
                f"{'…' if len(list(todo)) > 12 else ''}\n\n"
                f"Approve it explicitly:  --approve-spend {already + due}\n")
        log(f"sending {due:,} chars ({remaining:,} left of the {ceiling:,} approved"
            + (f", {already:,} already sent this run)" if already > 0 else ")"))
        generate_sections(prof, sections, parts_dir, only,
                          on_spend=(lambda n, i: record_spend(a.spend_log, n, i))
                          if a.spend_log else None)

    log("stitching")
    marks = stitch(parts_dir, sections, a.out, preset, level=not a.no_level_headings)
    # The stitch is this stage's artifact, so this stage says whether it exists.
    # ffmpeg reporting a problem on stderr and still exiting 0 has to end the run
    # here, not four minutes later inside the master with a confusing message.
    expect = marks[-1]["end"] if marks else 0.0
    if not os.path.isfile(a.out) or os.path.getsize(a.out) == 0:
        raise SystemExit(f"stitch produced no audio at {a.out} — nothing to master")
    try:
        import readcheck as _rc
        got = _rc.probe_duration(a.out)
    except Exception as e:                       # ffprobe missing or unhappy
        log(f"WARNING: could not probe {a.out} ({e}) — length unverified")
        got = 0.0
    if got <= 0:
        log(f"WARNING: {a.out} has no readable duration — length unverified")
    elif expect and got < expect * 0.9:
        raise SystemExit(
            f"stitch at {a.out} is {got:.1f}s but the section marks add up to "
            f"{expect:.1f}s — it is truncated. Not passing a short file to the master.")
    log(f"wrote {a.out}  ({marks[-1]['end']/60:.1f} min)")

    if a.sections_json:
        json.dump({"sections": sections, "marks": marks,
                   "script_lines": master_script_lines(raw_script, a.skip_headings, a.run_on)},
                  open(a.sections_json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
