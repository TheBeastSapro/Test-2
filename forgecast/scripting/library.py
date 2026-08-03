"""The operator's own scripting documents, read from a folder outside the repository.

## Why these files are never in the tree

The documents this module reads are somebody else's work, bought under a licence that
covers the operator and nothing else. Copying them into `forgecast/` would put them in
every commit and in every zip `tools/package.py` builds, and a zip is a thing that gets
sent to other people. So they stay where the operator put them, on their own machine,
and this module opens them at prompt-build time and hands the text straight to the
prompt. Nothing here writes, copies, caches or uploads them, and there is no code path
that puts one inside the repository — `tools/package.py`'s `EXCLUDE` is the second lock
on the same door, for the case where one ends up in the tree by hand.

## Why a file that will not load is named rather than skipped

The operator has sixteen documents. Three of them failing to load produces a style that
still works, still writes scripts, and is quietly missing a fifth of the method — which
is indistinguishable from a method that was always this weak. `forgecast/skills`
already learned this with its shipped documents: an absence that degrades gracefully is
an absence nobody ever discovers. So every file that is not read is named, with the
reason, in the warnings the page and the run log both print.

## Why there is a character budget

A folder is not a bounded thing. Sixteen documents today, a transcript dump tomorrow,
and the script prompt is suddenly three hundred kilobytes — paid for on every brief and
every script of every run, to deliver craft the model reads the first fifth of. The
budget is per style and it is spread across the documents rather than spent
first-come-first-served, because one 90 KB file must not evict the other fifteen.
Whatever gets cut is named and measured in the warnings, so a truncated library looks
like a truncated library rather than like a shorter one.

## Why an unset folder is not the current directory

`Path("")` is `Path(".")`. An operator who clears the field in Settings would otherwise
point the library at whatever directory the server was started from — which for a
development install is the repository, and the app would then read its own README, its
own docs and its own tests into a script prompt. Blank means unconfigured, and
unconfigured means there are no local styles.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from .method import HOUSE_SLUG

log = logging.getLogger("forgecast.scripting")

# What counts as a document. Prose formats only: everything here is opened as text and
# handed to a prompt, and a `.pdf` opened as text is a page of binary that costs tokens
# and says nothing.
READABLE: tuple[str, ...] = (".md", ".markdown", ".txt")

# Characters of the operator's own documents injected per style, per prompt. Roughly six
# thousand tokens — large enough for a real method, small enough that it is a fixed cost
# per run rather than an open one.
BUDGET_CHARS = 24_000

# A folder with more documents than this is not a scripting style, it is a directory the
# operator pointed at by mistake — a Downloads folder, a notes vault, a repository. Read
# the first ones in name order and say the rest were left, rather than opening nine
# hundred files on the way to building one prompt.
MAX_DOCUMENTS = 40

# The folder Forgecast reads is named, not merely configured, so that `EXCLUDE` in
# `tools/package.py` can name it too. A pattern can only refuse a directory it can
# recognise, and "wherever the operator pointed the setting" is not recognisable from
# inside a packaging script.
LIBRARY_DIRNAME = "scripting-library"


@dataclass
class Document:
    """One of the operator's files, as it will reach the prompt."""

    name: str
    text: str
    original_chars: int

    @property
    def truncated_by(self) -> int:
        return max(0, self.original_chars - len(self.text))


@dataclass
class LocalStyle:
    """One folder of documents, as a selectable style."""

    slug: str
    name: str
    path: Path
    documents: list[Document] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(len(document.text) for document in self.documents)


