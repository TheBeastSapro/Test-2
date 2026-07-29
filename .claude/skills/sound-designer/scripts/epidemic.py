#!/usr/bin/env python3
"""epidemic.py — asset acquisition + automatic track selection.

This is the layer that makes scoring the video *my* job rather than a
shopping list handed to Sapro. It turns a cue sheet into finished, filled
`assets/` with no manual picking:

    plan     cue sheet            -> per-cue search briefs (what to ask Epidemic)
    select   candidates + cues    -> the winning track per cue, scored and explained
    fetch    winners              -> assets/<cue id>.wav + cue sheet asset paths

Two intake routes, because Epidemic can be reached two ways:

  A. MCP  — Claude calls the Epidemic MCP tools (soundmatch / semantic search /
     track-versions), dumps the raw results to JSON, and pipes them in:
         epidemic.py select --cues cues.json --candidates mcp_results.json
     The MCP is reached by Claude's backend, so this works even when this
     container has no direct egress to epidemicsound.com.

  B. Direct API — needs EPIDEMIC_API_KEY (or client id/secret) in the env AND
     network egress to partnerapi.epidemicsound.com:
         epidemic.py search --cues cues.json --out candidates.json

Candidate JSON is a dict keyed by cue id, each holding a list of track objects.
Unknown fields are ignored, so raw MCP output can be passed through untouched:

  { "m1": [ { "id": "...", "title": "...", "bpm": 84, "energy": 0.4,
              "duration": 180, "moods": ["warm"], "genres": ["ambient"],
              "hasVocals": false, "url": "https://..." }, ... ] }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

API_BASE = os.environ.get("EPIDEMIC_API_BASE", "https://partnerapi.epidemicsound.com")
API_KEY = os.environ.get("EPIDEMIC_API_KEY", "")

STOP = {"for", "and", "the", "with", "no", "a", "an", "of", "in", "to",
        "video", "explainer", "instrumental", "energy", "vocals"}


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


# ------------------------------------------------------------------ plan

def brief_for(cue: dict, kind: str) -> dict:
    """What we would ask Epidemic for this cue."""
    if kind == "music":
        return {
            "cue": cue["id"], "type": "music",
            "preferred_tool": "soundmatch",
            "soundmatch_slice": [cue["start"], cue["end"]],
            "fallback_tool": "semantic_search",
            "query": cue["epidemic"]["search"],
            "want": {
                "bpm": cue.get("bpm_hint"),
                "energy": cue.get("energy"),
                "min_duration_s": round(cue["dur"], 1),
                "instrumental": True,
            },
            "then": {"tool": "track-versions", "target_duration_s": round(cue["dur"], 1)},
        }
    return {
        "cue": cue["id"], "type": "sfx",
        "preferred_tool": "semantic_search",
        "query": cue["epidemic"]["search"],
        "want": {"max_duration_s": 6 if "riser" in cue.get("kind", "") else 3},
    }


def cmd_plan(args):
    cues = json.load(open(args.cues))
    briefs = [brief_for(m, "music") for m in cues.get("music_sections", [])]
    briefs += [brief_for(s, "sfx") for s in cues.get("sfx_cues", [])]
    json.dump(briefs, open(args.out, "w"), indent=2)
    print(f"[epidemic] {len(briefs)} search briefs -> {args.out}")
    for b in briefs:
        print(f"   {b['cue']:>3} [{b['type']:5}] {b['preferred_tool']:16} {b['query'][:64]}")


# ------------------------------------------------------------------ scoring

def get(t: dict, *names, default=None):
    """Pull a field by any of several likely names (MCP/API shapes vary)."""
    for n in names:
        if n in t and t[n] is not None:
            return t[n]
        low = {k.lower(): v for k, v in t.items()}
        if n.lower() in low and low[n.lower()] is not None:
            return low[n.lower()]
    return default


def normalize(raw):
    """Flatten Epidemic's real MCP/GraphQL shape into flat track dicts.

    Verified against live responses, which look like:
      {"data": {"recordings":   {"nodes": [{"recording":   {...}}]}}}
      {"data": {"soundEffects": {"nodes": [{"soundEffect": {...}}]}}}
    with duration under audioFile.durationInMilliseconds and tags as
    [{displayName, slug}]. Anything already flat passes straight through.
    """
    if isinstance(raw, dict):
        d = raw.get("data", raw)
        for key in ("recordings", "soundEffects", "tracks", "results"):
            if isinstance(d.get(key), dict) and "nodes" in d[key]:
                raw = d[key]["nodes"]
                break
        else:
            raw = raw if isinstance(raw, list) else [raw]

    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        t = item.get("recording") or item.get("soundEffect") or item
        af = t.get("audioFile") or {}
        ms = af.get("durationInMilliseconds")
        tags = []
        for tag in t.get("tags") or []:
            if isinstance(tag, dict):
                tags.append(tag.get("slug") or tag.get("displayName") or "")
            else:
                tags.append(str(tag))
        moods = [m.get("slug") if isinstance(m, dict) else str(m) for m in (t.get("moods") or [])]

        # The `vocals: false` search filter is not airtight — live results still
        # returned a track tagged "vocal presence". Trust the tags over the filter.
        low = " ".join(tags).lower()
        if t.get("vocals") is not None:
            vox = bool(t["vocals"])
        elif "no vocals" in low or "no-vocals" in low:
            vox = False
        elif "vocal" in low:          # "vocal presence", "lead vocals", ...
            vox = True
        else:
            vox = False
        out.append({
            "id": t.get("id"),
            "title": t.get("title") or t.get("name") or "",
            "bpm": t.get("bpm"),
            "energy": t.get("energy"),
            # the search filter already constrains this; default to instrumental
            "hasVocals": vox,
            "duration": (ms / 1000.0) if ms else t.get("duration"),
            "tags": [x for x in tags if x],
            "moods": [x for x in moods if x],
            # no assetUrl until DownloadRecording is called; keep the preview as a fallback
            "url": t.get("assetUrl") or af.get("lqmp3Url") or "",
            "waveform": af.get("waveformUrl") or "",
        })
    return out


def score_music(track: dict, cue: dict) -> tuple[float, list[str]]:
    why, s = [], 0.0

    vocals = get(track, "hasVocals", "has_vocals", "vocals", default=False)
    if vocals:
        s -= 6.0
        why.append("has vocals (bad under VO)")
    else:
        s += 2.0
        why.append("instrumental")

    bpm, want_bpm = get(track, "bpm", "tempo"), cue.get("bpm_hint")
    if bpm and want_bpm:
        d = abs(float(bpm) - float(want_bpm))
        s += max(0.0, 2.5 - d / 12.0)
        why.append(f"{int(float(bpm))}bpm vs ~{want_bpm} target")

    energy, want_e = get(track, "energy", "intensity"), cue.get("energy")
    if energy is not None and want_e is not None:
        e = float(energy)
        if e > 1:
            e /= 100.0
        d = abs(e - float(want_e))
        s += max(0.0, 2.0 - d * 4.0)
        why.append(f"energy {e:.2f} vs {float(want_e):.2f}")

    dur, need = get(track, "duration", "length", "durationSeconds"), cue.get("dur", 0)
    if dur:
        if float(dur) >= float(need) - 1:
            s += 1.2
            why.append("covers the slot")
        else:
            s += 0.3
            why.append("short — needs track-versions or looping")

    tags = set()
    for f in ("moods", "genres", "tags", "mood", "genre"):
        v = get(track, f)
        if isinstance(v, list):
            tags |= {str(x).lower() for x in v}
        elif isinstance(v, str):
            tags |= words(v)
    want_tags = words(cue.get("mood_hint", "")) | words(cue["epidemic"]["search"])
    hit = tags & want_tags
    if hit:
        s += min(2.5, 0.8 * len(hit))
        why.append("matches " + "/".join(sorted(hit)[:3]))

    return s, why


def score_sfx(track: dict, cue: dict) -> tuple[float, list[str]]:
    why, s = [], 0.0
    kind = cue.get("kind", "")
    dur = get(track, "duration", "length", "durationSeconds")
    cap = 6.0 if "riser" in kind else 3.0
    if dur:
        d = float(dur)
        if d <= cap:
            s += 2.0
            why.append(f"{d:.1f}s — tight")
        else:
            s -= min(2.0, (d - cap) / 4.0)
            why.append(f"{d:.1f}s — long for a hit")

    tags = set()
    for f in ("tags", "categories", "moods", "genres"):
        v = get(track, f)
        if isinstance(v, list):
            tags |= {str(x).lower() for x in v}
        elif isinstance(v, str):
            tags |= words(v)
    tags |= words(get(track, "title", "name", default=""))
    hit = tags & (words(kind) | words(cue["epidemic"]["search"]))
    if hit:
        s += min(3.0, 1.0 * len(hit))
        why.append("matches " + "/".join(sorted(hit)[:3]))
    return s, why


def cmd_select(args):
    cues = json.load(open(args.cues))
    cands = json.load(open(args.candidates))
    cands = {k: normalize(v) for k, v in cands.items()}
    picks, used = {}, set()

    def choose(cue, kind):
        pool = cands.get(cue["id"]) or []
        if not pool:
            print(f"   {cue['id']:>3}  no candidates supplied")
            return
        scored = []
        for t in pool:
            sc, why = (score_music if kind == "music" else score_sfx)(t, cue)
            tid = str(get(t, "id", "trackId", "uuid", default=get(t, "title", "name", default="?")))
            # variety: don't reuse the same bed twice in one video
            if kind == "music" and tid in used:
                sc -= 3.0
                why.append("already used elsewhere")
            scored.append((sc, tid, t, why))
        scored.sort(key=lambda x: -x[0])
        best = scored[0]
        if kind == "music":
            used.add(best[1])
        picks[cue["id"]] = {
            "track_id": best[1],
            "title": get(best[2], "title", "name", default=""),
            "url": get(best[2], "url", "downloadUrl", "download_url", "previewUrl", "hls", default=""),
            "score": round(best[0], 2),
            "why": best[3],
            "runners_up": [
                {"track_id": s[1], "title": get(s[2], "title", "name", default=""), "score": round(s[0], 2)}
                for s in scored[1:3]
            ],
        }
        print(f"   {cue['id']:>3}  {best[0]:+5.2f}  {picks[cue['id']]['title'][:38]:38}  {'; '.join(best[3][:3])}")

    print("[epidemic] selecting music")
    for m in cues.get("music_sections", []):
        choose(m, "music")
    print("[epidemic] selecting sfx")
    for s in cues.get("sfx_cues", []):
        choose(s, "sfx")

    json.dump(picks, open(args.out, "w"), indent=2)
    print(f"[epidemic] {len(picks)} picks -> {args.out}")

    if args.manifest:
        man = {k: v["url"] for k, v in picks.items() if v.get("url")}
        json.dump(man, open(args.manifest, "w"), indent=2)
        print(f"[epidemic] {len(man)} download URLs -> {args.manifest}  (feed to fetch.py)")
        missing = [k for k, v in picks.items() if not v.get("url")]
        if missing:
            print(f"[epidemic] NOTE: no URL on {', '.join(missing)} — "
                  "candidate records carried no download/preview link.")


# ------------------------------------------------------------------ direct API

def api(path: str, payload: dict | None = None):
    if not API_KEY:
        sys.exit("[epidemic] EPIDEMIC_API_KEY is not set — use the MCP route "
                 "(`select --candidates`) or set the key in the environment.")
    url = API_BASE.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        sys.exit(f"[epidemic] request to {url} failed: {e}\n"
                 "  If this is a connection/403 error, this environment's network policy "
                 "likely blocks epidemicsound.com — allowlist it, or use the MCP route.")


def cmd_search(args):
    cues = json.load(open(args.cues))
    out = {}
    for m in cues.get("music_sections", []):
        r = api("/v0/partner/search/tracks", {"query": m["epidemic"]["search"], "limit": 10})
        out[m["id"]] = r.get("tracks", r.get("results", r if isinstance(r, list) else []))
        print(f"   {m['id']}: {len(out[m['id']])} candidates")
    for s in cues.get("sfx_cues", []):
        r = api("/v0/partner/search/sound-effects", {"query": s["epidemic"]["search"], "limit": 10})
        out[s["id"]] = r.get("soundEffects", r.get("results", r if isinstance(r, list) else []))
        print(f"   {s['id']}: {len(out[s['id']])} candidates")
    json.dump(out, open(args.out, "w"), indent=2)
    print(f"[epidemic] candidates -> {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="cue sheet -> per-cue search briefs")
    p.add_argument("--cues", required=True)
    p.add_argument("--out", default="briefs.json")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("select", help="candidates -> the winning track per cue")
    p.add_argument("--cues", required=True)
    p.add_argument("--candidates", required=True)
    p.add_argument("--out", default="picks.json")
    p.add_argument("--manifest", help="also write a cue-id -> URL manifest for fetch.py")
    p.set_defaults(fn=cmd_select)

    p = sub.add_parser("search", help="direct Partner API search (needs key + egress)")
    p.add_argument("--cues", required=True)
    p.add_argument("--out", default="candidates.json")
    p.set_defaults(fn=cmd_search)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
