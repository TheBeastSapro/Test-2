"""
Run VO Studio as a desktop app, not a browser tab.

Sapro's complaint was fair: a Chrome tab with an address bar, a Gemini button and
a "Built with Gradio" footer is not an application. This opens a real OS window
with its own taskbar entry and no browser chrome around it.

WHY THIS AND NOT A SINGLE .EXE
    A one-file PyInstaller build that contains PyTorch and the CUDA runtime lands
    around 5 GB, takes many minutes to start because it unpacks itself on every
    launch, and breaks whenever a CUDA DLL is not where the bundler guessed. The
    model weights are another 1 GB that has to download on first run regardless,
    so the .exe would not even make it self-contained.

    What actually delivers "it feels like an app" is a native window plus a
    Start-menu and desktop shortcut with an icon — which is this file plus the
    shortcut setup creates. Double-click, a window opens. No terminal, no
    browser, no localhost URL to remember.

    On Windows the renderer is WebView2, which ships with Windows 11 — nothing
    extra to install.
"""
import os
import socket
import sys
import threading
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent

# Same bundled-tools PATH as launcher.py, for when this is started by run.bat
# rather than the .exe. ffmpeg and espeak-ng are invoked by name.
_rt = APP_ROOT / "runtime"
for _d in (_rt / "ffmpeg" / "bin", _rt / "espeak", _rt / "node"):
    if _d.exists():
        os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("HF_HOME", str(_rt / "models"))


def free_port() -> int:
    """Ask the OS for an unused port rather than hoping 7860 is free."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = 180.0) -> bool:
    """
    Gradio takes a while on first launch — imports torch, builds the UI.

    A blank window while that happens looks like a crash, so the window is only
    created once the port answers.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> int:
    try:
        import webview
    except ImportError:
        print("pywebview is not installed — opening in the browser instead.\n"
              "    pip install pywebview")
        import uvicorn, webbrowser
        from server import app as api
        port = free_port()
        threading.Thread(
            target=lambda: webbrowser.open(f"http://127.0.0.1:{port}"),
            daemon=True).start()
        uvicorn.run(api, host="127.0.0.1", port=port, log_level="warning")
        return 0

    port = free_port()

    def serve():
        import uvicorn
        from server import app as api
        # log_level="warning": there is no console in the .exe build, so an
        # access log would go nowhere.
        uvicorn.run(api, host="127.0.0.1", port=port, log_level="warning")

    threading.Thread(target=serve, daemon=True).start()

    if not wait_for_server(port):
        print("The app did not start within 3 minutes. Run run.bat to see the error.")
        return 1

    icon = APP_ROOT / "assets" / "icon.png"
    webview.create_window(
        "ExplainTory VO Studio",
        f"http://127.0.0.1:{port}",
        width=1240, height=880, min_size=(940, 640),
        background_color="#0a0a0b",     # matches app.css --bg, so no flash on open
        confirm_close=True,             # a render in progress dies with the window
    )
    webview.start(icon=str(icon) if icon.exists() else None, private_mode=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
