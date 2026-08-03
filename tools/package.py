#!/usr/bin/env python3
"""Build the distributable zip.

    python tools/package.py [--out dist/]

## Why this is a script and not `git archive`

The thing being shipped is not the repository. A person who unzips this should be able
to double-click one file and have a working application, which means the archive has to
contain exactly the runtime and nothing that would confuse or endanger them:

* **`.env` must never be in it.** It holds the encryption key for stored provider
  credentials and a password for the account. Shipping one install's secrets to another
  machine is the worst thing this script could do, so the exclusion is asserted at the
  end rather than assumed from the ignore list.
* **`.venv`, `forgecast.db` and `storage/` must never be in it.** They are one machine's
  state — a virtualenv with absolute paths baked in, a database of someone else's runs,
  and gigabytes of renders.
* **Tests and CI config are excluded** because they are for developing Forgecast, not
  for running it, and a first-time user opening the folder should see the launcher, not
  a `tests/` directory.

Everything the launcher needs is included, including `pyproject.toml` — the first run
pip-installs the project from it, so an archive without it produces an app that cannot
start.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Forgecast"

# Everything a person needs to run the app, and nothing else.
INCLUDE_FILES = [
    "launcher.py",
    "Forgecast.bat",
    "Forgecast.command",
    "pyproject.toml",
    "alembic.ini",
    "INSTALL.md",
    "README.md",
    "DEPLOY.md",
    "ARCHITECTURE.md",
]
INCLUDE_TREES = ["forgecast", "migrations", "remotion"]

# Checked against every archive member before the zip is written. These are the paths
# that would leak secrets or one machine's state onto another's.
FORBIDDEN = (".env", ".venv/", "forgecast.db", "storage/", ".git/", "node_modules/")

SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".db", ".sqlite", ".sqlite3"}
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache",
             ".ruff_cache", "out", "dist", "storage"}


def files_to_ship() -> list[tuple[Path, str]]:
    """(absolute path, path inside the archive) for everything being shipped."""
    picked: list[tuple[Path, str]] = []

    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.exists():
            picked.append((path, f"{NAME}/{name}"))
        else:
            print(f"  note: {name} is missing, skipping", file=sys.stderr)

    for tree in INCLUDE_TREES:
        base = ROOT / tree
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if set(relative.parts) & SKIP_DIRS:
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            picked.append((path, f"{NAME}/{relative.as_posix()}"))

    return picked


def check(members: list[str]) -> None:
    """Refuse to write an archive containing anything on the forbidden list.

    Asserted rather than trusted. The include list already excludes these, but the cost
    of being wrong is shipping an encryption key, and the check is three lines.
    """
    leaked = [
        member for member in members
        if any(part in member for part in FORBIDDEN)
    ]
    if leaked:
        raise SystemExit(
            "refusing to build: the archive would contain\n  "
            + "\n  ".join(leaked[:10])
        )


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    version = "0.1.0"
    try:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("version"):
                version = line.split("=")[1].strip().strip('"')
                break
    except OSError:
        pass

    picked = files_to_ship()
    check([member for _, member in picked])

    archive = out_dir / f"{NAME}-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, member in picked:
            info = zipfile.ZipInfo(member)
            # Fixed timestamp so the same source produces the same archive, and the
            # executable bit survives on the two launchers that need it.
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = member.endswith((".command", ".sh")) or member.endswith("launcher.py")
            info.external_attr = (0o755 if executable else 0o644) << 16
            zf.writestr(info, path.read_bytes())

    size_mb = archive.stat().st_size / 1_048_576
    print(f"  {archive}  ({len(picked)} files, {size_mb:.1f} MB)")
    return archive


def verify(archive: Path) -> None:
    """Open the archive and confirm the things a first run depends on are in it."""
    required = [
        f"{NAME}/launcher.py",
        f"{NAME}/Forgecast.bat",
        f"{NAME}/Forgecast.command",
        f"{NAME}/pyproject.toml",
        f"{NAME}/INSTALL.md",
        f"{NAME}/forgecast/api/main.py",
        f"{NAME}/forgecast/desktop/bootstrap.py",
        f"{NAME}/forgecast/web/base.html",
        # The chat and the surface it is drawn on. Shipping the routes without these
        # produces an app that starts, serves an unstyled page and has no way in —
        # which looks like a broken build rather than a missing file.
        f"{NAME}/forgecast/web/chat.html",
        f"{NAME}/forgecast/web/settings.html",
        f"{NAME}/forgecast/web/static/app.css",
        f"{NAME}/forgecast/web/static/chat.js",
        f"{NAME}/forgecast/agent/assistant.py",
        f"{NAME}/migrations/env.py",
    ]
    with zipfile.ZipFile(archive) as zf:
        members = set(zf.namelist())
        broken = zf.testzip()
    if broken:
        raise SystemExit(f"archive is corrupt at {broken}")

    missing = [name for name in required if name not in members]
    if missing:
        raise SystemExit("archive is incomplete:\n  " + "\n  ".join(missing))
    check(sorted(members))
    print(f"  verified: {len(members)} members, no secrets, all entry points present")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="dist", help="output directory (default dist/)")
    args = parser.parse_args()

    print("Packaging Forgecast")
    archive = build(ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out))
    verify(archive)
    print("\n  Send this file. The person who gets it unzips it and double-clicks")
    print(f"  {NAME}.bat (Windows) or {NAME}.command (macOS/Linux).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
