"""Settings: connect providers, see what is actually wired, switch to live.

## Why this page has to exist

Until now the only way to connect Anthropic or ElevenLabs was to edit `.env` in a text
editor and restart. For an application you double-click, that is not a configuration
step — it is a wall. Worse, there was no way to find out whether anything *was*
connected: the app looked identical with a working key and with no key at all, right
up until a run failed.

So this page does two things, and the second matters as much as the first:

* **connect** — a key goes in, is encrypted at rest, and takes effect immediately;
* **report** — for every capability, which vendor will actually serve it and why.

That second half is the part that is easy to skip and expensive to miss. "Is Claude
connected?" is a question the app should be able to answer plainly.

## Where each setting lives, and why they differ

Provider keys are **per user, in the database, encrypted**. They are secrets belonging
to an account, and `crypto.encrypt` already exists for exactly this.

Provider mode and the YouTube Data key are **process settings in `.env`**. They are not
per-user — they describe this installation. Writing them means rewriting `.env`, and
because `get_settings()` is cached for the life of the process, the cached object is
updated too so the change lands now rather than at the next restart.
"""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, optional_user
from ..config import get_settings
from ..crypto import encrypt, fingerprint, mask
from ..db import get_session
from ..models import ProviderKey, User
from ..providers.registry import CATALOGUE, Capability, registry_for

log = logging.getLogger("forgecast.api.settings")

router = APIRouter(include_in_schema=False)

# The keys worth showing, in the order someone actually sets them up. Each carries
# what it unlocks, because "anthropic" alone does not tell you the script stage
# depends on it.
PROVIDER_FIELDS = [
    {"key": "anthropic", "label": "Anthropic (Claude)", "unlocks": "briefs, research, scripts, compliance",
     "hint": "sk-ant-…", "where": "console.anthropic.com"},
    # Labelled against being mistaken for the ChatGPT agent, because it was. There are two
    # OpenAI-shaped things in this app and only one of them wants a key: this row is the
    # *pipeline* LLM, billed per token, used for briefs and scripts. The ChatGPT **agent**
    # signs in to the subscription through the Codex CLI and needs nothing here — so
    # someone looking for "where do I connect ChatGPT" found this box and pasted into it.
    {"key": "openai", "label": "OpenAI API (not your ChatGPT subscription)",
     "unlocks": "an alternative to Claude for briefs and scripts, billed per token. This "
                "is NOT how you use a ChatGPT plan — for that, pick ChatGPT in the agent "
                "picker at the bottom of the chat and press Sign in. Leave this empty "
                "unless you want the paid API as well",
     "hint": "sk-…", "where": "platform.openai.com"},
    {"key": "elevenlabs", "label": "ElevenLabs", "unlocks": "narration, on the "
     "character allowance your subscription already includes",
     "hint": "", "where": "elevenlabs.io"},
    # Named as the alternative rather than the fallback, and the billing difference is on
    # the label instead of in a doc: this key is drawn down per character, where the
    # ElevenLabs one spends a plan that is already paid for.
    {"key": "minimax", "label": "MiniMax", "unlocks": "narration as an alternative to "
     "ElevenLabs — billed per character against your MiniMax API balance, not your "
     "subscription; set a channel's voice vendor to minimax-voice to use it",
     "hint": "", "where": "platform.minimax.io — API Keys"},
    {"key": "fal", "label": "fal.ai", "unlocks": "generated stills and B-roll clips",
     "hint": "", "where": "fal.ai/dashboard/keys"},
    # Off unless a key is present, and what it buys is stated as the reason to turn it on:
    # a recurring character whose face is the same in shot 30 as in shot 1, and the same
    # next episode. It bills per generation, so it is never used unless a channel asks.
    {"key": "higgsfield", "label": "Higgsfield", "unlocks": "a recurring character whose "
     "face stays the same across shots and across episodes (Soul), plus Kling/Veo/"
     "Seedance behind one key — billed per generation against your Higgsfield credits, "
     "so it is only used on channels you set to it",
     "hint": "key:secret — both halves", "where": "platform.higgsfield.ai"},
    {"key": "heygen", "label": "HeyGen", "unlocks": "talking-head avatar passes",
     "hint": "", "where": "heygen.com"},
    {"key": "runway", "label": "Runway", "unlocks": "an alternative video generator",
     "hint": "", "where": "runwayml.com"},
]

