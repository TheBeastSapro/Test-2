"""What a person notices in a browser, asserted mechanically.

Three defects shipped past a suite that checked status codes. A template referenced
`var(--panel)` after the token was renamed, so the rule rendered transparent and the
panel vanished into the page. A raw `2026-08-03T08:16:23+00:00` went on screen. An
absolute path wrapped across three lines of mono type. Every one of them returned 200
and every one of them was obvious to look at.

So each check here is one of those three failures generalised, and each is written to
name the file and the offending text — a red test that only says "assertion failed"
costs more to diagnose than the defect cost to ship.

Where the current tree contains something a rule would flag, it is listed below with
the reason it is allowed rather than the rule being weakened. An entry that stops being
used fails the test too, so the lists cannot quietly outlive what they excused.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jinja2
import pytest
from jinja2 import StrictUndefined, meta

from forgecast.api import routes_web

WEB = Path(routes_web.__file__).resolve().parent.parent / "web"
CSS = WEB / "static" / "app.css"
BASE = WEB / "base.html"
TEMPLATES = sorted(WEB.glob("*.html"))
PAGES = [path for path in TEMPLATES if path != BASE]
# chat.js sets colours from tokens too, and a token it names is as dead as one a
# template names. Nothing else in static/ is checked here.
STYLED = TEMPLATES + sorted(WEB.glob("static/*.js"))


def _line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _at(path: Path, text: str, index: int) -> str:
    """`file:line` — a location an editor can jump to, not a template name."""
    return f"{path.name}:{_line(text, index)}"


def _report(offenders: list[str], headline: str) -> None:
    assert not offenders, headline + "\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------- custom properties

TOKEN_DEFINED = re.compile(r"(--[a-zA-Z0-9-]+)\s*:")
TOKEN_USED = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)")


def _defined_tokens() -> set[str]:
    return set(TOKEN_DEFINED.findall(CSS.read_text()))


def _undefined_token_uses(name: str, text: str, defined: set[str]) -> list[str]:
    return [
        f"{name}:{_line(text, match.start())} uses var({match.group(1)}), "
        f"which app.css does not define"
        for match in TOKEN_USED.finditer(text)
        if match.group(1) not in defined
    ]


def test_every_custom_property_a_template_uses_is_defined():
    """The `--panel` failure. An undefined token is not an error anywhere.

    `background: var(--panel)` against a stylesheet with no `--panel` is not a parse
    error and not a 500 — the declaration is dropped and the surface renders
    transparent, which looks like a layout choice rather than a bug.
    """
    defined = _defined_tokens()
    offenders: list[str] = []
    for path in STYLED:
        offenders += _undefined_token_uses(path.name, path.read_text(), defined)
    _report(offenders, "the UI uses custom properties app.css does not define:")


def test_the_token_scan_catches_the_token_that_was_actually_removed():
    """The scan above passes on a clean tree, which is also how a broken scan looks."""
    caught = _undefined_token_uses(
        "fake.html", ".x { background: var(--panel-2); }", _defined_tokens()
    )
    assert caught and "--panel-2" in caught[0]


# ------------------------------------------------------------------------ colour

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
HEAD_BLOCK = re.compile(r"{%-?\s*block\s+head\s*-?%}(.*?){%-?\s*endblock", re.S)

# Shades a page defines for itself, in its own head block, because they exist for one
# page and putting them in app.css would grow the shared palette by ten one-offs. Any
# hex here is a shade a human agreed to; a hex that is not here is either a token that
# should have been used or a near-miss of one, which is the thing this list exists to
# make visible.
PAGE_SHADES = {
    "#ff8a5c": "research: the 'strong' outlier band, the one colour warmer than --warn",
    "#6b3319": "research: border under that band",
    "#2a1710": "research: fill under that band",
    "#1f4b38": "research/styles: a green border dark enough to sit under --ok text",
    "#10201a": "research: fill under the 'clear' band",
    "#5c4a1e": "research/styles: an amber border dark enough to sit under --warn text",
    "#241f10": "research: fill under the 'soft' band",
    "#40306b": "run/styles: a violet border for a gate, matching .status.awaiting_approval",
    "#0b0e14": "preview: the timeline gutter, one step below --bg so the track reads as a well",
    "#dfe4ee": "preview: clip labels over video, brighter than --text to survive any frame",
}

# A hex outside a head block cannot be a class, so each of these is a value handed to
# something that takes a colour rather than a stylesheet rule. They are allowed one at a
# time, with the reason, because "it is in JavaScript" is not a reason.
INLINE_HEX = {
    ("preview.html", "#101418"): "fallback fill for a scene whose plan carries no colour",
    ("run.html", "#2f6b52"): "SVG wire between two completed nodes, drawn from script",
    ("run.html", "#2b3543"): "SVG wire between nodes not yet completed, drawn from script",
    ("styles.html", "#333"): "swatch fill when a learned palette entry has no hex at all",
}


def _palette() -> set[str]:
    """Every colour app.css commits to, whether it is a token value or a literal."""
    return {_norm(match.group()) for match in HEX.finditer(CSS.read_text())}


def _norm(value: str) -> str:
    """`#abc` and `#aabbcc` are the same colour and must not count as two."""
    text = value.lower()
    if len(text) == 4:
        return "#" + "".join(char * 2 for char in text[1:])
    return text


def _head_span(text: str) -> tuple[int, int] | None:
    match = HEAD_BLOCK.search(text)
    return (match.start(1), match.end(1)) if match else None


def test_colour_stays_in_the_palette():
    """A near-miss shade is the defect this prevents, not a wrong colour.

    Nobody ships `#ff0000` by accident. What gets shipped is a green two degrees off
    `--ok`, or a grey one step off `--line`, and side by side on the same page that
    reads as carelessness while never looking like a bug. So a page may define its own
    shades in its own head block, and only shades that were agreed to.
    """
    palette = _palette()
    stray: list[str] = []
    unknown: list[str] = []
    used_shades: set[str] = set()
    used_inline: set[tuple[str, str]] = set()

    # base.html included: the shell is a template like any other and rots the same way.
    for path in TEMPLATES:
        text = path.read_text()
        span = _head_span(text)
        for match in HEX.finditer(text):
            raw, hexval = match.group(), _norm(match.group())
            inside = span is not None and span[0] <= match.start() < span[1]
            if not inside:
                key = (path.name, raw)
                if hexval in palette:
                    continue  # a colour app.css already commits to cannot be a near miss
                if key in INLINE_HEX:
                    used_inline.add(key)
                    continue
                stray.append(
                    f"{_at(path, text, match.start())} hard-codes {raw} outside its head "
                    f"block — use a token, or add it to INLINE_HEX with the reason"
                )
            elif hexval in palette:
                continue
            elif hexval in PAGE_SHADES:
                used_shades.add(hexval)
            else:
                unknown.append(
                    f"{_at(path, text, match.start())} introduces {raw}, which is neither "
                    f"in app.css nor in PAGE_SHADES — if it is not a near miss of a "
                    f"token, say why in PAGE_SHADES"
                )

    _report(stray + unknown, "templates hard-code colour outside the palette:")
    _report(
        [f"PAGE_SHADES has {shade} ({why}) which no template uses any more"
         for shade, why in PAGE_SHADES.items() if shade not in used_shades]
        + [f"INLINE_HEX has {key} ({why}) which no template uses any more"
           for key, why in INLINE_HEX.items() if key not in used_inline],
        "the colour allowances have outlived what they excused:",
    )


# ------------------------------------------------------------------------- blocks

BLOCK = re.compile(r"{%-?\s*block\s+([a-zA-Z0-9_]+)")
EXTENDS = re.compile(r'{%-?\s*extends\s+"([^"]+)"')


def test_pages_fill_the_blocks_base_html_has_and_no_others():
    """A block name base.html does not have is a no-op that reads as a broken page.

    `{% block content %}` in a template whose parent calls it `body` renders nothing at
    all: the page comes back 200, with the shell around an empty main. Nothing warns,
    because inventing a block is legal Jinja.
    """
    base_blocks = set(BLOCK.findall(BASE.read_text()))
    assert "body" in base_blocks, "base.html no longer has a body block to fill"

    offenders: list[str] = []
    for path in PAGES:
        text = path.read_text()
        parent = EXTENDS.search(text)
        if parent is None or parent.group(1) != BASE.name:
            continue
        blocks = set(BLOCK.findall(text))
        if "body" not in blocks:
            offenders.append(
                f"{path.name} extends base.html but declares no body block, so the "
                f"page renders as an empty shell"
            )
        for unknown in sorted(blocks - base_blocks):
            offenders.append(
                f"{path.name} declares {{% block {unknown} %}}, which base.html does "
                f"not have — its contents are silently dropped"
            )
    _report(offenders, "templates do not line up with base.html:")


# ------------------------------------------------------------- placeholders, emoji

# Uppercase, deliberately: `.tool.todo` in setup.html is a state class for a tool that
# is not installed yet, and lowercasing the rule would flag it. The marker convention
# that means "unfinished" is the shouted form, plus the shape someone types in a hurry.
MARKER = re.compile(r"\b(TODO|FIXME|XXX)\b|(?i:\b(?:todo|fixme)\b\s*[:!])|(?i:\blorem\b)")

# Emoji by default presentation, not by "is a symbol". The rail is built from ◆ ✦ ◎ ▤ ⚙
# and those are text-presentation glyphs that inherit the font and the colour; a colour
# emoji next to them is what does not belong. U+FE0F is the giveaway on its own — it is
# the request to render the previous character in colour.
EMOJI_RANGES = (
    (0x1F000, 0x1FAFF), (0x1F1E6, 0x1F1FF), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55), (0x2705, 0x2705), (0x270A, 0x270B), (0x2728, 0x2728),
    (0x274C, 0x274C), (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757),
    (0x2795, 0x2797), (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2614, 0x2615),
    (0x231A, 0x231B), (0x23E9, 0x23EC), (0x23F0, 0x23F0), (0x23F3, 0x23F3),
    (0xFE0F, 0xFE0F), (0x200D, 0x200D),
)


def _is_emoji(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in EMOJI_RANGES)


def test_no_template_ships_a_placeholder_or_an_emoji():
    offenders: list[str] = []
    for path in TEMPLATES:
        text = path.read_text()
        for match in MARKER.finditer(text):
            offenders.append(
                f"{_at(path, text, match.start())} ships {match.group()!r}"
            )
        for index, char in enumerate(text):
            if _is_emoji(char):
                offenders.append(
                    f"{_at(path, text, index)} contains the emoji "
                    f"{char!r} (U+{ord(char):04X})"
                )
    _report(offenders, "templates contain placeholder text or emoji:")


def test_the_placeholder_scan_would_catch_the_obvious_cases():
    """`.tool.todo` is a state class and must pass; the marker forms must not."""
    assert not MARKER.search(".tool.todo .verdict { color: var(--warn); }")
    for bad in ("<!-- TODO: wire this up -->", "{# FIXME #}", "XXX", "Lorem ipsum dolor"):
        assert MARKER.search(bad), bad
    assert _is_emoji("\U0001f680") and not _is_emoji("◆") and not _is_emoji("⚙")


# ---------------------------------------------------------------------- timestamps

# The names SQLAlchemy models carry. A `datetime` reaching a template under one of
# these is the exact value the `when` filter exists to format.
STAMP = re.compile(
    r"\.(created_at|updated_at|started_at|finished_at|completed_at|expires_at)\b"
)
INTERPOLATION = re.compile(r"{{(.*?)}}", re.S)
ATTRIBUTE = re.compile(r'[-\w:@]+\s*=\s*"[^"]*"')


def _raw_timestamps(name: str, text: str) -> list[str]:
    """Interpolated timestamps that reach the reader without going through `when`.

    Attribute values are exempt because that is where the exact value belongs: the
    pattern in skills.html is `title="{{ x.updated_at }}"` around `{{ x.updated_at |
    when }}`, so hovering gives you the ISO string and the page gives you "4 min ago".
    """
    attributes = [match.span() for match in ATTRIBUTE.finditer(text)]
    offenders = []
    for match in INTERPOLATION.finditer(text):
        if any(start <= match.start() < end for start, end in attributes):
            continue
        expression = match.group(1)
        if STAMP.search(expression) and not re.search(r"\|\s*when\b", expression):
            offenders.append(
                f"{name}:{_line(text, match.start())} puts {{{{{expression.strip()}}}}} "
                f"on screen without |when, so a reader gets a raw ISO timestamp"
            )
    return offenders


def test_the_when_filter_is_registered():
    """`{{ x|when }}` against an env with no `when` is a 500, not a formatting bug."""
    assert routes_web.TEMPLATES.env.filters.get("when") is routes_web.when


def test_timestamps_on_screen_go_through_the_when_filter():
    offenders: list[str] = []
    for path in TEMPLATES:
        offenders += _raw_timestamps(path.name, path.read_text())
    _report(offenders, "templates put raw timestamps on screen:")


def test_the_timestamp_scan_catches_the_shape_that_shipped():
    """No template offends today, which is indistinguishable from a scan that is off."""
    caught = _raw_timestamps("fake.html", "<td>{{ run.created_at }}</td>")
    assert caught and "run.created_at" in caught[0]
    assert not _raw_timestamps(
        "fake.html",
        '<span title="{{ run.created_at }}">{{ run.created_at | when }}</span>',
    )


# ---------------------------------------------------------------------- long paths

TAILED = re.compile(r"{{\s*([\w.]+)\s*\|\s*tail\b")


def test_a_shortened_path_keeps_the_whole_one_within_reach():
    """`tail` throws away the front of the path, which is sometimes the answer.

    `…/storage/runs/41/render.mp4` is the right thing to read and the wrong thing to
    copy. The convention the two call sites follow is a `title` on the same element
    holding the full value; a shortened path with no title is a path you cannot recover.
    """
    offenders: list[str] = []
    for path in TEMPLATES:
        text = path.read_text()
        for match in TAILED.finditer(text):
            expression = match.group(1)
            opening = text.rfind("<", 0, match.start())
            tag = text[opening:match.start()] if opening != -1 else ""
            if f'title="{{{{ {expression} }}}}"' not in tag:
                offenders.append(
                    f'{_at(path, text, match.start())} shortens {expression} with |tail '
                    f'but the element carries no title="{{{{ {expression} }}}}", so the '
                    f"full path is unrecoverable"
                )
    _report(offenders, "shortened paths have nowhere to show the full value:")


# ------------------------------------------------------------------- render for real

class Anything:
    """Stands in for whatever a route passes that is not part of the shell contract.

    A page is not allowed to need a database to be checked for undefined names, so
    everything a route supplies itself becomes one of these: truthy so `{% if %}`
    takes the branch that renders, iterable once so `{% for %}` renders its body, and
    numeric enough to survive `format` and `round`. It answers to any attribute, which
    is the point — what is under test is the names the shell owes the page, not the
    shape of a Run.
    """

    __slots__ = ("_path",)

    def __init__(self, path: str) -> None:
        self._path = path

    def __getattr__(self, item: str) -> Anything:
        if item.startswith("_"):
            raise AttributeError(item)
        return Anything(f"{self._path}.{item}")

    def __getitem__(self, key) -> Anything:
        return Anything(f"{self._path}[{key!r}]")

    def __call__(self, *args, **kwargs) -> Anything:
        return Anything(f"{self._path}()")

    def __iter__(self):
        return iter((Anything(f"{self._path}[0]"),))

    def __len__(self) -> int:
        return 1

    def __bool__(self) -> bool:
        return True

    def __contains__(self, item) -> bool:
        return False

    # Comparisons answer False rather than another stub: `{{ 'on' if a == b }}` has to
    # pick one branch, and a stub is truthy, so every comparison would read as equal.
    def __eq__(self, other) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)

    def __lt__(self, other) -> bool:
        return False

    __gt__ = __le__ = __ge__ = __lt__

    def __add__(self, other):
        return other if isinstance(other, str) else 0

    __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __add__

    def __truediv__(self, other) -> float:
        return 0.0

    __rtruediv__ = __truediv__

    def __float__(self) -> float:
        return 0.0

    def __int__(self) -> int:
        return 0

    def __index__(self) -> int:
        return 0

    def __round__(self, digits: int = 0) -> float:
        return 0.0

    def __format__(self, spec: str) -> str:
        return format(0, spec) if spec else self._path

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"<supplied by the route: {self._path}>"


# base.html reads these two beyond the shell contract. `embed` is set only by the
# preview route and every other page relies on it being missing; `ffmpeg_ok` is a
# template global. Both are named here so that a *third* name appearing in base.html
# fails the test below instead of being papered over.
BASE_ONLY = ("embed", "ffmpeg_ok")


def _env() -> jinja2.Environment:
    """The real environment's filters and globals, with undefined names made fatal."""
    env = routes_web.TEMPLATES.env.overlay(undefined=StrictUndefined)
    # `|tojson` on a stub raises TypeError, which would abort the render before the
    # undefined-name check had seen the rest of the page.
    env.policies["json.dumps_function"] = lambda value, **kwargs: json.dumps(
        value, default=str, **{k: v for k, v in kwargs.items() if k != "default"}
    )
    # `urlencode` reads an iterable as key/value pairs, and a stub is iterable. Without
    # this the render dies on the first `|urlencode` and the rest of the page — the part
    # that might hold an undefined name — is never reached.
    quote = env.filters["urlencode"]
    env.filters["urlencode"] = lambda value: quote(
        str(value) if isinstance(value, Anything) else value
    )
    return env


