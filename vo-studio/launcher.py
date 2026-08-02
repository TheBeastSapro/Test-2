"""
VOStudio.exe — the thing you double-click.

WHY THIS IS A THIN LAUNCHER AND NOT ONE GIANT .EXE

    Bundling PyTorch and the CUDA runtime into a single executable produces a
    ~5 GB file that unpacks itself to a temp folder on EVERY launch, so it takes
    minutes to open, and it breaks whenever a CUDA DLL is not where the bundler
    guessed. It would not even be self-contained: the Chatterbox weights are
    another ~1 GB that downloads on first run either way.

    So the .exe is small and does one job — find the environment sitting next to
    it and start the app in a native window, with no console and no browser. It
    is a real Windows executable with a real icon and a real taskbar entry. What
    it is not is a copy of PyTorch pretending to be one.

    Rebuild it any time with build_exe.bat.
"""
import os
import subprocess
import sys
from pathlib import Path


def app_dir() -> Path:
    """Where the app lives — next to the .exe when frozen, next to this file otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def die(title: str, message: str) -> int:
    """
    A message box, not a traceback.

    There is no console window in a --noconsole build, so a bare exception is
    completely invisible — the icon bounces and nothing happens. Every failure
    here has to be something you can read.
    """
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        print(f"{title}\n\n{message}")
    return 1


def main() -> int:
    root = app_dir()

    # Everything lives in .\runtime — nothing is installed on the machine, so
    # there is no system Python to fall back to and none is wanted.
    # Setup either unpacks the embeddable Python flat, or — when a supported
    # Python is already on the machine — builds a venv from it, which nests the
    # interpreter under Scripts\. Both layouts are normal; take the first that
    # exists, preferring pythonw so no console flashes.
    rt = root / "runtime"
    interpreter = next(
        (p for p in (rt / "python" / "Scripts" / "pythonw.exe",
                     rt / "python" / "pythonw.exe",
                     rt / "python" / "Scripts" / "python.exe",
                     rt / "python" / "python.exe") if p.exists()),
        rt / "python" / "python.exe")

    if not interpreter.exists():
        # First run. Setup happens in a window of the app's own, not in a
        # console — you double-clicked an app, so an app is what should open.
        try:
            import bootstrap
        except Exception as exc:
            return die("VO Studio — cannot set up",
                       f"The setup module is missing ({exc}).\n\n"
                       "Re-download and unzip the folder.")
        if not bootstrap.show(root):
            # Either it failed — the window already said why — or it was closed
            # part-way. Downloads resume where they stopped on the next launch.
            return 1
        # Re-resolve: a venv nests the interpreter under Scripts\, the
        # embeddable build does not, and which one was used is only known now.
        rt = root / "runtime"
        for cand in (rt / "python" / "Scripts" / "pythonw.exe",
                     rt / "python" / "Scripts" / "python.exe",
                     rt / "python" / "pythonw.exe", rt / "python" / "python.exe"):
            if cand.exists():
                interpreter = cand
                break
        else:
            return die("VO Studio — setup did not finish",
                       "Setup reported success but no interpreter is in "
                       f".\\runtime.\n\nLooked under:\n{rt / 'python'}")

    entry = root / "desktop.py"
    if not entry.exists():
        return die("VO Studio — files missing",
                   f"desktop.py was not found in:\n{root}\n\n"
                   "The folder looks incomplete — re-download and unzip it.")

    env = dict(os.environ)
    # The bundled tools go on PATH for this process only. ffmpeg is called by
    # name all through the pipeline and espeak-ng by phonemizer, so they have to
    # be findable — but putting them on the SYSTEM path is exactly what this
    # app is avoiding.
    bundled = [rt / "ffmpeg" / "bin", rt / "espeak", rt / "node"]
    env["PATH"] = os.pathsep.join(
        [str(p) for p in bundled if p.exists()] + [env.get("PATH", "")])
    # Keep model weights inside the folder too, so deleting it really is a
    # clean uninstall rather than leaving a gigabyte in the user profile.
    env.setdefault("HF_HOME", str(rt / "models"))
    # A set ANTHROPIC_API_KEY silently outranks the Claude subscription login and
    # would bill an API account instead. Cleared for the app's process only —
    # removing it machine-wide is the user's call, and doing it silently would
    # hide the problem instead of fixing it.
    env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONIOENCODING"] = "utf-8"
    # Windows still defaults to cp1252 for open() and Path.read_text(). The UI
    # files are full of em-dashes and box-drawing rules, so serving the page
    # would die on a decode error with no console to print it to.
    env["PYTHONUTF8"] = "1"

    # Fire-and-forget was wrong: with no console attached, a child that dies on
    # import prints its traceback into the void and the icon just bounces.
    # Everything it says goes to a log, and if it exits badly that log is put on
    # screen instead of nothing at all.
    log = rt / "last-run.log"
    try:
        creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8", errors="replace") as sink:
            proc = subprocess.Popen([str(interpreter), str(entry)], cwd=str(root),
                                    env=env, stdout=sink, stderr=subprocess.STDOUT,
                                    creationflags=creation)
            code = proc.wait()
    except Exception as exc:
        return die("VO Studio — could not start", f"{type(exc).__name__}: {exc}")

    if code != 0:
        try:
            tail = log.read_text(encoding="utf-8", errors="replace").strip()[-1600:]
        except Exception:
            tail = ""
        return die("VO Studio — the app stopped",
                   (tail or f"It exited with code {code} and said nothing.")
                   + f"\n\nFull log:\n{log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
