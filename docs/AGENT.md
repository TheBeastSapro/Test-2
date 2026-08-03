# The agent half, for whoever maintains it

Everything below is read out of the code. Line references are `file:line` and are worth
opening — most of the non-obvious decisions already carry a comment saying which failure
they prevent, and this document points at those rather than restating them.

A bare filename means the one in the table below. That matters for exactly one of them:
`auth.py` here is always `forgecast/agent/auth.py`, which answers "can we reach Claude".
There is a second `forgecast/auth.py`, and it is unrelated — passwords, JWTs and the
`current_user` dependency.

## Map

| File | What it is |
| --- | --- |
| `forgecast/agent/auth.py` | Is Claude reachable, and if not, which of three separate things is wrong |
| `forgecast/agent/studio.py` | Every operation the app has, as plain methods on one class |
| `forgecast/agent/tools.py` | Those operations wrapped as an in-process MCP server |
| `forgecast/agent/connectors.py` | Outside services: remote MCP servers, and services that only have a REST API |
| `forgecast/agent/prefs.py` | Model, edit-confirmation and web access, in a JSON file |
| `forgecast/agent/assistant.py` | One turn, as a stream of events |
| `forgecast/api/routes_agent.py` | The HTTP end: threads, attachments, the NDJSON turn |

The load-bearing rule is `studio.py:1-16`: an operation exists in exactly one place, and
both the chat and the buttons reach it there. `Studio.status()` is what the agent gets
from `studio_status` (`tools.py:85`) *and* what the right-hand panel gets from
`GET /api/agent/status` (`routes_agent.py:324`). `tests/test_agent.py:228` asserts the
two cannot disagree; if they could, the panel and the transcript would describe the same
install differently in the same window.

`Studio` takes a session *factory*, not a session (`studio.py:104`). Tool calls arrive
from the agent's event loop minutes apart while the browser is using its own
request-scoped session, and a shared one hands the agent a channel that was renamed two
turns ago out of a stale identity map.

---

## Auth is a subscription, not an API key

There is no API key in this app and you should not add one. The agent drives the Claude
Code CLI, signed in with the operator's own Claude subscription — the same `/login`
browser flow they already use. `auth.py:1-29` is the full statement of intent.

`auth.check()` (`auth.py:187`) runs **before a single token is spent** and returns an
`AuthStatus` (`auth.py:53`) describing exactly one of four states, in this order:

1. **A key is shadowing the login** (`auth.py:192-208`) — see below.
2. **The CLI is a Windows `.cmd` shim** (`auth.py:211-223`).
3. **The CLI is missing** (`auth.py:224-234`).
4. **The CLI is there but nobody signed in** (`auth.py:236-249`) — the only case the app
   can act on itself, so it is the only case that sets `can_login=True` (`auth.py:64`).

Conflating 3 and 4 was a real bug in the app this pattern comes from: "signed in with
your subscription" sat above a chat answering *Not logged in*, because CLI **present**
had been treated as CLI **signed in** (`auth.py:25-28`). They are separate reads now:
`find_cli()` (`auth.py:114`) for presence, `_credentials()` (`auth.py:150`) for the
sign-in. `_credentials` reads `~/.claude/.credentials.json` (falling back to
`~/.claude.json`) off disk rather than probing with a request — sending a prompt to find
out whether a prompt would work spends tokens on every page load.

The self-consistency this buys is asserted at `tests/test_agent.py:166`: a report may
never be `ok` *and* offer the sign-in button. If you extend `AuthStatus`, keep that
invariant — a green chip above a sign-in prompt is the failure mode the whole module
exists to prevent, and `tools/smoke.py` checks it against a built install too.

### The `ANTHROPIC_API_KEY` shadowing trap

This is the one that costs money silently.

Credential resolution checks `ANTHROPIC_API_KEY` **first**. A leftover key from any
earlier experiment therefore outranks the subscription login, and requests bill an API
account instead of the plan the operator already pays for. Nothing breaks. There is no
error to notice.

Two consequences that catch people out, both encoded in the code:

* **An empty value still wins.** `ANTHROPIC_API_KEY=""` occupies the slot. So the check
  is `os.environ.get(...) is not None`, not a truthiness test — `auth.py:190`, and again
  in `desktop/bootstrap.py:255`. It has to be genuinely unset, not blanked, which is why
  the Windows fix printed at `auth.py:204` is `setx … "" && set ANTHROPIC_API_KEY=`
  (two commands: one for the stored value, one for this shell).