def _shell_context(session, user) -> dict:
    """The real shell dict, from the real function, with no runs or channels to load."""
    return routes_web.shell(session, user, "chat", channels=[], runs=[])


def _contract(env: jinja2.Environment) -> set[str]:
    """The names base.html reads — the shell's side of the deal, and never stubbed.

    Stubbing these would make the render check vacuous: chat.html reads `credits` in its
    own body as well as inheriting the sidebar that reads it, so a stub for every name a
    page mentions would cover for a `shell()` that had stopped supplying it.
    """
    return set(meta.find_undeclared_variables(env.parse(BASE.read_text())))


def test_base_html_reads_only_what_the_shell_contract_provides(session, user):
    """The shell is a contract and this is the only place it is written down.

    A name added to base.html and not to `shell()` renders as nothing on every page at
    once — the sidebar loses its channel list, or the credit count, and every route
    still returns 200.
    """
    env = _env()
    names = meta.find_undeclared_variables(env.parse(BASE.read_text()))
    provided = set(_shell_context(session, user)) | set(BASE_ONLY)
    _report(
        sorted(f"base.html reads {name!r}, which shell() does not provide" for name in names - provided),
        "base.html reads names nothing supplies:",
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda path: path.name)
def test_every_page_renders_with_only_the_shell_and_its_own_context(page, session, user):
    """StrictUndefined, so a missing name is an error instead of an empty string.

    Jinja's default `Undefined` prints as "" and is falsey, which is why a renamed
    shell key is invisible: the page renders, the section it guarded simply is not
    there. Everything the page's own route passes is stubbed; everything the shell owes
    it is real. So a failure here means the page and the shell disagree.
    """
    env = _env()
    text = page.read_text()
    contract = _contract(env)
    context: dict = {**_shell_context(session, user), "embed": False}
    for name in meta.find_undeclared_variables(env.parse(text)):
        if name not in contract:
            context.setdefault(name, Anything(name))

    try:
        env.get_template(page.name).render(context)
    except jinja2.UndefinedError as exc:
        pytest.fail(
            f"{page.name} references a name the shell does not provide: {exc}\n"
            f"Either shell() should supply it or the page should stop reading it."
        )


