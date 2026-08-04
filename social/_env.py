"""Minimal .env loader. No dependency on python-dotenv."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE lines from .env into os.environ without clobbering
    anything already exported in the shell."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require(*names: str) -> list[str]:
    """Return the values of names, or raise with a message that says exactly
    which ones are missing and where to put them."""
    load_env()
    missing = [n for n in names if not get(n)]
    if missing:
        raise SystemExit(
            "Missing credential(s): "
            + ", ".join(missing)
            + f"\nAdd them to {ENV_FILE} (copy .env.example first).\n"
            "Run `python3 social/check.py` for per-service setup steps."
        )
    return [get(n) for n in names]
