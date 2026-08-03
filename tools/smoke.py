#!/usr/bin/env python3
"""Check that a built install actually works.

    python tools/smoke.py                          # start a server, check it, stop it
    python tools/smoke.py --url http://localhost:8000
    python tools/smoke.py --email me@example.com --password ...

Exits 0 when every check passed and 1 when any of them did not, printing what failed and
what it saw. Nothing here needs a Claude subscription or a provider key.

Which database it touches, and what it creates, depends on how it is called — and the
split is deliberate:

* **With no `--url`** it starts its own server, so it owns that instance and creates the
  account it signs in as. Registration is closed on a shipped install, correctly, so
  without this every check stopped at the sign-in with nothing actually checked. The
  account is made through the app's own `bootstrap` command, which is idempotent.
* **With `--url`** it never creates anything. It is then pointed at a server someone else
  is running, and signs in as an account that already exists — pass `--email` and
  `--password` for one.

Either way the thread and the attachment it makes are deleted again, because a check that
leaves debris in somebody's sidebar every run is a check they will stop running.

To keep even the first case away from a real database, point it at a scratch one:

    FORGECAST_DATABASE_URL=sqlite:///./smoke.db FORGECAST_STORAGE_DIR=./smoke-storage \\
    python tools/smoke.py

## Why this is not a test

`pytest` proves the code is right against a `TestClient`, which never starts a server,
never loads a template through the real static mount, and never touches the database or
storage directory the operator will actually be using. The failures this catches are the
ones that only exist in a shipped install: a template the packager left out of the zip, a
`/static` mount resolved from the working directory, a migration that never ran, a
`storage/` the process cannot write to. Every one of those produces an app that imports
cleanly and serves a broken page.

So the checks are deliberately shallow and end-to-end. Each one is a question an operator
would ask on a fresh machine — is it up, can I see the chat, does it know what it is
missing, does a thread survive a round trip — and each reports what it *saw*, not "ok",
because a check whose output is a tick tells you nothing when the next one fails.

## Why the auth check asserts self-consistency rather than success

A test machine may legitimately have no Claude CLI and no sign-in, so "connected" cannot
be required. What can be required is that the report does not contradict itself: it must
not claim to be connected while also offering a sign-in button. That exact contradiction
shipped once — "signed in with your subscription" sat above a chat answering *Not logged
in*, because the CLI being present had been treated as the CLI being signed in. See
`forgecast/agent/auth.py`.

stdlib plus httpx, which the app already depends on. Nothing else, because this has to
run against an install that was never set up for development.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

# Long enough for a cold start that runs migrations and creates the storage directory on a
# slow disk, short enough that a server which is never going to come up is not mistaken
# for one that is merely slow.
BOOT_TIMEOUT = 60.0
REQUEST_TIMEOUT = 30.0


class Wrong(Exception):
    """A check's expectation was not met. The message is shown to the operator."""


def expect(condition: object, complaint: str) -> None:
    if not condition:
        raise Wrong(complaint)


def body(response: httpx.Response) -> dict:
    """A JSON object from a response, or a complaint naming what came back instead.

    Worth its own helper because the interesting failure is an HTML error page arriving
    where JSON was expected — a redirect to /login, a proxy's 502 — and
    `json.JSONDecodeError` on its own says only "Expecting value: line 1 column 1".
    """
    try:
        payload = response.json()
    except ValueError:
        raise Wrong(f"{response.request.url.path} answered {response.status_code} with "
                    f"{response.text[:120]!r}, which is not JSON") from None
    if not isinstance(payload, dict):
        raise Wrong(f"{response.request.url.path} answered with a "
                    f"{type(payload).__name__}, not an object")
    return payload


# ------------------------------------------------------------------------- the checks
#
# Each takes a client that is already signed in and returns one line saying what it saw.
# They are plain functions rather than methods so `tests/test_smoke.py` can call any one
# of them with a stub client and prove it actually fails when the answer is wrong.


def check_serving(client: httpx.Client) -> str:
    """The app started and is answering requests at all."""
    response = client.get("/healthz")
    expect(response.status_code == 200,
           f"/healthz answered {response.status_code}, so the app is not serving")
    return "the app answers on /healthz"