* **The desktop launcher removes it from its own process.** `toolchain.activate()` pops
  it (`desktop/toolchain.py:481`) before anything spawns a child, and
  `desktop/app.py:155-157` prints that it did. The operator's shell keeps the variable;
  only the app ignores it. So a `check()` that reports shadowing under the desktop
  launcher means the variable was set *after* start-up, or the server was started some
  other way — `forgecast serve`, uvicorn directly, Docker — where nothing scrubbed it.

`FORGECAST_ANTHROPIC_API_KEY` in `.env.example:18` is a different thing entirely: a
provider key for the pipeline's LLM calls, namespaced by the settings prefix. It does not
shadow anything. Do not "fix" one by renaming the other.

Two more Windows-only facts worth knowing before you debug a report you think is wrong:

* npm's global install produces `claude.cmd`, and the SDK refuses to spawn a batch
  script. A shim is deliberately reported as *not found* (`_spawnable`, `auth.py:100`),
  because reporting it as connected produces the worst possible failure — setup goes
  green, the chip says connected, the first message dies. `shim_only()` (`auth.py:137`)
  exists so that case gets the native installer (`WINDOWS_NATIVE_HINT`, `auth.py:47`)
  rather than the npm line that produced the shim. `tests/test_agent.py:590` pins this,
  including the assertion that the fix does **not** mention `npm install -g`.
* The `claude-agent-sdk` wheel bundles a native binary and the SDK resolves it before
  PATH, so most installs need nothing at all. `_bundled_cli()` (`auth.py:77`) finds it by
  importing the SDK and asking where its package lives, so a wheel that moves the
  directory does not silently return `None`.

`start_login()` (`auth.py:264`) opens a *visible* terminal running the CLI. That is not
sloppiness: `/login` is an interactive command inside Claude Code — there is no
`claude login` subcommand — so it cannot be driven from behind the UI. Hiding the window
would mean nothing happens and the button looks broken.

---

## The tool set

`tools.build_server()` (`tools.py:76`) wraps `Studio` methods as an in-process MCP server
named `forgecast` (`tools.py:41`), created with `create_sdk_mcp_server` at `tools.py:259`.
The studio object is passed in rather than constructed there so the tools and the pages
share one — a second copy drifts inside a single conversation.

Three lists, and the difference between them is the whole policy (`tools.py:43-59`):

```python
_READ_ONLY = (
    "studio_status", "list_channels", "study_youtube_channel", "list_runs",
    "run_status", "preview_run", "list_styles", "score_videos", "research_channel",
    "run_files", "cast_voice", "voice_catalogue",
)
_WRITES = ("create_channel", "update_channel", "start_run", "apply_style",
           "blend_styles", "cancel_run")

ALLOWED = [f"mcp__{SERVER_NAME}__{name}" for name in (*_READ_ONLY, *_WRITES)]
ALL_TOOLS = [*_READ_ONLY, *_WRITES, "decide_gate"]
```

`ALLOWED` is handed to the SDK as `allowed_tools` (`assistant.py:181`) — the set the
agent may call without stopping to ask. `ALL_TOOLS` is every tool the server actually
serves. The gap between them is exactly one name.

### Why `decide_gate` is deliberately not pre-allowed

`decide_gate` is registered and callable (`tools.py:161`, dispatching to
`Studio.decide_gate` at `studio.py:501`) but absent from `ALLOWED`, so calling it stops
and asks the operator.

The reason is not that approving a gate is risky in the abstract. It is that **approving
is the moment a run is allowed to spend.** A run pauses at a gate; the stage behind it
costs real credits and real machine time; releasing it is the decision the operator is
being asked to make. Every other tool in the set is read-only or re-runnable, including
`start_run` — which takes a credit hold and then stops at the first gate rather than
running to completion (`tools.py:147-152`), which is why it *is* pre-allowed.

The system prompt says the same thing in prose (`assistant.py:112-118`): *"'It looked
fine so I approved it' is the single worst thing you can do in this app."* Belt and
braces on purpose — the prompt is a request and the allow-list is a mechanism, and only
one of them is enforced. `tests/test_agent.py:343` asserts both halves: `decide_gate` out
of `ALLOWED`, present in `ALL_TOOLS`, and `start_run` still in `ALLOWED`.

