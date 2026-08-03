"""Chat preferences: which model answers, and how much it may do unasked.

A file rather than a settings row. These are decided in the composer — the moment
you notice a reply is slower than you want, or that being asked about every edit is
getting tedious — and making someone open a Settings page to keep that choice would
be silly. A file also means the value survives the database being reset, which is
the other thing that happens while trying things out.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("forgecast.agent.prefs")


@dataclass
class Prefs:
    # Which agent answers: "claude" or "chatgpt". Claude, always, until someone
    # changes it — an install that never touches this setting behaves exactly as it
    # did before the second backend existed.
    engine: str = "claude"
    model: str = "claude-sonnet-5"
    # ChatGPT's model, kept in its own field rather than sharing `model`.
    #
    # One field would mean switching engine either silently overwrites the choice you
    # made for the other one, or hands a Claude model id to Codex — which fails as a
    # vendor error about an unknown model rather than as anything you could act on. It
    # also means switching back and forth does not lose your pick.
    chatgpt_model: str = "gpt-5.6-terra"
    # True: every file edit asks first. False: it edits, then tells you.
    # Tool calls are unaffected — those are pre-allowed because each is re-runnable.
    # Claude only: `codex exec` is non-interactive and cannot stop to ask, which the
    # picker says out loud rather than leaving the toggle looking effective.
    confirm_edits: bool = True
    # Web search and fetch. On by default: research is half of what this app does.
    allow_web: bool = True
    # A ceiling per turn, in dollars of equivalent API spend. None means the CLI's own.
    # Claude only — Codex has no per-turn budget flag.
    budget_usd: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    # Models belong to an engine. These two methods are the only place that mapping
    # lives, so a third backend does not mean hunting for `prefs.model` at ten call
    # sites and guessing which of them meant "the Claude one".

    def model_for(self, engine: str) -> str:
        return self.chatgpt_model if engine == "chatgpt" else self.model

    def set_model_for(self, engine: str, model: str) -> None:
        if engine == "chatgpt":
            self.chatgpt_model = model
        else:
            self.model = model


def _path() -> Path:
    return get_settings().storage_dir / "agent_prefs.json"


def load() -> Prefs:
    path = _path()
    if not path.exists():
        return Prefs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("agent prefs at %s are unreadable — using defaults", path)
        return Prefs()
    known = {f for f in Prefs().as_dict()}
    return Prefs(**{k: v for k, v in raw.items() if k in known})


def save(prefs: Prefs) -> Prefs:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs.as_dict(), indent=2), encoding="utf-8")
    return prefs


def update(**changes) -> Prefs:
    current = load()
    for key, value in changes.items():
        if value is not None and hasattr(current, key):
            setattr(current, key, value)
    return save(current)