def check_healthz(client: httpx.Client) -> str:
    """And what it answers is a coherent description of this install."""
    report = body(client.get("/healthz"))
    expect(report.get("ok") is True, f"/healthz reports ok={report.get('ok')!r}")
    mode = report.get("provider_mode")
    expect(mode in ("mock", "live"),
           f"/healthz reports provider_mode={mode!r}, which is neither mock nor live")
    expect(isinstance(report.get("ffmpeg"), bool),
           f"/healthz reports ffmpeg={report.get('ffmpeg')!r}, which is not a boolean")
    return f"provider_mode={mode}, ffmpeg={'found' if report['ffmpeg'] else 'missing'}"


def check_chat_page(client: httpx.Client) -> str:
    """The front door renders, with the script that makes it a chat.

    Asserted on the two things a missing file actually breaks. `chat.html` and `chat.js`
    are shipped separately from the routes, so a zip missing either produces a server that
    starts, returns 200, and has no way in — which reads as a broken build rather than a
    missing file. `tools/package.py` asserts they are in the archive; this asserts they
    are on the page.
    """
    page = client.get("/")
    expect(page.status_code == 200,
           f"the chat page answered {page.status_code}"
           + (" — the smoke client is not signed in" if page.status_code in (302, 303)
              else ""))
    html = page.text
    expect('id="chat"' in html, "the chat page rendered without the chat itself")
    expect("/static/chat.js" in html,
           "the chat page does not load /static/chat.js, so nothing on it will work")
    script = client.get("/static/chat.js")
    expect(script.status_code == 200,
           f"/static/chat.js answered {script.status_code} — the static mount is wrong "
           f"or the file was not shipped")
    return f"{len(html):,} bytes of page, {len(script.content):,} bytes of chat.js"


def check_setup_state(client: httpx.Client) -> str:
    """Setup knows what this machine has and has not got.

    This is what the operator is shown on a first run, so a report that cannot name the
    two tools the app installs is a setup page that offers nothing.
    """
    state = body(client.get("/api/setup/state"))
    tools = state.get("tools")
    expect(isinstance(tools, list) and tools,
           "/api/setup/state reports no toolchain at all")
    for tool in tools:
        expect(isinstance(tool, dict) and {"key", "label", "present"} <= set(tool),
               f"a toolchain entry is missing key, label or present: {tool!r}")
        expect(isinstance(tool["present"], bool),
               f"{tool.get('key')!r} reports present={tool['present']!r}, not a boolean")
    keys = {tool["key"] for tool in tools}
    expect({"ffmpeg", "claude"} <= keys,
           f"the toolchain report names {sorted(keys)}, which does not cover ffmpeg and "
           f"the Claude Code CLI")
    expect(isinstance(state.get("ready"), bool),
           f"/api/setup/state reports ready={state.get('ready')!r}, not a boolean")

    found = sorted(tool["key"] for tool in tools if tool["present"])
    absent = sorted(tool["key"] for tool in tools if not tool["present"])
    return (f"ready={state['ready']}; present: {', '.join(found) or 'none'}"
            + (f"; missing: {', '.join(absent)}" if absent else ""))


def check_agent_auth(client: httpx.Client) -> str:
    """The Claude report says one thing, not two contradictory things.

    Deliberately does not require `ok`. A machine with no CLI and no sign-in is a valid
    install of this app — everything except the chat and rendering works. What is not
    valid is a report that is connected *and* offering the sign-in button, or one that
    refuses without saying why.
    """
    report = body(client.get("/api/agent/auth"))
    required = {"ok", "headline", "detail", "cli_found", "signed_in", "can_login", "fixes"}
    missing = required - set(report)
    expect(not missing, f"the auth report is missing {sorted(missing)}")
    expect(not (report["ok"] and report["can_login"]),
           "the auth report claims to be connected AND offers a sign-in button")
    expect(not (report["ok"] and not report["signed_in"]),
           "the auth report claims to be connected without anyone being signed in")
    expect(str(report["headline"]).strip(), "the auth report has no headline")
    if not report["ok"]:
        # A refusal has to be actionable, or the operator is told no and nothing else.
        expect(str(report["detail"]).strip() and (report["fixes"] or report["can_login"]),
               f"{report['headline']!r} offers neither a fix nor a sign-in button")
    return f"{report['headline']} (cli_found={report['cli_found']})"


