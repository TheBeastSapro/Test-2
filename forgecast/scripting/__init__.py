"""Scripting styles: which method a channel's scripts are written to.

## What a scripting style is, and what it is not

An **editing** style (`forgecast/style/editing.py`) is measured off a video: cuts per
minute, saturation, caption position. Nobody argues with one, because it came off a
reference. A **skill** (`forgecast/skills`) is craft the operator holds and would
otherwise retype every week, loaded by the agent when its `when_to_use` matches.

A **scripting** style is neither. It is the method a script is *written to* — the shape
of the beats, what holds attention between them, which sentences are forbidden — and it
is chosen once per channel and applied to every script that channel ever produces,
without anybody deciding to load it. It has to be a column on the channel for the same
reason `voice_vendor` is: it is a standing decision, not a learned fact, and a run that
silently used a different one is a run whose output nobody can explain.

## Two sources, one selection

* **The house method** (`method.py`) — Forgecast's own, written from first principles,
  shipped in the zip, needs no folder and no configuration. It is the default for every
  channel and it is what any unresolvable selection falls back to.
* **The operator's own documents** (`library.py`) — read at prompt-build time from a
  folder on their machine. Never committed, never packaged, never copied. One subfolder
  per style; loose files at the root form a style named after the folder.

Both appear in `available()` as rows of the same shape, because the dropdown that shows
them cannot care where a style came from and the channel column stores a slug either way.

## Why a missing folder degrades instead of failing

The folder lives outside the repository, which means it is exactly the thing that goes
missing: a machine change, a renamed directory, a drive that did not mount. A channel
whose saved slug no longer resolves still has to render its page, still has to start
runs, and still has to produce a script. So `prompt_block` falls back to the house
method rather than raising, and `selection()` keeps the missing slug in the list marked
unavailable with the reason — a dropdown that silently drops the selected option is one
that reports itself as having lost the setting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import library, method
from .library import BUDGET_CHARS, LIBRARY_DIRNAME, READABLE, Document
from .method import (
    BANKS,
    BANNED,
    BLOCKS,
    HOUSE_NAME,
    HOUSE_SLUG,
    METHOD,
    STRUCTURE_IDS,
    MethodBlock,
)

BUILT_IN = "built-in"
LOCAL = "local folder"

__all__ = [
    "BANKS",
    "BANNED",
    "BLOCKS",
    "BUDGET_CHARS",
    "BUILT_IN",
    "HOUSE_NAME",
    "HOUSE_SLUG",
    "LIBRARY_DIRNAME",
    "LOCAL",
    "METHOD",
    "READABLE",
    "STRUCTURE_IDS",
    "Document",
    "MethodBlock",
    "Style",
    "available",
    "folder_status",
    "get",
    "prompt_block",
    "selection",
]

# The house method's one-line description, for a page that has to say what the default
# does before an operator has any documents of their own to compare it with.
HOUSE_SUMMARY = ("Rising payoffs, curiosity loops that close, but/therefore joins, "
                 "rotated openings and transitions, and a banned-phrase list.")


@dataclass
class Style:
    """One selectable scripting style, wherever it came from."""

    slug: str
    name: str
    origin: str                       # BUILT_IN | LOCAL
    source: str = ""                  # the folder it was read from, "" for the house one
    documents: list[Document] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_house(self) -> bool:
        return self.slug == HOUSE_SLUG

    def as_row(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "origin": self.origin,
            "source": self.source,
            "documents": len(self.documents),
            "chars": sum(len(document.text) for document in self.documents),
            "warnings": list(self.warnings),
            "available": True,
            "reason": "",
            "summary": HOUSE_SUMMARY if self.is_house else
                       f"{len(self.documents)} document"
                       f"{'' if len(self.documents) == 1 else 's'} from {self.source}",
        }


def house() -> Style:
    """The built-in style. Constructed per call rather than cached as a module constant
    so that a caller mutating the returned object cannot change what the next channel
    gets — the warnings list on a `Style` is a list, and a shared one accumulates."""
    return Style(slug=HOUSE_SLUG, name=HOUSE_NAME, origin=BUILT_IN)


def _local(base=None) -> list[Style]:
    return [
        Style(slug=found.slug, name=found.name, origin=LOCAL, source=str(found.path),
              documents=found.documents, warnings=found.warnings)
        for found in library.discover(base)
    ]


def styles(base=None) -> list[Style]:
    """Every selectable style, house first.

    House first and always present: an install with no folder, a folder that has gone,
    or a folder full of `.pdf`s still offers a working choice rather than an empty
    dropdown that reads as a broken page.
    """
    return [house(), *_local(base)]


def available(base=None) -> list[dict]:
    """Every selectable style as a row: slug, name, where it came from, count, warnings."""
    return [style.as_row() for style in styles(base)]


def get(slug: str, base=None) -> Style | None:
    """One style, or `None` when nothing by that slug can be loaded right now.

    `None` rather than a raise, because every caller of this is either building a prompt
    or rendering a page, and neither of those is allowed to fail over a folder that was
    renamed. The caller decides what to say about it; `prompt_block` falls back to the
    house method and the channel page marks the selection unavailable.
    """
    wanted = (slug or "").strip() or HOUSE_SLUG
    if wanted == HOUSE_SLUG:
        return house()
    return next((style for style in _local(base) if style.slug == wanted), None)


def selection(selected: str = "", base=None) -> list[dict]:
    """The rows a dropdown needs: every selectable style, plus `selected` if it is gone.

    The missing one is kept in the list rather than dropped. A `<select>` that omits the
    stored value silently shows the first option instead, so the page reports a setting
    the channel does not have — and saving that page then makes the lie true.
    """
    rows = available(base)
    wanted = (selected or "").strip()
    if not wanted or any(row["slug"] == wanted for row in rows):
        return rows
    where = library.status(base)
    rows.append({
        "slug": wanted,
        "name": wanted,
        "origin": LOCAL,
        "source": where["path"],
        "documents": 0,
        "chars": 0,
        "warnings": [],
        "available": False,
        "reason": (f"not found in {where['path']}" if where["exists"] else where["note"]),
        "summary": "unavailable — scripts fall back to the house method",
    })
    return rows


def folder_status(base=None) -> dict:
    """Whether the local folder is configured, whether it exists, and what to do."""
    return library.status(base)


def prompt_block(slug: str, *, target_seconds: int, only: tuple[str, ...] = (),
                 base=None) -> str:
    """The text injected into a script prompt for this style.

    `only` names method-block ids and narrows the built-in half — the brief stage passes
    the structural ones, because a brief is beats and no prose and the banned-phrase list
    would be policing writing that stage does not produce. It never narrows the
    operator's own documents: they are one method and serving a third of it would be
    worse than serving none.

    An unresolvable slug returns the house method rather than raising or returning "".
    An empty prompt block is the failure that costs the most and shows the least — the
    script comes back written to nothing in particular, and it reads as the model having
    a bad day.
    """
    style = get(slug, base) or house()
    built_in = method.render(target_seconds=int(target_seconds or 0), only=only)

    if style.is_house or not style.documents:
        return (
            f"SCRIPTING METHOD — {style.name}. These are constraints on the script, not "
            f"background reading: a beat that breaks one of them is a rewrite, not a "
            f"note in the margin.\n\n{built_in}"
        )

    parts = [
        f"SCRIPTING METHOD — {style.name}. The {len(style.documents)} documents below "
        f"are the operator's own scripting method and they are the authority for this "
        f"channel: where they and the house rules underneath them disagree, the "
        f"documents win. Follow them as instructions. Do not quote them in the script "
        f"and do not imitate their example sentences — apply what they say to this "
        f"topic.",
    ]
    for document in style.documents:
        parts.append(f"----- {document.name} -----\n{document.text}")
    parts.append(
        "THE HOUSE FLOOR — these still apply to everything the documents above leave "
        f"open:\n\n{built_in}"
    )
    return "\n\n".join(parts)
