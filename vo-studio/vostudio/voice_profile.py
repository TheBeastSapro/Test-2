"""
Voice profiles, and the dial-in loop that produces them.

Sapro's Rookcast transcript is the spec for the LOOP, not for any of its numbers.
He said so explicitly: it was an example of how he likes to work. What worked
there was not a settings panel:

    render 40 seconds -> he says what is wrong in plain English ->
    the numbers move -> render again -> lock it

Seven rounds, each one a sentence of feedback ("too flat", "the pacing has gaps",
"feels bit fast", "in some areas it feels like there's a comma but it ends like
there's not"), and at the end a saved profile every later run picks up. He never
touched a slider. That is what this file reproduces.

The values from that session are ElevenLabs values for a different channel and a
different model, and none of them are carried over. This module starts from
Chatterbox's own neutral defaults and converges from there. The numbers that ARE
locked for ExplainTory live in config.py — WER 0.20, RUNTHROUGH 0.060, the 160 ms
comma target, the 3 ms edge fade, -14 LUFS — and each one is annotated with the
specific failure that set it. Nothing here overrides those.

TRANSLATING THE FEEDBACK IS THE WHOLE JOB
    Chatterbox does not have ElevenLabs' knobs. There is no stability, no style,
    no similarity_boost. The real parameters are:

        exaggeration        how performed the read is (0.5 neutral)
        cfg_weight          how tightly it follows the reference's own delivery
        temperature         how much it varies between takes
        repetition_penalty  discourages stuck/repeated tokens

    So his vocabulary has to be mapped onto those instead, and FEEDBACK below is
    that map. It is a starting point, not physics — the loop is what converges.

AND ONE KNOB HAD TO BE BUILT
    Chatterbox has NO speed parameter at all, and pace is something he tunes by
    ear every time, so speed is applied after generation with ffmpeg's atempo,
    which is pitch-preserving. The profile starts at 1.00x and the loop finds his
    number -- it is not seeded from anywhere.

    That choice was measured, not assumed. librosa's phase vocoder shifts his
    median f0 by 4.5-8.5% at these rates — audibly higher, a different-sounding
    person. atempo moves it 0.2-1.5%:

        rate    atempo      librosa
        1.05x   +0.4%       +6.7%
        1.07x   +1.5%       +4.5%
        1.15x   +0.2%       +8.5%
"""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import re
import subprocess
import tempfile


@dataclass
class VoiceProfile:
    name: str = "default"
    reference: str = ""              # path to the reference clip
    exaggeration: float = 0.50
    cfg_weight: float = 0.50
    temperature: float = 0.80
    repetition_penalty: float = 1.2
    speed: float = 1.00              # applied post-generation via atempo
    history: list = field(default_factory=list)   # every round, so a revert is possible

    def save(self, voices_dir: Path) -> Path:
        d = voices_dir / self.name
        d.mkdir(parents=True, exist_ok=True)
        path = d / "profile.json"
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, voices_dir: Path, name: str) -> "VoiceProfile":
        path = voices_dir / name / "profile.json"
        if not path.exists():
            return cls(name=name)
        raw = json.loads(path.read_text())
        raw.pop("history", None)
        return cls(**raw, history=json.loads(path.read_text()).get("history", []))

    def summary(self) -> str:
        return (f"exaggeration {self.exaggeration:.2f} | cfg_weight {self.cfg_weight:.2f} | "
                f"temperature {self.temperature:.2f} | speed {self.speed:.2f}x")