def check_thread_round_trip(client: httpx.Client) -> str:
    """A conversation can be created, renamed, read back, and deleted.

    The round trip is the point. Creating a row proves the tables exist; reading it back
    through a second request proves it was committed rather than held in a session that
    was rolled back, which is the failure a migration that never ran actually produces.
    """
    made = body(client.post("/api/agent/threads", json={}))
    thread_id = made.get("id")
    expect(isinstance(thread_id, int), f"a new thread came back without an id: {made!r}")
    expect(made.get("title") == "New chat",
           f"a new thread is titled {made.get('title')!r}")

    try:
        client.patch(f"/api/agent/threads/{thread_id}", json={"title": "smoke check"})
        read = body(client.get(f"/api/agent/threads/{thread_id}"))
        expect(read.get("title") == "smoke check",
               f"the rename did not survive the round trip: {read.get('title')!r}")
        expect(isinstance(read.get("messages"), list),
               "the thread came back without a messages list")
        listed = body(client.get("/api/agent/threads")).get("threads") or []
        expect(any(row.get("id") == thread_id for row in listed),
               "a created thread does not appear in the thread list")
    finally:
        # Smoke runs against installs people are using, so they clean up after
        # themselves. A run that leaves a "smoke check" thread in someone's sidebar every
        # time is a check nobody will keep running.
        with contextlib.suppress(httpx.HTTPError):
            client.delete(f"/api/agent/threads/{thread_id}")

    gone = client.get(f"/api/agent/threads/{thread_id}")
    expect(gone.status_code == 404,
           f"a deleted thread still answers {gone.status_code}")
    return f"thread {thread_id} created, renamed, listed, deleted"