def test_the_signed_out_pages_render_with_no_user(session, user):
    """Login and setup run before there is an account, and base.html branches on it.

    Their routes pass no shell at all, so the signed-out header is the branch nobody
    exercises — and it is the first page anybody sees.
    """
    env = _env()
    contract = _contract(env)
    for name in ("login.html", "setup.html"):
        text = (WEB / name).read_text()
        context: dict = {
            "user": None, "embed": False, "settings": routes_web.get_settings(),
        }
        for missing in meta.find_undeclared_variables(env.parse(text)):
            if missing not in contract:
                context.setdefault(missing, Anything(missing))
        try:
            env.get_template(name).render(context)
        except jinja2.UndefinedError as exc:
            pytest.fail(f"{name} cannot render for a visitor with no account: {exc}")


# --------------------------------------------------------- the delete-chat control
#
# Delete now lives inside a three-dots overflow menu rather than bare on the row, so
# these three read `.thread-more` — the dots button — where they used to read
# `.thread-x`. What they defend is unchanged: the way to delete a chat must be visible
# without hovering, legible on the selected row, and a real button that is not nested
# inside the row's own clickable element.


def _css() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "forgecast" / "web" / "static"
            / "app.css").read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    """The declarations of one rule, by exact selector."""
    import re

    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"{selector} is not in app.css"
    return match.group(1)


