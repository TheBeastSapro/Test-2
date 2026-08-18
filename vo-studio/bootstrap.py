"""
First-run setup, inside the app.

The chicken-and-egg problem this solves: the app needs Python to draw its own
window, and on a fresh machine there is no Python yet. A .bat file was the easy
answer and the wrong one — a console scrolling pip output is not an installer.

So this module is written in nothing but the standard library (urllib, zipfile,
subprocess, tkinter) and gets frozen INTO VOStudio.exe. Double-clicking the exe
on a machine with nothing installed opens this window, shows every download with
a real progress bar, and hands over to the app when it finishes. Nothing is
installed on the machine — it all lands in .\\runtime next to the exe.

tkinter specifically because it ships with Python and freezes cleanly. Anything
prettier would need a package, and needing a package is the problem being solved.
"""
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

PY_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
NODE_URL = "https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip"
ESPEAK_URL = ("https://github.com/espeak-ng/espeak-ng/releases/download/1.51/"
              "espeak-ng-X64.msi")

TORCH = ["torch==2.6.0", "torchaudio==2.6.0"]
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
PIPELINE = ["chatterbox-tts", "faster-whisper", "soundfile", "scipy", "pyloudnorm",
            "phonemizer", "panphon", "allosaurus", "fastapi", "uvicorn",
            "python-multipart", "pywebview", "pillow", "claude-agent-sdk",
            # Builds VOStudio.exe at the end of setup, so the .bat is used once
            # and never again. A Windows exe can only be built on Windows.
            "pyinstaller"]

# (label, weight) — weights are rough download sizes so the bar tracks reality
# rather than counting steps. A step-counting bar sits at 60% through a 2.5 GB
# download, which is worse than no bar.
STEPS = [("Python runtime", 2), ("ffmpeg", 8), ("Node + Claude CLI", 4),
         ("PyTorch with CUDA", 60), ("Chatterbox and the QC stack", 22),
         ("espeak-ng", 2), ("Finishing up", 2)]
TOTAL = sum(w for _, w in STEPS)

BG, CARD, LINE, TEXT, MUTED, ACCENT = "#0a0a0b", "#121214", "#2e2e34", "#fafafa", "#a1a1aa", "#8b5cf6"


