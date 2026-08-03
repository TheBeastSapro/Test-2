"""Cloud backup, reachable. The HTTP end of `forgecast/cloud`.

## Why this file exists

`forgecast/cloud/` is the whole feature — manifest, snapshot, git transport, restore,
device flow — with the push/clone/restore round trip exercised against a real bare
repository on every test run. Its own docstring lists what was deliberately left out,
and the settings page is on that list.

The consequence was the same one this app has now hit three times: a capability that
works perfectly and cannot be reached from the application, so it is indistinguishable
from a capability that does not exist. It was reported as missing. It was not missing;
it had no door.

## Why the device code never reaches the browser

`device.DeviceCode.public_dict()` omits `device_code`, and this module holds it in
`_PENDING` instead. That is not belt-and-braces — `device_code` is the value that
redeems the authorisation, and the browser has no use for it. What the operator needs
is `user_code`, which they type into GitHub, and the verification URL. Sending the
redeeming value to a page so the page can send it back is a round trip that adds a
place for it to leak and buys nothing.

One slot, not a dictionary keyed by user. This is a local application with one
operator; a second concurrent device flow means the first one was abandoned, and
overwriting it is the correct outcome rather than a leak of pending state.

## Why the backup runs in a thread

`cloud.backup()` shells out to git and pushes over the network. On the event loop that
blocks every other request in the process — including the chat stream the operator is
probably watching — for as long as the push takes.

## What this module refuses to do

It never returns the token, in any shape, on any endpoint. `CloudConfig.public_dict()`
is the only serialisation used here, and it omits even the ciphertext: the encrypted
blob is not usable on its own, but it is one leaked `.env` away from being the token,
and API responses get copied into support threads.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ..auth import current_user
from ..cloud import (
    backup as run_backup,
)
from ..cloud import (
    config as cloud_config,
)
from ..cloud import (
    device,
    dry_run,
    staging_dir,
)
from ..cloud import (
    restore as run_restore,
)
from ..cloud import (
    status as cloud_status,
)
from ..cloud.errors import AuthorisationPending, CloudError
from ..config import get_settings
from ..models import User

log = logging.getLogger("forgecast.api.cloud")

router = APIRouter(prefix="/api/cloud", tags=["cloud"])

# The device code awaiting approval, if one is. Server-side on purpose — see the module
# docstring. `None` means no flow is in progress, which is also what the page is told.
_PENDING: device.DeviceCode | None = None


def _have_client_id() -> bool:
    """Whether this build has a GitHub app registered.

    `device.client_id()` *raises* `NotConfigured` rather than returning "" when there is
    none — which is correct where it is called to build a request, and wrong here. Asked
    as a truth test it took the status endpoint down with a 500 on every build that has
    no client id, which is every build until one is registered. The panel has to be able
    to render and say so.
    """
    try:
        return bool(device.client_id(""))
    except CloudError:
        return False


def _failed(exc: CloudError) -> dict:
    """A cloud failure as the page renders it.

    `sentence` is what the operator reads and it is always populated — the errors module
    puts it on the class so a failure state cannot be added without one. `detail` carries
    the git stderr for a maintainer and is deliberately not part of the sentence, because
    a stack of git output appended to plain English is read by nobody.
    """
    return {"ok": False, "state": type(exc).__name__, "sentence": exc.sentence,
            "detail": str(getattr(exc, "detail", "") or "")[:400]}


@router.get("")
def read_status(_user: User = Depends(current_user)) -> dict:
    """Everything the panel draws, with no network call and no credential in it."""
    payload = cloud_status()
    payload["client_id_configured"] = _have_client_id()
    payload["awaiting_code"] = _PENDING is not None
    payload["staging_dir"] = str(staging_dir())
    return payload


@router.get("/plan")
async def read_plan(_user: User = Depends(current_user)) -> dict:
    """What a backup would contain, without doing one.

    Callable while the feature is off, which is the point of it: "what would this send
    to GitHub" must be answerable before enabling the thing being asked about. That is
    the question an operator should ask first and the one they cannot ask anywhere else.
    """
    try:
        plan = await run_in_threadpool(dry_run)
    except CloudError as exc:
        return _failed(exc)
    return {
        "ok": True,
        "files": plan.file_count,
        "total_bytes": plan.total_bytes,
        "excluded": [str(item) for item in plan.excluded][:200],
        "excluded_count": len(plan.excluded),
    }


@router.post("/enable")
def set_enabled(payload: dict | None = None,
                _user: User = Depends(current_user)) -> dict:
    """Turn it on or off.

    Turning it off leaves the token and the remote in place rather than clearing them.
    Off means "do not talk to GitHub", and someone switching it off for a week should
    not have to authorise again — clearing the credential on a toggle is how a pause
    becomes a re-setup.
    """
    wanted = bool((payload or {}).get("enabled", True))
    current = cloud_config.load()
    current.enabled = wanted
    current.save()
    return current.public_dict()


@router.post("/device")
async def start_device_flow(_user: User = Depends(current_user)) -> dict:
    """Step one: ask GitHub for a code the operator types in.

    The device flow rather than a web redirect, and the reason is that this app ships
    as a zip: the token exchange sends no `client_secret`, so the archive carries only a
    public client ID. A redirect flow would need a secret in the zip, which hands every
    operator the key to every other operator's app.
    """
    global _PENDING

    if not _have_client_id():
        raise HTTPException(
            status_code=503,
            detail="This build has no GitHub app registered, so there is nothing to "
                   "sign in to. Set FORGECAST_GITHUB_CLIENT_ID and restart.")
    try:
        _PENDING = await run_in_threadpool(device.request_code)
    except CloudError as exc:
        return _failed(exc)
    return {"ok": True, **_PENDING.public_dict()}


@router.post("/device/poll")
async def poll_device_flow(_user: User = Depends(current_user)) -> dict:
    """Step two: has it been approved yet.

    Polled by the page rather than waited on here. A single request that blocks for the
    fifteen minutes a code is valid holds a worker for the whole time and dies to any
    proxy's read timeout, and the operator learns nothing while it hangs.

    `AuthorisationPending` is answered as `ok: False` with `pending: True` rather than as
    an error, because it is the expected state for most of this flow — treating the
    normal case as a failure is how a page ends up showing a red box for ten minutes
    while everything is working.
    """
    global _PENDING

    if _PENDING is None:
        raise HTTPException(status_code=409,
                            detail="no sign-in is in progress — press Connect first")

    try:
        token = await run_in_threadpool(device.poll_once, _PENDING.device_code)
    except AuthorisationPending as exc:
        return {"ok": False, "pending": True, "sentence": exc.sentence}
    except CloudError as exc:
        # Anything other than "still waiting" ends this attempt. Keeping the code around
        # after it expired or was declined means the page polls a dead code forever and
        # shows the same sentence each time, which reads as the app being stuck.
        _PENDING = None
        return {**_failed(exc), "pending": False}

    _PENDING = None
    current = cloud_config.load()
    current.set_token(token)
    try:
        who = await run_in_threadpool(device.whoami, token)
    except CloudError:
        # Authorised, but the identity lookup failed. Saved anyway: the token is the
        # thing that matters and discarding a good one because a second call failed
        # would send the operator through the whole flow again for nothing.
        who = {}
    if who.get("login") and not current.owner:
        current.owner = str(who["login"])
    current.enabled = True
    current.save()
    return {"ok": True, "pending": False,
            "account": who.get("login", ""),
            **current.public_dict()}


@router.post("/repository")
async def set_repository(payload: dict, _user: User = Depends(current_user)) -> dict:
    """Point the backup at a repository, creating it if asked.

    Private is not an option here, it is the only behaviour: this repository holds the
    operator's scripts, briefs and channel memory, and a public default would be a
    disclosure caused by a checkbox nobody read.
    """
    current = cloud_config.load()
    if not current.authorised:
        raise HTTPException(status_code=409,
                            detail="connect to GitHub first — there is nothing to "
                                   "create a repository with")

    name = str(payload.get("repository") or "").strip()
    owner = str(payload.get("owner") or current.owner or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="which repository?")

    if payload.get("create"):
        try:
            made = await run_in_threadpool(device.create_repository,
                                           current.token, name)
        except CloudError as exc:
            return _failed(exc)
        current.remote = str(made.get("clone_url") or "")
        current.owner = str((made.get("owner") or {}).get("login") or owner)
        current.repository = str(made.get("name") or name)
    else:
        current.owner = owner
        current.repository = name
        current.remote = f"https://github.com/{owner}/{name}.git"

    current.save()
    return {"ok": True, **current.public_dict()}


@router.post("/backup")
async def back_up_now(payload: dict | None = None,
                      _user: User = Depends(current_user)) -> dict:
    """Take one snapshot and push it.

    In a thread, because it shells out to git and pushes over the network — on the event
    loop that stalls every other request in the process, including the chat stream the
    operator is most likely watching while they press this.
    """
    try:
        result = await run_in_threadpool(
            run_backup, message=str((payload or {}).get("message") or ""))
    except CloudError as exc:
        return _failed(exc)
    return {"ok": True, **result}


@router.post("/restore")
async def restore_here(payload: dict | None = None,
                       _user: User = Depends(current_user)) -> dict:
    """Write the backup into this install's storage directory.

    Refused unless the target is empty, by `snapshot.restore` rather than by a check
    here. This is the one operation in the feature that can destroy local work, and the
    guard belongs beside the code that does the writing — a check at the HTTP layer is a
    check that the CLI path does not get.
    """
    into = get_settings().storage_dir
    try:
        restored = await run_in_threadpool(
            run_restore, into, remote=str((payload or {}).get("remote") or ""))
    except CloudError as exc:
        return _failed(exc)
    return {"ok": True, "files": getattr(restored, "file_count", 0),
            "into": str(into)}