def test_the_delete_chat_control_is_not_hidden():
    """Reported as missing twice, and each time by a different attempt to be discreet.

    First `opacity: 0` until the row was hovered — invisible unless you already knew where
    it was. Then `opacity: .45` in `--muted`, which vanished against the accent background
    of the *selected* row, which is the chat you most want to delete.

    So this pins the outcome rather than the styling: the control may be restyled freely,
    but it may not be made transparent again. It is now the dots that open the menu
    Delete lives in, which is the same control by a different name — a dots button you
    cannot see is a chat you cannot delete.
    """
    declarations = _block(_css(), ".thread-more")
    assert "opacity" not in declarations, (
        "the control that reaches delete must not be hidden with opacity — it has been "
        "reported missing twice for exactly that reason")


def test_it_stays_legible_on_the_selected_row():
    """`.thread.on` fills the row with `--accent-dim`, so the foreground token that works
    on the page background does not necessarily work here."""
    css = _css()
    assert ".thread.on .thread-more" in css, (
        "the selected row paints an accent background; the control needs its own colour "
        "there or it disappears on the one row that matters most")


def test_the_control_is_a_real_button_outside_the_row_button():
    """A `<button>` inside a `<button>` is invalid, and browsers drop one of the two —
    which one is up to the browser. The row is a div with role=button for this reason."""
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "forgecast" / "web" / "static"
              / "chat.js").read_text(encoding="utf-8")
    assert 'class="thread ' in script and 'role="button"' in script
    assert 'button class="thread-more"' in script