# Settings that describe the installation rather than an account.
ENV_FIELDS = [
    # Not "unlocks reading a channel": `sources.read_channel` falls back to yt-dlp, so
    # the old copy sent people to the Google console for a feature they already had.
    # What the key buys is measured dates and engagement counts.
    {"key": "FORGECAST_YOUTUBE_API_KEY", "label": "YouTube Data API key",
     "unlocks": "measured publish dates, likes and comments in research (without it, "
                "pip install yt-dlp reads the same channel with approximate dates)",
     "where": "console.cloud.google.com — enable YouTube Data API v3"},
    {"key": "FORGECAST_TAVILY_API_KEY", "label": "Tavily",
     "unlocks": "better research sources (Wikipedia is used without it)",
     "where": "tavily.com"},
    # A path rather than a credential, and it belongs here for the same reason the keys
    # do: it describes this machine, not an account. It is also the one setting an
    # operator has to be able to change without opening `.env`, because the documents it
    # points at are theirs and live wherever they keep them.
    #
    # Nothing is copied out of that folder — it is read while a prompt is being built and
    # never written to. Keep it outside the repository: the documents are licensed to the
    # operator alone, and a folder inside the tree is a folder that ends up in a commit.
    {"key": "FORGECAST_SCRIPTING_DIR", "label": "Scripting documents folder",
     "unlocks": "your own scripting method as a per-channel style — one subfolder per "
                "style, or loose .md/.txt files for a single one. Nothing is copied out "
                "of it and nothing from it is ever packaged",
     "where": "a folder on this machine, outside the Forgecast folder",
     "secret": False},
    # Also a machine fact rather than an account one, and for a sharper reason than the
    # folder above: a channel restored onto a second computer must not arrive asking for
    # a GPU that computer does not have. `Channel` is what the cloud backup copies;
    # `.env` is not.
    {"key": "FORGECAST_VIDEO_ENCODER", "label": "Video encoder",
     "unlocks": "hardware-accelerated rendering — cpu, nvidia or intel. An NVIDIA or "
                "Intel GPU encodes far faster than the processor does, including small "
                "cards that cannot generate video at all, because encoding is a "
                "fixed-function block. Slightly larger files for the same picture. "
                "Leave empty for the CPU; anything this machine cannot run falls back "
                "to it rather than failing a paid render",
     "where": "this machine — see /api/encoders for what it can actually do",
     "secret": False},
]

_SECRET_LINE = re.compile(r"^([A-Z0-9_]+)\s*=\s*(.*)$")


