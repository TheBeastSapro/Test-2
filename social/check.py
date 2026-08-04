#!/usr/bin/env python3
"""Credential doctor. Says exactly what is configured, what is missing, and
whether each credential actually works from this container.

    python3 social/check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

from _env import ENV_FILE, get, load_env

OK, NO, WARN = "  OK  ", " FAIL ", " WARN "


def mask(value: str) -> str:
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))


def check_network() -> None:
    print("\n== Network reachability ==")
    targets = [
        ("reddit anonymous JSON", "https://www.reddit.com/r/youtube/top.json?limit=1"),
        ("reddit OAuth endpoint", "https://www.reddit.com/api/v1/access_token"),
        ("x.com", "https://x.com/robots.txt"),
        ("api.x.com", "https://api.x.com/2/tweets"),
    ]
    for label, url in targets:
        try:
            code = requests.get(url, timeout=20,
                                headers={"User-Agent": "Mozilla/5.0"}).status_code
        except Exception as exc:  # noqa: BLE001
            line(NO, label, f"unreachable: {type(exc).__name__}")
            continue
        if code in (401, 403) and "access_token" in url:
            line(OK, label, f"HTTP {code} — reachable, needs credentials")
        elif code == 403 and "reddit.com/r/" in url:
            line(WARN, label,
                 "HTTP 403 — anonymous reads are blocked from this datacenter "
                 "IP. Expected. Use the OAuth path below.")
        elif code == 401:
            line(OK, label, f"HTTP {code} — reachable, needs credentials")
        elif code < 400:
            line(OK, label, f"HTTP {code}")
        else:
            line(WARN, label, f"HTTP {code}")


def check_reddit() -> None:
    print("\n== Reddit ==")
    cid, csec = get("REDDIT_CLIENT_ID"), get("REDDIT_CLIENT_SECRET")
    ua = get("REDDIT_USER_AGENT")
    user, pwd = get("REDDIT_USERNAME"), get("REDDIT_PASSWORD")

    line(OK if cid else NO, "REDDIT_CLIENT_ID", mask(cid))
    line(OK if csec else NO, "REDDIT_CLIENT_SECRET", mask(csec))
    line(OK if ua else NO, "REDDIT_USER_AGENT", ua or "(unset — required)")
    line(OK if user else WARN, "REDDIT_USERNAME",
         user or "(unset — public read-only mode)")
    line(OK if pwd else WARN, "REDDIT_PASSWORD",
         mask(pwd) if pwd else "(unset — public read-only mode)")

    if not (cid and csec and ua):
        print("\n  To set up (free, 2 minutes):")
        print("   1. https://www.reddit.com/prefs/apps -> 'create another app'")
        print("   2. Type: script.  Redirect uri: http://localhost:8080")
        print("   3. client_id is the string under the app name;")
        print("      client_secret is the 'secret' field")
        print(f"   4. Put both in {ENV_FILE} with a REDDIT_USER_AGENT")
        return

    try:
        import reddit as reddit_mod
        token, scope = reddit_mod.get_token()
        line(OK, "token request", f"got token, scope = {scope}")
    except SystemExit as exc:
        line(NO, "token request", str(exc).replace("\n", " "))
        return
    except Exception as exc:  # noqa: BLE001
        line(NO, "token request", f"{type(exc).__name__}: {exc}")
        return

    try:
        posts = reddit_mod.top("youtube", limit=1, time_filter="week")
        if posts:
            line(OK, "live read", f"r/youtube top: {posts[0]['title'][:60]!r}")
        else:
            line(WARN, "live read", "authenticated but returned no posts")
    except Exception as exc:  # noqa: BLE001
        line(NO, "live read", f"{type(exc).__name__}: {exc}")

    if not (user and pwd):
        return
    try:
        me = reddit_mod.whoami()
        line(OK, "account access", f"u/{me.get('name')} karma={me.get('total_karma')}")
    except Exception as exc:  # noqa: BLE001
        line(NO, "account access", f"{type(exc).__name__}: {exc}")


def check_x() -> None:
    print("\n== X / Twitter ==")
    bearer = get("X_BEARER_TOKEN")
    quad = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    line(OK if bearer else NO, "X_BEARER_TOKEN", mask(bearer))
    for name in quad:
        val = get(name)
        line(OK if val else WARN, name, mask(val) or "(unset)")

    if not bearer and not all(get(n) for n in quad):
        print("\n  To set up:")
        print("   1. https://developer.x.com -> create a project + app")
        print("   2. Keys and tokens -> copy the Bearer Token")
        print(f"   3. Put it in {ENV_FILE} as X_BEARER_TOKEN")
        print("   4. For posting, also generate Access Token + Secret with")
        print("      Read and Write permission, and copy the API Key/Secret")
        print("   NOTE: read endpoints (search, timelines) generally require a")
        print("   paid tier. A 403 'client-not-enrolled' is a tier limit.")
        return

    if bearer:
        try:
            import x as x_mod
            u = x_mod.user("x")
            line(OK, "live read (app-only)",
                 f"@{u.get('username')} followers="
                 f"{u.get('public_metrics', {}).get('followers_count')}")
        except SystemExit as exc:
            line(NO, "live read (app-only)", str(exc).replace("\n", " ")[:300])
        except Exception as exc:  # noqa: BLE001
            line(NO, "live read (app-only)", f"{type(exc).__name__}: {exc}")

    if all(get(n) for n in quad):
        try:
            import x as x_mod
            me = x_mod.whoami()
            line(OK, "user context", f"authenticated as @{me.get('username')}")
        except SystemExit as exc:
            line(NO, "user context", str(exc).replace("\n", " ")[:300])
        except Exception as exc:  # noqa: BLE001
            line(NO, "user context", f"{type(exc).__name__}: {exc}")


def check_hygiene() -> None:
    print("\n== Secret hygiene ==")
    root = Path(__file__).resolve().parent.parent
    gitignore = root / ".gitignore"
    if gitignore.exists() and ".env" in gitignore.read_text():
        line(OK, ".gitignore", "covers .env and cookie files")
    else:
        line(NO, ".gitignore", "does NOT protect .env — fix before adding secrets")

    if ENV_FILE.exists():
        line(OK, ".env", f"present at {ENV_FILE}")
        mode = oct(ENV_FILE.stat().st_mode)[-3:]
        line(OK if mode == "600" else WARN, ".env permissions",
             f"{mode}" + ("" if mode == "600" else " — consider chmod 600"))
    else:
        line(WARN, ".env", f"not created yet. cp {root}/.env.example {ENV_FILE}")

    print("\n  Reminder: TheBeastSapro/Test-2 is a PUBLIC repo. Never commit .env")
    print("  or cookie files, and never paste credentials into the chat — the")
    print("  chat transcript is stored. Write them into .env directly.")


def main() -> int:
    load_env()
    print("=" * 70)
    print("Social access check — Reddit + X")
    print("=" * 70)
    check_network()
    check_reddit()
    check_x()
    check_hygiene()
    print("\nDone. See social/README.md for the full setup walkthrough.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