# ------------------------------------------------------- the row overflow menu
#
# "add delete button like clicking the 3 dots at the chat" — so the row now carries a
# three-dots button and the destructive action moved into the menu behind it. That is one
# more place for the control to go missing, not one fewer, and the three checks above
# only pin the button. These pin the rest of the shape: that the dots are on the row at
# all, that they are a real button the row does not swallow, that no rule hides them
# until a pointer arrives, and that Delete is still reachable once the menu is open.

CHAT_JS = WEB / "static" / "chat.js"
CHAT_HTML = WEB / "chat.html"

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# `visibility: hidden` and `display: none` hide as thoroughly as `opacity: 0`, and a
# rule that sets any of them on this control is the reported defect wearing a new
# property name.
VANISHES = re.compile(r"\b(opacity|visibility)\s*:|display\s*:\s*none")


def _rules_for(css: str, selector_text: str) -> list[tuple[str, str, int]]:
    """Every rule whose selector names `selector_text`, with the line its brace is on.

    Comments are blanked rather than removed so offsets still point into the real file,
    and the line is taken from the opening brace: a selector's match starts wherever the
    previous rule ended, which is a blank line or the top of a comment, not the rule.
    """
    bare = CSS_COMMENT.sub(lambda m: " " * len(m.group()), css)  # keep offsets honest
    return [
        (match.group(1).strip(), match.group(2), _line(css, match.end(1)))
        for match in RULE.finditer(bare)
        if selector_text in match.group(1)
    ]


