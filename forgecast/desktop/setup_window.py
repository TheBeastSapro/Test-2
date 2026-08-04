"""The first-run setup window.

## Why a window and not the console

The launcher's console was honest and it looked like a crash. A double-clicked app that
opens a black terminal and streams pip output has already told the operator, before it
does anything, that they are running a script rather than using a program — and when
something does go wrong the traceback is indistinguishable to them from the normal
output. That was reported, twice.

So the same work happens behind a small window: what is being installed, a bar for the
one in progress, the line the installer last printed, and a checklist of everything with
what is done, what is running and what is still to come. Nothing about the installation
changes; only whether it can be read.

## Why tkinter

Because it is in the standard library, and this runs *before the virtualenv exists*. Any
GUI toolkit that needs installing cannot draw the window that installs things. That
constraint rules out every alternative and makes the choice for us.

Tk is not always present even so — a Linux build without `python3-tk`, a headless
machine, a broken `DISPLAY`. So `open()` returns `None` rather than raising, and the
caller falls back to the console bar. An installer that refuses to install because it
could not draw a progress bar is worse than an ugly one.

## Why it never blocks

`update()` rather than `mainloop()`. The installation is the program here and the window
is a view of it, so the work runs on the main thread and the window is pumped between
chunks. `mainloop()` would need the install moved to a worker, and a worker that touches
Tk widgets from off the main thread is a crash on macOS.

The cost is that the window is unresponsive while a chunk downloads, which is a fraction
of a second, and the Close button is deliberately disabled until the end — closing
mid-install would leave a half-unpacked runtime that the next launch would have to
detect and undo.
"""

from __future__ import annotations

import contextlib
import os
import queue
import sys
from collections.abc import Sequence

# Matched to the app's own palette so the installer and the thing it installs do not look
# like different products. `--bg`, `--raise`, `--text`, `--muted` and `--accent` from
# `web/static/app.css`, with the accent moved off mint: a filled mint bar on near-black
# reads as a warning strip, and violet is what the app already uses for "in progress".
BG = "#08090a"
PANEL = "#0e1110"
TEXT = "#e8ecea"
MUTED = "#7d8a85"
FAINT = "#55605c"
ACCENT = "#8b7cf6"
DONE = "#4ade80"


class SetupWindow:
    """A live view of the install. Every method is safe to call when Tk is absent."""

    def __init__(self, root, widgets: dict, steps: list[str]) -> None:
        self._root = root
        self._w = widgets
        self._steps = list(steps)
        self._done: set[str] = set()
        self._current = ""
        self._failed: set[str] = set()
        # Lines from a child process, waiting to be drawn by whoever owns the main
        # thread. See `note` for why they cannot be drawn where they arrive.
        self._lines: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------ the surface

    def begin(self, step: str) -> None:
        """Mark a step as the one now running."""
        self._current = step
        self._w["heading"].config(text=step)
        self._w["detail"].config(text="")
        self.progress(0, 0)
        self._repaint()

    def progress(self, done: int, total: int) -> None:
        bar = self._w["bar"]
        if total > 0:
            fraction = min(1.0, max(0.0, done / total))
            bar["mode"] = "determinate"
            bar["value"] = fraction * 100
            self._w["detail"].config(
                text=f"{done / 1_048_576:.1f} of {total / 1_048_576:.1f} MB")
        else:
            # No content-length, or a step that is not a download at all. An
            # indeterminate bar is the honest picture: something is happening and its
            # size is unknown. A fake percentage would be a lie that reaches 90% and
            # stops.
            bar["mode"] = "indeterminate"
        self._pump()

    def tick(self) -> None:
        """Redraw, with nothing to report.

        Public because a long child process — `npm install -g` is minutes and nearly
        silent — has to be able to keep this window alive without pretending to have news.
        Without it the window is redrawn only when something is printed, and a step that
        prints nothing for two minutes is a window Windows marks "(Not Responding)". That
        was reported: the checklist appeared, then froze, and it was closed mid-install.
        """
        self._pump()

    def note(self, line: str) -> None:
        """The installer's own last line, under the bar.

        One line, replaced, not appended. A scrolling log is what the console already
        was; the value here is knowing it is still moving and roughly where.

        **This is the one method on this class called from another thread**, and it must
        not touch a widget. `toolchain.run_watched` reads a child process on a reader
        thread because `readline` blocks, and hands each line here. Tk is not thread-safe:
        every widget call has to happen on the thread running the mainloop, and one made
        anywhere else raises `RuntimeError: main thread is not in main loop`.

        It did. This method used to call `.config()` directly, so the first line npm or
        pip printed killed the reader thread — and with it every further line, leaving a
        window that had stopped updating in front of an install that was still running.
        The reader thread's own comment claimed it "never touches a widget"; the wiring
        made that false, and the assertion is why nobody looked.

        So the line is queued and `_pump` draws it, on the main thread, where `tick`
        already calls twelve times a second for the whole life of the child process.
        """
        self._lines.put(line.strip()[:110])

    def finish(self, step: str, *, ok: bool = True) -> None:
        (self._done if ok else self._failed).add(step)
        if self._current == step:
            self._current = ""
        self._repaint()

    def done(self, message: str) -> None:
        """Everything is finished; let the window be closed."""
        self._w["heading"].config(text=message)
        self._w["detail"].config(text="")
        self._w["bar"]["mode"] = "determinate"
        self._w["bar"]["value"] = 100
        self._w["close"].config(state="normal")
        self._repaint()

    def close(self) -> None:
        # Suppressed because the window may already be gone — the operator closed it, or
        # the display went away — and failing to tear down a window nobody can see is
        # not a reason to fail an install that succeeded.
        with contextlib.suppress(Exception):
            self._root.destroy()

    # ------------------------------------------------------------------- internals

    def _repaint(self) -> None:
        for step, label in self._w["rows"].items():
            if step in self._failed:
                label.config(text=f"×  {step}", fg="#f87171")
            elif step in self._done:
                label.config(text=f"✓  {step}", fg=DONE)
            elif step == self._current:
                label.config(text=f"▸  {step}", fg=TEXT, font=self._w["font_on"])
            else:
                label.config(text=f"•  {step}", fg=FAINT, font=self._w["font_off"])
        self._pump()

    def _pump(self) -> None:
        """Draw now, on the main thread, which is the only thread that may.

        Every caller of this is on the main thread — the install owns it — which is what
        makes it the right place to drain the lines `note` queued from the reader thread.
        """
        try:
            # The most recent line wins. This is a single replaced line rather than a
            # log, so drawing every queued one would be several `config` calls the eye
            # cannot separate, at twelve redraws a second.
            latest = ""
            while True:
                try:
                    latest = self._lines.get_nowait()
                except queue.Empty:
                    break
            if latest:
                self._w["detail"].config(text=latest)

            if self._w["bar"]["mode"] == "indeterminate":
                self._w["bar"].step(4)
            self._root.update_idletasks()
            self._root.update()
        except Exception:                                            # pragma: no cover
            # The operator closed it, or the display went away. The install carries on
            # regardless — losing the window is not losing the work.
            pass


