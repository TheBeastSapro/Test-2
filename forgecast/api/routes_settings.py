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
    {"key": "openai", "label": "OpenAI", "unlocks": "an alternative to Claude for the same stages",
     "hint": "sk-…", "where": "platform.openai.com"},
    {"key": "elevenlabs", "label": "ElevenLabs", "unlocks": "narration",
     "hint": "", "where": "elevenlabs.io"},
    {"key": "fal", "label": "fal.ai", "unlocks": "generated stills and B-roll clips",
     "hint": "", "where": "fal.ai/dashboard/keys"},
    {"key": "heygen", "label": "HeyGen", "unlocks": "talking-head avatar passes",
     "hint": "", "where": "heygen.com"},
    {"key": "runway", "label": "Runway", "unlocks": "an alternative video generator",
     "hint": "", "where": "runwayml.com"},
]

# Settings that describe the installation rather than an account.
ENV_FIELDS = [
    {"key": "FORGECAST_YOUTUBE_API_KEY", "label": "YouTube Data API key",
     "unlocks": "pasting a channel or video link on the Research tab",
     "where": "console.cloud.google.com — enable YouTube Data API v3"},
    {"key": "FORGECAST_TAVILY_API_KEY", "label": "Tavily",
     "unlocks": "better research sources (Wikipedia is used without it)",
     "where": "tavily.com"},
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
        value = getattr(settings, attribute, "")
        env_values[field["key"]] = mask(value) if value else ""

    from ..agent import auth as claude_auth
    from ..agent import connectors

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
            # The two questions the old app could not answer at all: is Claude wired
            # up, and what else is the agent allowed to reach.
            "claude": claude_auth.check(),
            "connectors": connectors.Store.load().listing(),
        },
    )


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
