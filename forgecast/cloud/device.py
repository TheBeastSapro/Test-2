"""The GitHub OAuth device flow: a code on screen, no token ever typed.

## Why this flow and not a redirect

`agent/connectors.py` already records what happens when this app asks for a credential the
operator has never been shown: being asked for a URL you have never seen is being asked for
something that does not exist from where you are standing. A personal access token is worse
than a URL — it is a form with nine checkboxes, on a page somebody has to be told how to
find, whose wrong answer surfaces as a 403 twenty minutes later.

Device flow removes the credential from the operator's hands entirely. Forgecast shows
eight characters, they type them at github.com/login/device, and the token arrives here.

## Why it is the only flow that suits a zip

The token exchange sends **no client secret** — `client_id`, `device_code` and `grant_type`
and nothing else. That is what makes it correct for an app that ships as an archive anyone
can unzip: the only GitHub credential inside is a public client ID. A web-redirect flow
needs a client secret at exchange time, so shipping one would hand every operator the key
to every other operator's OAuth app, and there is no way to un-ship it.

## Why the polling loop is not in here

`poll_once` does one request and raises `AuthorisationPending` when the operator has not
finished. The loop belongs to the caller because the caller is the only thing that knows
whether it is allowed to block: a CLI can sleep, a request handler must not, and a function
that sleeps for fifteen minutes inside an event loop is a hung application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..config import get_settings
from .errors import (
    AuthorisationPending,
    CodeExpired,
    Declined,
    NotConfigured,
    Offline,
    RemoteFailed,
    TokenRejected,
)

log = logging.getLogger("forgecast.cloud.device")

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
API_URL = "https://api.github.com"

# `repo`, and there is no narrower option: GitHub's scope list has nothing between
# `public_repo` and `repo` that can write to a private repository, and `POST /user/repos`
# requires `repo` to create one. The cost is stated on the consent screen the operator
# sees, which is the only honest place to state it.
SCOPES = "repo"

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


@dataclass(frozen=True)
class DeviceCode:
    """What the operator is shown, and what the app needs to finish the exchange."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int

    def sentence(self) -> str:
        return (
            f"Open {self.verification_uri} and enter {self.user_code}. "
            f"The code is good for {self.expires_in // 60} minutes."
        )

    def public_dict(self) -> dict:
        """For the page. `device_code` is not in it — it is the thing that redeems the
        authorisation, so it belongs in the server's memory and not in a browser."""
        return {
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "expires_in": self.expires_in,
            "interval": self.interval,
            "sentence": self.sentence(),
        }


def client_id(override: str = "") -> str:
    value = override or get_settings().github_client_id
    if not value:
        raise NotConfigured("no FORGECAST_GITHUB_CLIENT_ID")
    return value