# Plain English -> which number moves, and which way.
# Each entry: (regex, field, delta, why it is the right lever)
FEEDBACK = [
    (r"\b(too )?(flat|monotone|robotic|lifeless|boring|dull)\b",
     "exaggeration", +0.10, "flat read — more performance"),
    (r"\b(too )?(expressive|dramatic|over[- ]?acted|theatrical|much emotion|overdone)\b",
     "exaggeration", -0.10, "over-performed — pull the performance back"),

    # Filler words go BETWEEN the verb and the adjective in real speech. His actual
    # sentence was "feels bit fast", and a \bfeels fast\b pattern misses it entirely.
    # A matcher that only understands tidy phrasing makes the loop feel broken.
    (r"\b(too|feels?|bit|little|slightly|sounds?|reads?|a)\W+(\w+\W+){0,2}?(fast|rushed|quick|speedy)\b",
     "speed", -0.03, "slow the delivery"),
    (r"\b(too|feels?|bit|little|slightly|sounds?|reads?|a)\W+(\w+\W+){0,2}?(slow|sluggish|dragging|draggy)\b",
     "speed", +0.03, "speed the delivery up"),

    # "the pacing has gaps" = dead air between sentences. In the Rookcast session
    # that was blank lines in the script, not a model setting -- script_prep already
    # collapses those, so say so rather than moving a number that will not fix it.
    (r"\b(pacing|timing).{0,20}(gaps?|holes?|dead air)\b|\bdead air\b|\b(long|big|huge) (gaps?|pauses?)\b",
     "__deadair__", 0.0, "dead air between sentences"),

    # His exact Rookcast complaint: "feels like there's a comma but there isn't"
    (r"\b(false|fake|extra|random|mid[- ]sentence) (pause|comma|gap|breath)",
     "cfg_weight", +0.08, "breathing where the script has no punctuation — "
                          "follow the reference's phrasing more tightly"),
    (r"\b(comma|pause).{0,30}(not there|isn't there|no comma|shouldn't)\b",
     "cfg_weight", +0.08, "phantom punctuation — tighten adherence to the reference"),

    (r"\b(no|not enough|lacks?|missing) (natural )?(gaps?|pauses?|breath|breathing)\b",
     "cfg_weight", -0.08, "no room to breathe — loosen adherence"),
    (r"\b(run(s|ning)? together|no space|crammed|smashed together)\b",
     "cfg_weight", -0.08, "phrases running together — loosen adherence"),

    (r"\b(doesn'?t sound like me|not my voice|drift(ing|s)?|off voice|wrong voice)\b",
     "cfg_weight", -0.06, "drifting off the reference — follow it more closely"),

    (r"\b(inconsistent|wobbly|unstable|varies|random|erratic)\b",
     "temperature", -0.10, "too much variance between takes"),
    (r"\b(stiff|same every time|identical|mechanical|samey)\b",
     "temperature", +0.10, "too little variance — loosen it"),

    (r"\b(repeat|repeats|repeating|stutter|stammers?|doubl(e|ed) word)\b",
     "repetition_penalty", +0.15, "words repeating — penalise repetition harder"),
]

LIMITS = {
    "exaggeration": (0.20, 0.90),
    "cfg_weight": (0.20, 0.90),
    "temperature": (0.40, 1.10),
    "repetition_penalty": (1.0, 2.0),
    "speed": (0.85, 1.25),
}


def apply_feedback(profile: VoiceProfile, feedback: str) -> tuple[VoiceProfile, list[str]]:
    """
    One round: his sentence in, moved numbers out, with the reasoning shown.

    Steps are small on purpose. Rookcast's worst rounds were the big ones — style
    0.0 -> 0.45 overshot into "too expressive", stability 0.42 -> 0.50 made it
    "feel slow", and both had to be walked back. Small steps converge; large ones
    oscillate, and every oscillation costs a render and his attention.
    """
    text = feedback.lower()
    changes, seen = [], set()

    for pattern, fieldname, delta, why in FEEDBACK:
        if fieldname in seen or not re.search(pattern, text):
            continue
        seen.add(fieldname)
        if fieldname == "__deadair__":
            changes.append(
                "dead air between sentences is a SCRIPT issue, not a setting — "
                "double/triple blank lines become long silences. script_prep already "
                "splits on blank lines, so check the script for stacked ones. Moving "
                "a model parameter will not fix it.")
            continue
        low, high = LIMITS[fieldname]
        before = getattr(profile, fieldname)
        after = round(min(high, max(low, before + delta)), 3)
        if after == before:
            changes.append(f"{fieldname} already at its limit ({before}) — "
                           f"the fix for this is the script or the reference clip, "
                           f"not the setting")
            continue
        setattr(profile, fieldname, after)
        changes.append(f"{fieldname} {before} -> {after}  ({why})")

    if not changes:
        changes.append(
            "Nothing in that mapped to a setting. Try naming what is wrong in the "
            "words this understands: flat, too expressive, too fast, too slow, "
            "false pauses, no natural gaps, doesn't sound like me, inconsistent, "
            "stiff, repeating.")
    else:
        profile.history.append({"feedback": feedback, "changes": changes,
                                "result": profile.summary()})
    return profile, changes


def apply_speed(wav_path: Path, speed: float) -> Path:
    """
    Post-generation speed, pitch preserved. Chatterbox has no speed parameter.

    atempo only, never a phase vocoder — see this module's docstring for the
    measurement. Chained in steps because a single atempo is only valid in
    [0.5, 2.0], and chaining keeps quality better than one extreme stage.
    """
    if abs(speed - 1.0) < 0.005:
        return wav_path

    factors, remaining = [], speed
    while remaining > 2.0:
        factors.append(2.0); remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5); remaining /= 0.5
    factors.append(remaining)

    out = Path(tempfile.mkdtemp()) / wav_path.name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav_path),
                    "-filter:a", ",".join(f"atempo={f:.4f}" for f in factors),
                    str(out)], check=True)
    return out