def _row_markup() -> str:
    """The template literal `paintThreads` builds one row from, as written.

    Bounded by the literal's own closing backtick rather than by the first `</div>`,
    which belongs to the title inside the row.
    """
    script = CHAT_JS.read_text(encoding="utf-8")
    start = script.find('<div class="thread ')
    assert start != -1, (
        "chat.js no longer renders a `.thread` row — every check below is about that row")
    end = script.find("`", start)
    assert end != -1, "the thread row template in chat.js is not a template literal"
    row = script[start:end].rstrip()
    assert row.endswith("</div>"), (
        f"the row template does not close its own div — read it at "
        f"chat.js:{_line(script, start)} before trusting anything below")
    return row


def test_the_row_carries_a_three_dots_overflow_control():
    """The operator asked for the dots; a menu with no way in is not the feature.

    Named on the row template rather than on a rendered page so the check survives
    having no browser: `paintThreads` is the only place a row is built.
    """
    row = _row_markup()
    offenders: list[str] = []
    if 'class="thread-more"' not in row:
        offenders.append(
            "chat.js paints a thread row with no `.thread-more` control, so there is no "
            "way to reach rename, pin or delete from the list")
    # Three dots drawn as three circles. A glyph would be at the mercy of the system
    # font; what matters to this test is only that the button is not empty.
    if "DOTS" not in row and "<svg" not in row:
        offenders.append(
            "the overflow button has no glyph in it — an empty 22px button is a control "
            "nobody will find")
    # A button whose only content is three dots has no name at all to a screen reader,
    # and a menu button that never says whether it is open is a menu you have to guess at.
    for name, spelling in (
        ("aria-label", 'aria-label="'),
        ("aria-expanded", 'aria-expanded="false"'),
        ("aria-haspopup", "aria-haspopup="),
    ):
        if spelling not in row:
            offenders.append(
                f"the overflow button carries no {name}, so the three dots have no "
                f"accessible name or no way to announce that their menu is open")
    _report(offenders, "the thread row has lost its overflow control:")


