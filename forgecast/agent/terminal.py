"""Opening a visible terminal, because some sign-ins cannot be driven from behind a UI.

Three separate flows in this app end in a browser: `claude` and its `/login`, `codex
login`, and `claude mcp add`, which authorises a remote MCP server by OAuth. Every one
of them waits on a local callback and prints something the operator needs to read, so
none of them can be run hidden. A hidden sign-in is not a quiet sign-in — it is a
button that appears to do nothing.

This module is the platform half of that, on its own, because the platform half is
where the mistakes are and they are the same mistakes each time:

* **Windows needs `cmd /k`, not `cmd /c`.** `/c` closes the console the moment the
  command returns, which for a flow that prints a URL means the URL flashes and is
  gone.
* **macOS `open -a Terminal` takes a file, not a command with arguments.** Passing an
  argv straight through opens Terminal with nothing running in it, which reads as a
  dead button. A command with arguments has to go through `osascript`.
* **Linux has no terminal.** There is no guaranteed emulator, so the honest failure is
  to hand back the exact command to paste rather than to report success and open
  nothing.

`quote()` is used rather than `" ".join()` for the AppleScript path: these commands
carry URLs and paths, and a path with a space in it silently becomes two arguments.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess

# Tried in order. `x-terminal-emulator` is Debian's alternatives symlink, so it is the
# one most likely to be the terminal the operator actually uses.
_LINUX_TERMINALS = ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")


def command_line(argv: list[str]) -> str:
    """The command as a person would type it, for a message that has to name it."""
    return " ".join(shlex.quote(part) for part in argv)


def open_terminal(argv: list[str], *, done: str, manual: str) -> tuple[bool, str]:
    """Run `argv` in a console the operator can see.

    `done` is what to say when a window opened; `manual` is the instruction to put
    above the command when no terminal could be opened at all. Both are passed in
    because the sentence differs per flow — "type /login there" is true of one of these
    three and false of the other two — and a generic message is how a button ends up
    telling you to do something that flow does not ask for.
    """
    if not argv:                                                      # pragma: no cover
        return False, "Nothing to run."

    try:
        if os.name == "nt":
            # `/k` keeps the console open after the command returns. With `/c` the
            # window closes on completion and takes the printed URL with it.
            subprocess.Popen(["cmd", "/k", *argv],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        elif shutil.which("osascript"):                                       # macOS
            subprocess.Popen(
                ["osascript",
                 "-e", 'tell application "Terminal" to do script '
                       f'"{command_line(argv)}"',
                 "-e", 'tell application "Terminal" to activate'])
        else:
            emulator = next((t for t in _LINUX_TERMINALS if shutil.which(t)), "")
            if not emulator:
                return False, (
                    f"{manual}\n\n    {command_line(argv)}")
            subprocess.Popen([emulator, "-e", *argv])
    except OSError as exc:
        return False, f"Could not open a terminal: {type(exc).__name__}: {exc}"

    return True, done