def slugify(name: str) -> str:
    """A folder name as a stable selection key.

    A whitelist rather than a blacklist, for the reason `forgecast/skills` gives: this is
    where a directory name becomes a value stored in a database column and echoed into an
    HTML attribute, and one rule that keeps only letters and digits disposes of quotes,
    separators, dots and everything else in a single line.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return cleaned[:60].strip("-")


# ---------------------------------------------------------------------- the folder


def directory(base: Path | str | None = None) -> Path | None:
    """Where the operator's documents live, or `None` when nothing is configured.

    `Path(...)` around the setting rather than trusting its type: `routes_settings`
    writes machine-level values with a plain `setattr`, and pydantic does not validate
    assignment, so this field is a `str` for the rest of the process's life after
    somebody saves it from the Settings page.
    """
    raw = base if base is not None else getattr(get_settings(), "scripting_dir", "")
    text = str(raw or "").strip()
    return Path(text).expanduser() if text else None


def status(base: Path | str | None = None) -> dict:
    """What the folder is doing, in the words a page can print.

    Separate from `discover` because "you have no local styles" and "the folder you
    configured is not there" are different sentences, and a page that prints the first
    for the second sends the operator looking for missing files instead of a missing
    directory.
    """
    folder = directory(base)
    if folder is None:
        return {"configured": False, "exists": False, "path": "",
                "note": "No scripting folder is set. Point FORGECAST_SCRIPTING_DIR at a "
                        "folder of your own documents and they appear here as styles."}
    shown = str(folder)
    if not folder.is_dir():
        return {"configured": True, "exists": False, "path": shown,
                "note": f"{shown} does not exist yet. Create it and put a folder of "
                        f"{', '.join(READABLE)} documents inside — one folder per style."}
    return {"configured": True, "exists": True, "path": shown,
            "note": f"Reading styles from {shown}."}


# ---------------------------------------------------------------------- reading


def _read(path: Path) -> tuple[str, str]:
    """(text, warning). Exactly one of the two is empty."""
    if path.suffix.lower() not in READABLE:
        return "", (f"{path.name} was not loaded — only "
                    f"{', '.join(READABLE)} files are read as documents")
    try:
        # `errors="replace"` rather than strict: a document saved on Windows in a legacy
        # encoding is craft the operator paid for, and losing the whole file over three
        # bytes of smart quotes is a worse answer than a document with three question
        # marks in it.
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return "", f"{path.name} could not be read ({exc.strerror or exc})"
    if not text:
        return "", f"{path.name} is empty"
    return text, ""


def _documents(folder: Path, *, recursive: bool) -> tuple[list[Document], list[str]]:
    """Every readable document in one style folder, with the failures named.

    `recursive` is False for the style made of the loose files at the root of the
    library, because its subfolders are separate styles — reading them here as well would
    put every document into every style and make the choice in the dropdown mean nothing.
    """
    found: list[Document] = []
    warnings: list[str] = []

    # Sorted by path so the order a prompt sees is the order the operator sees in their
    # file manager — a library whose documents arrive in filesystem order reads as a
    # different method every time the folder is touched.
    candidates = folder.rglob("*") if recursive else folder.iterdir()
    paths = sorted(
        (path for path in candidates
         if path.is_file() and not path.name.startswith(".")),
        key=lambda path: str(path).lower(),
    )
    if len(paths) > MAX_DOCUMENTS:
        warnings.append(
            f"{len(paths)} files in {folder.name}; only the first {MAX_DOCUMENTS} in "
            f"name order were considered")
        paths = paths[:MAX_DOCUMENTS]

    for path in paths:
        text, warning = _read(path)
        if warning:
            warnings.append(warning)
            continue
        # Named by their path inside the style, so two `intro.md` in different
        # subfolders are two documents in the warnings rather than one repeated name.
        found.append(Document(name=path.relative_to(folder).as_posix(), text=text,
                              original_chars=len(text)))
    return found, warnings


def _fit(documents: list[Document], budget: int) -> list[str]:
    """Trim documents to the budget in place, and say what was cut.

    An equal share each, with the headroom left by the short ones handed back to the long
    ones in a single pass. Spending the budget in name order instead would mean a library
    whose first document happens to be long ships one document and fifteen warnings.
    """
    total = sum(document.original_chars for document in documents)
    if not documents or total <= budget:
        return []

    share = budget // len(documents)
    spare = sum(share - d.original_chars for d in documents if d.original_chars < share)
    over = [d for d in documents if d.original_chars > share]
    if over:
        share += spare // len(over)

    warnings: list[str] = []
    for document in documents:
        if document.original_chars <= share:
            continue
        # Cut at a line boundary when there is one nearby, so a document does not end
        # mid-sentence in a way that reads as an instruction the writer must complete.
        head = document.text[:share]
        newline = head.rfind("\n")
        document.text = (head[:newline] if newline > share * 0.8 else head).rstrip()
        warnings.append(
            f"{document.name} was truncated by {document.truncated_by:,} characters to "
            f"fit the {budget:,}-character prompt budget")
    return warnings


def load_style(folder: Path, *, slug: str, name: str, recursive: bool = True,
               budget: int = BUDGET_CHARS) -> LocalStyle:
    """One folder as a style. Never raises — an unreadable folder is a style with warnings."""
    try:
        documents, warnings = _documents(folder, recursive=recursive)
    except OSError as exc:                                            # pragma: no cover
        return LocalStyle(slug=slug, name=name, path=folder,
                          warnings=[f"{folder} could not be listed ({exc})"])
    warnings += _fit(documents, budget)
    return LocalStyle(slug=slug, name=name, path=folder, documents=documents,
                      warnings=warnings)


def discover(base: Path | str | None = None, *, budget: int = BUDGET_CHARS) -> list[LocalStyle]:
    """Every style in the operator's folder. Never raises.

    Two shapes are supported because both are what people actually do: a folder per style
    for someone with several methods, and a folder of loose files for someone with one.
    Loose files become a style named after the folder itself, so an operator who drops
    sixteen documents in and selects the result is not first asked to invent a taxonomy.
    """
    folder = directory(base)
    if folder is None or not folder.is_dir():
        return []

    styles: list[LocalStyle] = []
    taken = {HOUSE_SLUG}

    def claim(candidate: str, fallback: str) -> str:
        """A slug nothing else has taken, including the built-in style's.

        A local folder called `house` would otherwise shadow the built-in method, and
        every channel that had selected the built-in one would silently start writing to
        somebody else's documents without a single row changing.
        """
        base_slug = candidate or fallback
        slug, suffix = base_slug, 2
        while slug in taken:
            slug, suffix = f"{base_slug}-{suffix}", suffix + 1
        taken.add(slug)
        return slug

    try:
        entries = sorted(folder.iterdir(), key=lambda path: path.name.lower())
    except OSError as exc:                                            # pragma: no cover
        log.warning("scripting folder %s could not be listed: %s", folder, exc)
        return []

    loose = [path for path in entries if path.is_file() and not path.name.startswith(".")]
    if loose:
        name = folder.name or "Local scripting"
        styles.append(load_style(folder, slug=claim(slugify(name), "local"), name=name,
                                 recursive=False, budget=budget))

    for path in entries:
        if not path.is_dir() or path.name.startswith("."):
            continue
        styles.append(load_style(path, slug=claim(slugify(path.name), "style"),
                                 name=path.name, budget=budget))
    return styles
