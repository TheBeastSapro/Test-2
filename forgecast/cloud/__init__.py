"""Cloud backup: the operator's work, mirrored into a private GitHub repository.

Read `docs/CLOUD.md` first — it is the design, including the part that matters most, which
is what deliberately does *not* sync. The short version: text goes to git, renders stay on
the machine, because GitHub blocks files over 100 MiB and a repository that accumulates
video never gets smaller again.

## Off by default, and what that has to mean

`Settings.cloud_sync` is `False` and `storage/cloud.json` does not exist on a fresh
install, so `enabled()` is false and every entry point below returns or raises without
touching a socket. Nothing else in the app imports this package: there is no call site in
the pipeline, the API or the agent that behaves differently because this module exists.
That is the strongest available form of "the local path is untouched when it is off" —
not a flag checked in twenty places, but nothing to check.

## What is built here and what is not

Built: the manifest, the snapshot builder and its audit, the config store with the token
encrypted at rest, the git transport with every failure classified, the restore path, and
the device flow. All of it tested against a real local bare repository, so the round trip
is exercised without a GitHub account.

Not built yet, deliberately, and each with its reason in `docs/CLOUD.md`: loading the row
export back into a live database, release assets as a home for `final.mp4`, the settings
page, and a schedule. The transport had to be right first — a restore that cannot fetch
the files is not improved by having somewhere to put them.
"""

from __future__ import annotations

import logging
import socket
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings
from . import config, device, manifest, repo, snapshot
from .config import CloudConfig, load
from .errors import CloudError, Diverged, NotAuthorised, NothingToDo
from .snapshot import Plan, Restored

log = logging.getLogger("forgecast.cloud")

__all__ = [
    "CloudConfig",
    "CloudError",
    "Plan",
    "Restored",
    "backup",
    "config",
    "device",
    "dry_run",
    "enabled",
    "machine_name",
    "manifest",
    "repo",
    "restore",
    "snapshot",
    "staging_dir",
    "status",
]


def enabled() -> bool:
    """Whether this install should talk to GitHub at all.

    The one question every entry point asks first. False on a fresh install, false when the
    operator has turned it off, and false when it is on but unauthorised — all three mean
    "do nothing", and the difference between them is a sentence rather than a behaviour.
    """
    try:
        return load().active()
    except Exception:  # pragma: no cover - a broken config must not break a caller
        log.exception("could not read cloud config — treating backup as off")
        return False


def machine_name() -> str:
    """A name for this install, for the branch a divergence goes to.

    The hostname, not a random id. The operator has to recognise it in "another machine
    backed up since this one did", and `machine/7f3a91` names nothing they can act on.
    """
    stored = load().machine
    if stored:
        return stored
    try:
        host = socket.gethostname().split(".")[0]
    except OSError:  # pragma: no cover
        host = ""
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in host) or "this-machine"


def staging_dir() -> Path:
    """Where the git working tree lives — beside `storage/`, never inside it.

    A `.git` directory inside the tree the render pipeline writes into means a checkout can
    rewrite a file mid-render, and that is a corruption invisible from both sides. So the
    snapshot is a copy and this is where the copy lives.
    """
    return get_settings().storage_dir.parent / ".forgecast-cloud"


def status() -> dict:
    """Everything a page or a log needs, with no network call and no credential in it."""
    current = load()
    payload = current.public_dict()
    payload["git_available"] = repo.git_available()
    payload["staging_dir"] = str(staging_dir())
    return payload


def dry_run(storage_dir: Path | None = None) -> Plan:
    """What a backup would contain. Always run before the first one.

    Separate from `backup` and callable when the feature is off, because the answer to
    "what would this do" must not require enabling the thing being asked about.
    """
    return snapshot.plan(storage_dir)


def backup(*, message: str = "", include_rows: bool = True,
           enforce_limits: bool = True) -> dict:
    """Stage, commit and push one snapshot. Returns what happened.

    Raises `NothingToDo` when nothing changed, `Diverged` when another machine got there
    first, and one of the other `CloudError` states for everything else — each carrying the
    sentence the operator reads. Never raises a bare git error.
    """
    current = load()
    if not current.active():
        raise NotAuthorised(
            "backup is not enabled, authorised, or has no remote"
            if not current.enabled else "no remote or no token"
        )

    rows = None
    if include_rows:
        try:
            rows = snapshot.export_rows()
        except Exception:
            # A database that cannot be read must not stop the files being backed up. The
            # scripts are the work; the row export is the index to it, and half a backup
            # is worth far more than none.
            log.exception("could not export database rows — backing up files only")
            rows = None

    staging = staging_dir()
    machine = machine_name()
    plan = snapshot.build(
        staging, rows=rows, machine=machine, enforce_limits=enforce_limits
    )

    repository = repo.Repository(
        staging, remote=current.remote, token=current.token,
    )
    repository.ensure()
    subject = message or (
        f"snapshot: {plan.file_count} files, "
        f"{plan.total_bytes / 1_048_576:.1f} MB, from {machine}"
    )
    commit = repository.commit(subject)
    if commit is None:
        raise NothingToDo(f"no change since {current.last_commit or 'the last snapshot'}")

    # Checked after committing and before pushing: the size that matters is the history's,
    # which only exists once the commit does, and the operator should hear about a
    # repository heading for GitHub's warning before the push rather than after.
    try:
        repository.check_size()
    except CloudError as exc:
        log.warning("%s", exc.sentence)

    try:
        branch = repository.push(machine=machine)
    except Diverged:
        # The commit is on the remote, on its own branch. The config is not advanced —
        # `last_commit` must keep naming the last commit that reached the shared branch, or
        # the next run will believe it is up to date with something it is not.
        raise

    current.last_commit = commit.sha
    current.last_pushed_at = datetime.now(UTC).isoformat(timespec="seconds")
    current.machine = machine
    current.save()
    return {
        "commit": commit.sha,
        "branch": branch,
        "files": plan.file_count,
        "total_bytes": plan.total_bytes,
        "excluded": len(plan.excluded),
        "sentence": (
            f"Backed up {plan.file_count} files "
            f"({plan.total_bytes / 1_048_576:.1f} MB) to "
            f"{current.owner}/{current.repository}." if current.repository else
            f"Backed up {plan.file_count} files."
        ),
    }


def restore(into: Path, *, remote: str = "", token: str = "",
            work_dir: Path | None = None) -> Restored:
    """Clone the backup and write it into `into`, which must be empty.

    This is the feature. Everything above it exists so that this works, and it is exercised
    on every test run against a real git remote — because a backup nobody has restored is a
    folder of hope.

    `remote` and `token` default to the stored ones but are arguments, so a restore can be
    performed on a machine that has never been enabled: the case that matters most is the
    new laptop, where there is no config to read.
    """
    current = load()
    source = remote or current.remote
    if not source:
        raise NotAuthorised("no remote to restore from")

    clone_at = Path(work_dir) if work_dir else staging_dir().with_name(
        ".forgecast-restore"
    )
    if clone_at.exists():
        # Removed rather than reused. A stale clone from a previous attempt would restore
        # whatever it happened to contain, which is the wrong snapshot presented as the
        # current one.
        import shutil

        shutil.rmtree(clone_at)

    repository = repo.Repository(clone_at, remote=source, token=token or current.token)
    repository.clone()
    return snapshot.restore(clone_at, into)
