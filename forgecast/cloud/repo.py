"""Git, over subprocess, with every failure turned into something sayable.

## Why subprocess and not a library

Because git is already a hard dependency of the thing being built — a GitHub backup is a
git repository — and adding a Python git implementation would mean two implementations of
the same protocol with different bugs, one of which the operator's `git --version` cannot
explain. The app also has no git dependency in `pyproject.toml` and this feature is not a
reason to add one: a missing `git` binary is reported as `GitMissing` and nothing else in
Forgecast is affected.

## Where the token goes, and everywhere it must not

The token is handed to git through a **credential helper that reads an environment
variable**, so what appears in the process arguments is the *name* of the variable and
never its value. Three places it is deliberately never written:

* **Not in the remote URL.** `https://<token>@github.com/...` is the obvious approach and
  it puts the credential in `.git/config`, in `git remote -v`, in the text of every error
  message git prints about that remote, and therefore in the log somebody pastes into a
  chat when asking why backup broke.
* **Not in `.git/config`** by any other route either. The staging repository lives inside
  the operator's own filesystem, but so does every other program on the machine.
* **Not in argv.** `ps` is readable by every process of the same user.

`GIT_TERMINAL_PROMPT=0` is set on every invocation. Without it, a git that cannot
authenticate blocks forever waiting for a username on a stdin nobody is attached to — the
backup does not fail, it hangs, and a hung backup is diagnosed as a hung application.

## Why the divergence case has its own branch

Two machines that both edited the same script produced two truths, and there is no rule
that picks the right one. A non-fast-forward push therefore goes to `machine/<name>` and
the operator is told both exist. The alternative — `--force`, or an automatic merge — is
the kind of thing that works for months and then silently overwrites the afternoon
somebody spent on the other laptop.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import (
    Diverged,
    GitMissing,
    Offline,
    PushRejectedTooLarge,
    RemoteFailed,
    RepositoryTooBig,
    TokenRejected,
)

log = logging.getLogger("forgecast.cloud.repo")

# The environment variable the credential helper reads. Its *name* is what ends up in the
# git config and in argv; the value never does.
TOKEN_ENV = "FORGECAST_GITHUB_TOKEN"

# `!f() { ... }; f` is git's shell-helper form. It answers only `get`, so git never asks it
# to store or erase a credential — there is nothing to store, the token comes from the
# environment on every invocation and is gone when the process exits.
CREDENTIAL_HELPER = (
    f'!f() {{ test "$1" = get && '
    f'echo username=x-access-token && '
    f'echo "password=${TOKEN_ENV}"; }}; f'
)

DEFAULT_BRANCH = "main"

# Long enough for a first clone of a text repository on a slow line, short enough that a
# stuck backup is reported rather than waited on. A hung git is worse than a failed one
# because the app looks broken rather than the network.
TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str


def git_available() -> bool:
    return shutil.which("git") is not None


def _environment(token: str = "") -> dict[str, str]:
    """A git environment that cannot prompt, cannot read the user's config, and cannot
    pick up an ambient credential helper.

    `GIT_CONFIG_GLOBAL=/dev/null` matters more than it looks: an operator's global config
    may set a credential helper, a signing key that blocks on a passphrase, or a
    `core.hooksPath` pointing at scripts. None of those should apply to a backup the app
    runs on its own, and inheriting them makes this feature behave differently on every
    machine.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    # Deterministic identity. The commit author is the app, not whoever happens to be
    # configured on the machine, so an install with no git identity does not fail its
    # first commit with "please tell me who you are".
    env.setdefault("GIT_AUTHOR_NAME", "Forgecast")
    env.setdefault("GIT_AUTHOR_EMAIL", "backup@forgecast.local")
    env.setdefault("GIT_COMMITTER_NAME", "Forgecast")
    env.setdefault("GIT_COMMITTER_EMAIL", "backup@forgecast.local")
    if token:
        env[TOKEN_ENV] = token
    else:
        env.pop(TOKEN_ENV, None)
    return env


