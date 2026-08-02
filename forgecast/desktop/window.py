"""Putting a window in front of the operator.

There is no single way to do this that works everywhere, so there are three, tried in
order of how much it feels like an application:

1. **pywebview** — a real native window using the platform's own web view
   (WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux). Best result, but an
   optional dependency, and on Linux it needs GTK bindings that many machines lack.
2. **A Chromium app window** — `--app=URL` gives a frameless window with no tabs, no
   address bar and its own icon in the dock. Nearly indistinguishable from native, and
   works anywhere a Chromium-family browser is installed, which is almost everywhere.
3. **A browser tab** — always available, never fails.

The distinction that matters for the supervisor is not which one was used but whether
the window's lifetime can be observed. Modes 1 and 2 block until the window closes, so
closing it quits the app. Mode 3 cannot, so the app keeps running until Quit is pressed
in the UI or the terminal is interrupted — and `blocking` says which happened.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass

log = logging.getLogger("forgecast.desktop.window")

TITLE = "Forgecast"
DEFAULT_SIZE = (1280, 860)

# Chromium-family binaries by platform, most preferred first. The Playwright-managed
# Chromium is included because a machine that has run this project's browser tooling
# already has one, and using it avoids requiring a second browser install.
_CHROME_CANDIDATES = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
}
_CHROME_ON_PATH = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "brave-browser",
]


@dataclass
class WindowResult:
    mode: str          # webview | chrome | browser | none
    blocking: bool     # did this call return only when the window closed?
    detail: str = ""


def _find_chrome() -> str | None:
    for path in _CHROME_CANDIDATES.get(sys.platform, []):
        if os.path.exists(path):
            return path
    for name in _CHROME_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    # Playwright keeps its browsers outside PATH; this is where this project puts them.
    managed = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if managed:
        candidate = os.path.join(managed, "chromium")
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _open_webview(url: str, stop_event: threading.Event | None = None) -> WindowResult | None:
    try:
        import webview  # type: ignore
    except Exception:
        return None
    try:
        webview.create_window(TITLE, url, width=DEFAULT_SIZE[0], height=DEFAULT_SIZE[1])
        if stop_event is not None:
            # Quit pressed in the UI has to close the native window too.
            watcher = threading.Thread(
                target=lambda: (stop_event.wait(), webview.destroy()),
                name="forgecast-window-watch", daemon=True,
            )
            watcher.start()
        webview.start()          # returns when the window is closed
    except Exception as exc:
        # A GUI toolkit that imports but cannot start — no display, missing GTK
        # bindings — must fall through to the next mode rather than kill the app.
        log.info("pywebview could not start (%s); falling back", exc)
        return None
    return WindowResult("webview", blocking=True)


def _open_chrome(
    url: str,
    stop_event: threading.Event | None = None,
    profile_dir: str | None = None,
) -> WindowResult | None:
    chrome = _find_chrome()
    if not chrome:
        return None

    # A dedicated profile directory keeps the app window out of the operator's normal
    # browsing session and, more usefully, makes the session cookie persist between
    # launches so the window comes back already signed in.
    profile = profile_dir or os.path.join(tempfile.gettempdir(), "forgecast-app-profile")
    width, height = DEFAULT_SIZE
    try:
        proc = subprocess.Popen(
            [chrome, f"--app={url}", f"--user-data-dir={profile}",
             f"--window-size={width},{height}", "--no-first-run",
             "--no-default-browser-check"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        log.info("could not launch %s (%s); falling back", chrome, exc)
        return None

    # Polled rather than `proc.wait()` so that Quit pressed *inside* the UI also
    # closes the window. Without this the app would shut its server down and leave an
    # empty frame on screen showing a connection error.
    while proc.poll() is None:
        if stop_event is not None and stop_event.wait(timeout=0.25):
            with contextlib.suppress(OSError):
                proc.terminate()
            break
        elif stop_event is None:
            time.sleep(0.25)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)
    return WindowResult("chrome", blocking=True, detail=chrome)


def _open_browser(url: str) -> WindowResult:
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    return WindowResult(
        "browser" if opened else "none",
        blocking=False,
        detail="" if opened else "no browser could be opened",
    )


def open_window(
    url: str, *, prefer: str = "auto", stop_event: threading.Event | None = None
) -> WindowResult:
    """Show `url` as an application window. Blocks if the mode allows it.

    `prefer` forces a mode — "webview", "chrome", "browser" or "none". "none" is what
    a headless run uses: it opens nothing, leaving the supervisor to wait on Quit or a
    signal. `stop_event`, when given, closes the window from the other direction, so
    Quit inside the UI does not leave an orphaned frame behind.
    """
    if prefer == "none":
        return WindowResult("none", blocking=False, detail="window suppressed")

    order = {
        "auto": (_open_webview, _open_chrome),
        "webview": (_open_webview,),
        "chrome": (_open_chrome,),
        "browser": (),
    }.get(prefer, (_open_webview, _open_chrome))

    for opener in order:
        result = opener(url, stop_event)
        if result is not None:
            return result

    return _open_browser(url)