def test_the_dots_are_a_real_button_the_row_does_not_swallow():
    """The nesting rule, checked structurally rather than by looking for one string.

    A `<button>` inside a `<button>` is invalid and browsers drop one of the two — which
    one is up to them, so on some browsers the dots stop responding and on others the row
    does. The row is a `div` with `role="button"` precisely so the dots can be real.
    """
    row = _row_markup()
    offenders: list[str] = []
    if not row.startswith("<div "):
        offenders.append(
            f"the row's own element is {row[:row.find(' ')]!r}, not a div — a real "
            f"button inside it would be nested markup the browser has to repair")
    if 'role="button"' not in row[:row.find(">") + 1]:
        offenders.append(
            'the row div has no role="button", so a list that behaves like buttons '
            "announces itself as a stack of divs")
    if "<a " in row:
        offenders.append(
            "the row wraps its contents in an anchor; a button inside one is the same "
            "nesting problem with a different tag")
    if row.count("<button") != 1:
        offenders.append(
            f"the row contains {row.count('<button')} buttons — this check reads the "
            f"count to prove the dots button is not inside another one, so a second "
            f"control needs this test rewritten rather than relaxed")
    _report(offenders, "the overflow control is nested where a browser will break it:")


def test_no_rule_hides_the_overflow_control_until_you_hover():
    """The first reported defect, generalised past the one property that caused it.

    `opacity: 0` until `.thread:hover` is the version that shipped. `visibility: hidden`
    and `display: none` behind the same hover would read identically to a user and to
    anyone on a touchscreen, where there is no hover to give — so the whole family is
    refused on this control, and hover may only change its colour.
    """
    css = _css()
    offenders = [
        f"app.css:{line} sets a visibility property on {selector!r} "
        f"({' '.join(declarations.split())}) — this control has been reported missing "
        f"twice and may not be hidden, least of all until a pointer arrives"
        for selector, declarations, line in _rules_for(css, ".thread-more")
        if VANISHES.search(declarations)
    ]
    _report(offenders, "the overflow control is hidden by a stylesheet rule:")


def test_the_hover_scan_catches_the_rule_that_actually_shipped():
    """A scan that passes on a clean tree looks exactly like a scan that is switched off."""
    broken = ".thread-more { opacity: 0; }\n.thread:hover .thread-more { opacity: 1; }"
    caught = [
        line for _, declarations, line in _rules_for(broken, ".thread-more")
        if VANISHES.search(declarations)
    ]
    assert len(caught) == 2, "the hover-reveal pattern must be caught on both halves"
    assert not [
        d for _, d, _ in _rules_for(".thread-more:hover { color: var(--text); }",
                                    ".thread-more")
        if VANISHES.search(d)
    ], "recolouring on hover is the allowed version and must not be flagged"