def check_attachment(client: httpx.Client) -> str:
    """An upload comes back classified, which is what decides whether it is usable.

    `kind` is not cosmetic: it is what tells the agent it has an image it can open rather
    than an opaque file. A clipboard paste arrives with no filename and only a MIME type,
    so the extension has to be derived — and when that goes wrong, pasting a screenshot
    looks like it worked and then does nothing. Posted here the way a browser posts a
    clipboard blob, for exactly that reason.

    The bytes are a PNG signature and nothing else. Classification is by extension, so a
    real image would prove nothing extra and would make this file carry a binary blob.
    """
    posted = client.post(
        "/api/agent/attach",
        files={"file": ("blob", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    expect(posted.status_code == 200,
           f"uploading an attachment answered {posted.status_code}: {posted.text[:120]}")
    saved = body(posted)
    path = saved.get("path", "")
    try:
        expect(saved.get("kind") == "image",
               f"a PNG came back as kind={saved.get('kind')!r}, so the agent would be "
               f"told it cannot open it")
        expect(str(saved.get("name", "")).endswith(".png"),
               f"a pasted PNG was saved as {saved.get('name')!r}, with no extension for "
               f"anything downstream to read")
        expect(saved.get("size") == 8, f"the upload stored {saved.get('size')!r} bytes")
        expect(path, "the upload came back without a path for the agent to open")
        served = client.get("/api/agent/file", params={"path": path})
        expect(served.status_code == 200,
               f"the attachment cannot be served back: {served.status_code}")
    finally:
        # Detaching deletes the file: attachments are context, not a library.
        with contextlib.suppress(httpx.HTTPError):
            client.post("/api/agent/detach", json={"path": path})
    return f"{saved['name']} stored as kind={saved['kind']} and served back"


def check_research_can_fetch(client: httpx.Client) -> str:
    """The research desk can read a channel, or says exactly what would let it.

    The complaint this answers is "research is not working": on an install with no
    YouTube Data API key the fetch box was disabled, which looks identical to a broken
    page. It is not disabled any more — `yt-dlp` reads the public listing without a key
    — so the two acceptable states are "the box is open" and "the box is shut and the
    sentence beside it names the fix".

    No channel is fetched. This script runs against a real install and a real network
    read would make it slow and dependent on a third party being up, which is the
    opposite of what a smoke check is for. What is asserted is the capability and the
    honesty of the message, both of which are decided server-side before any request.
    """
    page = client.get("/research")
    expect(page.status_code == 200,
           f"/research answered {page.status_code}, so the desk is not reachable")

    markup = page.text
    expect('id="channel"' in markup,
           "the /research page has no channel box at all, so nothing can be fetched")
    box = markup.split('id="channel"', 1)[1][:400]

    if "disabled" not in box:
        return "the channel box is open, so a link can be fetched"

    # Shut is allowed. Shut with no way out is not: that is the original complaint.
    expect("yt-dlp" in markup or "API key" in markup,
           "the channel box is disabled and the page does not say what would enable "
           "it, which reads as the feature being broken rather than unconfigured")
    return "the channel box is shut, and the page names the fix"


@dataclass(frozen=True)
class Check:
    name: str
    run: Callable[[httpx.Client], str]


CHECKS: tuple[Check, ...] = (
    Check("the app is serving", check_serving),
    Check("/healthz describes this install", check_healthz),
    Check("the chat page renders", check_chat_page),
    Check("setup reports the toolchain", check_setup_state),
    Check("the Claude report is self-consistent", check_agent_auth),
    Check("a thread round-trips", check_thread_round_trip),
    Check("an attachment uploads and is classified", check_attachment),
    Check("research can fetch a channel, or says why not", check_research_can_fetch),
)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def run_checks(client: httpx.Client, checks: tuple[Check, ...] = CHECKS) -> list[Result]:
    """Every check, in order, each one reporting what it saw.

    Nothing stops early. A first failure is usually the informative one, but the checks
    after it often say *why* — "the chat page renders" failing next to "the app is
    serving" passing is a different diagnosis from both failing — and running the rest
    costs a second.

    Every exception is caught, not just `Wrong`. A shipped install fails in ways this
    script has not predicted (a proxy closing the connection, a template raising while
    rendering), and a traceback out of here would abandon the remaining checks and the
    cleanup inside them.
    """
    results: list[Result] = []
    for check in checks:
        try:
            results.append(Result(check.name, True, check.run(client)))
        except Wrong as wrong:
            results.append(Result(check.name, False, str(wrong)))
        except Exception as exc:
            results.append(Result(check.name, False, f"{type(exc).__name__}: {exc}"))
    return results


def report(results: list[Result]) -> int:
    """Print the results and return the exit code."""
    for result in results:
        print(f"  {'pass' if result.ok else 'FAIL'}  {result.name}")
        print(f"        {result.detail}")

    # Nothing checked is not success. An empty result set means the run fell over before
    # any check ran — a filter that matched no names, an exception during collection —
    # and "0 checks passed. This install works." going green in CI is the one outcome
    # that makes having a smoke script pointless.
    if not results:
        print("\n  no checks ran, so nothing was verified.")
        return 1

    failed = [result for result in results if not result.ok]
    if not failed:
        print(f"\n  {len(results)} checks passed. This install works.")
        return 0
    print(f"\n  {len(failed)} of {len(results)} checks failed:")
    for result in failed:
        print(f"    {result.name}: {result.detail}")
    return 1


# ------------------------------------------------------------------------------ signing in
#
# Almost everything worth checking is behind an account, because almost everything in this
# app is scoped to one.


def sign_in(client: httpx.Client, email: str, password: str) -> str:
    """Put a bearer token on the client, creating the account only if signup is open.

    A bearer token rather than the browser cookie: both are accepted (`forgecast.auth`
    accepts either), and a header is the one that cannot be lost to a redirect.

    Signup is closed on a shipped instance by design, so a 403 here is not a bug — it
    means the account has to exist already, and the message says how to make one.
    """
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    if login.status_code == 401:
        created = client.post("/api/auth/signup", json={"email": email,
                                                        "password": password})
        if created.status_code == 403:
            raise Wrong(
                f"there is no account for {email} and registration is closed on this "
                f"instance.\n        Create one with:  forgecast bootstrap --email "
                f"{email} --password ...\n        or pass --email/--password for an "
                f"account that exists.")
        if created.status_code >= 400:
            raise Wrong(f"could not create {email}: {created.status_code} "
                        f"{created.text[:160]}")
        login = created
    elif login.status_code >= 400:
        raise Wrong(f"could not sign in as {email}: {login.status_code} "
                    f"{login.text[:160]}")

    token = body(login).get("access_token")
    expect(token, f"signing in as {email} returned no access token")
    client.headers["Authorization"] = f"Bearer {token}"
    return str(token)


# -------------------------------------------------------------------- starting a server


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


SMOKE_EMAIL = "smoke@forgecast.example"
SMOKE_PASSWORD = "smoke-check-not-a-real-password"


def ensure_account(email: str, password: str) -> None:
    """Make the account the checks sign in as, if it is not already there.

    Runs in a subprocess through the app's own `bootstrap` command rather than by
    importing the models here. Two reasons, and the second is the real one: it is the
    same path a deployment uses, so a broken bootstrap is a failure this script reports
    instead of a failure it works around; and importing `forgecast.db` in this process
    would build a second engine against the same SQLite file while the server is
    starting.
    """
    result = subprocess.run(
        [sys.executable, "-m", "forgecast.cli", "bootstrap",
         "--email", email, "--password", password],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-800:]
        raise Wrong(f"could not create the account to check with:\n{tail}")


@contextlib.contextmanager
def serve(port: int, email: str = SMOKE_EMAIL,
          password: str = SMOKE_PASSWORD) -> Iterator[str]:
    """Run the real app in a subprocess for the duration, and stop it afterwards.

    A subprocess rather than a thread, and uvicorn rather than `create_app()` in-process,
    because half of what this script is for is the start-up that only happens in a real
    server: the lifespan hook that runs `init_db`, creates `storage/` and binds the
    runner's event loop. Importing the app and poking it with a `TestClient` would skip
    the part most likely to be broken in a shipped install.
    """
    # An account first, because a shipped instance has registration closed — correctly —
    # and without one every check below stops at the sign-in with nothing checked. The
    # launcher does this on its own first run; a bare uvicorn does not, and this script
    # starts a bare uvicorn. It is idempotent, so an install that already has the
    # account is untouched.
    ensure_account(email, password)

    command = [sys.executable, "-m", "uvicorn", "forgecast.api.main:app",
               "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    print(f"  starting a server on port {port}")
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + BOOT_TIMEOUT
        while True:
            if process.poll() is not None:
                # It died. Its own output is the only thing that says why, and printing
                # "the server did not start" without it sends people to read a log that
                # was piped into this process and thrown away.
                output = (process.stdout.read() if process.stdout else "") or "(no output)"
                raise Wrong(f"the server exited with code {process.returncode} before it "
                            f"answered:\n{output.strip()[-2000:]}")
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{base}/healthz", timeout=2.0).status_code == 200:
                    break
            if time.monotonic() > deadline:
                raise Wrong(f"the server did not answer within {BOOT_TIMEOUT:.0f}s")
            time.sleep(0.25)
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:      # a hung worker must not hang the script
            process.kill()
            process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that a built Forgecast install actually works.")
    parser.add_argument("--url", default="",
                        help="check a server that is already running (default: start one)")
    # `.example` rather than the more obvious `.local`: signup validates the address, and
    # `.local`, `.test` and `.invalid` are special-use names it rejects outright — so that
    # default would fail on the address rather than on anything about the install.
    parser.add_argument("--email", default=SMOKE_EMAIL,
                        help="account to sign in as")
    parser.add_argument("--password", default=SMOKE_PASSWORD,
                        help="its password")
    parser.add_argument("--json", action="store_true",
                        help="print the results as JSON as well, for a CI job to read")
    args = parser.parse_args()

    print("Smoke-checking Forgecast")
    started = time.monotonic()
    try:
        with contextlib.ExitStack() as stack:
            base = args.url.rstrip("/") or stack.enter_context(
                serve(free_port(), args.email, args.password))
            print(f"  against {base}\n")
            client = stack.enter_context(
                httpx.Client(base_url=base, timeout=REQUEST_TIMEOUT,
                             follow_redirects=False))
            sign_in(client, args.email, args.password)
            results = run_checks(client)
    except (Wrong, httpx.HTTPError) as problem:
        # Everything above is setup, not a check. Failing here means no check ran at all,
        # which is a different answer from "a check failed" and has to read like one.
        # `HTTPError` is caught beside `Wrong` because the commonest version of this is a
        # `--url` pointing at nothing, and a connection traceback buries that.
        print(f"  FAIL  could not start checking\n        {problem}")
        return 1

    code = report(results)
    print(f"  {time.monotonic() - started:.1f}s")
    if args.json:
        print(json.dumps([vars(result) for result in results], indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
