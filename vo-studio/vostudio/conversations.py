"""
Conversations, kept as files.

WHY THIS EXISTS

    "New conversation" was one button in the corner of a card, and all it did
    was drop the in-memory session. That is an erase key, not a conversation
    list. The transcript is where the script lives, and the takes, and every
    note about the read — and the previous one became unreachable the moment
    the next one started.

    So each conversation is a file. The transcript replays from it, and the
    agent's own session id is stored beside it: reopening one hands that id
    back to the SDK as resume=, so Claude picks up with the script and the
    takes still in front of it rather than politely meeting you again.

WHAT IS STORED, AND WHAT IS NOT

    Text, attachment names, and the file name of any take that was rendered.
    Not the audio — that already lives under projects/ with its own numbering,
    and a second copy would be a second thing to keep in step.

    A take whose file has since been deleted replays as a dead player rather
    than a lie about there being no take; the file name is the record of what
    happened, which is the part worth keeping.
"""
import json
import re
import time
from pathlib import Path

# Ids are minted from the clock, so the folder sorts chronologically in
# Explorer as well as here. The counter only exists because two conversations
# started in the same second is a thing a person can do by double-clicking.
_SEQ = 0

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]+)?$")


def store(root: Path) -> Path:
    return Path(root) / "conversations"


def _path(root: Path, cid: str) -> Path | None:
    """The file for an id, or None if the id is not one we minted.

    Ids arrive from the front-end, which means they arrive from anywhere. This
    is the only place a caller-supplied string becomes a path, so it is the
    only place that has to refuse "../../settings".
    """
    if not _ID.match(cid or ""):
        return None
    return store(root) / f"{cid}.json"


def _now() -> float:
    return time.time()


def title_from(text: str) -> str:
    """A name taken from the first thing said, the way you would name it.

    Long enough to tell two apart, short enough for a 244 px column.
    """
    line = " ".join((text or "").split())
    if not line:
        return "New conversation"
    return line[:46].rstrip() + ("…" if len(line) > 46 else "")


def create(root: Path) -> dict:
    global _SEQ
    _SEQ += 1
    cid = time.strftime("%Y%m%d-%H%M%S") + (f"-{_SEQ}" if _SEQ > 1 else "")
    while (store(root) / f"{cid}.json").exists():
        _SEQ += 1
        cid = time.strftime("%Y%m%d-%H%M%S") + f"-{_SEQ}"
    rec = {"id": cid, "title": "New conversation", "created": _now(),
           "updated": _now(), "session_id": None, "turns": []}
    save(root, rec)
    set_active(root, cid)
    return rec


def save(root: Path, rec: dict) -> None:
    p = _path(root, rec["id"])
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    # Written beside and moved into place. A crash mid-write would otherwise
    # leave a half-written JSON file that never loads again, and the
    # conversation it held would be gone for good.
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(p)


def load(root: Path, cid: str) -> dict | None:
    p = _path(root, cid)
    if p is None or not p.is_file():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return rec if isinstance(rec, dict) and rec.get("id") == cid else None


def delete(root: Path, cid: str) -> bool:
    p = _path(root, cid)
    if p is None or not p.is_file():
        return False
    p.unlink(missing_ok=True)
    if active_id(root) == cid:
        (store(root) / "active.txt").unlink(missing_ok=True)
    return True


def summaries(root: Path) -> list[dict]:
    """Every conversation, newest first, without their transcripts.

    The list in the sidebar redraws after every turn; loading a hundred full
    transcripts to show a hundred titles is the kind of thing that makes an app
    feel heavy for no reason anyone can see.
    """
    out = []
    for p in sorted(store(root).glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue                       # a corrupt file is not a crash
        if not isinstance(rec, dict) or not rec.get("id"):
            continue
        out.append({"id": rec["id"], "title": rec.get("title") or "Conversation",
                    "updated": rec.get("updated") or rec.get("created") or 0,
                    "turns": len(rec.get("turns") or [])})
    out.sort(key=lambda r: r["updated"], reverse=True)
    return out


# -- which one is open -----------------------------------------------------
# On disk, not in a variable, so closing the app and opening it again lands you
# back in the conversation you were having rather than a blank one.

def active_id(root: Path) -> str | None:
    try:
        cid = (store(root) / "active.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return cid if _path(root, cid) and _path(root, cid).is_file() else None


def set_active(root: Path, cid: str) -> None:
    store(root).mkdir(parents=True, exist_ok=True)
    (store(root) / "active.txt").write_text(cid, encoding="utf-8")


def active(root: Path) -> dict:
    """The open conversation — the most recent one, or a new one if there is
    none at all. Never returns None: there is always a conversation."""
    cid = active_id(root)
    rec = load(root, cid) if cid else None
    if rec:
        return rec
    recent = summaries(root)
    if recent:
        rec = load(root, recent[0]["id"])
        if rec:
            set_active(root, rec["id"])
            return rec
    return create(root)


# -- writing to one --------------------------------------------------------

def add_turn(root: Path, cid: str, turn: dict) -> None:
    rec = load(root, cid)
    if rec is None:
        return
    rec.setdefault("turns", []).append(turn)
    rec["updated"] = _now()
    # The title comes from the first thing SAID, not from the first turn:
    # a conversation that opens with an attached clip and no words would
    # otherwise be called "New conversation" forever.
    if rec.get("title") in (None, "", "New conversation") and turn.get("role") == "me":
        text = (turn.get("text") or "").strip()
        if text:
            rec["title"] = title_from(text)
    save(root, rec)


def set_session(root: Path, cid: str, session_id: str | None) -> None:
    """Remember the agent's session so reopening can resume it.

    None clears it — the id would not resume, and keeping one that fails is
    worse than having none at all."""
    rec = load(root, cid)
    if rec is None or rec.get("session_id") == session_id:
        return
    rec["session_id"] = session_id
    save(root, rec)