Also deliberately not tools at all (`tools.py:18-30`): deleting a channel, deleting a
style, clearing credentials. Those are not reversible by re-running them, so they stay
buttons.

Two smaller conventions in this file, both easy to break by accident:

* `_text()` (`tools.py:62`) sets `is_error: True` when the payload carries an `error`
  key. Without it a returned `{"error": ...}` reads to the model as a *successful* call
  whose result happens to mention a problem, and it carries on regardless. `Studio`
  returns errors as dicts rather than raising (`studio.py:13-15`), so this is the only
  thing marking them as failures.
* Tool descriptions are the API. They are what the model reads to decide whether to call
  something, so they name what is measured and what the caveats are, in the imperative.
  Compare `study_youtube_channel` (`tools.py:101`) with what a docstring would have said.

### The sandbox

`build_options()` (`assistant.py:153`) confines the agent: `cwd` is the app root,
`add_dirs=[]`, and `sandbox.enabled` with `allowUnsandboxedCommands: False`
(`assistant.py:178-189`). `cwd` alone is not confinement — it says where a shell command
starts, not where it can go.

`autoAllowBashIfSandboxed: True` looks like a loosening and is the opposite: the sandbox
is the boundary, and prompting a second time for a guarantee already enforced trains
people to click through prompts.

Network stays on because research is half the job; `allow_web=False` narrows it to
managed domains *and* disallows `WebFetch`/`WebSearch` (`assistant.py:190-193`).

`permission_mode` is chosen per turn from prefs at `routes_agent.py:456`: `"default"`
(every file edit prompts) when `confirm_edits` is set, `"acceptEdits"` when it is not.
Tool calls are unaffected either way — that is `ALLOWED`'s job, and the distinction is
stated at `prefs.py:25-27`.

---

## A turn, and how a conversation is resumed

`assistant.run()` (`assistant.py:232`) is an async generator yielding
`{"type": "text"|"thinking"|"tool"|"tool_result"|"session"|"result"|"error", ...}`.
`routes_agent.chat()` (`routes_agent.py:338`) re-emits each event as one line of
newline-delimited JSON.

NDJSON rather than SSE, deliberately (`routes_agent.py:3-6`): the client is `fetch` in
the same window so SSE's framing buys nothing, and NDJSON survives a proxy that
helpfully buffers `text/event-stream`.

The first thing `run()` does is `auth.check()` (`assistant.py:255`) and yield an error
event if it fails — the refusal is honest and costs nothing.

Resumption is one string. Each `Conversation` row stores the CLI's own session id
(`models.py:356`); `chat()` reads it as `resume` (`routes_agent.py:384`) and passes it
into `build_options`, which forwards it to the SDK (`assistant.py:172-173`). A fresh
`query` per message — the obvious implementation — produces an agent with amnesia that
re-reads the same state every turn and still contradicts itself (`assistant.py:15-20`).

### Why the session id is persisted the moment it is known

This is the part to understand before changing anything in `chat()`.

`run()` emits a `session` event as soon as it sees a session id on an `AssistantMessage`,
not at the end of the turn (`assistant.py:264-272`). The route writes it immediately, in
its own database session, in `_remember_session()` (`routes_agent.py:422-440`).

The comment there names the bug, and it is worth quoting because the symptom does not
look like a bug at all:

> The id arrives early and the turn can run for minutes afterwards; if it is only
> written at the end, then any turn that does not reach the end — a closed window, a
> reload, a killed process — leaves the thread with no session to resume, and the *next*
> message starts a brand-new conversation. The agent then says things like "I don't have
> the script in front of me" one turn after you pasted it, and nothing looks broken.

There were two separate failures here and both had to be fixed:

1. **The write happened too late.** Fixed by emitting and persisting early
   (`assistant.py:264-272`, `routes_agent.py:495-498`).
2. **The end-of-turn save was skipped entirely on disconnect.** `_save()` is called from
   a `finally`, not from a statement after the loop (`routes_agent.py:509-524`). Closing
   the window mid-turn makes Starlette close the response generator, which raises
   `GeneratorExit` at the paused `yield` — and `GeneratorExit` and `CancelledError` are
   `BaseException`, so `except Exception` never sees them and anything after the loop
   never runs. A turn here can run for minutes, which makes a mid-turn reload the normal
   case rather than the unlucky one. `tests/test_agent.py:435` reproduces it by reading
   one line and walking away.

Two rules fall out of that, and breaking either reintroduces the bug:

