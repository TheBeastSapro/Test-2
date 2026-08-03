"""The one rule set: what may go into a backup repository, and what may never.

## Why this is shaped like `tools/package.py`

Because that script already learned the lesson this one would otherwise learn again. Its
docstring records it: the last leak of this class happened because two lists disagreed —
`.gitignore` named `*.db` but not `*.db-wal`, SQLite's write-ahead sidecars hold database
pages, and they were covered by neither the pattern anyone maintained nor the check meant
to catch it. So there is one rule set here, used twice: to decide what gets staged, and to
assert what ended up staged. `tests/test_cloud.py` walks a built snapshot through the same
functions the builder used, so a file kind nobody has thought of yet is caught because it
matches a rule rather than because somebody remembered to add a case.

## Why an allow-list *and* a deny-list

The deny-list alone fails in one direction: it can only refuse things that already exist.
The day a node starts writing `plate.avif`, or a vendor returns `.mkv`, a deny-list of
known media extensions lets it through — and the first time anyone notices is a push
rejected for a 400 MB file, by which point it is in the history.

So eligibility is decided by `ALLOW_SUFFIX` first: a file has to be one of a handful of
text kinds to be considered at all. A new artifact kind therefore defaults to *excluded*,
which is the direction where being wrong is recoverable. The deny-list then removes things
that are text but must not travel anyway — `.env`, the connector store, private keys.

## Why 25 MB and not 100

GitHub blocks at 100 MiB and warns from 50 MiB. A cap at either would make GitHub's
warning the mechanism that discovers a mistake, and a warning arriving from a third party
during a push is a bad way to learn what your own manifest does. 25 MB is far enough below
that no legitimate text artifact reaches it: the largest observed here is a 967 KB voice
catalogue, and that one is excluded for a different reason.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from .errors import FileTooLarge

# The only file kinds eligible for a backup at all. Text, diffable, and readable in a
# browser on github.com without Forgecast installed — which is the property that makes
# the backup outlive the app.
ALLOW_SUFFIX = frozenset({
    ".md", ".json", ".jsonl", ".srt", ".vtt", ".txt", ".csv",
})

# 25 MB. See the module docstring for why not 50 or 100.
MAX_FILE_BYTES = 25 * 1024 * 1024

# The refusal rule set. Every pattern is an fnmatch glob, matched case-insensitively
# against *each component* of a storage-relative path — so a pattern naming a directory
# excludes its whole subtree, and one naming a file excludes it at any depth. Identical
# semantics to `package.excluded`, deliberately: two rule sets with different matching
# behaviour is the same failure as two rule sets with different contents.
#
# Add to this list rather than adding a check somewhere else.
DENY = (
    # --- secrets ------------------------------------------------------------------
    # `.env` holds FORGECAST_ENCRYPTION_KEY, which is the key to every stored provider
    # credential. It lives outside `storage/` and the snapshot only walks `storage/`, so
    # this pattern is the second of two independent reasons it cannot reach a repository.
    # Two reasons, because one of them being wrong is survivable and both being wrong is
    # not.
    ".env",
    ".env.*",
    "*.env",
    "*.pem", "*.key", "*.crt", "*.cer", "*.der", "*.p12", "*.pfx",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.ppk",
    "credentials.json", ".credentials.json", "client_secret*.json", "token.json",
    "*service-account*.json", "*service_account*.json", "secrets.*", "*.secret",
    # The connector store. Small JSON, and excluded anyway: it holds service tokens
    # encrypted with a key that never leaves this machine, so committing it is a
    # liability with no benefit — the ciphertext cannot be decrypted after a restore.
    "connectors.json",
    # This feature's own state, holding the encrypted GitHub token. A backup that
    # contains the credential used to write it is a credential that leaks with it.
    "cloud.json",
    # --- one machine's state ------------------------------------------------------
    # `*.db` alone does not match `forgecast.db-wal`, and the sidecars hold database
    # pages, so shipping one ships rows. Rows travel as an export instead — see
    # `snapshot.export_rows`.
    "*.db", "*.db-*", "*.sqlite", "*.sqlite3", "*.sqlite-*",
    "*.log",
    # Regenerated from ElevenLabs on demand, ~1 MB, and different on every account. It is
    # a cache of somebody else's catalogue, not work.
    "voice_catalogue_all.json",
    # --- renders and everything that becomes one ----------------------------------
    # Redundant against ALLOW_SUFFIX and kept anyway: this list is also the readable
    # answer to "why is my video not in the backup", and a reader should not have to
    # infer it from the absence of `.mp4` in an allow-list.
    "*.mp4", "*.mov", "*.webm", "*.mkv", "*.avi", "*.m4v", "*.mpg", "*.mpeg",
    "*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac", "*.ogg", "*.opus", "*.weba",
    "*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp", "*.avif", "*.tif", "*.tiff",
    "*.zip", "*.tar", "*.gz", "*.bz2", "*.xz", "*.7z", "*.dmg", "*.exe",
    # ffmpeg concat lists and intermediate work directories.
    "work",
    # --- droppings ----------------------------------------------------------------
    ".git", "__pycache__", "*.py[cod]", "node_modules", ".ds_store",
)


def denied(relative: str | Path) -> str | None:
    """The `DENY` pattern that refuses this path, or None if nothing does.

    Every component is tested, not just the file name, so patterns naming directories
    refuse their whole subtree. Matching is case-insensitive on every platform — a check
    that lets `.ENV` through on Linux is not a check.
    """
    for part in PurePosixPath(str(relative).replace("\\", "/")).parts:
        lowered = part.lower()
        for pattern in DENY:
            if fnmatch.fnmatchcase(lowered, pattern):
                return pattern
    return None


def eligible(relative: str | Path) -> bool:
    """Whether a path's *name* qualifies for backup, ignoring its size.

    Name-only so it can be applied while walking a directory, before any stat. Size is a
    separate question because it has a separate answer — an oversized file is reported
    and skipped, an ineligible one is silently not work.
    """
    path = PurePosixPath(str(relative).replace("\\", "/"))
    if denied(path):
        return False
    return path.suffix.lower() in ALLOW_SUFFIX


def reason(relative: str | Path) -> str:
    """Why a path is not backed up, in words, or "" if it is.

    Exists because "where is my video" is the most predictable question this feature
    will ever be asked, and answering it from the same rule set that made the decision is
    the only way the answer stays true.
    """
    pattern = denied(relative)
    if pattern:
        return f"excluded by the rule {pattern}"
    suffix = PurePosixPath(str(relative)).suffix.lower()
    if suffix not in ALLOW_SUFFIX:
        return (
            f"{suffix or 'no extension'} is not a text kind Forgecast backs up — only "
            f"{', '.join(sorted(ALLOW_SUFFIX))}"
        )
    return ""


def classify(root: Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Split a directory tree into (included, [(excluded, why)]).

    Returned as two lists rather than logged, because the first thing the first-enable
    flow does is *show* this: how much syncs, how much does not, and the reason for each
    of the largest exclusions. An operator who is told what the manifest does before the
    first push never has to discover it from a missing file.

    Symlinks are not followed and are reported as excluded. A link inside `storage/`
    pointing at a home directory would otherwise be committed by its target's name, which
    is the traversal `api/routes_files.py:91` exists to prevent on the read side.
    """
    included: list[Path] = []
    excluded: list[tuple[Path, str]] = []
    root = Path(root)
    if not root.exists():
        return included, excluded

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            excluded.append((relative, "a symlink; only real files are backed up"))
            continue
        if path.is_dir():
            continue
        if not eligible(relative):
            excluded.append((relative, reason(relative)))
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            excluded.append((relative, f"could not be read: {exc}"))
            continue
        if size > MAX_FILE_BYTES:
            # The wording comes from `FileTooLarge` rather than being written again here,
            # so the table on the page and the message in the log cannot describe the same
            # exclusion differently. Not raised: dropping one oversized file and backing up
            # the other four thousand is better than refusing the snapshot.
            excluded.append((relative, FileTooLarge(relative.as_posix(), size).sentence))
            continue
        included.append(relative)

    return included, excluded