def _classify(command: list[str], stderr: str, code: int) -> Exception:
    """Turn a git failure into the state it actually is.

    Matched on git's own message text, which is fragile and is the only signal there is:
    git returns 128 for a DNS failure, a rejected password and a missing repository alike.
    The fallback is `RemoteFailed`, which still carries a sentence — an unrecognised git
    error must not reach a request handler as a `CalledProcessError`.
    """
    text = stderr.lower()
    if "could not resolve host" in text or "failed to connect" in text \
            or "network is unreachable" in text or "timed out" in text \
            or "temporary failure in name resolution" in text:
        return Offline(stderr)
    if "authentication failed" in text or "invalid username or password" in text \
            or "403" in text or "401" in text or "permission denied" in text \
            or "repository not found" in text:
        # "Repository not found" is what GitHub returns for a private repository the
        # credential cannot see, which is indistinguishable from a wrong token and has the
        # same remedy — so it is reported as the remedy rather than as the ambiguity.
        return TokenRejected(stderr)
    if "gh001" in text or "file size limit" in text or ("exceeds" in text and "mb" in text):
        return PushRejectedTooLarge(stderr)
    if "data quota" in text or ("quota" in text and "repository" in text):
        return RepositoryTooBig(stderr)
    if "non-fast-forward" in text or "fetch first" in text \
            or "updates were rejected" in text:
        return Diverged(detail=stderr)
    return RemoteFailed(f"{' '.join(command)} exited {code}: {stderr.strip()[:600]}")


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    token: str = "",
    check: bool = True,
) -> subprocess.CompletedProcess:
    """One git invocation. Raises a `CloudError` subclass, never `CalledProcessError`."""
    if not git_available():
        raise GitMissing("git is not on PATH")

    command = ["git"]
    if token:
        # Set per-invocation with `-c` rather than written into `.git/config`, so the
        # helper configuration does not persist in a repository that outlives the process.
        command += ["-c", f"credential.helper={CREDENTIAL_HELPER}"]
    command += args

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=_environment(token),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise GitMissing(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise Offline(f"git timed out after {TIMEOUT_SECONDS}s") from exc

    if check and completed.returncode != 0:
        raise _classify(args, completed.stderr or completed.stdout, completed.returncode)
    return completed


# ---------------------------------------------------------------------------- the repo


class Repository:
    """A local git working tree that mirrors one remote.

    Kept *outside* `storage_dir`. A `.git` directory inside the tree the app writes
    artifacts into means `git checkout` and the render pipeline share a filesystem, and a
    checkout that rewrites a file mid-render is a corruption invisible from either side.
    So the staging tree is a copy — see `snapshot.build` — and this class owns the copy.
    """

    def __init__(self, path: Path, *, remote: str = "", token: str = "",
                 branch: str = DEFAULT_BRANCH) -> None:
        self.path = Path(path)
        self.remote = remote
        self.token = token
        self.branch = branch

    # -------------------------------------------------------------------- lifecycle

    def ensure(self) -> None:
        """Make `self.path` a repository on `self.branch` pointed at `self.remote`.

        Idempotent, and has to be: it runs before every push, on a directory that may be
        new, may be a valid repository, or may be a repository whose remote the operator
        has since changed.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        if not (self.path / ".git").exists():
            run(["init", "-b", self.branch], cwd=self.path)
        else:
            # `symbolic-ref` rather than `checkout -b`: the branch may already exist with
            # commits on it, and `checkout -b` fails on that rather than being a no-op.
            run(["symbolic-ref", "HEAD", f"refs/heads/{self.branch}"], cwd=self.path,
                check=False)
        if self.remote:
            existing = run(["remote"], cwd=self.path).stdout.split()
            action = ["set-url"] if "origin" in existing else ["add"]
            run(["remote", *action, "origin", self.remote], cwd=self.path)

    def commit(self, message: str) -> Commit | None:
        """Stage everything and commit. `None` when there was nothing to commit.

        `None` rather than an empty commit, because the caller has to be able to tell the
        operator "nothing changed" — and a chain of empty commits makes the history unable
        to answer when anything actually did.
        """
        run(["add", "-A", "."], cwd=self.path)
        status = run(["status", "--porcelain"], cwd=self.path).stdout.strip()
        if not status:
            return None
        run(["commit", "-m", message], cwd=self.path)
        sha = run(["rev-parse", "HEAD"], cwd=self.path).stdout.strip()
        return Commit(sha=sha, subject=message)

    def push(self, *, machine: str = "") -> str:
        """Push `self.branch` to origin. Raises `Diverged` rather than forcing.

        On a non-fast-forward the same commit is pushed to `machine/<name>` so the work is
        safe on the remote before the operator is told anything, and *then* `Diverged` is
        raised. Telling them first and pushing later would mean a message about two
        snapshots existing when only one does.
        """
        try:
            run(["push", "-u", "origin", self.branch], cwd=self.path, token=self.token)
        except Diverged:
            fallback = f"machine/{machine or 'unknown'}"
            run(["push", "origin", f"HEAD:refs/heads/{fallback}"],
                cwd=self.path, token=self.token)
            raise Diverged(branch=fallback) from None
        return self.branch

    def clone(self) -> None:
        """Fetch the remote into `self.path`, which must be empty or absent.

        Used by restore. A clone into a populated directory is refused by git itself, which
        is the correct behaviour and is left to git rather than reimplemented.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        run(["clone", "--depth", "1", self.remote, str(self.path)], token=self.token)

    # ------------------------------------------------------------------- inspection

    def head(self) -> Commit | None:
        result = run(["log", "-1", "--pretty=%H%x00%s"], cwd=self.path, check=False)
        if result.returncode != 0 or "\x00" not in result.stdout:
            return None
        sha, subject = result.stdout.strip().split("\x00", 1)
        return Commit(sha=sha, subject=subject)

    def size_bytes(self) -> int:
        """The repository's own on-disk size, for the "past 1 GB" warning.

        `count-objects -v` in kibibytes, because the number that matters is the size of
        the history rather than of the checkout — a repository whose working tree is 4 MB
        can have 3 GB of objects behind it, which is precisely the failure mode this whole
        design is arranged to avoid.
        """
        result = run(["count-objects", "-v"], cwd=self.path, check=False)
        total = 0
        for line in result.stdout.splitlines():
            if line.startswith(("size:", "size-pack:")):
                try:
                    total += int(line.split(":", 1)[1].strip()) * 1024
                except ValueError:
                    continue
        return total

    def check_size(self, *, limit_bytes: int = 1024 ** 3) -> None:
        """Raise `RepositoryTooBig` before GitHub has an opinion about it.

        1 GB is GitHub's own "ideally less than" figure. Reaching it in a text-only backup
        means the manifest is including something it should not, so this is a bug detector
        rather than a capacity limit.
        """
        if self.size_bytes() > limit_bytes:
            raise RepositoryTooBig(f"{self.size_bytes()} bytes of git objects")