* **`_save()` must not raise.** It runs during unwinding. It builds its own
  `SessionLocal()` (`routes_agent.py:396`) because the request's session was closed when
  the response started streaming, and writing through a closed session is how a whole
  conversation silently fails to save. It swallows and logs.
* **`assistant.run()` must never `yield` from a `finally`.** Yielding while unwinding
  raises "async generator ignored GeneratorExit", which aborts teardown of the CLI
  subprocess. `assistant.py:310-314` says so where the `finally` would have gone, and
  `tests/test_agent.py:570` asserts it against the AST of the function — the failure only
  shows up when a generator is closed early, which is the hardest case to notice.

### Dead sessions

A `resume` id the CLI no longer has happens for ordinary reasons: its session store was
cleared, the app was copied to another machine, storage was reset. Without handling, the
thread is bricked — every later message resumes the same dead id and fails identically.

The SDK raises a generic `ProcessError` for this, so there is nothing typed to catch.
`_looks_like_a_dead_session()` (`assistant.py:327`) matches substrings
(`_DEAD_SESSION_SIGNS`, `assistant.py:321`) and sets `resume_failed` on the error event.
`chat()` retries **once**, from scratch: clears the stored id via `_forget_session()`,
drops the partial text and tool calls, and streams a `notice` event saying it started
fresh (`routes_agent.py:465-479`). Guessing wrong here means either a bricked thread or a
silent retry that hides a real failure, which is why the retry is capped at one and
announced. `tests/test_agent.py:477` asserts the attempt sequence
`[None, "brand-new", None]`.

### One turn per thread

`_IN_FLIGHT` (`routes_agent.py:51`) is a plain in-process set of conversation ids; a
second POST gets 409 (`routes_agent.py:364-369`). The browser's own guard is per page, so
two desktop windows — or a tab left open from earlier — sail past it, both turns resume
the same session id, and the last to finish writes its session over the other's. A set
rather than a row lock because the thing being serialised is a CLI subprocess owned by
this process. Discarded in the same `finally` as the save (`routes_agent.py:524`), so a
crashed turn does not leave a thread permanently refusing to talk.

### Attachments

Uploads land in `APP_ROOT/attachments` (`routes_agent.py:58-67`) — inside the sandbox on
purpose, because a file dropped anywhere else is a path the agent is not allowed to open
and the attachment looks like it worked and then quietly fails at the `Read`.

`describe()` (`routes_agent.py:214`) classifies by extension and returns a `note` that
tells the agent what it can *honestly* do: an image it can open, audio it **cannot**
listen to and must measure with ffprobe, video it cannot watch. Said plainly because a
model that cannot hear will otherwise describe how something sounds anyway. The notes are
injected into the prompt as a file listing at `routes_agent.py:379-381`.

`safe_name()` (`routes_agent.py:234`) exists because the extension is what everything
downstream reads, and a clipboard paste arrives with no filename and only a MIME type. It
derives one, so a pasted screenshot is an image the agent opens rather than an opaque
blob. `tests/test_agent.py:531` covers the cases, including that a de-duplicated `.env`
does not become `-1` with no extension.

---

## Connectors: two kinds, and why conflating them was a bug

A connector is an outside service the agent can *call*, in the same conversation, rather
than asking the operator to copy numbers between two apps (`connectors.py:3-5`). Connect
NexLev and the agent gains its niche finder, outlier search and channel analytics.

There are two kinds and the distinction is load-bearing (`connectors.py:75`):

* **`mcp`** — a remote MCP server, which hands the agent a set of tools. A URL, usually a
  token. The module originally assumed everything was this.
* **`api`** — a service with a REST API and no MCP server at all. A credential, no URL.

`active()` used to return every connected entry, so an API-only service was configured as
an MCP endpoint speaking a protocol it has never spoken. That fails as a 401 — identical
to a rejected token — so the operator re-pastes a credential that was never wrong. It now
filters on `kind == "mcp"`, and `api_credentials()` (`connectors.py:257`) is how the
provider adapter for a service asks for its own. Pinned by
`tests/test_agent.py:780`.

Keep this distinct from a provider key, because they fail differently:

* a **provider key** lets *the pipeline* call a vendor (ElevenLabs renders narration) — a
  dead one breaks a render;
* a **connector** lets *the agent* call one — a dead one means fewer tools this turn, and
  the agent should say so.

They are configured in separate places for that reason, and `GET /api/connectors` returns
that sentence as a `note` (`routes_agent.py:543`).