def test_the_menu_behind_the_dots_offers_delete():
    """Delete moved into the menu, so the menu is now the only route to it.

    Also pinned here: it is a real `<button role="menuitem">` rather than a div someone
    attached a click to, and the confirmation and the endpoint behind it did not change
    when the control moved.
    """
    template = CHAT_HTML.read_text(encoding="utf-8")
    script = CHAT_JS.read_text(encoding="utf-8")
    offenders: list[str] = []

    menu_at = template.find('id="thread-menu"')
    if menu_at == -1:
        offenders.append("chat.html has no #thread-menu, so the dots open nothing")
    else:
        menu = template[template.rfind("<", 0, menu_at):template.find("</div>", menu_at)]
        if 'data-act="delete"' not in menu:
            offenders.append(
                f'{_at(CHAT_HTML, template, menu_at)} the row menu has no '
                f'data-act="delete" item — the dots replaced the delete control on the '
                f"row, so this is the only way left to delete a chat")
        if "Delete" not in menu:
            offenders.append(
                f"{_at(CHAT_HTML, template, menu_at)} nothing in the menu says Delete")
        if menu.count('role="menuitem"') < 2:
            offenders.append(
                f"{_at(CHAT_HTML, template, menu_at)} the menu items are not marked "
                f'role="menuitem", so the menu is a box of unrelated buttons')
    if "dropThread(id)" not in script:
        offenders.append("chat.js no longer routes the menu's delete item to dropThread")
    if "confirm(" not in script or "'DELETE'" not in script:
        offenders.append(
            "dropThread lost its confirmation or its DELETE call — moving the control "
            "into a menu was not licence to change what it does")
    _report(offenders, "the row menu cannot delete a chat:")


def test_the_menu_is_not_clipped_by_the_scrolling_thread_list():
    """`.threads .list` scrolls, and a scroller clips whatever is positioned inside it.

    An absolutely positioned menu on the last visible row came out as a sliver with
    Delete cut off the bottom. It is fixed, and it lives outside the aside, and both
    halves have to stay true — a fixed menu inside a `display: none` aside is gone
    entirely on the narrow layout.
    """
    css = _css()
    template = CHAT_HTML.read_text(encoding="utf-8")
    offenders: list[str] = []

    if "position: fixed" not in _block(css, ".rowmenu"):
        offenders.append(
            "app.css positions .rowmenu inside the flow, so the thread list's own "
            "overflow will clip it at the bottom of the column")

    aside = template.find('<aside class="threads">')
    menu_at = template.find('id="thread-menu"')
    if aside != -1 and menu_at != -1 and aside < menu_at < template.find("</aside>", aside):
        offenders.append(
            f"{_at(CHAT_HTML, template, menu_at)} the menu is inside the threads aside, "
            f"which is `display: none` under 1240px and scrolls above it")
    _report(offenders, "the row menu is placed where it will be clipped:")


# ── errors, as a person sees them ───────────────────────────────────────────────
#
# A wrong address used to answer `{"detail":"Not Found"}` as text on a white page.
# That is an API's error handed to a person: no navigation on it, nothing naming what
# was missing, and no way back except the browser's own button. It is not a rare path
# in a local app whose operator types URLs and keeps bookmarks — a renamed route turns
# every saved link into one.

def _client():
    from fastapi.testclient import TestClient

    from forgecast.api.main import create_app

    return TestClient(create_app())


def test_a_browser_gets_the_app_back_when_it_asks_for_a_page_that_is_not_there():
    response = _client().get("/no-such-page", headers={"accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "detail" not in body[:200]      # not the JSON error, rendered as text
    assert "There is no page here" in body
    assert 'href="/"' in body              # a way back, on the page itself
    assert "/no-such-page" in body         # and it says which address failed


def test_a_json_caller_still_gets_json():
    """The split is on Accept, so nothing that was parsing these responses breaks."""
    response = _client().get("/no-such-page", headers={"accept": "application/json"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_the_api_answers_json_even_to_a_browser():
    """`/api/...` is machine surface. A fetch() sending the browser's default Accept
    must not start receiving a rendered page where it expects a payload."""
    response = _client().get("/api/no-such-thing", headers={"accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_every_status_the_error_page_claims_to_explain_has_copy_for_it():
    """The fallback exists, but a status listed in the app's own routes and left to it
    is a page that says "Something went wrong" where it could have said what."""
    from forgecast.api.main import _ERROR_COPY

    for code, (headline, detail) in _ERROR_COPY.items():
        assert isinstance(code, int)
        assert headline and not headline.endswith(".")   # a headline, not a sentence
        assert len(detail) > 40                          # says something, not a label
