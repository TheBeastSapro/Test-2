"""The setup window, and the one method on it that another thread calls.

`toolchain.run_watched` reads a child process on a reader thread, because `readline`
blocks and blocking is the thing being avoided. It hands each line to `on_line`, which
for the desktop installer is `SetupWindow.note`.

Tk is not thread-safe. Every widget call has to happen on the thread running the
mainloop, and one made anywhere else raises `RuntimeError: main thread is not in main
loop`. `note` used to call `.config()` directly, so the first line npm or pip printed
killed the reader thread — and with it every further line, leaving a frozen window in
front of an install that was still running. On Windows the launcher then re-ran itself
visibly to show the error, which is the black console box the whole window exists to
avoid.

The comment on the reader thread claimed it "never touches a widget". It was not a fact
about that function; it was a hope about its callers, and the hope is why nobody looked.
"""

from __future__ import annotations

import threading

from forgecast.desktop.setup_window import SetupWindow


class _Widget:
    """A widget that refuses to be touched from anywhere but the thread that made it.

    Exactly what Tk does, made explicit so the failure is a test rather than a platform.
    """

    def __init__(self, owner: int) -> None:
        self.owner = owner
        self.text = ""
        self.touched_from: list[int] = []

    def config(self, **kwargs) -> None:
        here = threading.get_ident()
        self.touched_from.append(here)
        if here != self.owner:
            raise RuntimeError("main thread is not in main loop")
        self.text = kwargs.get("text", self.text)

    # `_pump` reads and writes the bar like a mapping.
    def __getitem__(self, key):
        return "determinate"

    def __setitem__(self, key, value):
        pass

    def step(self, _amount):
        pass


class _Root:
    def update_idletasks(self) -> None:
        pass

    def update(self) -> None:
        pass


def _window() -> tuple[SetupWindow, _Widget]:
    here = threading.get_ident()
    detail = _Widget(here)
    widgets = {
        "heading": _Widget(here), "detail": detail, "bar": _Widget(here),
        "close": _Widget(here), "rows": {}, "font_on": None, "font_off": None,
    }
    return SetupWindow(_Root(), widgets, ["Python", "ffmpeg"]), detail


def test_a_line_from_a_reader_thread_does_not_touch_a_widget():
    """The crash, in the shape it actually happened.

    A child process prints; `run_watched`'s reader thread calls `note`; the window must
    survive it. Before the fix this raised and took the reader thread with it.
    """
    window, detail = _window()
    failure: list[BaseException] = []

    def reader() -> None:
        try:
            for line in ("added 1 package", "npm notice", "changed 2 packages"):
                window.note(line)
        except BaseException as exc:
            failure.append(exc)

    thread = threading.Thread(target=reader, name="forgecast-child-output")
    thread.start()
    thread.join(timeout=5)

    assert not failure, f"note() raised off the main thread: {failure[0]!r}"
    assert detail.touched_from == [], "note() touched a widget from the reader thread"


def test_the_queued_line_is_drawn_on_the_main_thread():
    """Queuing it is only half the fix. It has to reach the window."""
    window, detail = _window()

    thread = threading.Thread(target=lambda: window.note("installing ffmpeg"))
    thread.start()
    thread.join(timeout=5)

    assert detail.text == ""      # nothing drawn yet
    window.tick()                 # the main thread's redraw, 12x a second during a child
    assert detail.text == "installing ffmpeg"
    assert detail.touched_from == [threading.get_ident()]


def test_the_most_recent_line_wins():
    """This is one replaced line, not a log. Drawing every queued line would be several
    `config` calls the eye cannot separate, at twelve redraws a second."""
    window, detail = _window()
    for line in ("step one", "step two", "step three"):
        window.note(line)
    window.tick()
    assert detail.text == "step three"


def test_a_burst_of_output_does_not_lose_the_window():
    """npm prints hundreds of lines in a second. None of them may raise, and the last
    one still has to be the one on screen."""
    window, detail = _window()
    failure: list[BaseException] = []

    def reader() -> None:
        try:
            for index in range(500):
                window.note(f"line {index}")
        except BaseException as exc:
            failure.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not failure
    window.tick()
    assert detail.text.startswith("line ")


def test_a_line_is_trimmed_so_it_cannot_resize_the_window():
    window, detail = _window()
    window.note("x" * 400)
    window.tick()
    assert len(detail.text) <= 110


def test_note_is_the_only_method_that_defers():
    """Everything else runs on the main thread and draws immediately. Deferring those
    would mean a checklist that lags the install it is describing."""
    window, detail = _window()
    window.begin("Python")
    # `begin` writes the heading and clears the detail synchronously.
    assert detail.touched_from == [threading.get_ident()]


# ------------------------------------------------------------------ the deadlock


def test_a_callback_that_raises_does_not_stop_the_pipe_being_read():
    """The real cost of the Tk crash, and the reason it looked like npm failing.

    `run_watched` gives the child a pipe and reads it on this thread. The pipe buffer is
    about 64 KB. If the reader dies, nobody drains it — so a child printing more than
    that blocks on write and never exits, and the poll loop spins until the fifteen
    minute timeout kills it. Every CLI install then failed, a quarter of an hour apart,
    for a reason with nothing to do with npm.

    The visible symptom was a frozen setup window. The expensive one was a deadlocked
    installer, and it is the reason this guard is here rather than merely tidy.
    """
    import sys
    import time

    from forgecast.desktop import toolchain

    def explodes(_line: str) -> None:
        raise RuntimeError("main thread is not in main loop")

    started = time.monotonic()
    code, output = toolchain.run_watched(
        [sys.executable, "-c", "for i in range(20000): print('x'*80)"],
        on_line=explodes, timeout=60)
    elapsed = time.monotonic() - started

    assert code == 0, "the child did not finish"
    # 1.6 MB, far past any pipe buffer — the case that deadlocks if draining stops.
    assert len(output.splitlines()) == 20000
    assert elapsed < 30, "it blocked rather than draining"


def test_the_full_output_survives_a_callback_that_never_works():
    """A failure has to stay reportable. Output that only ever went to a window which
    has since closed is a failure with no reason attached."""
    import sys

    from forgecast.desktop import toolchain

    code, output = toolchain.run_watched(
        [sys.executable, "-c", "print('the real error'); raise SystemExit(3)"],
        on_line=lambda _line: 1 / 0, timeout=30)
    assert code == 3
    assert "the real error" in output
