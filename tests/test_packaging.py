"""What `tools/package.py` is allowed to put in the zip, and everything it is not.

The zip is the product. It is built from a working tree that also contains the encryption
key for stored provider credentials, a database of this machine's runs, a downloaded
toolchain and whatever the last chat attached — so the interesting property of the
packager is not what it includes but what it refuses to.

That property has already failed once in the neighbouring rule set: `.gitignore` listed
`*.db` and `*.db-journal` but not `*.db-shm` or `*.db-wal`, SQLite writes those two beside
the database and they hold database pages, and two of them were committed. The lesson is
that a hand-maintained list of cases catches yesterday's file. So the assertions here are
written against `package.EXCLUDE` itself:

* `test_no_archive_member_is_excluded` walks the finished archive and runs every member
  through the same rule set the collector used. A file nobody has thought of yet is caught
  because it matches a pattern, not because somebody added a case for it here.
* `test_every_pattern_is_enforced` turns each pattern into a concrete file name and
  requires the check to reject it, so a pattern cannot rot into decoration.
* `test_decoys_are_never_packaged` writes real files into the trees that get shipped and
  builds a real archive, because a rule set that is only tested against strings is a rule
  set that has never met the filesystem.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "tools" / "package.py"


def load_package():
    """Import `tools/package.py` by path.

    `tools/` is deliberately not a package — it is a folder of scripts — so there is
    nothing to import normally. Loading by path keeps that true rather than adding an
    `__init__.py` to make a test tidier.
    """
    spec = importlib.util.spec_from_file_location("forgecast_package", PACKAGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package = load_package()


@pytest.fixture(scope="module")
def archive(tmp_path_factory) -> Path:
    """One real build of the real tree, into a temporary directory."""
    return package.build(tmp_path_factory.mktemp("dist"))


@pytest.fixture(scope="module")
def members(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as zf:
        return sorted(zf.namelist())


# ------------------------------------------------------------- the archive as it is built


def test_no_archive_member_is_excluded(members):
    """The assertion that does not need updating when a new kind of secret shows up.

    Every member goes through `package.excluded`, so anything matching any pattern fails
    this test — including a file added to the tree years from now by someone who has never
    read this file.
    """
    leaked = [(name, package.excluded(name)) for name in members]
    leaked = [f"{name} matched {pattern}" for name, pattern in leaked if pattern]
    assert not leaked, "excluded paths reached the archive:\n  " + "\n  ".join(leaked)


def test_the_archive_still_contains_what_a_first_run_needs(archive):
    """The other half: an exclusion rule set that excludes everything also passes.

    `verify` is the packager's own completeness check — entry points, templates, the
    executable bits — and it re-runs the exclusion check over the written file.
    """
    package.verify(archive)


def test_the_named_forbidden_paths_are_absent(members):
    """The four standing requirements, spelled out, so they cannot be argued away."""
    joined = "\n".join(members)
    for forbidden in (".env", ".venv", "forgecast.db", "storage/"):
        assert forbidden not in joined, f"{forbidden} is in the archive"


# ---------------------------------------------------------------------- the rule set itself

# Names that must never be shipped, one per class of leak. Each is checked against
# `excluded` both on its own and nested inside a shipped tree, because the last two
# regressions of this kind were a suffix that did not match and a directory that was only
# filtered at the top level.
MUST_BE_EXCLUDED = [
    # secrets
    ".env",
    ".env.local",
    ".env.production",
    "secret.pem",
    "server.key",
    "ca.crt",
    "client.pfx",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "credentials.json",
    "client_secret_1234.json",
    "token.json",
    "my-service-account-key.json",
    # the database and every SQLite sidecar. `-shm` and `-wal` are the pair that got
    # committed; `-journal` is the rollback journal; the glob covers the next one too.
    "forgecast.db",
    "forgecast.db-shm",
    "forgecast.db-wal",
    "forgecast.db-journal",
    "forgecast.db-somethingnew",
    "app.sqlite3",
    # one machine's state
    "storage/renders/1/final.mp4",
    "attachments/blob.png",
    "runtime/node/bin/node",
    "debug.log",
    "uvicorn.log",
    # build and dev droppings
    ".git/config",
    ".github/workflows/ci.yml",
    ".venv/bin/python",
    "__pycache__/thing.cpython-311.pyc",
    "thing.pyc",
    "forgecast.egg-info/PKG-INFO",
    "node_modules/left-pad/index.js",
    ".pytest_cache/CACHEDIR.TAG",
    ".ruff_cache/content",
    "dist/Forgecast-0.1.0.zip",
]


@pytest.mark.parametrize("name", MUST_BE_EXCLUDED)
def test_excluded_at_the_root_and_at_depth(name):
    assert package.excluded(name), f"{name} is not excluded"
    assert package.excluded(f"Forgecast/forgecast/web/{name}"), f"{name} is not excluded when nested"


@pytest.mark.parametrize("name", MUST_BE_EXCLUDED)
def test_check_refuses_to_build_an_archive_containing_it(name):
    """`check` is the last gate before bytes are written; it has to fail, loudly."""
    with pytest.raises(SystemExit) as raised:
        package.check([f"Forgecast/{name}"])
    assert name.split("/")[0] in str(raised.value)


def sample_name(pattern: str) -> str:
    """A concrete file name that the pattern is meant to match."""
    return pattern.replace("[cod]", "c").replace("*", "decoy")


@pytest.mark.parametrize("pattern", package.EXCLUDE)
def test_every_pattern_is_enforced(pattern):
    """No pattern in the list is decoration.

    Each one is materialised into a name and has to be caught, so a typo'd pattern — the
    thing that made `*.db` miss `forecast.db-wal` — fails here instead of in a release.
    """
    name = sample_name(pattern)
    assert package.excluded(name) is not None, f"{pattern!r} matches nothing, via {name!r}"
    with pytest.raises(SystemExit):
        package.check([f"Forgecast/{name}"])


def test_the_things_that_must_ship_are_not_excluded():
    """The rule set has to be narrow enough to still produce an app.

    A pattern like `*.py[cod]` written as `*.py*` would silently ship nothing.
    """
    for name in (
        "launcher.py",
        "pyproject.toml",
        "alembic.ini",
        "INSTALL.md",
        "forgecast/api/main.py",
        "forgecast/web/base.html",
        "forgecast/web/static/app.css",
        "forgecast/web/static/chat.js",
        "forgecast/motion/data/land_110m.bin",
        "migrations/env.py",
        "remotion/package.json",
        "remotion/src/Root.tsx",
        "Forgecast.command",
    ):
        assert package.excluded(name) is None, f"{name} would be excluded"


def test_matching_ignores_case_and_separator():
    """`.ENV` on a case-insensitive filesystem is still `.env`."""
    assert package.excluded(".ENV")
    assert package.excluded("Forgecast/Storage/out.mp4")
    assert package.excluded("forgecast\\__pycache__\\x.pyc")


# ------------------------------------------------------------------------ the decoy proof

# Written into the trees that get shipped, then built for real. Every one of these would
# have been packaged by a rule set with a hole in it, and `forgecast/secret.pem`,
# `forgecast/forgecast.db-wal` and `forgecast/id_rsa` were packaged by the one this
# replaced. Kept out of `forgecast/agent/` and `forgecast/research/` so a test run never
# writes into a directory somebody else may be editing.
DECOYS = {
    "forgecast/forgecast.db-wal": b"decoy sqlite write-ahead log\n",
    "forgecast/forgecast.db-shm": b"decoy sqlite shared memory\n",
    "forgecast/forgecast.db-journal": b"decoy sqlite rollback journal\n",
    "forgecast/secret.pem": b"-----BEGIN PRIVATE KEY-----\ndecoy\n",
    "forgecast/id_rsa": b"decoy ssh key\n",
    "forgecast/service.key": b"decoy tls key\n",
    "forgecast/credentials.json": b'{"decoy": true}\n',
    "forgecast/debug.log": b"decoy log line\n",
    "forgecast/.env": b"DECOY_SECRET=1\n",
    "forgecast/.env.local": b"DECOY_SECRET=2\n",
    "forgecast/__pycache__/decoy_leak.cpython-311.pyc": b"decoy bytecode\n",
    "forgecast/storage/decoy-render.mp4": b"decoy render\n",
    "forgecast/attachments/decoy-attachment.png": b"decoy attachment\n",
    "remotion/out/decoy-render.mp4": b"decoy render\n",
}


@pytest.fixture
def decoys() -> list[Path]:
    """Create the decoys, hand back the ones actually created, then remove exactly those.

    A decoy is skipped if something is already there — the point is to prove the packager
    excludes these paths, not to overwrite a real file that happens to share a name.
    """
    created: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for relative, body in DECOYS.items():
            path = ROOT / relative
            if path.exists():
                continue
            if not path.parent.exists():
                path.parent.mkdir(parents=True)
                created_dirs.append(path.parent)
            path.write_bytes(body)
            created.append(path)
        assert created, "no decoys could be created; nothing was proved"
        yield created
    finally:
        for path in created:
            path.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()


def test_decoys_are_never_packaged(decoys, tmp_path):
    """Build with the decoys in place. They must be absent, and the build must succeed."""
    built = package.build(tmp_path / "dist")
    package.verify(built)
    with zipfile.ZipFile(built) as zf:
        names = set(zf.namelist())

    for path in decoys:
        member = f"{package.NAME}/{path.relative_to(ROOT).as_posix()}"
        assert member not in names, f"{member} was packaged"
    # And the archive is still the archive: nothing anywhere in it is excluded, and the
    # app it contains still starts.
    assert not [name for name in names if package.excluded(name)]


def test_the_script_runs_end_to_end(tmp_path):
    """The CLI path, not just the functions, since the CLI is what a release runs."""
    done = subprocess.run(
        [sys.executable, str(PACKAGE_PATH), "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(ROOT), check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    built = list(tmp_path.glob("*.zip"))
    assert len(built) == 1
    with zipfile.ZipFile(built[0]) as zf:
        assert not [name for name in zf.namelist() if package.excluded(name)]


# ------------------------------------------------------- the same class of leak elsewhere


def test_dockerignore_covers_the_same_patterns():
    """The image build context is the second way this tree ships.

    Docker copies from the working tree, so a `.dockerignore` missing what
    `package.EXCLUDE` has is the same leak with a different delivery mechanism.
    """
    lines = {
        line.strip().removeprefix("**/").rstrip("/")
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for required in (".env", "*.db", "*.db-shm", "*.db-wal", "*.db-journal", "storage",
                     "attachments", "runtime", "node_modules", "*.log", "*.pem", "*.key",
                     ".git", ".venv", "__pycache__"):
        assert required in lines, f".dockerignore does not exclude {required}"


def test_gitignore_covers_the_patterns_that_already_leaked_once():
    """The fourth way this tree ships, and the one that has already failed.

    `*.db` was there and `*.db-shm`/`*.db-wal` were not, so two files holding database
    pages were committed. This is a regression test for that fix and for the rest of the
    class it belongs to.
    """
    lines = {
        line.strip().rstrip("/")
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for required in (".env", ".env.*", "*.db", "*.db-shm", "*.db-wal", "*.db-journal",
                     "storage", "attachments", "runtime", "node_modules", "*.log",
                     "*.pem", "*.key", "*.crt", "id_rsa*", ".venv", "__pycache__"):
        assert required in lines, f".gitignore does not exclude {required}"


def test_manifest_prunes_the_same_patterns_from_an_sdist():
    """`pip sdist`/`build` is the third. MANIFEST.in is the only lever for it."""
    text = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    for required in ("*.db", "*.db-shm", "*.db-wal", "*.db-journal", "*.pem", "*.key",
                     "*.log", ".env"):
        assert f"global-exclude {required}" in text, f"MANIFEST.in does not exclude {required}"
    for pruned in ("storage", "attachments", "runtime", "dist"):
        assert f"prune {pruned}" in text, f"MANIFEST.in does not prune {pruned}"


def test_no_competitor_is_named_anywhere_that_ships():
    """The operator asked for these references gone, and a zip is a thing you send.

    They were design rationale rather than copied text — "X scopes its shell to a
    channel, this is that" — but rationale naming a competitor still ships in every
    archive, and `ARCHITECTURE.md` is in `INCLUDE_FILES`. The reasoning survived the
    edit; the attribution did not.

    Asserted over the built file list rather than the working tree, so a document added
    later under a name nobody thought to check is still covered.
    """
    from tools.package import files_to_ship

    named = ("rookcast", "faceless os", "facelessos")
    offenders: list[str] = []
    for path, member in files_to_ship():
        if path.suffix.lower() not in (".py", ".md", ".html", ".css", ".js", ".txt"):
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:                                               # pragma: no cover
            continue
        for word in named:
            if word in body:
                offenders.append(f"{member}: {word!r}")

    assert not offenders, "a competitor is named in the archive:\n  " + "\n  ".join(offenders)