class Setup:
    """Runs the install on a worker thread and reports through a queue."""

    def __init__(self, root: Path, report):
        self.root = root
        self.rt = root / "runtime"
        self.report = report
        self.done_weight = 0
        self.have: dict[int, bool] = {}
        self.total = TOTAL

    _venv_layout = False

    def python_exe(self) -> Path:
        """Where the interpreter ended up — a venv nests it under Scripts\\."""
        venv = self.rt / "python" / "Scripts" / "python.exe"
        flat = self.rt / "python" / "python.exe"
        return venv if venv.exists() else flat

    def _find_system_python(self):
        """
        A Python already here, if it is one the wheels actually support.

        3.11 and 3.12 only. Chatterbox's dependency set has no 3.13 wheels for
        several packages, and finding that out 2 GB into the download is a much
        worse experience than spending 11 MB on a known-good one.
        """
        seen = []
        for name in ("python", "python3", "python3.12", "python3.11", "py"):
            exe = shutil.which(name)
            if not exe or exe in seen:
                continue
            seen.append(exe)
            try:
                out = subprocess.run(
                    [exe, "-c", "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                    capture_output=True, text=True, timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if out.stdout.strip() in ("3.11", "3.12"):
                    return Path(exe)
            except Exception:
                continue
        return None

    def _imports(self, *mods: str) -> bool:
        """Is this stack actually importable in the runtime interpreter?"""
        if not self.python_exe().exists():
            return False
        try:
            out = subprocess.run([str(self.python_exe()), "-c", "import " + ", ".join(mods)],
                                 capture_output=True, timeout=180,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return out.returncode == 0
        except Exception:
            return False

    def _probe(self):
        """
        What is already on this machine before a single byte is downloaded.

        Setup gets re-run — a connection drops 2 GB into torch, a driver gets
        updated, the user just wants to check. A window that lists all seven
        steps as pending and restarts the bar at zero reads as "none of that
        counted", so every step reports what it found and only the missing ones
        are downloaded or charged to the progress bar.
        """
        self.have = {
            0: self.python_exe().exists(),
            1: (self.rt / "ffmpeg" / "bin" / "ffmpeg.exe").exists(),
            2: (self.rt / "node" / "claude.cmd").exists(),
            3: self._imports("torch", "torchaudio"),
            4: self._imports("chatterbox", "faster_whisper", "soundfile",
                             "pyloudnorm", "fastapi", "webview"),
            5: (self.rt / "espeak" / "espeak-ng.exe").exists(),
            # Verification always runs. It takes seconds and it is the one
            # answer worth having: whether CUDA is actually live on this GPU.
            6: False,
        }
        # Only the work left to do drives the bar. Otherwise a re-run that has
        # nothing but espeak-ng missing would crawl across 2% of its width.
        self.total = max(1, sum(w for i, (_, w) in enumerate(STEPS) if not self.have[i]))
        self.report(probe=dict(self.have))
        return self.have

    # -- helpers -----------------------------------------------------------
    def _fetch(self, url: str, dest: Path, label: str, weight: int):
        """Download with byte-level progress, so the bar moves during the 2.5 GB step."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                got += len(chunk)
                if total:
                    frac = got / total
                    self.report(pct=(self.done_weight + weight * frac) / self.total * 100,
                                detail=f"{label} — {got/1e6:.0f} of {total/1e6:.0f} MB")

    def _unzip_flat(self, zip_path: Path, dest: Path):
        """Extract, then lift a single wrapper directory out if there is one."""
        tmp = dest.parent / (dest.name + "_tmp")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        inner = [p for p in tmp.iterdir()]
        src = inner[0] if len(inner) == 1 and inner[0].is_dir() else tmp
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        if dest.exists():
            # move() onto a SURVIVING directory puts the source INSIDE it, so
            # you get runtime\node\node-v22-win-x64\node.exe and every later
            # check quietly fails. Better to stop and say what to delete.
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(
                f"Could not replace {dest.name} — something is holding it open "
                f"(antivirus, or a path too long). Close this, delete "
                f"{dest}, and run setup again.")
        shutil.move(str(src), str(dest))
        shutil.rmtree(tmp, ignore_errors=True)
        zip_path.unlink(missing_ok=True)

    def _pip(self, args: list[str], label: str, weight: int):
        """
        pip, streamed so the window keeps updating.

        --no-warn-script-location because the embeddable build has no Scripts on
        PATH and the warning is noise the user cannot act on.
        """
        py = self.python_exe()
        cmd = [str(py), "-m", "pip", "install", "--no-warn-script-location", *args]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        seen = 0
        for line in proc.stdout:
            line = line.strip()
            if line.startswith(("Collecting", "Downloading", "Installing")):
                seen += 1
                # Creeps toward the step's full weight without ever claiming to
                # finish early — pip gives no total, so this is honest guessing.
                frac = min(0.95, seen / 45)
                self.report(pct=(self.done_weight + weight * frac) / self.total * 100,
                            detail=f"{label} — {line[:64]}")
        if proc.wait() != 0:
            raise RuntimeError(f"{label} failed. Re-run and it resumes from here.")

    def _step(self, i: int):
        """
        Announce a step. Returns (label, weight, skip).

        skip is True when the probe already found it — the caller reports it as
        installed and moves on without spending a byte or a percent on it.
        """
        label, weight = STEPS[i]
        if self.have.get(i):
            self.report(step=i, label=label, status=(i, "installed"),
                        pct=self.done_weight / self.total * 100,
                        detail=f"{label} — already installed, skipping")
            return label, weight, True
        self.report(step=i, label=label, status=(i, "working"),
                    pct=self.done_weight / self.total * 100, detail="starting")
        return label, weight, False

    # What each step must leave behind. Checked AFTER the step, not just
    # before: a download that 403s, an extract that nests a folder or an npm
    # that quietly fails used to turn the row green anyway, and the first sign
    # of trouble was the app failing to start days later.
    PROOF = {
        1: lambda rt: (rt / "ffmpeg" / "bin" / "ffmpeg.exe").exists(),
        2: lambda rt: (rt / "node" / "claude.cmd").exists() or (rt / "node" / "node.exe").exists(),
        5: lambda rt: (rt / "espeak" / "espeak-ng.exe").exists(),
    }
    # Node and espeak are not fatal -- the Assistant and the pronunciation
    # check are the only things that need them.
    REQUIRED = {0, 1, 3, 4, 6}

    def _finish(self, i: int, weight: int, skipped: bool):
        """Mark a step done and charge its weight to the bar — unless it never ran."""
        proof = self.PROOF.get(i)
        if not skipped and proof and not proof(self.rt):
            label = STEPS[i][0]
            if i in self.REQUIRED:
                raise RuntimeError(
                    f"{label} did not install. Nothing was left in .\\runtime. "
                    f"Close this, delete the runtime folder, and run setup again.")
            self.report(status=(i, "failed"),
                        detail=f"{label} did not install — continuing without it.")
            self.done_weight += weight
            return
        self.report(status=(i, "installed" if skipped else "done"))
        if not skipped:
            self.done_weight += weight
            self.report(pct=self.done_weight / self.total * 100)

    # -- the install -------------------------------------------------------
    def run(self):
        self.rt.mkdir(parents=True, exist_ok=True)
        self.report(detail="Checking what is already installed…")
        self._probe()

        # 1 · Python
        label, w, skip = self._step(0)
        if not skip:
            existing = self._find_system_python()
            if existing:
                # Reuse the Python already on this machine, but build a venv from
                # it rather than installing into it. 2.5 GB of CUDA torch dropped
                # into a system interpreter is exactly the pollution this app is
                # meant to avoid -- and it would break the moment another project
                # wanted a different torch.
                self.report(detail=f"{label} — found {existing.name}, creating an "
                                   f"isolated environment from it")
                subprocess.run([str(existing), "-m", "venv", str(self.rt / "python")],
                               check=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                # A venv puts the interpreter under Scripts\, the embeddable build
                # does not. python_exe() already prefers whichever exists, so
                # this only records which layout we ended up with.
                self._venv_layout = (self.rt / "python" / "Scripts" / "python.exe").exists()
            else:
                self.report(detail=f"{label} — no suitable Python found, downloading one")
                zp = self.rt / "py.zip"
                self._fetch(PY_URL, zp, label, w)
                self._unzip_flat(zp, self.rt / "python")
                # The embeddable build disables site-packages; pip needs it on.
                for pth in (self.rt / "python").glob("python*._pth"):
                    pth.write_text(pth.read_text(encoding="utf-8").replace(
                        "#import site", "import site"), encoding="utf-8")
                gp = self.rt / "get-pip.py"
                self._fetch(PIP_URL, gp, label, w)
                subprocess.run([str(self.python_exe()), str(gp), "-q",
                                "--no-warn-script-location"], check=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                gp.unlink(missing_ok=True)
        self._finish(0, w, skip)

        # 2 · ffmpeg
        label, w, skip = self._step(1)
        if not skip:
            zp = self.rt / "ff.zip"
            self._fetch(FFMPEG_URL, zp, label, w)
            self._unzip_flat(zp, self.rt / "ffmpeg")
        self._finish(1, w, skip)

        # 3 · Node and the Claude CLI — only the Assistant needs these
        label, w, skip = self._step(2)
        if not skip:
            try:
                if not (self.rt / "node" / "node.exe").exists():
                    zp = self.rt / "node.zip"
                    self._fetch(NODE_URL, zp, label, w)
                    self._unzip_flat(zp, self.rt / "node")
                npm = self.rt / "node" / "npm.cmd"
                if npm.exists():
                    self.report(detail=f"{label} — installing the Claude CLI")
                    subprocess.run([str(npm), "install", "-g", "@anthropic-ai/claude-code",
                                    "--prefix", str(self.rt / "node")],
                                   capture_output=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as exc:
                # Not fatal. Rendering does not touch this.
                self.report(detail=f"{label} unavailable ({exc}) — Assistant will be off")
        self._finish(2, w, skip)

        # 4 · PyTorch
        label, w, skip = self._step(3)
        if not skip:
            self._pip([*TORCH, "--index-url", TORCH_INDEX], label, w)
        self._finish(3, w, skip)

        # 5 · the pipeline
        label, w, skip = self._step(4)
        if not skip:
            self._pip(PIPELINE, label, w)
        self._finish(4, w, skip)

        # 6 · espeak-ng, unpacked from the MSI without installing it
        label, w, skip = self._step(5)
        if not skip:
            try:
                msi = self.rt / "es.msi"
                self._fetch(ESPEAK_URL, msi, label, w)
                raw = self.rt / "esraw"
                # One command STRING, not a list. msiexec wants TARGETDIR="path"
                # with the quotes around the value only; Python's list quoting
                # would wrap the whole TARGETDIR=... argument instead, and the
                # extraction silently goes nowhere the moment the app folder has
                # a space in it (D:\My Tools\VOStudio).
                subprocess.run(f'msiexec /a "{msi}" /qn TARGETDIR="{raw}"',
                               capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                found = next(raw.rglob("espeak-ng.exe"), None)
                if found:
                    shutil.copytree(found.parent, self.rt / "espeak", dirs_exist_ok=True)
                msi.unlink(missing_ok=True)
                shutil.rmtree(raw, ignore_errors=True)
            except Exception:
                self.report(detail=f"{label} unavailable — only the pronunciation check is affected")
        self._finish(5, w, skip)

        # 7 · verify
        label, w, skip = self._step(6)
        out = subprocess.run(
            [str(self.python_exe()), "-c",
             "import torch,chatterbox,faster_whisper,soundfile,fastapi,webview;"
             "print('CUDA', torch.cuda.is_available(),"
             "torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if out.returncode != 0:
            raise RuntimeError("Verification failed:\n" + (out.stderr or "")[-400:])

        # Build the real .exe. Not fatal if it fails — the app still starts from
        # the same launcher either way — but from here on the icon on screen is
        # a Windows executable, and the .bat that got us here is never used again.
        if not (self.root / "VOStudio.exe").exists():
            self.report(detail=f"{label} — building VOStudio.exe")
            try:
                built = subprocess.run(
                    [str(self.python_exe()), "-m", "PyInstaller", "--onefile",
                     "--noconsole", "--clean", "--name", "VOStudio",
                     "--icon", str(self.root / "assets" / "icon.ico"),
                     "--hidden-import", "bootstrap", "--paths", str(self.root),
                     "--distpath", str(self.root),
                     "--workpath", str(self.rt / "build" / "work"),
                     "--specpath", str(self.rt / "build"),
                     str(self.root / "launcher.py")],
                    capture_output=True, cwd=str(self.root), timeout=900,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                shutil.rmtree(self.rt / "build", ignore_errors=True)
                if not (self.root / "VOStudio.exe").exists():
                    tail = (built.stderr or b"").decode("utf-8", "replace")[-300:]
                    self.report(detail="VOStudio.exe did not build — use "
                                       f"\"VO Studio.bat\" to start it. {tail}")
            except subprocess.TimeoutExpired:
                # A part-written exe is worse than none: it exists, so nothing
                # ever rebuilds it, and it will not run.
                (self.root / "VOStudio.exe").unlink(missing_ok=True)
                self.report(detail="Building VOStudio.exe timed out (antivirus "
                                   "scanning it, usually). Start with \"VO Studio.bat\".")
            except Exception as exc:
                self.report(detail=f"VOStudio.exe did not build ({exc}). "
                                   "Start with \"VO Studio.bat\".")

        self.report(status=(6, "done"))
        self.done_weight += w

        # Written down, not just flashed. INSTALL.md tells him the CUDA line is
        # the one thing to check, and the window used to close 1.2 s after
        # showing it, with the text saved nowhere.
        verdict = out.stdout.strip()
        # Written last and only here, after the import check has passed. This
        # is what tells the launcher the runtime is finished rather than
        # merely begun.
        try:
            (self.rt / ".setup-complete").write_text(verdict, encoding="utf-8")
        except OSError:
            pass
        try:
            (self.root / "setup-result.txt").write_text(
                verdict + "\n\nCUDA True and your GPU named = it worked.\n"
                "CPU only = generation runs about 10x realtime; update your "
                "NVIDIA driver and reopen the app.\n", encoding="utf-8")
        except OSError:
            pass
        self.report(pct=100, detail=verdict, finished=True)


def interpreter(root_dir: Path) -> Path | None:
    """The runtime's Python, whichever layout setup produced."""
    rt = Path(root_dir) / "runtime" / "python"
    for c in (rt / "Scripts" / "pythonw.exe", rt / "pythonw.exe",
              rt / "Scripts" / "python.exe", rt / "python.exe"):
        if c.exists():
            return c
    return None


def ready(root_dir: Path) -> bool:
    """
    Is the runtime COMPLETE, not merely started?

    This used to ask only whether python.exe existed, and launcher.py used the
    same test to decide whether to open the installer. So a setup that died
    during PyTorch -- the 2.5 GB step, the one most likely to be interrupted --
    left a Python behind, and every later launch skipped the installer
    entirely and failed with ModuleNotFoundError instead. There was no way
    back to setup except deleting the runtime folder, which nothing told you
    to do.

    A MARKER, not an import check: asking the runtime to import torch would
    add ten to thirty seconds to every single launch to answer a question that
    only changes when setup runs.
    """
    rt = Path(root_dir) / "runtime"
    if interpreter(root_dir) is None:
        return False
    if not (rt / "ffmpeg" / "bin" / "ffmpeg.exe").exists():
        return False
    if (rt / ".setup-complete").exists():
        return True
    # No marker, but the packages are on disk: a runtime installed by an
    # earlier version of this file, which never wrote one. Treated as finished
    # rather than dragging a working install back through setup — checked by
    # looking for the folder, not by importing it, so it stays instant.
    return any((rt / "python" / lib / "site-packages" / "torch").is_dir()
               for lib in ("Lib", "lib"))


# ══════════════════════════════════════════════════════════════════ window
def show(root_dir: Path) -> bool:
    """Returns True once the runtime is ready. Blocks until the user closes it."""
    import tkinter as tk
    from tkinter import ttk

    q: queue.Queue = queue.Queue()
    state = {"ok": False, "error": None}

    win = tk.Tk()
    win.title("VO Studio — Setup")
    win.configure(bg=BG)
    # Tall enough for all seven rows AND the button underneath them. At 330 the
    # last step and the Close button fell off the bottom edge, which during a
    # 40-minute install means you cannot see the step you are waiting on.
    # Measured, not guessed: 30+28+20+20+20+24+30+7*18+16+34+30 = 378, plus room
    # for the detail line wrapping to two.
    win.geometry("560x440")
    win.minsize(560, 440)
    win.resizable(False, False)
    try:
        win.iconbitmap(str(root_dir / "assets" / "icon.ico"))
    except Exception:
        pass

    wrap = tk.Frame(win, bg=BG, padx=34, pady=30)
    wrap.pack(fill="both", expand=True)

    tk.Label(wrap, text="Setting up VO Studio", bg=BG, fg=TEXT,
             font=("Segoe UI", 17, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Everything installs into this folder. Nothing is added to your system.",
             bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 20))

    step_lbl = tk.Label(wrap, text="Starting…", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold"))
    step_lbl.pack(anchor="w")

    style = ttk.Style(win)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("VO.Horizontal.TProgressbar", troughcolor=CARD, background=ACCENT,
                    bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
    bar = ttk.Progressbar(wrap, style="VO.Horizontal.TProgressbar",
                          length=492, mode="determinate", maximum=100)
    bar.pack(anchor="w", pady=(10, 8))

    detail = tk.Label(wrap, text="", bg=BG, fg=MUTED, font=("Consolas", 8),
                      anchor="nw", justify="left", wraplength=492, height=2)
    detail.pack(anchor="w", fill="x")

    # One label per step rather than one multi-line label, so a finished step can
    # go green and an already-present one can say so in its own row. A single
    # Label paints every line the same colour, which is what made the old list
    # read as "nothing has happened yet".
    checklist = tk.Frame(wrap, bg=BG)
    checklist.pack(anchor="w", fill="x", pady=(16, 0))
    rows = []
    for name, _ in STEPS:
        row = tk.Label(checklist, text=f"  •   {name}", bg=BG, fg=MUTED,
                       font=("Segoe UI", 8), anchor="w", justify="left")
        row.pack(anchor="w", fill="x")
        rows.append(row)

    MARK = {"failed": ("  !   {} — not installed", "#fbbf24"),
            "pending": ("  •   {}", MUTED),
            "working": ("  ▸   {}", TEXT),
            "done": ("  ✓   {}", "#4ade80"),
            "installed": ("  ✓   {} — already installed", "#4ade80")}

    btn = tk.Button(wrap, text="Close", bg=CARD, fg=TEXT, relief="flat",
                    activebackground=LINE, activeforeground=TEXT,
                    font=("Segoe UI", 9), padx=18, pady=6,
                    command=win.destroy, state="disabled")
    btn.pack(anchor="e", pady=(18, 0))

    def report(**kw):
        q.put(kw)

    def worker():
        try:
            Setup(root_dir, report).run()
            state["ok"] = True
        except Exception as exc:
            state["error"] = str(exc)
            q.put({"error": str(exc)})

    threading.Thread(target=worker, daemon=True).start()

    status = {i: "pending" for i in range(len(STEPS))}

    def paint(i):
        fmt, colour = MARK[status[i]]
        rows[i].config(text=fmt.format(STEPS[i][0]), fg=colour)

    def pump():
        try:
            while True:
                msg = q.get_nowait()
                if "error" in msg:
                    step_lbl.config(text="Setup could not finish", fg="#f87171")
                    detail.config(text=msg["error"])
                    btn.config(state="normal", text="Close")
                    return
                if "probe" in msg:
                    # Everything already present is marked before the first
                    # download starts, so the list opens as an inventory of what
                    # is here rather than a list of everything to come.
                    for i, present in msg["probe"].items():
                        if present:
                            status[i] = "installed"
                        paint(i)
                    left = [n for i, (n, _) in enumerate(STEPS) if status[i] != "installed"]
                    detail.config(text="Nothing left to install." if len(left) <= 1
                                  else "To install: " + ", ".join(left[:-1]))
                if "status" in msg:
                    i, s = msg["status"]
                    # A step that ran does not get downgraded by a later repaint.
                    if not (s == "working" and status[i] == "installed"):
                        status[i] = s
                    paint(i)
                if "label" in msg:
                    step_lbl.config(text=msg["label"], fg=TEXT)
                if "pct" in msg:
                    bar["value"] = msg["pct"]
                if "detail" in msg:
                    detail.config(text=msg["detail"])
                if msg.get("finished"):
                    step_lbl.config(text="Ready", fg="#4ade80")
                    btn.config(state="normal", text="Open VO Studio")
                    # Waits for a click now. The verification line is the whole
                    # point of the last step and it used to vanish in a second.
                    return
        except queue.Empty:
            pass
        win.after(120, pump)

    pump()
    win.mainloop()
    return state["ok"]