class _Silent:
    """The no-window case, with the same shape so the caller needs no branches."""

    def begin(self, step: str) -> None: ...
    def progress(self, done: int, total: int) -> None: ...
    def tick(self) -> None: ...
    def note(self, line: str) -> None: ...
    def finish(self, step: str, *, ok: bool = True) -> None: ...
    def done(self, message: str) -> None: ...
    def close(self) -> None: ...


def available() -> bool:
    """Whether a window can be drawn at all, without side effects.

    `FORGECAST_NO_GUI` forces the console path — for CI, for a remote shell, and for
    anyone who prefers to watch pip.
    """
    if os.environ.get("FORGECAST_NO_GUI"):
        return False
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def open(steps: Sequence[str], *, title: str = "Forgecast — Setup"):
    """The window, or `None` when one cannot be drawn.

    Never raises. Every failure here means "use the console", and a first run that dies
    because Tk is missing would be a worse bug than the console it replaced.
    """
    if not available():
        return None
    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title(title)
        root.configure(bg=BG)
        root.geometry("560x470")
        root.resizable(False, False)

        base = ("Segoe UI", 10) if os.name == "nt" else ("Helvetica", 12)
        head = (base[0], 19, "bold")

        frame = tk.Frame(root, bg=BG, padx=30, pady=26)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Setting up Forgecast", bg=BG, fg=TEXT, font=head,
                 anchor="w").pack(fill="x")
        tk.Label(frame,
                 text="Everything installs into this folder. Nothing is added to your "
                      "system.",
                 bg=BG, fg=MUTED, font=base, anchor="w", wraplength=480,
                 justify="left").pack(fill="x", pady=(6, 22))

        heading = tk.Label(frame, text="Starting", bg=BG, fg=TEXT,
                           font=(base[0], base[1] + 1, "bold"), anchor="w")
        heading.pack(fill="x")

        style = ttk.Style(root)
        with_theme = "clam" if "clam" in style.theme_names() else style.theme_use()
        style.theme_use(with_theme)
        style.configure("Forgecast.Horizontal.TProgressbar",
                        troughcolor=PANEL, background=ACCENT,
                        bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT,
                        thickness=10)
        bar = ttk.Progressbar(frame, style="Forgecast.Horizontal.TProgressbar",
                              length=480, mode="determinate", maximum=100)
        bar.pack(fill="x", pady=(10, 8))

        detail = tk.Label(frame, text="", bg=BG, fg=ACCENT, font=(base[0], base[1] - 1),
                          anchor="w", wraplength=480, justify="left")
        detail.pack(fill="x")

        rows: dict[str, object] = {}
        checklist = tk.Frame(frame, bg=BG)
        checklist.pack(fill="x", pady=(20, 0))
        font_off = (base[0], base[1])
        font_on = (base[0], base[1], "bold")
        for step in steps:
            label = tk.Label(checklist, text=f"•  {step}", bg=BG, fg=FAINT,
                             font=font_off, anchor="w")
            label.pack(fill="x", pady=2)
            rows[step] = label

        close = tk.Button(frame, text="Close", state="disabled", relief="flat",
                          bg=PANEL, fg=TEXT, activebackground=PANEL,
                          font=base, padx=18, pady=6, command=root.destroy)
        close.pack(side="bottom", anchor="e", pady=(18, 0))

        # Closing mid-install would leave a half-unpacked runtime behind, so the button
        # is disabled until the end and the window manager's X is ignored until then too.
        root.protocol("WM_DELETE_WINDOW",
                      lambda: close["state"] == "normal" and root.destroy())

        window = SetupWindow(root, {
            "heading": heading, "bar": bar, "detail": detail, "rows": rows,
            "close": close, "font_on": font_on, "font_off": font_off,
        }, list(steps))
        window._pump()
        return window
    except Exception:
        return None


def silent():
    """A do-nothing window, for the console path."""
    return _Silent()
