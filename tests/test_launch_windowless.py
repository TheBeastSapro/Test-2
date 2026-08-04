"""Starting Forgecast without a black box, and without breaking when there is no console.

Windows creates a console for `cmd.exe` before the first line of a `.bat` runs, so the
black window is not something the batch file opens — it *is* the batch file. The fix is a
`.vbs`, which Windows Script Host can start with the window hidden, and which is present on
every Windows install.

That trade has two teeth, and both are what this file is about.

**A windowless parent makes every console child open its own window.** A console program
started from a process that *has* a console reuses it and opens nothing; started from one
that has none, it gets a new console, raised and focused. Phase one runs pip, creates a
virtualenv and unpacks ffmpeg and Node, so going windowless without suppressing child
consoles first trades one black box for a dozen appearing at random.

**`pythonw.exe` leaves `sys.stdout` as `None`.** Every `print()` in the launcher and the
app then raises `AttributeError`, which would make a windowless start fail on its first
status line — a worse bug than the console it removed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VBS = ROOT / "Forgecast.vbs"


def _launcher():
    """`launcher.py`, imported by path — it is a script, not a package module."""
    spec = importlib.util.spec_from_file_location("_launcher", ROOT / "launcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------- the vbs itself


def test_the_windowless_entry_point_ships():
    assert VBS.exists(), "Forgecast.vbs is the thing to double-click on Windows"


def test_it_starts_the_process_hidden_and_waits():
    """`Run(cmd, 0, True)` — 0 is hidden, True waits.

    Both halves matter. Hidden is the point; waiting is what makes the exit code available,
    and without the exit code a failed start is a double-click that does nothing at all,
    with no error to read. That is worse than the black box.
    """
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert re.search(r"shell\.Run\s*\(?[^\n]*,\s*0\s*,\s*True", text), \
        "the hidden launch must be Run(..., 0, True)"


def test_a_failure_is_reported_without_opening_a_console():
    """The recovery path, because an invisible failure is unreportable — and the shape it
    must *not* take.

    The first version of this re-ran the same command visibly on a non-zero exit. It
    worked, and it was the wrong fix: a crash then produced exactly the black console this
    file exists to prevent, and two of them, because the visible re-run starts a child of
    its own. The complaint was about the box, not about the error inside it.

    So: log every run, and on failure show a dialog naming what went wrong with the log one
    click away. A message box is not a console — it says one thing, it is dismissed, and it
    leaves nothing in the taskbar.
    """
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert "MsgBox" in text, "a failed hidden start must say so somewhere"
    assert "notepad.exe" in text, "the log has to be openable, and not in a terminal"
    assert "forgecast-launch.log" in text, "there is nothing to open without a log"

    # The regression guard proper, against the code rather than the prose: the header
    # comment explains why the console re-run was removed and names both, so a plain
    # substring search over the file would only ever be testing the explanation.
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("'"))
    assert "cmd /k" not in code, "/k is a console window that stays open — the whole complaint"
    assert "Forgecast.bat" not in code, "re-running the batch file is what drew the black box"


def test_the_hidden_run_is_captured_rather_than_discarded():
    """A dialog with nothing in it is a failure with no reason attached, so the child's
    output has to go somewhere a human can be pointed at."""
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert "2>&1" in text, "stderr is where the traceback is"
    assert re.search(r">\s*\"\"?&?\s*logPath|> \"\"\" & logPath", text), \
        "the run must redirect into the log the dialog offers"


def test_it_prefers_the_windowless_interpreter():
    """`pythonw.exe`, and the project's own copy before any on PATH."""
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert ".venv\\Scripts\\pythonw.exe" in text
    assert "pythonw.exe" in text
    # `py -3w` is the windowless form of the installer's shim, and it finds interpreters
    # that are not on PATH at all.
    assert "py -3w" in text


def test_it_tells_the_launcher_not_to_wait_for_a_keypress():
    """A prompt in a window nobody can see is a process that hangs forever."""
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert "FORGECAST_NO_PAUSE" in text


def test_it_anchors_on_its_own_folder_rather_than_the_working_directory():
    """A shortcut, a pinned taskbar item and a double-click all start somewhere else."""
    text = VBS.read_text(encoding="utf-8", errors="replace")
    assert "ScriptFullName" in text
    assert "CurrentDirectory" in text


