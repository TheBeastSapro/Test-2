#!/usr/bin/env python3
"""Reddit access for the agent.

Anonymous reddit.com JSON endpoints return HTTP 403 from this container's
datacenter IP range, which is why unauthenticated reads fail here. The OAuth
API works fine from the same IP, so authentication — not a proxy or cookies —
is what unblocks Reddit.

Two credential levels:
  * client_id + client_secret          -> app-only token, public read access
  * ... plus username + password       -> account-scoped access (saved, votes,
                                          inbox, submitting)

CLI:
    python3 social/reddit.py whoami
    python3 social/reddit.py top youtube --limit 10 --time week
    python3 social/reddit.py search "faceless channel" --subreddit NewTubers
    python3 social/reddit.py comments <post_id>
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import requests

from _env import get, load_env, require

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"

_token_cache: dict[str, object] = {}


def _user_agent() -> str:
    ua = get("REDDIT_USER_AGENT")
    if not ua:
        raise SystemExit(
            "REDDIT_USER_AGENT is required by Reddit's API rules.\n"
            "Set it in .env, e.g. linux:sapro-agent:0.1 (by /u/yourname)"
        )
    return ua


def get_token() -> tuple[str, str]:
    """Return (token, scope_label). Caches until ~1 min before expiry."""
    load_env()
    now = time.time()
    if _token_cache.get("token") and float(_token_cache.get("expires", 0)) > now:
        return str(_token_cache["token"]), str(_token_cache["scope"])

    client_id, client_secret = require("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
    username, password = get("REDDIT_USERNAME"), get("REDDIT_PASSWORD")

    if username and password:
        data = {"grant_type": "password", "username": username, "password": password}
        scope = f"account:{username}"
    else:
        data = {"grant_type": "client_credentials"}
        scope = "app-only (public read)"

    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data=data,
        headers={"User-Agent": _user_agent()},
        timeout=30,
    )
    if resp.status_code == 401:
        raise SystemExit(
            "Reddit returned 401 on the token request.\n"
            "  - Check REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET.\n"
            "  - The app at reddit.com/prefs/apps must be type 'script'.\n"
            "  - For the password grant, 2FA must be off, or send the password "
            "as 'password:123456' with your current OTP."
        )
    resp.raise_for_status()
    payload = resp.json()
    if "access_token" not in payload:
        raise SystemExit(f"No access_token in Reddit response: {payload}")

    _token_cache.update(
        token=payload["access_token"],
        scope=scope,
        expires=now + float(payload.get("expires_in", 3600)) - 60,
    )
    return payload["access_token"], scope


def call(path: str, **params) -> dict:
    token, _ = get_token()
    resp = requests.get(
        f"{API}{path}",
        headers={"Authorization": f"bearer {token}", "User-Agent": _user_agent()},
        params={k: v for k, v in params.items() if v is not None},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _posts(listing: dict) -> list[dict]:
    out = []
    for child in listing.get("data", {}).get("children", []):
        d = child.get("data", {})
        out.append(
            {
                "id": d.get("id"),
                "title": d.get("title"),
                "subreddit": d.get("subreddit"),
                "author": d.get("author"),
                "score": d.get("score"),
                "num_comments": d.get("num_comments"),
                "upvote_ratio": d.get("upvote_ratio"),
                "created_utc": d.get("created_utc"),
                "url": d.get("url"),
                "permalink": "https://reddit.com" + d.get("permalink", ""),
                "selftext": (d.get("selftext") or "")[:2000],
                "flair": d.get("link_flair_text"),
                "over_18": d.get("over_18"),
            }
        )
    return out


def top(subreddit: str, limit: int = 25, time_filter: str = "week") -> list[dict]:
    return _posts(call(f"/r/{subreddit}/top", limit=limit, t=time_filter))


def hot(subreddit: str, limit: int = 25) -> list[dict]:
    return _posts(call(f"/r/{subreddit}/hot", limit=limit))


def new(subreddit: str, limit: int = 25) -> list[dict]:
    return _posts(call(f"/r/{subreddit}/new", limit=limit))


def search(query: str, subreddit: str | None = None, limit: int = 25,
           sort: str = "relevance", time_filter: str = "all") -> list[dict]:
    path = f"/r/{subreddit}/search" if subreddit else "/search"
    params = {"q": query, "limit": limit, "sort": sort, "t": time_filter}
    if subreddit:
        params["restrict_sr"] = "true"
    return _posts(call(path, **params))


def comments(post_id: str, limit: int = 50) -> list[dict]:
    """Top-level comments for a post id (the base36 id, not the full URL)."""
    token, _ = get_token()
    resp = requests.get(
        f"{API}/comments/{post_id}",
        headers={"Authorization": f"bearer {token}", "User-Agent": _user_agent()},
        params={"limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    listings = resp.json()
    if len(listings) < 2:
        return []
    out = []
    for child in listings[1].get("data", {}).get("children", []):
        d = child.get("data", {})
        if d.get("body"):
            out.append(
                {
                    "author": d.get("author"),
                    "score": d.get("score"),
                    "body": d.get("body")[:2000],
                    "created_utc": d.get("created_utc"),
                }
            )
    return out


def whoami() -> dict:
    """Account identity — only works with the password grant."""
    token, scope = get_token()
    if scope.startswith("app-only"):
        return {
            "scope": scope,
            "note": "App-only token: public reads work, but there is no user "
                    "identity. Set REDDIT_USERNAME/REDDIT_PASSWORD in .env for "
                    "account-scoped access.",
        }
    data = call("/api/v1/me")
    return {
        "scope": scope,
        "name": data.get("name"),
        "created_utc": data.get("created_utc"),
        "total_karma": data.get("total_karma"),
        "has_mail": data.get("has_mail"),
    }


def saved(limit: int = 25) -> list[dict]:
    """Your saved posts — requires the password grant."""
    _, scope = get_token()
    if scope.startswith("app-only"):
        raise SystemExit(
            "Reading saved posts needs account access. Set REDDIT_USERNAME and "
            "REDDIT_PASSWORD in .env."
        )
    username = get("REDDIT_USERNAME")
    return _posts(call(f"/user/{username}/saved", limit=limit))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reddit access via OAuth")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")

    for name in ("top", "hot", "new"):
        sp = sub.add_parser(name)
        sp.add_argument("subreddit")
        sp.add_argument("--limit", type=int, default=25)
        if name == "top":
            sp.add_argument(
                "--time", default="week",
                choices=["hour", "day", "week", "month", "year", "all"],
            )

    sp = sub.add_parser("search")
    sp.add_argument("query")
    sp.add_argument("--subreddit")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--sort", default="relevance",
                    choices=["relevance", "hot", "top", "new", "comments"])
    sp.add_argument("--time", default="all",
                    choices=["hour", "day", "week", "month", "year", "all"])

    sp = sub.add_parser("comments")
    sp.add_argument("post_id")
    sp.add_argument("--limit", type=int, default=50)

    sp = sub.add_parser("saved")
    sp.add_argument("--limit", type=int, default=25)

    a = p.parse_args(argv)

    if a.cmd == "whoami":
        result: object = whoami()
    elif a.cmd == "top":
        result = top(a.subreddit, a.limit, a.time)
    elif a.cmd == "hot":
        result = hot(a.subreddit, a.limit)
    elif a.cmd == "new":
        result = new(a.subreddit, a.limit)
    elif a.cmd == "search":
        result = search(a.query, a.subreddit, a.limit, a.sort, a.time)
    elif a.cmd == "comments":
        result = comments(a.post_id, a.limit)
    elif a.cmd == "saved":
        result = saved(a.limit)
    else:
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
