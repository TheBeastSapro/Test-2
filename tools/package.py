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

There is one exclusion rule set — `EXCLUDE` — and it is used twice: to filter what gets
collected, and to assert what ended up in the finished archive. It is one list on purpose.
The last leak of this class happened because two lists disagreed: `.gitignore` named `*.db`
but not `*.db-wal`, and SQLite's write-ahead sidecars, which contain database pages, were
covered by neither the pattern anyone was maintaining nor the check that was supposed to
catch it. A new secret-ish file is meant to be caught by a pattern, not by somebody
remembering to add a case.

Everything the launcher needs is included, including `pyproject.toml` — the first run
pip-installs the project from it, so an archive without it produces an app that cannot
start.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
NAME = "Forgecast"

# Everything a person needs to run the app, and nothing else.
INCLUDE_FILES = [
    "launcher.py",
    # The windowless Windows entry point, and the console one behind it. Both ship: the
    # .vbs is what to double-click, the .bat is what to run when you want to watch.
    "Forgecast.vbs",
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

# --------------------------------------------------------------- the exclusion rule set
#
# The single list of things that must never reach the archive. Every pattern is an fnmatch
# glob, matched case-insensitively against *each component* of a path — so a pattern that
# names a directory excludes everything beneath it, and a pattern that names a file
# excludes it at any depth. Used by `files_to_ship` to filter and by `check` to assert.
#
# Add to this list rather than adding a check somewhere. The patterns are deliberately
# wider than the files that exist today: `*.db-*` covers the `-wal`, `-shm` and `-journal`
# sidecars *and* whatever SQLite invents next, which is the failure that started this.
EXCLUDE = (
    # --- secrets and credentials --------------------------------------------------------
    # `.env` holds the credential-encryption key and the account password. `.env.*` covers
    # `.env.local`, `.env.production` and friends; it also catches `.env.example`, which
    # holds nothing secret, but a rule that lets `.env.<anything>` through is exactly how a
    # real one ships. The example is for people who cloned the repo, not for the zip.
    ".env",
    ".env.*",
    "*.env",
    # Private keys and certificates. Nothing in the shipped tree needs one: TLS trust
    # comes from `certifi` inside the virtualenv the launcher builds on the target
    # machine, and provider credentials are typed into Settings and encrypted into the
    # database. So every one of these names in a source tree is somebody's key.
    "*.pem",
    "*.key",
    "*.crt",
    "*.cer",
    "*.der",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.ppk",
    # OAuth and service-account drops, by the names the issuing consoles hand out.
    "credentials.json",
    ".credentials.json",
    "client_secret*.json",
    "token.json",
    "*service-account*.json",
    "*service_account*.json",
    "secrets.*",
    "*.secret",
    # --- one machine's state ------------------------------------------------------------
    # The database and every SQLite sidecar. `*.db` alone does not match `forgecast.db-wal`
    # — neither as a glob nor as a suffix, since `Path("x.db-wal").suffix` is `.db-wal` —
    # and the sidecars hold database pages, so shipping one ships rows.
    "*.db",
    "*.db-*",
    "*.sqlite",
    "*.sqlite3",
    "*.sqlite-*",
    "storage",  # renders and uploads: gigabytes of someone else's output
    # The cloud-backup staging tree: a git working copy of one install's scripts, briefs
    # and run records, sitting beside `storage/` rather than inside it. It is one
    # machine's work by definition, and it contains a `.git` directory whose `config` and
    # `FETCH_HEAD` name the operator's own private repository.
    ".forgecast-cloud",
    ".forgecast-restore",
    "attachments",  # chat attachments; they live in the app root because the agent is
    # sandboxed to it, so they sit next to the source while developing
    # The operator's own scripting documents. These are not this project's work — they are
    # bought under a licence covering one person — and `forgecast/scripting/library.py`
    # reads them from a folder in the home directory precisely so they are never here.
    # This is the second lock on that door, for the folder somebody copies in "just to
    # keep it with the app": a zip is a thing you send to other people, and shipping
    # somebody else's paid documents inside it is not a bug that can be apologised for
    # afterwards. The trailing glob catches `scripting-library-2` and
    # `scripting-library backup`, which is what the folder is called the day after it is
    # first duplicated. It does not touch `forgecast/scripting/`, which is this project's
    # own code and must ship.
    "scripting-library*",
    "runtime",  # the downloaded toolchain: Node, the Claude CLI, ffmpeg. Machine-specific
    # binaries, and the launcher fetches them on first run anyway.
    "*.log",
    # --- build and editor droppings -----------------------------------------------------
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    "*.py[cod]",
    "*.egg-info",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    "out",
    ".claude",
    ".idea",
    ".vscode",
    ".ds_store",
)


# Directories that ship as code and must therefore contain no prose. `EXCLUDE` is
# matched per path *component*, which cannot express "a markdown file under this
# folder" — and that gap shipped: an audit dropped `forgecast/scripting/16-hooks.md`
# into a tree and the packager collected it and passed its own check. `forgecast/` is
# an include tree with no extension allowlist, and `forgecast/scripting/` is exactly
# where somebody puts their documents when they decide to keep them "with the scripting
# code". The extension is the signal, not the folder name: this package is Python and
# its method is Python strings, so a document here is never this project's work.
CODE_ONLY_TREES = ("forgecast/scripting",)
PROSE_SUFFIXES = (".md", ".markdown", ".txt", ".pdf", ".docx", ".rtf", ".doc", ".epub")


def excluded(path: str | Path) -> str | None:
    """The pattern that excludes `path`, or `None` if nothing does.

    Every component is tested, not just the file name, so `EXCLUDE` entries naming
    directories exclude their whole subtree. Matching is case-insensitive on every
    platform — a check that lets `.ENV` through on Linux is not a check.
    """
    posix = PurePosixPath(str(path).replace("\\", "/"))
    lowered_path = str(posix).lower()
    for tree in CODE_ONLY_TREES:
        # `in` rather than `startswith`, because `check()` is handed archive members
        # prefixed with the distribution name (`Forgecast/forgecast/scripting/…`) while
        # `files_to_ship` works with repo-relative paths. A rule that only held for one
        # of the two would pass the build and fail the operator.
        if tree in lowered_path and posix.suffix.lower() in PROSE_SUFFIXES:
            return f"{tree}/*{posix.suffix.lower()}"

    for part in posix.parts:
        lowered = part.lower()
        for pattern in EXCLUDE:
            if fnmatch.fnmatchcase(lowered, pattern):
                return pattern
    return None


def files_to_ship() -> list[tuple[Path, str]]:
    """(absolute path, path inside the archive) for everything being shipped."""
    picked: list[tuple[Path, str]] = []

    # Not filtered through `excluded` on purpose: this list is hand-written, so an entry
    # that is forbidden is a mistake somebody should be told about. Dropping it quietly
    # here would build a silently different archive; `check` refuses to build instead.
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
            if excluded(relative):
                continue
            picked.append((path, f"{NAME}/{relative.as_posix()}"))

    return picked


# Files whose line endings are load-bearing. A shell script whose shebang ends in
# CRLF fails with `env: bash\r: No such file or directory` — /usr/bin/env looks for a
# program whose name has a carriage return in it. Git for Windows converts on checkout
# by default, so a zip built there ships exactly that unless it is normalised here.
LF_ONLY = (".command", ".sh")

# The other direction. `cmd.exe` mis-parses a multi-line block in a `.bat` with LF
# endings, and Windows Script Host is reading a Windows script — so these are normalised
# up rather than left to whatever the build machine happened to have. A zip built on
# Linux would otherwise ship both Windows entry points with the wrong endings, and the
# person who built it never sees the failure.
CRLF_ONLY = (".bat", ".vbs")


def read_for_shipping(path: Path, member: str) -> bytes:
    """The bytes to put in the archive, with line endings that will survive the trip."""
    data = path.read_bytes()
    if member.endswith(LF_ONLY):
        return data.replace(b"\r\n", b"\n")
    if member.endswith(CRLF_ONLY):
        # Normalised down first, so a file that is already CRLF does not become CR CR LF.
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return data


def check(members: list[str]) -> None:
    """Refuse to write an archive containing anything `EXCLUDE` names.

    Asserted rather than trusted, and asserted with the same rule set that did the
    filtering. The collection pass already drops these, but the cost of being wrong is
    shipping an encryption key or a database, and the check is a loop.
    """
    leaked = [
        f"{member}  (matched {pattern})"
        for member, pattern in ((member, excluded(member)) for member in members)
        if pattern
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
            # Fixed timestamp so the same source produces the same archive.
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            # Unix, always. `create_system` defaults to 0 (FAT) when the zip is built
            # on Windows, and every unpacker then IGNORES external_attr — so a zip
            # built on Windows arrives on macOS with Forgecast.command at mode 0644
            # and Finder refuses to open it. Stating the system is what makes the
            # permission bits mean anything.
            info.create_system = 3
            executable = member.endswith((".command", ".sh")) or member.endswith("launcher.py")
            info.external_attr = (0o755 if executable else 0o644) << 16
            zf.writestr(info, read_for_shipping(path, member))

    size_mb = archive.stat().st_size / 1_048_576
    print(f"  {archive}  ({len(picked)} files, {size_mb:.1f} MB)")
    return archive


def verify(archive: Path) -> None:
    """Open the archive and confirm the things a first run depends on are in it."""
    required = [
        f"{NAME}/launcher.py",
        f"{NAME}/Forgecast.vbs",
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
        # The built-in scripting method. It is the default for every channel and the
        # fallback for every selection that stops resolving, and `prompt_block` never
        # raises — so an archive missing it produces an app whose scripts are written to
        # nothing in particular, with no error anywhere to say why they got worse.
        f"{NAME}/forgecast/scripting/method.py",
        # The first-run installer. Without these the app starts and tells you to go
        # and install Node yourself, which is the thing they exist to avoid.
        f"{NAME}/forgecast/desktop/toolchain.py",
        f"{NAME}/forgecast/web/setup.html",
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

    # Assert the two things that only break on someone else's machine, where there is
    # nobody to notice and no way to guess the cause from the symptom.
    with zipfile.ZipFile(archive) as zf:
        for name in (f"{NAME}/Forgecast.command", f"{NAME}/launcher.py"):
            info = zf.getinfo(name)
            mode = (info.external_attr >> 16) & 0o777
            if info.create_system != 3 or not mode & 0o100:
                raise SystemExit(
                    f"{name} would arrive without its executable bit "
                    f"(create_system={info.create_system}, mode={mode:o})")
        launcher = zf.read(f"{NAME}/Forgecast.command")
        if b"\r\n" in launcher.split(b"\n", 1)[0] + b"\n":
            raise SystemExit("Forgecast.command has CRLF line endings; its shebang "
                             "would fail with `env: bash\\r: No such file or directory`")
        # And the Windows pair the other way. A `.vbs` with LF endings is read by Windows
        # Script Host as one very long line, and the error it reports names a line number
        # that does not exist in the file.
        for name in (f"{NAME}/Forgecast.bat", f"{NAME}/Forgecast.vbs"):
            body = zf.read(name)
            if b"\n" in body and b"\r\n" not in body:
                raise SystemExit(f"{name} has LF line endings; Windows needs CRLF")
    print(f"  verified: {len(members)} members, no secrets, all entry points present")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="dist", help="output directory (default dist/)")
    args = parser.parse_args()

    print("Packaging Forgecast")
    archive = build(ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out))
    verify(archive)
    print("\n  Send this file. The person who gets it unzips it and double-clicks")
    print(f"  {NAME}.vbs (Windows) or {NAME}.command (macOS/Linux).")
    print(f"  {NAME}.bat is the same thing with a console, for when something is wrong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
