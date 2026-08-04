"""Building the tree that gets committed, and reading one back.

## What a snapshot is

A directory that looks like this, and nothing cleverer:

    snapshot.json          who wrote it, and in what format version
    storage/...            the eligible files from storage_dir, at their own paths
    db/<table>.json        rows, with secret columns dropped

Plain text at readable paths on purpose. The value of this backup must not depend on
Forgecast existing: an operator who has lost the machine should be able to open
github.com, click into `storage/runs/12/script/`, and read the script. Any format that
needed this app to decode it would be a backup of a hostage.

## Why the database travels as rows and not as the file

`forgecast.db` is excluded by `manifest.DENY`, and would be even if it were small.
`package.py` records the reason: the `-wal` and `-shm` sidecars hold database pages, so
shipping one ships rows — and shipping the file itself makes the backup a binary blob that
grows a new copy of the whole database in git history on every commit. A JSON export per
table is text, diffs to the rows that actually changed, and is readable without SQLite.

## Why secret columns are dropped by name

`DENY_COLUMNS` is a list of column names, applied to every table. Named columns rather
than named tables, because the failure being prevented is a *new* table with a
`ciphertext` column added later by someone who never read this file — a table-level
allow-list would let it through, a column-level deny-list catches it. `tests/test_cloud.py`
asserts that nothing in an export decrypts, which is the check that survives a column being
renamed to something this list does not name.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..config import get_settings
from . import manifest
from .errors import RestoreTargetNotEmpty, SnapshotTooBig, SnapshotTooNew

log = logging.getLogger("forgecast.cloud.snapshot")

# Bumped when the layout changes in a way an older reader would misread. A restore
# compares this against the number in the snapshot and refuses to apply rows from a newer
# one — see `SnapshotTooNew` for why refusing part of the job beats dropping fields.
SCHEMA = 1

HEADER = "snapshot.json"
STORAGE_DIR = "storage"
DB_DIR = "db"

# Tables worth backing up: the work, and the record of the work. `users` is not here — the
# account is local to an install, and a restore that recreated accounts would be restoring
# password hashes across machines. `provider_keys` is not here for the same reason plus a
# stronger one: it is ciphertext that cannot be decrypted after a restore anyway.
TABLES = (
    "channels",
    "channel_memories",
    "runs",
    "nodes",
    "artifacts",
    "run_events",
)

# Column names never exported, from any table. See the module docstring.
DENY_COLUMNS = frozenset({
    "hashed_password",
    "ciphertext",
    "youtube_credentials",
    "youtube_refresh_token",
    "token",
    "secret",
    "password",
    "access_token",
    "refresh_token",
    "api_key",
})

# The first-enable guard. Not a GitHub limit — the point past which the manifest is
# provably including something it should not, and where finding out costs a dry run rather
# than an unpushable repository.
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_TOTAL_FILES = 20_000


@dataclass
class Plan:
    """What a snapshot would contain, computed without writing anything.

    Always produced before the first push, and cheap enough to produce before every push.
    An operator who is shown this once never has to discover the manifest from a missing
    file.
    """

    included: list[Path] = field(default_factory=list)
    excluded: list[tuple[Path, str]] = field(default_factory=list)
    total_bytes: int = 0
    root: Path | None = None

    @property
    def file_count(self) -> int:
        return len(self.included)

    def largest_exclusions(self, limit: int = 10) -> list[dict]:
        """The biggest things left out, by size, with the reason.

        Sorted by size because that is the order in which an operator recognises what is
        missing: the 400 MB render is the thing they were looking for, the 2 KB ffmpeg
        concat list is not.
        """
        rows = []
        for relative, why in self.excluded:
            path = (self.root / relative) if self.root else None
            try:
                size = path.stat().st_size if path and path.is_file() else 0
            except OSError:
                size = 0
            rows.append({"path": relative.as_posix(), "reason": why, "size_bytes": size})
        rows.sort(key=lambda row: row["size_bytes"], reverse=True)
        return rows[:limit]

    def summary(self) -> dict:
        return {
            "files": self.file_count,
            "total_bytes": self.total_bytes,
            "excluded": len(self.excluded),
            "largest_exclusions": self.largest_exclusions(),
        }

    def sentence(self) -> str:
        """What the operator is told before the first backup runs."""
        return (
            f"{self.file_count} files ({self.total_bytes / 1_048_576:.1f} MB) will be "
            f"backed up. {len(self.excluded)} files stay on this machine — renders, voice "
            f"takes, stills and the database itself. What goes up is everything that took "
            f"thinking; the renders are made again from it."
        )


def plan(storage_dir: Path | None = None) -> Plan:
    """What a snapshot of this install would contain. Writes nothing, sends nothing."""
    root = Path(storage_dir) if storage_dir else get_settings().storage_dir
    included, excluded = manifest.classify(root)
    total = 0
    for relative in included:
        try:
            total += (root / relative).stat().st_size
        except OSError:
            continue
    return Plan(included=included, excluded=excluded, total_bytes=total, root=root)


def export_rows(tables: tuple[str, ...] = TABLES) -> dict[str, list[dict]]:
    """Every backed-up table as JSON-safe rows, with secret columns dropped.

    Read-only, through a plain connection rather than the ORM: this has to work on a
    schema slightly ahead of or behind the models — which is exactly the situation a
    restore-across-versions is — and reflecting the table is what makes a new column
    export itself instead of being silently dropped.
    """
    from sqlalchemy import select

    from ..db import engine
    from ..models import Base

    out: dict[str, list[dict]] = {}
    metadata = Base.metadata
    with engine.connect() as connection:
        for name in tables:
            table = metadata.tables.get(name)
            if table is None:  # a table this version does not have
                continue
            keep = [c for c in table.columns if c.name.lower() not in DENY_COLUMNS]
            rows: list[dict] = []
            for record in connection.execute(select(*keep)):
                rows.append({
                    column.name: _jsonable(value)
                    for column, value in zip(keep, record, strict=True)
                })
            out[name] = rows
    return out


def _jsonable(value):
    """Datetimes to ISO, enums to their value, bytes refused.

    Bytes are turned into a marker rather than base64'd. A column holding bytes in this
    schema would be a binary blob, and quietly widening a text backup to carry binary is
    how the size discipline in `manifest` gets bypassed one column at a time.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes not exported>"
    if hasattr(value, "value") and type(value).__mro__[1].__name__ in ("str", "Enum"):
        return value.value
    return value