How they reach the agent: `build_options` merges `connectors.active_servers()` into the
same `mcp_servers` dict as the app's own server (`assistant.py:164-165`). `active()`
(`connectors.py:246`) returns only entries that are both enabled and have a URL, and
`as_mcp()` (`connectors.py:146`) shapes each one — `{"type": "http"|"sse", "url": …,
"headers": {"Authorization": "Bearer …"}}`. A bearer header, never a query parameter;
`tests/test_agent.py:251` pins that.

Things that will bite you:

* **The catalogue asks for a URL rather than shipping one** (`connectors.py:28-33`,
  `CATALOGUE` at `connectors.py:86`). Several of these endpoints are issued per
  workspace. Guessing one produces an app that silently fails to connect and blames the
  network, so every `ConnectorSpec` carries a `where` field saying which page of which
  service to copy it from. `tests/test_agent.py:240` asserts `where` is non-empty.
* **Storage is a file, not a table** (`connectors.py:133-140`,
  `storage/connectors.json`). The agent's MCP servers have to be resolved before a
  request exists, from a worker thread, at CLI start-up. Reaching for a request-scoped
  database session there is how a config load ends up holding a connection it should not
  have.
* **Tokens are encrypted with the `.env` envelope key.** `Store.save()` calls
  `crypto.encrypt` (`connectors.py:218`); `load()` catches a decrypt failure, logs it and
  attaches a note telling the operator to paste it again rather than crashing the page
  (`connectors.py:206-210`). This is why `.env` must not be copied between installs. URLs
  are stored in the clear so a misconfiguration is readable.
* **A blank token on save means "leave it alone"** (`connectors.py:230-232`). The page
  shows a mask, so an unedited field submits empty; treating that as "clear it" would
  wipe a working token on any unrelated edit.
* **`active_servers()` never raises** (`connectors.py:291`). A broken connectors file
  degrades to an agent with fewer tools, not a chat that will not start.
* **`listing()` includes configured keys that are not in the catalogue**
  (`connectors.py:279-281`), or they would be invisible and unremovable.

`POST /api/connectors/{key}/test` (`routes_agent.py:569`) sends a real MCP `initialize`
to the configured endpoint. Deliberately a request and not a URL-shape check: the failure
it catches is a token pasted with a trailing space, and no amount of validating the
string finds that. 401/403 gets its own message; a non-JSON body is treated as a
streaming server answering in SSE, which is a perfectly good sign of life.
`GET /api/connectors/mcp-config` (`routes_agent.py:618`) shows what the agent will
actually be handed, header values redacted, so a mistake is visible.

---

## Research reads a channel with no key

`research_channel` (`studio.py:639`) and `study_youtube_channel` (`studio.py:308`) both
start from a link, because a link is what is in the operator's clipboard. Neither needs a
YouTube Data API key.

That was not always true, and the old behaviour is worth stating because it is the failure
this path exists to remove: the most obvious thing anyone can do here — paste a channel —
answered *"no key configured, paste the numbers instead"*, on every fresh install. A
feature that sends you to the Google console before it will do anything reads as broken,
and it was reported as exactly that. `tests/test_research_keyless.py:342` pins the
behaviour that replaced it.

Both methods call one function, `sources.read_channel` (`research/sources.py:354`), so the
choice of source is made in one place instead of separately in each caller:

* **a key in Settings** → the YouTube Data API (`research/sources.py:273`). Preferred when
  it is there: measured timestamps, plus like and comment counts.
* **no key** → the channel's public uploads listing, read with `yt-dlp`
  (`research/keyless.py:126`). No key, no quota, no account.
* **the API failing** → the same keyless read. Not a hedge: a quota exhausted at lunchtime
  is the ordinary way this breaks, and the numbers are still sitting on the public page.
  When both fail the error names both, API first, because that is the one the operator
  configured and can therefore act on (`research/sources.py:377-386`).

`read_channel` returns the parsed videos *and* a note naming the source, and every caller
passes that note on as `via` — `studio.py:360` and `studio.py:677` for the two tools,
`routes_research.py:176` for the desk. The caveat belongs in what the operator reads, not
in a log line, which is also why the tool description states it (`tools.py:195`) rather
than leaving the model to assume a number is measured.

### The dates are reconstructed, and the scorer decides what that costs

