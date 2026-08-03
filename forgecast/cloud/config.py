"""Cloud backup state: whether it is on, which repository, and the token.

## Why a JSON file and not a settings row

Because that is what this app already does for a decision the operator makes once and
changes rarely — `agent/prefs.py` for the model, `agent/connectors.json` for service
tokens. The alternative is a `.env` edit, and asking an operator to open `.env` to turn on
a feature is asking them to do the thing the desktop build exists to remove.

`Settings.cloud_sync` seeds the flag for a fresh install so a container or a headless
deployment can arrive pre-enabled. Once this file exists it is the answer, because it
records a decision a person made rather than a default somebody shipped.

## Why the token is ciphertext, and what that costs

`crypto.encrypt`, the same envelope as provider keys and connector tokens, keyed from
`FORGECAST_ENCRYPTION_KEY` in `.env`. The cost is real and is the point: a backup restored
onto a second machine cannot use the first machine's GitHub authorisation, because the key
never left. Re-authorising is fifteen seconds and a device code. A credential that travels
with a backup is a credential that leaks with the backup.

`cloud.json` is also in `manifest.DENY` by name, so the file holding the token cannot end
up inside the backup that token wrote.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..crypto import SecretBoxError, decrypt, encrypt

log = logging.getLogger("forgecast.cloud.config")

FILENAME = "cloud.json"


def default_path() -> Path:
    return get_settings().storage_dir / FILENAME


@dataclass
class CloudConfig:
    """Everything the feature needs to know, and nothing about how it works."""

    enabled: bool = False
    # `https://github.com/<owner>/<repo>.git`, or a local path in the tests. Stored in the
    # clear: it is not secret, and a misconfigured remote should be readable rather than
    # opaque. The token is never in it — see `repo.py` on why a token in a remote URL ends
    # up in `git remote -v` and in every error message.
    remote: str = ""
    owner: str = ""
    repository: str = ""
    # Which machine this install is, for the branch a divergence goes to. A name, not a
    # fingerprint: the operator has to recognise it in "another machine backed up".
    machine: str = ""
    # ISO timestamp and commit of the last successful push, so "nothing changed since" is
    # answerable without a network call.
    last_pushed_at: str = ""
    last_commit: str = ""

    _token_ciphertext: str = field(default="", repr=False)

    # ------------------------------------------------------------------ the token

    @property
    def token(self) -> str:
        """The GitHub token in the clear, or "" if there is none or it cannot be read.

        Returns "" rather than raising on a decryption failure. The key having changed is
        indistinguishable from never having authorised as far as what the operator has to
        do about it — re-authorise — and a settings page that raises while rendering is a
        settings page nobody can use to fix the problem.
        """
        if not self._token_ciphertext:
            return ""
        try:
            return decrypt(self._token_ciphertext)
        except SecretBoxError:
            log.warning("stored GitHub token cannot be decrypted — re-authorise")
            return ""

    def set_token(self, plaintext: str) -> None:
        self._token_ciphertext = encrypt(plaintext) if plaintext else ""

    @property
    def authorised(self) -> bool:
        return bool(self.token)

    # ------------------------------------------------------------------ the gate

    def active(self) -> bool:
        """Whether the app should actually talk to GitHub.

        Three conditions, not one, because each can be false on its own and each has a
        different sentence: the flag is off, nothing is authorised, or no repository has
        been chosen yet. Collapsing them would produce "backup is off" for an install that
        is enabled and authorised and just has no remote.
        """
        return bool(self.enabled and self.remote and self.authorised)

    # ------------------------------------------------------------------ storage

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "remote": self.remote,
            "owner": self.owner,
            "repository": self.repository,
            "machine": self.machine,
            "last_pushed_at": self.last_pushed_at,
            "last_commit": self.last_commit,
            "token": self._token_ciphertext,
        }

    def public_dict(self) -> dict:
        """For a page or a log. The ciphertext is not in it.

        Ciphertext is not a secret in the sense that it can be used, but it is a secret in
        the sense that it should not be in an HTML response, a JSON API body or a support
        log — all three get copied around, and the encrypted blob plus a leaked `.env` is
        the token.
        """
        return {
            "enabled": self.enabled,
            "active": self.active(),
            "authorised": self.authorised,
            "remote": self.remote,
            "owner": self.owner,
            "repository": self.repository,
            "machine": self.machine,
            "last_pushed_at": self.last_pushed_at,
            "last_commit": self.last_commit,
        }

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path else default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written through a temporary file and replaced, because the alternative is a
        # truncated `cloud.json` after a crash mid-write, and a config file that fails to
        # parse is a feature that has silently turned itself off.
        scratch = target.with_suffix(".json.tmp")
        scratch.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        scratch.replace(target)
        return target


def load(path: Path | None = None) -> CloudConfig:
    """Read the config, or the shipped default when there is nothing to read.

    A malformed file becomes the default rather than an exception. The failure mode that
    matters is not "backup ran with stale settings" — it is "the app will not start
    because a JSON file has a trailing comma in it", and this feature is not important
    enough to take the app down.
    """
    target = Path(path) if path else default_path()
    seed = CloudConfig(enabled=get_settings().cloud_sync)
    if not target.exists():
        return seed
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("could not read %s — treating backup as unconfigured", target)
        return seed
    if not isinstance(raw, dict):
        return seed

    config = CloudConfig(
        enabled=bool(raw.get("enabled", seed.enabled)),
        remote=str(raw.get("remote") or ""),
        owner=str(raw.get("owner") or ""),
        repository=str(raw.get("repository") or ""),
        machine=str(raw.get("machine") or ""),
        last_pushed_at=str(raw.get("last_pushed_at") or ""),
        last_commit=str(raw.get("last_commit") or ""),
    )
    config._token_ciphertext = str(raw.get("token") or "")
    return config
