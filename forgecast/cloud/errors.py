"""Every way cloud backup can fail, and the sentence the operator is shown for it.

## Why the sentence lives on the exception

A backup that fails silently is worse than no backup, and a backup that fails with
`CalledProcessError: git returned 128` is the same thing with extra steps. The operator
has to learn three things from a failure — what happened, whether their work is safe, and
what to do next — and none of those are in a git exit code.

So the state is the type and the sentence is data on it, which means the sentence cannot
be forgotten at the call site and cannot drift between the page and the log. It also
makes exhaustiveness testable: `tests/test_cloud.py` asserts every subclass carries a
non-empty sentence that mentions what is safe, so a new failure state added without one
fails the suite rather than reaching an operator as a traceback.

## Why "your work is safe" is in almost every sentence

Because the question a person actually has when a backup fails is not "why" — it is
"did I just lose the afternoon". Answering that first is what makes the rest of the
message readable.
"""

from __future__ import annotations


class CloudError(RuntimeError):
    """A cloud-backup failure with something useful to say.

    `sentence` is what the operator reads. `detail` is what a maintainer needs and is
    kept off the sentence deliberately: a git stderr dump appended to a plain-English
    message makes the plain-English part look like noise, so callers show one or the
    other depending on who is looking.
    """

    sentence = "Cloud backup failed."

    def __init__(self, detail: str = "", *, sentence: str = "") -> None:
        self.detail = detail
        if sentence:
            self.sentence = sentence
        super().__init__(sentence or self.sentence)

    def as_dict(self) -> dict:
        return {"state": type(self).__name__, "sentence": self.sentence,
                "detail": self.detail}


# ------------------------------------------------------------------ not set up yet


class NotConfigured(CloudError):
    """No GitHub OAuth client ID compiled in or configured.

    Distinct from `NotAuthorised` because the operator can act on that one and cannot act
    on this one. Showing a device-code screen that can never issue a code is the failure
    this separation prevents.
    """

    sentence = (
        "This build has no GitHub app configured, so backup cannot authorise. "
        "Set FORGECAST_GITHUB_CLIENT_ID, or use a fine-grained token for the "
        "repository instead."
    )


class NotAuthorised(CloudError):
    sentence = (
        "Backup is not authorised. Open github.com/login/device and enter the code "
        "shown to connect it."
    )


class GitMissing(CloudError):
    sentence = (
        "Backup needs git and this machine does not have it. Everything else in "
        "Forgecast works without it."
    )


# --------------------------------------------------------------------- the device flow


class AuthorisationPending(CloudError):
    """Not an error to show — the caller polls on it.

    It is an exception rather than a return value because every other outcome of the
    poll is one, and a mixed contract where one case comes back as data is how a caller
    ends up treating "still waiting" as "authorised".
    """

    sentence = "Waiting for you to approve the code on GitHub."


class CodeExpired(CloudError):
    sentence = "That code expired after 15 minutes. Here is a new one."


class Declined(CloudError):
    sentence = "You declined the authorisation on GitHub. Backup stays off; nothing changed."


class TokenRejected(CloudError):
    sentence = (
        "GitHub rejected the stored authorisation — it was revoked or has expired. "
        "Re-authorise and backup resumes where it stopped; nothing on this machine "
        "was touched."
    )


# ------------------------------------------------------------------------- the network


class Offline(CloudError):
    sentence = (
        "Could not reach GitHub. Nothing was lost — the snapshot is on disk and will "
        "go up on the next attempt."
    )


# ------------------------------------------------------------------------- the payload


class FileTooLarge(CloudError):
    """One file exceeded the manifest cap, so it was left out.

    Not fatal on purpose. Dropping one oversized file and backing up the other four
    thousand is better than refusing the snapshot, and the sentence names the file so the
    decision is reviewable.
    """

    sentence = "A file was too large to back up and was left out of this snapshot."

    def __init__(self, name: str, size_bytes: int) -> None:
        self.name = name
        self.size_bytes = size_bytes
        super().__init__(
            f"{name} is {size_bytes} bytes",
            sentence=(
                f"{name} is {size_bytes / 1_048_576:.1f} MB, over the 25 MB cap for a "
                f"backed-up file, so it was left out of this snapshot and everything "
                f"else went up. Renders are never included; if this is not a render, it "
                f"belongs on the exclude list."
            ),
        )