A flat playlist listing has no publish dates at all. `youtubetab:approximate_date`
(`research/keyless.py:143`) produces one anyway, worked back from the relative label the
page shows — "2 months ago" — so it can be about half a month out. The fixture in
`tests/test_research_keyless.py:34` is the evidence rather than an illustration: three of
its six real entries carry an identical timestamp, because all three said "2 months ago".

An outlier is views divided by age, so an age that is fifteen days wrong reports a
multiple wrong in exact proportion — under 2% on a two-year-old video, around 17% on a
three-month-old one, and 3.0x is the threshold this app uses. That is why the reader only
records the fact (`date_is_approximate`, `research/outliers.py:99`) and the arithmetic
decides what it costs, per video: `approximate_date_span` (`research/outliers.py:201`)
brackets the multiple using `APPROXIMATE_DATE_ERROR_DAYS` (`research/outliers.py:80`), and
if half a month of error is enough to drop a video below the threshold it was included at,
it comes back unreliable with the range it could really be in
(`research/outliers.py:301-321`). `Outlier.as_dict()` (`research/outliers.py:165`) carries
`multiple_low`, `multiple_high`, `date_is_approximate` and `engagement_known` so a UI can
print a range, or "not known", instead of a point number nobody measured.

That is the fifth of the scorer's corrections; the first four — age, format, sample size,
youth — are at `research/outliers.py:17-36` and the fifth at `research/outliers.py:38-49`.
None of them is a prompt. Every one is arithmetic over public statistics, because a model
asked whether 240k views is good for a channel answers with a confident number and no
method behind it.

### The dependency, and why it stopped being optional

`yt-dlp` is a base dependency (`pyproject.toml:40`), so every install path has it: the
launcher installs `-e .` (`desktop/bootstrap.py:144`) and the image installs `.[postgres]`
(`Dockerfile:30`), and both resolve the base list.

It was the `research` extra, on the reasoning that the desk still answers without it and
that a scraper wanting frequent updates is a bad thing to pin. The first half was true and
the second is still true, but they were the wrong things to weigh. What actually happened
was that the agent answered the most obvious request in the app — "here is a channel link"
— by telling the operator to run `pip install yt-dlp`. An installer that asks the operator
to finish the installation has not installed anything, and it was reported as exactly that.
The update concern belongs in the toolchain page, which lists a version and can upgrade in
place, not in a decision about whether the feature works on first launch.

Absence is reported, not crashed on. `keyless.available()` (`research/keyless.py:87`)
returns the fix — install it, or add a key — and the research page prints that line and
disables its fetch box (`routes_research.py:76-103`). The box was gated on the *key*
before, which switched fetching off on installs that could in fact fetch; the same slot
now carries the approximate-date caveat when a keyless read is possible.
`tests/test_agent.py:131` covers the only case that genuinely cannot read a channel: no
key *and* no binary.

---

## Adding a new tool: a worked example

Four edits, in this order. The example is `channel_memory` — a genuine gap: gate
decisions accumulate in `ChannelMemory` (`models.py:162`) and are injected into stage
prompts by `memory.recall()` (`forgecast/memory.py:47`), but the agent has no way to see
what a channel has learned, so it cannot tell you why a script came out the way it did.

### 1. The operation, in `studio.py`

It goes here and only here, so the chat and any future panel cannot disagree. Match the
house shape of `list_channels` (`studio.py:243`): open a session from the factory,
resolve the user, **scope every query to that user**, return a dict of numbers, return
`{"error": …}` rather than raising.

```python
    def channel_memory(self, channel: Any, *, limit: int = 12) -> dict:
        """What this channel has learned, so the agent can explain its own output.

        Recall order is the one the pipeline actually uses, not chronological — a
        chronological list invites the agent to quote the oldest lesson as the
        operative one, when the stage prompt was built from the ranked few.
        """
        from ..memory import recall

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            found = self._channel(session, user, channel)
            if found is None:
                return {"error": f"No channel matching {channel!r}.",
                        "channels": [row["name"]
                                     for row in self.list_channels()["channels"]]}
            entries = recall(session, found.id, limit=max(1, min(int(limit), 50)))
            return {
                "channel": found.name,
                "count": len(entries),
                "memories": [
                    {"kind": entry.kind.value, "content": entry.content,
                     "stage": entry.node_type or "(any)", "weight": entry.weight,
                     "run": entry.run_id}
                    for entry in entries
                ],
            }
```