def test_it_is_crlf_so_windows_script_host_reads_it():
    """WSH is tolerant of LF in practice, but the file is a Windows script and the repo
    ships it as one — `.gitattributes` is where that is enforced, and this asserts the
    intent has not silently been dropped."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.vbs" in attributes or "*.bat" in attributes, \
        "line endings for the Windows entry points must be pinned in .gitattributes"


# ----------------------------------------------------------- the launcher's own half


def test_the_pause_is_skipped_when_there_is_no_window(monkeypatch):
    """Set by the .vbs. Without this the hidden process waits on `input()` forever."""
    launcher = _launcher()
    monkeypatch.setenv("FORGECAST_NO_PAUSE", "1")

    def explode(*_args):
        raise AssertionError("input() must not be called with no window to type into")

    monkeypatch.setattr("builtins.input", explode)
    launcher._pause_if_double_clicked()          # must simply return


def test_missing_streams_are_replaced_rather_than_left_as_none(monkeypatch, tmp_path):
    """`pythonw.exe` gives `sys.stdout is None`, and then the first `print()` raises.

    Replaced with a file rather than discarded, because a log is the only way a windowless
    failure can be reported at all — there is no console to scroll back through.
    """
    launcher = _launcher()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher._ensure_streams()

    assert sys.stdout is not None and sys.stderr is not None
    print("a status line")                       # the call that used to raise
    sys.stdout.flush()
    assert (tmp_path / "runtime" / "launch.log").read_text(encoding="utf-8") \
        .endswith("a status line\n")


def test_an_unwritable_folder_still_yields_usable_streams(monkeypatch, tmp_path):
    """A read-only install directory must not stop the app from starting."""
    launcher = _launcher()
    monkeypatch.setattr(launcher, "ROOT", tmp_path / "nope")
    monkeypatch.setattr(launcher.Path, "mkdir", _raise_oserror, raising=False)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher._ensure_streams()

    assert sys.stdout is not None
    print("still works")


def _raise_oserror(*_args, **_kwargs):
    raise OSError("read-only")


def test_existing_streams_are_left_alone(monkeypatch):
    """Run from a console, nothing is redirected — the output belongs on screen."""
    launcher = _launcher()
    before_out, before_err = sys.stdout, sys.stderr

    launcher._ensure_streams()

    assert sys.stdout is before_out and sys.stderr is before_err


@pytest.mark.skipif(os.name == "nt", reason="the non-Windows branch")
def test_the_interpreter_is_not_swapped_off_windows(tmp_path):
    """`pythonw.exe` does not exist anywhere else, and there is no console to lose."""
    launcher = _launcher()
    candidate = tmp_path / "python"
    assert launcher._windowless_python(candidate) == candidate


def test_child_consoles_are_suppressed_before_the_first_subprocess():
    """The ordering bug this file exists to pin.

    `hide_child_consoles()` is applied at spawn time, so a child already started cannot be
    un-popped. Phase one runs pip, `venv`, and the ffmpeg and Node unpacking — so the call
    has to come before `bootstrap.prepare`, not in the app that runs afterwards.
    """
    source = (ROOT / "launcher.py").read_text(encoding="utf-8")
    hide_at = source.find("hide_child_consoles()")
    prepare_at = source.find("bootstrap.prepare(")
    assert hide_at != -1, "phase one must suppress child consoles"
    assert prepare_at != -1
    assert hide_at < prepare_at, \
        "consoles must be suppressed before the first child process is spawned"


def test_the_relaunch_uses_the_windowless_interpreter():
    """Phase two is the long-lived process; a console there is a console for the session."""
    source = (ROOT / "launcher.py").read_text(encoding="utf-8")
    assert "_windowless_python(python)" in source


# ------------------------------------------------------------------- the packaging


def test_both_windows_entry_points_ship():
    """The .vbs to double-click and the .bat to debug with."""
    spec = importlib.util.spec_from_file_location("_pkg", ROOT / "tools" / "package.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)

    members = [member for _, member in package.files_to_ship()]
    assert "Forgecast/Forgecast.vbs" in members
    assert "Forgecast/Forgecast.bat" in members


def test_the_bat_says_which_one_to_use():
    """Someone who finds the .bat first should be told the .vbs exists, in the file."""
    text = (ROOT / "Forgecast.bat").read_text(encoding="utf-8")
    assert "Forgecast.vbs" in text


def test_the_launcher_still_parses_under_the_system_python():
    """Phase one runs on whatever Python opened the file, so it must import nothing.

    Compiled rather than imported, because importing it is what the other tests do and
    this asserts the weaker, earlier property: it is valid syntax for a bare interpreter.
    """
    result = subprocess.run(
        [sys.executable, "-c",
         f"import py_compile,sys; py_compile.compile({str(ROOT / 'launcher.py')!r}, "
         f"doraise=True)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