class PushRejectedTooLarge(CloudError):
    sentence = (
        "GitHub refused the push because a file is over its 100 MB limit. The snapshot "
        "is unchanged on disk and nothing was lost — this is a bug in what Forgecast "
        "decided to include, not in your work."
    )


class RepositoryTooBig(CloudError):
    sentence = (
        "The backup repository is past 1 GB, which GitHub warns about. Something large "
        "is being included that should not be — check the size report before the "
        "repository becomes unpushable."
    )


class SnapshotTooBig(CloudError):
    """The first-enable guard.

    Not a GitHub limit — the threshold where the manifest is provably including
    something it should not, and where finding out now is far cheaper than finding out
    on the third push.
    """

    sentence = (
        "This would back up more than expected, which means something large is being "
        "included that should not be. Nothing was sent. Check the size report."
    )


# ---------------------------------------------------------------------- two machines


class Diverged(CloudError):
    """A push that is not a fast-forward.

    Never resolved automatically. Two machines that edited the same script produced two
    truths and git cannot choose between them; a `--force` here would be the last thing
    that ever went wrong in this feature, exactly once.
    """

    sentence = (
        "Another machine backed up since this one last did. Both snapshots are kept — "
        "this one went to its own branch — because guessing which is newer is how a "
        "merge loses an afternoon."
    )

    def __init__(self, branch: str = "", detail: str = "") -> None:
        self.branch = branch
        super().__init__(
            detail,
            sentence=(
                f"Another machine backed up since this one last did. Both snapshots are "
                f"kept — this one is on the branch {branch} — because guessing which is "
                f"newer is how a merge loses an afternoon."
            ) if branch else Diverged.sentence,
        )


# -------------------------------------------------------------------------- restoring


class SnapshotTooNew(CloudError):
    """The backup was written by a later version of Forgecast than this one.

    Files still restore; the row export does not get applied. A newer schema can hold
    fields this version would silently drop, and a restore that quietly discards data is
    worse than one that refuses part of the job and says which part.
    """

    sentence = (
        "This backup was written by a newer Forgecast than the one running. The files "
        "were restored; the database export was not applied, because a newer format can "
        "hold things this version would drop. Update Forgecast and restore again."
    )

    def __init__(self, snapshot_schema: int, supported: int) -> None:
        self.snapshot_schema = snapshot_schema
        self.supported = supported
        super().__init__(f"snapshot schema {snapshot_schema} > supported {supported}")


class RestoreTargetNotEmpty(CloudError):
    """Refusing to write a restore over a populated storage directory.

    A restore that overwrites is a data-loss feature with a reassuring name: the most
    likely reason someone restores onto a working install is panic, and panic plus
    overwrite is how the thing they still had gets replaced by the thing they were
    trying to recover.
    """

    sentence = (
        "That folder already has work in it, so nothing was written. Restore into an "
        "empty folder and compare the two — an overwrite here would replace the work "
        "you still have with the copy you were trying to recover."
    )


class NothingToDo(CloudError):
    """Not a failure, and typed anyway.

    The caller needs to distinguish "backed up" from "nothing changed", and a bare
    success for both means the UI reports a backup that did not happen.
    """

    sentence = "Nothing has changed since the last backup, so nothing was sent."


class RemoteFailed(CloudError):
    """A git operation failed for a reason none of the specific states cover.

    The generic case exists so an unrecognised git failure still arrives as a
    `CloudError` with a sentence, rather than as a `CalledProcessError` escaping into a
    request handler.
    """

    sentence = (
        "GitHub refused the operation and Forgecast does not recognise the reason. Your "
        "work is untouched on this machine; the details are in the log."
    )