def build(
    into: Path,
    *,
    storage_dir: Path | None = None,
    rows: dict[str, list[dict]] | None = None,
    machine: str = "",
    enforce_limits: bool = True,
) -> Plan:
    """Stage a snapshot into `into`, returning what went in.

    `rows` is passed rather than fetched so a caller can snapshot a storage tree without a
    database — which is how the tests exercise the git round trip, and how a broken
    database still gets its files backed up rather than nothing at all.

    Files are copied rather than hard-linked or moved. A hard link into a git working tree
    means `git checkout` can rewrite a file the app still considers its own artifact, and
    that is a corruption whose cause is invisible from either side.
    """
    into = Path(into)
    computed = plan(storage_dir)
    if enforce_limits and (
        computed.total_bytes > MAX_TOTAL_BYTES or computed.file_count > MAX_TOTAL_FILES
    ):
        raise SnapshotTooBig(
            f"{computed.file_count} files, {computed.total_bytes} bytes "
            f"(caps: {MAX_TOTAL_FILES} files, {MAX_TOTAL_BYTES} bytes)"
        )

    root = computed.root or Path(".")
    target_storage = into / STORAGE_DIR
    # The staging tree is rebuilt rather than updated. An incremental copy leaves files
    # behind that were deleted locally, so a skill the operator removed would be restored
    # by a backup that was supposed to reflect the current state — and git's diff would
    # never show it, because nothing changed in the staging tree.
    if target_storage.exists():
        shutil.rmtree(target_storage)
    for relative in computed.included:
        destination = target_storage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)

    db_dir = into / DB_DIR
    if rows is not None:
        if db_dir.exists():
            shutil.rmtree(db_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        for name, records in rows.items():
            (db_dir / f"{name}.json").write_text(
                json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

    header = {
        "schema": SCHEMA,
        "app_version": __version__,
        "machine": machine,
        "files": computed.file_count,
        "total_bytes": computed.total_bytes,
        "excluded": len(computed.excluded),
        # No `created_at`. It used to be here, and it made every snapshot differ from the
        # last one whether or not anything had been backed up: two builds a second apart
        # produced two different manifests, so `Repository.commit` saw a change and made
        # a commit. That is precisely the failure its own docstring describes guarding
        # against — "a chain of empty commits makes the history unable to answer when
        # anything actually did" change — and the field defeating it was inside the
        # snapshot rather than in the commit logic.
        #
        # The time a backup was taken is not lost: it is the commit's own author date,
        # which is where a reader would look for it and which git already keeps. A field
        # duplicating it into the content is the content lying about having changed.
        # Recorded so a restore can say *why* something is missing without guessing, and
        # so a manifest change is visible in the diff of the next snapshot.
        "manifest": {
            "allow_suffix": sorted(manifest.ALLOW_SUFFIX),
            "max_file_bytes": manifest.MAX_FILE_BYTES,
        },
        "tables": sorted(rows) if rows else [],
    }
    into.mkdir(parents=True, exist_ok=True)
    (into / HEADER).write_text(
        json.dumps(header, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Asserted with the same rule set that did the filtering, for the reason
    # `package.check` gives: the collection pass already drops these, but the cost of
    # being wrong is committing a credential, and the check is a loop.
    audit(into)
    return computed


def audit(staged: Path) -> None:
    """Refuse a staging tree containing anything the manifest forbids.

    The second use of the one rule set. Runs over the finished tree, not over the list of
    paths the builder decided to copy, so a file that arrived by some other route — a
    stray copy, a leftover from an older layout, something a test wrote — is caught too.
    """
    staged = Path(staged)
    storage = staged / STORAGE_DIR
    offenders = []
    if storage.exists():
        for path in storage.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(storage)
            if not manifest.eligible(relative):
                offenders.append(f"{relative.as_posix()} ({manifest.reason(relative)})")
            elif path.stat().st_size > manifest.MAX_FILE_BYTES:
                offenders.append(f"{relative.as_posix()} (over the per-file cap)")
    if offenders:
        raise SnapshotTooBig(
            "refusing to commit: the snapshot would contain\n  "
            + "\n  ".join(offenders[:10])
        )


# ------------------------------------------------------------------------- reading one


@dataclass
class Restored:
    """The result of a restore: what was written, and what was deliberately not."""

    header: dict
    files: list[str]
    tables: dict[str, int]
    rows_applied: bool
    note: str = ""

    @property
    def schema(self) -> int:
        return int(self.header.get("schema") or 0)


def read_header(clone: Path) -> dict:
    path = Path(clone) / HEADER
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def restore(clone: Path, into: Path) -> Restored:
    """Materialise a cloned snapshot into a storage directory.

    Refuses a populated target. The most likely reason someone restores onto a working
    install is panic, and panic plus overwrite is how the copy they were trying to recover
    replaces the work they still had. An empty directory, or a new one — and then they can
    compare.

    The row export is copied across as readable JSON and counted, but not inserted into
    any database. `docs/CLOUD.md` states why that boundary is where it is: re-importing
    rows into a database that may already hold work is a merge with ID remapping, not a
    copy, and the transport has to be right before it is worth building.
    """
    clone = Path(clone)
    into = Path(into)
    if into.exists() and any(into.iterdir()):
        raise RestoreTargetNotEmpty(str(into))

    header = read_header(clone)
    schema = int(header.get("schema") or 0)
    too_new = schema > SCHEMA

    written: list[str] = []
    source = clone / STORAGE_DIR
    if source.exists():
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            # Checked again on the way in. A repository is editable by anyone with push
            # access, including a future version of this app with a wider manifest, so a
            # restore that trusted the snapshot's own claim about its contents would write
            # whatever was committed.
            if not manifest.eligible(relative):
                continue
            destination = into / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            written.append(relative.as_posix())

    tables: dict[str, int] = {}
    db_source = clone / DB_DIR
    if db_source.exists():
        db_target = into / "restored-rows"
        db_target.mkdir(parents=True, exist_ok=True)
        for path in sorted(db_source.glob("*.json")):
            shutil.copy2(path, db_target / path.name)
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            tables[path.stem] = len(records) if isinstance(records, list) else 0

    result = Restored(
        header=header, files=written, tables=tables, rows_applied=False,
        note=(
            f"Restored {len(written)} files. The database export is in "
            f"restored-rows/ as readable JSON and has not been loaded into this "
            f"install's database."
        ),
    )
    if too_new:
        # Raised after the files are on disk, not instead of writing them. A newer
        # snapshot's text is still readable text; it is only the rows whose shape this
        # version might misread, so refusing the whole restore would withhold the part
        # that works.
        error = SnapshotTooNew(schema, SCHEMA)
        result.note = error.sentence
        log.warning("%s", error.detail)
    return result
