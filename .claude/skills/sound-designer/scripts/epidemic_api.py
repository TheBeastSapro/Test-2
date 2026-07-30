#!/usr/bin/env python3
"""epidemic_api.py — talk to Epidemic Sound over HTTPS, with no MCP connector.

Why this exists: the claude.ai MCP connector for Epidemic dropped in and out
repeatedly across one session, taking searching and downloading with it and
stalling the work each time. The connector is not the only way in. Epidemic's
MCP endpoint also accepts a plain bearer token, so the same catalogue is
reachable with an ordinary HTTPS request from inside the container, which cannot
be disconnected by anything outside it.

Setup, once:

  1. Generate a key at https://www.epidemicsound.com/account/api-keys
     (It is tied to your own Epidemic account -- no partnership needed. The
     separate Partner Content API at partner-content-api.epidemicsound.com does
     require a partnership agreement; this does not.)
  2. Put it in the environment as EPIDEMIC_SOUND_API_KEY. In Claude Code on the
     web that is the cloud environment's environment-variables setting. Never
     paste it into a chat -- chats are stored, environments are not.
  3. Keys expire after 30 days. When calls start returning 401, regenerate.

Usage:
  epidemic_api.py tools                        # list what the server exposes
  epidemic_api.py sfx "sword hits wooden shield" [-n 12] [--min-ms 200] [--max-ms 4000]
  epidemic_api.py music "cinematic tension drums" [-n 8]
  epidemic_api.py url  <sound-effect-id>       # resolve a download url
  epidemic_api.py pull <id> [<id> ...] --out DIR [--name PREFIX]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://www.epidemicsound.com/a/mcp-service/mcp"
KEY_ENV = ("EPIDEMIC_SOUND_API_KEY", "EPIDEMIC_API_KEY")


def api_key() -> str:
    for name in KEY_ENV:
        v = os.environ.get(name)
        if v:
            return v.strip()
    raise SystemExit(
        "[epidemic] no API key in the environment.\n"
        f"           Set one of {' or '.join(KEY_ENV)} to a key from\n"
        "           https://www.epidemicsound.com/account/api-keys\n"
        "           (In Claude Code on the web: the cloud environment's\n"
        "           environment-variables setting. Do not paste it into chat.)")


class Client:
    """Minimal MCP streamable-HTTP client: initialize, then call tools."""

    def __init__(self, key: str, endpoint: str = ENDPOINT):
        self.key = key
        self.endpoint = endpoint
        self.session = None
        self._id = 0

    def _post(self, payload: dict, notify: bool = False):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", **({} if notify else {"id": self._id}),
                           **payload}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        # A streamable-HTTP MCP server may answer as JSON or as an SSE stream,
        # so both have to be acceptable or it returns 406.
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Authorization", f"Bearer {self.key}")
        if self.session:
            req.add_header("Mcp-Session-Id", self.session)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    self.session = sid
                raw = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code == 401:
                raise SystemExit("[epidemic] 401 unauthorized — the key is wrong or "
                                 "expired. Keys last 30 days; regenerate at "
                                 "https://www.epidemicsound.com/account/api-keys")
            raise SystemExit(f"[epidemic] HTTP {e.code} from the server: {detail}")
        if notify:
            return None
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str):
        """Accept a bare JSON body or an SSE stream of `data:` lines."""
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith("{"):
            return json.loads(raw)
        out = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        out = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
        if out is None:
            raise SystemExit(f"[epidemic] could not parse the response: {raw[:300]}")
        return out

    def initialize(self):
        r = self._post({"method": "initialize", "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "sound-designer", "version": "1.0"}}})
        self._post({"method": "notifications/initialized", "params": {}}, notify=True)
        return (r or {}).get("result", {})

    def list_tools(self):
        return (self._post({"method": "tools/list", "params": {}}) or {}) \
            .get("result", {}).get("tools", [])

    def call(self, name: str, arguments: dict):
        r = self._post({"method": "tools/call",
                        "params": {"name": name, "arguments": arguments}}) or {}
        if "error" in r:
            raise SystemExit(f"[epidemic] {name} failed: {r['error']}")
        res = r.get("result", {})
        # tool results arrive as content blocks; unwrap the JSON payload
        for block in res.get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    return {"text": block["text"]}
        return res


def flatten(payload: dict, kind: str) -> list[dict]:
    """Pull the useful fields out of the GraphQL-shaped search response."""
    node_key = {"sfx": "soundEffects", "music": "recordings"}[kind]
    inner = {"sfx": "soundEffect", "music": "recording"}[kind]
    nodes = (payload.get("data", {}) or {}).get(node_key, {}).get("nodes", []) or []
    out = []
    for n in nodes:
        e = n.get(inner, n)
        af = e.get("audioFile") or {}
        out.append({"id": e.get("id"), "title": e.get("title"),
                    "ms": af.get("durationInMilliseconds"),
                    "lqmp3": af.get("lqmp3Url")})
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools")
    for c in ("sfx", "music"):
        p = sub.add_parser(c)
        p.add_argument("term")
        p.add_argument("-n", type=int, default=12)
        p.add_argument("--min-ms", type=int)
        p.add_argument("--max-ms", type=int)
    p = sub.add_parser("url")
    p.add_argument("id")
    p = sub.add_parser("pull")
    p.add_argument("ids", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--name", default="sfx")
    args = ap.parse_args()

    c = Client(api_key())
    info = c.initialize()
    if args.cmd == "tools":
        print(f"[epidemic] connected to {info.get('serverInfo', {}).get('name', '?')}")
        for t in c.list_tools():
            print(f"  {t.get('name')}")
        return

    if args.cmd in ("sfx", "music"):
        q = {"term": args.term}
        f = {}
        if args.min_ms or args.max_ms:
            f["duration"] = {k: v for k, v in (("min", args.min_ms),
                                               ("max", args.max_ms)) if v}
        tool = "SearchSoundEffects" if args.cmd == "sfx" else "SearchRecordings"
        # query/filter/options are OBJECTS, not JSON strings. Passing them
        # stringified returns GRAPHQL_VALIDATION_FAILED on ['variable','query']
        # with no hint that the type is the problem -- the tool's own
        # inputSchema ($ref SoundEffectsQuery) is what says so.
        payload = c.call(tool, {"query": q, "first": args.n,
                                **({"filter": f} if f else {})})
        rows = flatten(payload, args.cmd)
        if not rows:
            print(f"[epidemic] nothing matched. raw: {str(payload)[:300]}")
            return
        for r in rows:
            ms = f"{r['ms']/1000:.2f}s" if r.get("ms") else "?"
            print(f"  {r['id']}  {ms:>8}  {r['title']}")
        return

    ids = [args.id] if args.cmd == "url" else args.ids
    if args.cmd == "pull":
        os.makedirs(args.out, exist_ok=True)
    for i, sid in enumerate(ids, 1):
        res = c.call("DownloadSoundEffect", {"id": sid,
                                            "options": {"fileType": "WAV"}})
        url = ((res.get("data", {}) or {}).get("soundEffectDownload", {})
               or {}).get("assetUrl")
        if not url:
            print(f"[epidemic] {sid}: no assetUrl ({str(res)[:200]})")
            continue
        if args.cmd == "url":
            print(url)
            continue
        dst = os.path.join(args.out, f"{args.name}_{i:02d}.wav")
        # curl, not ffmpeg: ffmpeg re-encodes the %-escapes in a signed CDN URL
        # and the signature stops matching, which returns 403.
        subprocess.run(["curl", "-sS", "-f", "-o", dst, url], check=True)
        print(f"  -> {dst}")


if __name__ == "__main__":
    sys.exit(main())