def _post(client: httpx.Client, url: str, data: dict) -> dict:
    """POST a form, get JSON back, and turn transport failures into states.

    `Accept: application/json` is not optional: without it GitHub answers the token
    endpoint with a url-encoded body, and a caller written against JSON reads that as an
    empty response — which looks exactly like "not authorised yet" and turns a declined
    authorisation into an infinite poll.
    """
    try:
        response = client.post(url, data=data, headers={"Accept": "application/json"})
    except httpx.TimeoutException as exc:
        raise Offline(f"{url} timed out") from exc
    except httpx.HTTPError as exc:
        raise Offline(str(exc)) from exc
    if response.status_code >= 500:
        raise RemoteFailed(f"{url} returned {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RemoteFailed(f"{url} returned {response.text[:200]!r}") from exc
    return payload if isinstance(payload, dict) else {}


def request_code(*, override_client_id: str = "",
                 client: httpx.Client | None = None) -> DeviceCode:
    """Step 1: ask GitHub for a code pair.

    `client` is injectable so the tests exercise this against a transport rather than
    against GitHub. An auth flow that can only be tested by authorising is an auth flow
    whose error paths are never tested.
    """
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        payload = _post(http, DEVICE_CODE_URL, {
            "client_id": client_id(override_client_id),
            "scope": SCOPES,
        })
    finally:
        if owned:
            http.close()

    if payload.get("error") or not payload.get("device_code"):
        raise NotConfigured(
            str(payload.get("error_description") or payload.get("error") or payload),
            sentence=(
                "GitHub would not issue a device code for this app. The most likely "
                "cause is that device flow is not enabled on the OAuth app — it has to "
                "be ticked in the app's settings before it works."
            ),
        )
    return DeviceCode(
        device_code=str(payload["device_code"]),
        user_code=str(payload.get("user_code") or ""),
        verification_uri=str(payload.get("verification_uri")
                             or "https://github.com/login/device"),
        expires_in=int(payload.get("expires_in") or 900),
        # Floored at 5s. GitHub adds five seconds to the interval on `slow_down`, and a
        # caller that polled faster than the stated interval would be rate-limited into
        # exactly the failure it was trying to avoid.
        interval=max(5, int(payload.get("interval") or 5)),
    )


def poll_once(device_code: str, *, override_client_id: str = "",
              client: httpx.Client | None = None) -> str:
    """Step 3, once. Returns the token, or raises the state it is in.

    `AuthorisationPending` is a raise rather than a `None` return so the caller cannot
    treat "still waiting" as "authorised and empty" — every other outcome here is an
    exception, and a contract where one case comes back as data is the one that gets
    mishandled.
    """
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        payload = _post(http, ACCESS_TOKEN_URL, {
            "client_id": client_id(override_client_id),
            "device_code": device_code,
            "grant_type": GRANT_TYPE,
        })
    finally:
        if owned:
            http.close()

    token = payload.get("access_token")
    if token:
        return str(token)

    error = str(payload.get("error") or "")
    detail = str(payload.get("error_description") or error)
    if error == "authorization_pending":
        raise AuthorisationPending(detail)
    if error == "slow_down":
        # Reported as pending with the new interval attached: the caller's job is still to
        # wait, only slower, and a distinct exception type for "wait longer" would make
        # every caller handle two cases that mean the same thing.
        pending = AuthorisationPending(detail)
        pending.retry_after = int(payload.get("interval") or 10)  # type: ignore[attr-defined]
        raise pending
    if error == "expired_token":
        raise CodeExpired(detail)
    if error == "access_denied":
        raise Declined(detail)
    if error in ("incorrect_device_code", "unsupported_grant_type"):
        raise RemoteFailed(detail)
    raise RemoteFailed(detail or f"unexpected response: {payload}")


def whoami(token: str, *, client: httpx.Client | None = None) -> dict:
    """Who the token belongs to. Used to name the repository and to prove the token works.

    Called immediately after the exchange, because the alternative is discovering that the
    stored token does not work at the first backup — which is minutes or hours later, with
    no obvious connection back to the authorisation that succeeded.
    """
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        response = http.get(
            f"{API_URL}/user",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
    except httpx.HTTPError as exc:
        raise Offline(str(exc)) from exc
    finally:
        if owned:
            http.close()

    if response.status_code in (401, 403):
        raise TokenRejected(f"/user returned {response.status_code}")
    if not response.is_success:
        raise RemoteFailed(f"/user returned {response.status_code}")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def create_repository(token: str, name: str, *,
                      client: httpx.Client | None = None) -> dict:
    """Create the private backup repository, so the operator never has to.

    `private: true` and `auto_init: false`. Not initialised on GitHub's side because the
    first push carries the initial commit, and a remote that already has a commit turns
    that push into a divergence on the very first backup.

    A 422 is treated as success-if-it-exists: re-enabling backup on a machine that already
    created the repository must not fail, and "name already exists" is the expected answer
    the second time.
    """
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        response = http.post(
            f"{API_URL}/user/repos",
            json={
                "name": name,
                "private": True,
                "auto_init": False,
                "description": "Forgecast backup — scripts, briefs and run records. "
                               "Renders are not stored here.",
            },
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
    except httpx.HTTPError as exc:
        raise Offline(str(exc)) from exc
    finally:
        if owned:
            http.close()

    if response.status_code in (401, 403):
        raise TokenRejected(f"/user/repos returned {response.status_code}")
    if response.status_code == 422:
        raise RemoteFailed(
            response.text[:300],
            sentence=(
                f"GitHub would not create a repository called {name} — most likely "
                f"because one with that name already exists on the account. Point backup "
                f"at the existing one instead of creating a second."
            ),
        )
    if not response.is_success:
        raise RemoteFailed(f"/user/repos returned {response.status_code}")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}
