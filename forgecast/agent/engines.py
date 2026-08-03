"""Which agent answers: Claude, or ChatGPT. One seam, one contract.

## Where the seam is, and why it is here

`assistant.run()` — an async generator yielding `{"type": ...}` dicts — was already
the whole boundary between "an agent doing work" and "a page rendering it". So the
second backend is a second implementation of exactly that, and this module is nothing
but the choice between them.

What was rejected:

* **A branch inside `assistant.run`.** That file is about Claude: its sandbox, its
  permission prompts, its session ids. A second agent's process management wedged into
  it would leave neither readable.
* **A provider abstraction over "send a prompt, get text".** The loop is not that. It
  is a tool-calling agent over twenty-one studio operations, and an interface narrow
  enough to hide the difference would also hide the tool calls, which are the part
  worth showing.
* **One flat model picker.** `gpt-5.6-terra` and `claude-opus-5` in one list means
  choosing a model that the running backend cannot serve, and a 400 from a vendor
  instead of a sentence. Models belong to an engine; see `prefs.model_for`.

## Why `run()` is not itself a generator

It picks an implementation and returns *its* generator, rather than iterating it and
re-yielding. A wrapper generator would add a second frame that GeneratorExit has to
unwind through when the browser closes mid-turn — and `assistant.run` carries a long
comment about exactly that hazard, plus a test asserting it. Returning the inner
generator means the caller's `async for` drives the real one, and there is no new place
for teardown to go wrong.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from . import (assistant, auth, codex_agent, codex_auth, minimax_agent,
               minimax_auth, prefs)

CLAUDE = "claude"
CHATGPT = "chatgpt"
MINIMAX = "minimax"


@dataclass(frozen=True)
class Engine:
    """One backend, and everything the picker has to say about it.

    The prose lives here rather than in the template because the honest version of it
    is a claim about how the code authenticates, and a claim like that belongs beside
    the code that would make it false.
    """

    key: str
    label: str
    # What it needs, in the one line shown under the picker. This is the sentence that
    # has to be true: both of these are "sign in to a plan you already have", and if
    # that ever stops being true for one of them, this string is the thing that lies.
    signin: str
    models: list[dict]
    default_model: str
    # What the other one can do and this one cannot. Shown, not hidden: a setting that
    # silently does nothing is worse than a setting that says it does nothing here.
    limits: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "signin": self.signin,
                "models": self.models, "default_model": self.default_model,
                "limits": self.limits}


ENGINES: list[Engine] = [
    Engine(
        key=CLAUDE,
        label="Claude",
        signin="Signs in with your Claude subscription — the browser flow you already "
               "use. No API key, nothing billed per token.",
        models=assistant.MODELS,
        default_model=assistant.DEFAULT_MODEL,
    ),
    Engine(
        key=CHATGPT,
        label="ChatGPT",
        signin="Signs in with your ChatGPT plan through OpenAI's Codex CLI — the same "
               "kind of browser sign-in. No API key, nothing billed per token.",
        models=codex_agent.MODELS,
        default_model=codex_agent.DEFAULT_MODEL,
        limits=[
            "Runs each turn non-interactively, so it cannot stop to ask before editing "
            "a file — “Confirm calls” has no effect on this backend.",
            "It is never given decide_gate: approving a gate releases real spend and "
            "this backend has no way to pause and ask you first.",
            "Needs OpenAI's Codex CLI installed once (npm install -g @openai/codex). "
            "Claude needs nothing new.",
        ],
    ),
    Engine(
        key=MINIMAX,
        label="MiniMax",
        signin="Signs in with your MiniMax subscription through their own CLI — a browser "
               "flow, no API key. Narration is separate and still bills the MiniMax API "
               "balance; this covers the chat.",
        models=minimax_agent.MODELS,
        default_model=minimax_agent.DEFAULT_MODEL,
        limits=[
            "Runs each turn non-interactively, so it cannot stop to ask before editing "
            "a file — “Confirm calls” has no effect on this backend.",
            "It is never given decide_gate: approving a gate releases real spend and "
            "this backend has no way to pause and ask you first.",
            "Their CLI has no resumable session, so the thread is re-sent each turn. A "
            "very long conversation costs more here than on Claude.",
            "Needs the MiniMax CLI installed once (npm install -g mmx-cli). Claude needs "
            "nothing new.",
        ],
    ),
]

BY_KEY = {engine.key: engine for engine in ENGINES}
DEFAULT = CLAUDE


def resolve(key: str | None) -> Engine:
    """The engine for a stored or requested key, falling back to Claude.

    Never raises. An unreadable prefs file, a value from a newer build, a typo in a
    request — every one of those should leave you talking to Claude, which is what the
    install did before anybody touched the setting.
    """
    return BY_KEY.get((key or "").strip().lower(), BY_KEY[DEFAULT])


def current(settings: prefs.Prefs | None = None) -> Engine:
    return resolve((settings or prefs.load()).engine)


def catalogue() -> list[dict]:
    return [engine.as_dict() for engine in ENGINES]


def auth_check(key: str | None = None) -> dict:
    """"Is it connected", for whichever agent is selected.

    Both report the same field names on purpose — see `codex_auth.CodexStatus` — so the
    chat has one auth panel rather than one per vendor.
    """
    engine = resolve(key)
    if engine.key == CHATGPT:
        report = codex_auth.check().as_dict()
    elif engine.key == MINIMAX:
        report = minimax_auth.check().as_dict()
    else:
        report = auth.check().as_dict()
    return {**report, "engine": engine.key, "engine_label": engine.label}


def start_login(key: str | None = None) -> tuple[bool, str]:
    engine = resolve(key)
    if engine.key == CHATGPT:
        return codex_auth.start_login()
    if engine.key == MINIMAX:
        return minimax_auth.start_login()
    return auth.start_login()


def run(prompt: str, *, studio, settings: prefs.Prefs | None = None,
        engine: str | None = None, **kwargs: Any) -> AsyncIterator[dict]:
    """One turn from the selected backend, as the same stream of events either way.

    Note the return, not `yield` — see the module docstring.
    """
    settings = settings or prefs.load()
    chosen = resolve(engine or settings.engine)
    model = kwargs.pop("model", None) or settings.model_for(chosen.key)
    # Which account's studio the tools act on. Claude's tools are in this process and
    # already hold the right `studio`; Codex's run in a subprocess that has to be told.
    # Passing it to both would reach `ClaudeAgentOptions` as an unknown keyword.
    user_id = kwargs.pop("user_id", None)

    if chosen.key == MINIMAX:
        return minimax_agent.run(prompt, studio=studio, model=model, user_id=user_id,
                                 allowed=allowed, history=history)
    if chosen.key == CHATGPT:
        return codex_agent.run(prompt, studio=studio, model=model, user_id=user_id,
                               **kwargs)
    # Called through the module rather than as an imported name so that patching
    # `assistant.run` — which the tests do, and which is how a fake turn is injected —
    # is still seen from here.
    return assistant.run(prompt, studio=studio, model=model, **kwargs)