`self._channel()` (`studio.py:129`) is why the tool can take a name or an id — the agent
has the name from the conversation and the id nowhere, and requiring the id would mean a
`list_channels` call before every operation. Returning the real channel names alongside
the error is the pattern from `start_run` (`tests/test_agent.py:99`): a failed lookup that
also tells you what exists is one round trip instead of two.

### 2. The MCP wrapper, in `tools.build_server()`

Inside `build_server`, beside the other channel tools (`tools.py:92-134`). The
description is what the model reads to decide whether to call it, so it says what comes
back and when to use it:

```python
    @tool("channel_memory",
          "What a channel has learned from its own gate decisions: what was approved, "
          "what was sent back and why, ranked the way the pipeline ranks it when it "
          "builds a prompt. Read-only. Use it to explain why a script or an edit came "
          "out the way it did, instead of guessing.",
          {"channel": str, "limit": int})
    async def channel_memory(args):
        return _text(studio.channel_memory(args.get("channel") or "",
                                           limit=int(args.get("limit") or 12)))
```

Note the coercions: MCP arguments arrive as whatever the model sent, so
`args.get(...) or ""` and `int(... or 12)` are load-bearing, not defensive noise. Every
existing wrapper does the same.

### 3. Register it in the server

`create_sdk_mcp_server`'s `tools=[…]` list at `tools.py:259` is explicit — a tool the
decorator created but the list omits is silently absent, which presents as a model that
"forgot" a tool it was told about. Add `channel_memory` to that list.

### 4. Decide which list it belongs in

This is the decision, and it is not automatic:

```python
_READ_ONLY = (
    "studio_status", "list_channels", "channel_memory", "study_youtube_channel",
    ...
)
```

Put it in `_READ_ONLY` if it only reads. Put it in `_WRITES` if it changes something that
can be changed back or produced again. **Put it in neither if calling it spends money,
deletes something, or releases a gate** — `ALL_TOOLS` (`tools.py:59`) lists it so the
server serves it, `ALLOWED` (`tools.py:57`) omits it so the agent has to ask, and that
gap is the whole safety model. `channel_memory` reads rows, so `_READ_ONLY`.

If the tool is one the agent should treat differently — always call it first, never call
it unasked — say so in `system_prompt()` (`assistant.py:62`) as well. The prompt is a
request and the allow-list is a mechanism; use the mechanism for anything that matters.

### 5. Test it

`tests/test_agent.py` tests `Studio` methods directly, without the MCP layer or a signed-in
CLI (`tests/test_agent.py:1-7`), and asserts on the numbers rather than on `ok`:

```python
def test_channel_memory_is_scoped_to_its_owner(user, session):
    from forgecast.auth import hash_password
    from forgecast.memory import remember
    from forgecast.models import MemoryKind, User

    studio = Studio(user_id=user.id)
    made = studio.create_channel("Ocean Freight", niche="logistics")
    remember(session, made["id"], MemoryKind.revision, "Never open on a question.")
    session.commit()

    # Addressable by name, because that is what the agent has in the conversation.
    recalled = studio.channel_memory("ocean freight")
    assert recalled["count"] == 1
    assert "Never open on a question" in recalled["memories"][0]["content"]

    # And not addressable at all by another account, even with the real id in hand.
    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.commit()
    assert "error" in Studio(user_id=other.id).channel_memory(made["id"])
```

That last assertion is the one that matters and the one easiest to leave out — and it has
to use a second *real* account, not an id that does not exist, or it passes on "no such
user" and proves nothing about scoping. Every `Studio` method filters on `user_id`; a new
one that forgets is a cross-account read no test will catch unless the test looks for it.

---

## What is not covered by tests, and why

The agent loop itself needs the CLI and a subscription, which CI does not have
(`tests/test_agent.py:1-7`). What is asserted is everything up to and including the point
where the loop would start, plus the honest refusal when it cannot — and the two bugs that
only appear on early generator close are asserted structurally instead: `test_agent.py:435`
by abandoning a stream, `test_agent.py:570` by walking the AST of `assistant.run`.

For a built install, `tools/smoke.py` runs the same checks against a real server: the app
starts, `/healthz` answers, the chat page renders, `/api/setup/state` reports the
toolchain, a thread round-trips, an attachment comes back with the right `kind`, and the
auth report is self-consistent. `tests/test_smoke.py` checks the smoke script's own checks
against the `TestClient`, so a check that can never fail does not sit there looking green.
