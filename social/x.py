#!/usr/bin/env python3
"""X (Twitter) access for the agent, via the official API v2.

Two credential levels:
  * X_BEARER_TOKEN                     -> app-only reads (lookup, search, timelines)
  * X_API_KEY/SECRET + X_ACCESS_TOKEN/SECRET
                                       -> user context (post, read your own
                                          timeline/DM-scoped endpoints)

Read access depends on your developer tier. The free tier is mainly write plus a
very small read quota; timeline and recent-search reads generally need a paid
tier. A 403 with "client-not-enrolled" means the endpoint is above your tier —
that is a billing state, not a bug in this file. Current limits and prices:
https://developer.x.com/en/portal/products

OAuth 1.0a is signed here with stdlib hmac/hashlib so this file has no
dependency beyond `requests`.

CLI:
    python3 social/x.py whoami
    python3 social/x.py user elonmusk
    python3 social/x.py tweets elonmusk --limit 10
    python3 social/x.py search "faceless youtube" --limit 20
    python3 social/x.py post "hello world"        # needs user-context creds
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import sys
import time
from urllib.parse import quote, urlencode, urlparse, urlunparse

import requests

from _env import load_env, require

API = "https://api.x.com/2"

TWEET_FIELDS = "created_at,public_metrics,lang,conversation_id,referenced_tweets,entities"
USER_FIELDS = "created_at,description,public_metrics,verified,location,profile_image_url"


# --------------------------------------------------------------------------
# OAuth 1.0a (user context)
# --------------------------------------------------------------------------
def _pct(value: str) -> str:
    return quote(str(value), safe="~-._")


def _oauth1_header(method: str, url: str, query: dict[str, str]) -> str:
    """Build an OAuth 1.0a Authorization header. Per spec, a JSON request body
    is not part of the signature base string — only OAuth params and the query
    string are, which is what the API v2 JSON endpoints expect."""
    load_env()
    key, key_secret, token, token_secret = require(
        "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"
    )

    oauth = {
        "oauth_consumer_key": key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }

    all_params = {**{k: str(v) for k, v in query.items()}, **oauth}
    encoded = sorted((_pct(k), _pct(v)) for k, v in all_params.items())
    param_string = "&".join(f"{k}={v}" for k, v in encoded)

    parts = urlparse(url)
    base_url = urlunparse((parts.scheme, parts.netloc, parts.path, "", "", ""))
    base = f"{method.upper()}&{_pct(base_url)}&{_pct(param_string)}"
    signing_key = f"{_pct(key_secret)}&{_pct(token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()

    oauth["oauth_signature"] = signature
    return "OAuth " + ", ".join(
        f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
    )


# --------------------------------------------------------------------------
# Request plumbing
# --------------------------------------------------------------------------
def _explain(resp: requests.Response) -> str:
    hint = ""
    if resp.status_code == 401:
        hint = ("\nHint: bearer token is missing, wrong, or regenerated. "
                "Copy it fresh from developer.x.com -> Keys and tokens.")
    elif resp.status_code == 403:
        hint = ("\nHint: 403 usually means this endpoint is above your API tier "
                "(look for 'client-not-enrolled'), or the app lacks Read/Write "
                "permission. Check your product tier in the developer portal.")
    elif resp.status_code == 429:
        reset = resp.headers.get("x-rate-limit-reset")
        when = ""
        if reset:
            when = f" Window resets at epoch {reset}."
        hint = f"\nHint: rate limited.{when} Free/Basic tiers have small windows."
    return f"X API {resp.status_code}: {resp.text[:600]}{hint}"


def call(path: str, method: str = "GET", user_context: bool = False,
         body: dict | None = None, **params) -> dict:
    load_env()
    url = f"{API}{path}"
    query = {k: v for k, v in params.items() if v is not None}

    if user_context:
        headers = {"Authorization": _oauth1_header(method, url, query)}
    else:
        (bearer,) = require("X_BEARER_TOKEN")
        headers = {"Authorization": f"Bearer {bearer}"}

    if body is not None:
        headers["Content-Type"] = "application/json"

    full = url + ("?" + urlencode(query) if query else "")
    resp = requests.request(method, full, headers=headers, json=body, timeout=30)
    if not resp.ok:
        raise SystemExit(_explain(resp))
    return resp.json()


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
def user(username: str) -> dict:
    data = call(f"/users/by/username/{username.lstrip('@')}",
                **{"user.fields": USER_FIELDS})
    return data.get("data", data)


def tweets(username: str, limit: int = 10) -> list[dict]:
    uid = user(username)["id"]
    data = call(f"/users/{uid}/tweets",
                max_results=max(5, min(limit, 100)),
                **{"tweet.fields": TWEET_FIELDS})
    return data.get("data", [])


def search(query: str, limit: int = 10) -> list[dict]:
    data = call("/tweets/search/recent", query=query,
                max_results=max(10, min(limit, 100)),
                **{"tweet.fields": TWEET_FIELDS})
    return data.get("data", [])


def tweet(tweet_id: str) -> dict:
    data = call(f"/tweets/{tweet_id}", **{"tweet.fields": TWEET_FIELDS})
    return data.get("data", data)


def whoami() -> dict:
    """Identity of the authenticated account — requires user-context creds."""
    data = call("/users/me", user_context=True, **{"user.fields": USER_FIELDS})
    return data.get("data", data)


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------
def post(text: str) -> dict:
    data = call("/tweets", method="POST", user_context=True, body={"text": text})
    return data.get("data", data)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="X (Twitter) access via API v2")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")

    sp = sub.add_parser("user")
    sp.add_argument("username")

    sp = sub.add_parser("tweets")
    sp.add_argument("username")
    sp.add_argument("--limit", type=int, default=10)

    sp = sub.add_parser("search")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)

    sp = sub.add_parser("tweet")
    sp.add_argument("tweet_id")

    sp = sub.add_parser("post")
    sp.add_argument("text")

    a = p.parse_args(argv)

    if a.cmd == "whoami":
        result: object = whoami()
    elif a.cmd == "user":
        result = user(a.username)
    elif a.cmd == "tweets":
        result = tweets(a.username, a.limit)
    elif a.cmd == "search":
        result = search(a.query, a.limit)
    elif a.cmd == "tweet":
        result = tweet(a.tweet_id)
    elif a.cmd == "post":
        result = post(a.text)
    else:
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
