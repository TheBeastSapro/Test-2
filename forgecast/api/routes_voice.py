"""Signing in to a voice vendor with a subscription instead of pasting a key.

## What was missing

`MiniMaxCliVoiceProvider` narrates through `mmx speech synthesize`, signed in with the
operator's plan, so the characters come out of an allowance already paid for rather than
off an API balance. `minimax_auth` knows how to find that CLI, read whether it is signed
in, tell a plan sign-in from a key one, and start the browser flow. The registry routes to
it. All of that existed and worked.

Settings offered one thing for MiniMax: a box to paste an API key. So the only reachable
way to narrate on this vendor was the one that bills per character — the route the CLI
adapter was written specifically to avoid. This is the door.

## Why the status is fetched by the browser rather than rendered into the page

Reading the CLI's state means running it, and the settings page already refuses to spawn
a subprocess during a render for the connectors panel, in its own words: "a subprocess
during a page render lets one wedged CLI hold up every other panel on it". The same is
true here, and more so — `mmx auth status` talks to the network. So the card renders
immediately and asks this router afterwards.

## Why installing happens here

The operator's standing instruction, and the failure it came from: being told to go and
run an npm command is the homework `desktop/toolchain.py` exists to remove, and it was
reported as exactly that once already for a CLI that was never being installed at all.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..agent import minimax_auth
from ..auth import current_user
from ..desktop import toolchain
from ..models import User
from .routes_setup import app_root

log = logging.getLogger("forgecast.api.voice")

router = APIRouter(prefix="/api/voice", tags=["voice"], include_in_schema=False)


@router.get("/minimax")
def minimax_status(user: User = Depends(current_user)) -> dict:
    """Whether narration can go through the subscription right now, and if not, why.

    `with_api_key` is reported rather than folded into `signed_in`, because they are
    different states with different bills: a CLI authenticated with a key charges per
    character exactly like the HTTP route, so a page that showed it as "signed in" would
    be telling the operator their narration is on the plan while it draws down a balance.
    """
    status = minimax_auth.check(app_root())
    return {
        **status.as_dict(),
        "install_hint": minimax_auth.INSTALL_HINT,
        "package": minimax_auth.PACKAGE,
        # What this route buys, said where the decision is made rather than in a doc.
        "why": ("Narration goes through the MiniMax plan you already pay for instead of "
                "an API balance. A key pasted below does the opposite — it bills per "
                "character."),
    }


@router.post("/minimax/login")
def minimax_login(user: User = Depends(current_user)) -> dict:
    """Open the browser sign-in in a visible terminal.

    Visible on purpose: the flow prints a URL and a code and then waits. Behind a hidden
    window it is a button that appears to do nothing.
    """
    ok, message = minimax_auth.start_login(app_root())
    return {"ok": ok, "message": message}


@router.post("/minimax/install")
def minimax_install(user: User = Depends(current_user)) -> StreamingResponse:
    """Install the MiniMax CLI, streaming npm's output as it goes.

    Into the app's own `runtime/node` prefix, the same place the Claude and Codex CLIs
    go, for the reason `install_codex_cli` gives: one Node, one npm cache, one folder to
    delete — and a copy installed anywhere else would work from a terminal and be
    invisible to the app.
    """
    root = app_root()

    def stream():
        yield json.dumps({
            "type": "log",
            "text": f"Installing {minimax_auth.PACKAGE}…",
        }) + "\n"

        def note(line: str) -> None:
            pass  # collected by run_watched; the result carries what matters

        try:
            ok, detail = toolchain.install_npm_package(
                root, minimax_auth.PACKAGE, on_note=note,
                # Found the way the narration route will look for it, not the way npm
                # reports it. An install that npm called a success and this app cannot
                # locate is the failure `install_codex_cli` documents, and it takes a
                # panel green and the first render to a crash.
                verify=lambda: minimax_auth.find_cli(root))
        except Exception as exc:                                    # pragma: no cover
            log.exception("minimax cli install failed")
            ok, detail = False, f"{type(exc).__name__}: {exc}"

        yield json.dumps({"type": "done", "ok": ok, "detail": detail}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