def write_env(root: Path, values: dict[str, str]) -> None:
    """Update `.env` in place, keeping comments, order and unrelated keys.

    Rewriting the file wholesale would drop the operator's own additions and the
    header explaining what the file is. A line-by-line update means the file someone
    hand-edited still looks like the file they hand-edited.
    """
    path = root / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()

    out: list[str] = []
    for line in lines:
        match = _SECRET_LINE.match(line.strip())
        if match and match.group(1) in values:
            name = match.group(1)
            out.append(f"{name}={values[name]}")
            seen.add(name)
        else:
            out.append(line)

    for name, value in values.items():
        if name not in seen:
            out.append(f"{name}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):  # Windows and odd filesystems
        path.chmod(0o600)


def capability_report(session: Session, user: User) -> list[dict]:
    """For each capability, the vendor that will actually serve it.

    Resolved through the real registry rather than inferred from which keys exist.
    Inferring is how a report ends up disagreeing with the run — the registry has
    fallbacks, keyless providers and a mock mode, and only it knows the answer.
    """
    settings = get_settings()
    registry = registry_for(session, user)
    rows: list[dict] = []

    for capability in Capability:
        entry = {"capability": capability.value, "vendor": "—", "state": "missing",
                 "detail": ""}
        if settings.is_mock:
            entry.update(vendor="mock", state="mock",
                         detail="placeholder output; nothing is called or charged")
        else:
            try:
                provider = registry.resolve(capability)
                name = getattr(provider, "name", type(provider).__name__)
                entry.update(vendor=name, state="ready")
                key_name = next(
                    (k for v, (c, _cls, k) in CATALOGUE.items()
                     if c is capability and v.lower() in str(name).lower()), "")
                if key_name:
                    entry["detail"] = f"using your {key_name} key" \
                        if registry.key_owner(key_name) == "user" else \
                        f"using the {key_name} key from .env"
                else:
                    entry["detail"] = "keyless"
            except Exception as exc:
                entry["detail"] = str(exc)[:160]
        rows.append(entry)
    return rows


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request, session: Session = Depends(get_session), saved: str = "",
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/settings", 303)  # type: ignore[return-value]

    settings = get_settings()
    stored = {
        row.provider: row for row in session.execute(
            select(ProviderKey).where(ProviderKey.user_id == user.id)
        ).scalars().all()
    }

    providers = []
    for field in PROVIDER_FIELDS:
        row = stored.get(field["key"])
        providers.append({
            **field,
            "masked": row.masked if row else "",
            "from_env": bool(settings.platform_key(field["key"])) and row is None,
        })

    env_values = {}
    for field in ENV_FIELDS:
        attribute = field["key"].removeprefix("FORGECAST_").lower()
        value = str(getattr(settings, attribute, "") or "")
        # Masked unless the field says it is not a secret. A folder path shown as
        # `/hom…rary` is a setting nobody can check, and an operator who cannot read the
        # value back cannot tell a saved path from a typo'd one — which for the scripting
        # folder presents as "my documents did not load" with nothing to look at.
        env_values[field["key"]] = (
            mask(value) if value and field.get("secret", True) else value)

    from ..agent import connectors, engines

    return TEMPLATES.TemplateResponse(
        request,
        "settings.html",
        {
            **shell(session, user, "settings"),
            "providers": providers,
            "env_fields": ENV_FIELDS,
            "env_values": env_values,
            "capabilities": capability_report(session, user),
            "is_mock": settings.is_mock,
            "storage_dir": str(settings.storage_dir.resolve()),
            "saved": saved,
            # The two questions the old app could not answer at all: is the agent wired
            # up, and what else is it allowed to reach.
            #
            # Every backend, not just the selected one. The page used to render one
            # panel headed "Claude" and nothing else, so an operator who had ChatGPT
            # and MiniMax available saw no sign either existed and reported them as
            # missing from the build. What each one *is* comes from the server here;
            # whether each one is signed in is asked per agent from the browser, so a
            # CLI that hangs delays its own card instead of the whole page.
            "agents": engines.catalogue(),
            "engine": engines.current().key,
            # Without `cli_held`, so this render spawns nothing. Reading what the
            # Claude CLI holds means `claude mcp list`, and a subprocess during a page
            # render lets one wedged CLI hold up every other panel on it. The page
            # re-asks `/api/connectors` from the browser and marks the rows there.
            "connectors": connectors.Store.load().listing(),
        },
    )


@router.get("/api/encoders", include_in_schema=False)
def encoders(user: User = Depends(current_user)) -> dict:
    """What this machine can actually encode with, proved rather than listed.

    A separate endpoint from the settings page because the answer costs a subprocess per
    encoder, and the page already refuses to spawn one during a render — a wedged probe
    would hold up every other panel on it.

    The distinction it reports is the one that matters and the one `ffmpeg -encoders`
    gets wrong: a great many builds carry `h264_nvenc` on machines with no NVIDIA driver,
    so the encoder is listed, is selectable, and fails at the first clip with
    `Cannot load libcuda.so.1`. `available_encoders` settles it by encoding a frame.
    """
    from ..render.ffmpeg import (
        DEFAULT_ENCODER,
        ENCODERS,
        available_encoders,
        resolve_encoder,
    )

    can = available_encoders()
    asked = str(get_settings().video_encoder or "")
    return {
        "chosen": asked or DEFAULT_ENCODER,
        # Resolved, not echoed. An operator who set `nvidia` on a machine that cannot run
        # it should read that the render is on the CPU, not that it is on the GPU.
        "will_use": resolve_encoder(asked),
        "encoders": [
            {"key": key, "label": spec["label"], "note": spec["note"],
             "available": bool(can.get(key))}
            for key, spec in ENCODERS.items()
        ],
    }


@router.post("/settings/provider")
def save_provider_key(
    provider: str = Form(...),
    api_key: str = Form(""),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    known = {entry[2] for entry in CATALOGUE.values() if entry[2]}
    if provider not in known:
        raise HTTPException(status_code=400, detail=f"unknown provider {provider!r}")

    row = session.execute(
        select(ProviderKey).where(
            ProviderKey.user_id == user.id, ProviderKey.provider == provider)
    ).scalar_one_or_none()

    if not api_key.strip():
        # An empty submit means "disconnect", which has to be possible — a key that
        # can be set and never cleared is a key you have to edit the database to fix.
        if row is not None:
            session.delete(row)
            session.commit()
        return RedirectResponse(f"/settings?saved=removed+{provider}", 303)

    if row is None:
        row = ProviderKey(user_id=user.id, provider=provider)
        session.add(row)
    row.ciphertext = encrypt(api_key.strip())
    row.masked = mask(api_key.strip())
    row.fingerprint = fingerprint(api_key.strip())
    session.commit()
    log.info("provider key saved for %s", provider)
    return RedirectResponse(f"/settings?saved={provider}", 303)


@router.post("/settings/instance")
def save_instance_settings(
    provider_mode: str = Form("mock"),
    _user: User = Depends(current_user),
    **_form,
) -> RedirectResponse:
    """Switch between mock and live, and persist it for the next launch."""
    settings = get_settings()
    mode = "live" if provider_mode == "live" else "mock"
    settings.provider_mode = mode  # type: ignore[assignment]
    write_env(Path.cwd(), {"FORGECAST_PROVIDER_MODE": mode})
    log.info("provider mode set to %s", mode)
    return RedirectResponse(f"/settings?saved=mode+{mode}", 303)


@router.post("/settings/env")
def save_env_setting(
    name: str = Form(...),
    value: str = Form(""),
    _user: User = Depends(current_user),
) -> RedirectResponse:
    allowed = {field["key"] for field in ENV_FIELDS}
    if name not in allowed:
        raise HTTPException(status_code=400, detail=f"unknown setting {name!r}")

    settings = get_settings()
    attribute = name.removeprefix("FORGECAST_").lower()
    setattr(settings, attribute, value.strip())
    write_env(Path.cwd(), {name: value.strip()})
    return RedirectResponse(f"/settings?saved={name}", 303)
