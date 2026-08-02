"""Turning a measured outlier into transferable angles and titles.

## What is being asked for, and what is not

The model is not asked whether the source video did well — that was measured before it
was ever shown to the model. It is asked the only question arithmetic cannot answer:
*what is transferable about it*, and what to make instead.

That distinction is what keeps the output useful. A model asked "find me good video
ideas" produces plausible titles unattached to anything. A model handed one video that
demonstrably beat its cohort by a measured multiple, and asked what mechanism made it
work, produces angles you can argue with.

## Why the reply is structured

Three fields per idea — the angle, the title, and *why this transfers* — because the
reasoning is the part the operator judges. A bare list of titles gives nothing to
disagree with, so every one looks equally good, which means the list is worthless.
"""

from __future__ import annotations

import json
import re

# Character budget for a title. Beyond this it is truncated in search results and on
# mobile, which is where most of the impressions are.
MAX_TITLE_CHARS = 70

TITLE_INSTRUCTIONS = """A video in this niche measurably outperformed its cohort. Work
out what is transferable about it, then propose titles for videos this channel could
actually make.

Return JSON: {"mechanism", "transferable", "avoid", "ideas"}

  mechanism     one sentence: what made the source video work. Be specific about the
                mechanism — a curiosity gap, a stake the viewer shares, a number that
                reframes something familiar — not "it was engaging".
  transferable  array of 2-4 strings: what carries over to a different topic.
  avoid         array of 1-3 strings: what about the source is NOT transferable —
                a one-off news peg, a named person's audience, a format this channel
                cannot produce.
  ideas         array of 5-7 objects, each:
                  angle    what the video is actually about, one line
                  title    under 70 characters, no year stamp, no clickbait the video
                           cannot deliver
                  why      why this inherits the source's mechanism

Rules for titles:
  - Specific over general. A number, a name, or a concrete claim beats a category.
  - The video must be able to deliver what the title promises. A title the body does
    not pay off costs more in retention than it gains in clicks.
  - No "you won't believe", no "ultimate guide", no year stamps — these read as
    machine-written and date instantly.
  - Do not copy the source title with words swapped. Inherit the mechanism, not the
    sentence."""


def parse_ideas(text: str) -> dict:
    """Read the model's reply, tolerating the ways models wrap JSON.

    Fenced blocks and a sentence of preamble are both common enough that failing on
    them would make the feature unreliable for no reason. A reply that genuinely is not
    JSON comes back as an empty result with the raw text attached, so the operator can
    see what happened rather than getting a silent blank panel.
    """
    stripped = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    if not stripped.startswith("{"):
        brace = stripped.find("{")
        if brace >= 0:
            stripped = stripped[brace:]

    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return {"mechanism": "", "transferable": [], "avoid": [], "ideas": [],
                "error": "the model did not return JSON", "raw": (text or "")[:600]}

    if not isinstance(payload, dict):
        return {"mechanism": "", "transferable": [], "avoid": [], "ideas": [],
                "error": "expected a JSON object"}

    ideas = []
    for entry in payload.get("ideas") or []:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        ideas.append({
            "angle": str(entry.get("angle") or "").strip(),
            "title": title,
            "why": str(entry.get("why") or "").strip(),
            # Flagged rather than truncated: the operator may want the long version and
            # shorten it themselves, and silently cutting a title mid-word is worse.
            "too_long": len(title) > MAX_TITLE_CHARS,
        })

    def strings(key: str) -> list[str]:
        value = payload.get(key)
        if isinstance(value, str):
            return [value]
        return [str(item) for item in (value or []) if str(item).strip()]

    return {
        "mechanism": str(payload.get("mechanism") or "").strip(),
        "transferable": strings("transferable"),
        "avoid": strings("avoid"),
        "ideas": ideas,
    }
