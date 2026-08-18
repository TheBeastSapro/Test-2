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
import traceback
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent

# Same bundled-tools PATH as launcher.py, for when this is started by run.bat
# rather than the .exe. ffmpeg and espeak-ng are invoked by name.
_rt = APP_ROOT / "runtime"
for _d in (_rt / "ffmpeg" / "bin", _rt / "espeak", _rt / "node"):
    if _d.exists():
        os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("HF_HOME", str(_rt / "models"))

# Windows blocks symlink creation without Developer Mode, which is what breaks
# the Hugging Face cache mid-download with WinError 1314. See vostudio/winfix.py.
try:
    from vostudio import winfix
    winfix.apply()
except Exception:
    pass


def free_port() -> int:
    """Ask the OS for an unused port rather than hoping 7860 is free."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# Set by the server thread when it dies. A thread that raises takes its
# traceback with it, so without this the only symptom of a bad import is the
# port never answering — three minutes of nothing, then a timeout that blames
# the wrong thing.
SERVER_ERROR: list = []


def wait_for_server(port: int, timeout: float = 180.0) -> bool:
    """
    The backend takes a while on first launch — it imports torch.

    A blank window while that happens looks like a crash, so the window is only
    created once the port answers. Give up early if the server already failed.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if SERVER_ERROR:
            return False
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
        try:
            import uvicorn
            from server import app as api
            # log_level="warning": there is no console in the .exe build, so an
            # access log would go nowhere.
            uvicorn.run(api, host="127.0.0.1", port=port, log_level="warning")
        except BaseException as exc:
            traceback.print_exc()
            SERVER_ERROR.append(exc)

    threading.Thread(target=serve, daemon=True).start()

    if not wait_for_server(port):
        if SERVER_ERROR:
            print(f"\nThe backend failed to start: {SERVER_ERROR[0]}")
        else:
            print("The app did not start within 3 minutes.")
        return 1

    # window.ico, not icon.png. On Windows pywebview hands this straight to
    # .NET's System.Drawing.Icon, which rejects a PNG outright — "Argument
    # 'picture' must be a picture that can be used as a Icon" — thrown on the UI
    # thread, so the window never appears and nothing on screen explains why.
    #
    # And window.ico rather than icon.ico: both are icons, but icon.ico stores
    # PNG-compressed frames, which System.Drawing handles inconsistently.
    # window.ico is old-fashioned BMP frames it cannot argue with. icon.ico
    # stays as it is — PyInstaller is happy with it and it is what gives the exe
    # its icon in Explorer.
    icon = APP_ROOT / "assets" / ("window.ico" if os.name == "nt" else "icon.png")

    webview.create_window(
        "ExplainTory VO Studio",
        f"http://127.0.0.1:{port}",
        width=1240, height=880, min_size=(940, 640),
        background_color="#0a0a0b",     # matches app.css --bg, so no flash on open
        confirm_close=True,             # a render in progress dies with the window
    )
    try:
        webview.start(icon=str(icon) if icon.exists() else None, private_mode=False)
    except Exception:
        # The window matters, the icon does not. Whatever the backend dislikes
        # about the icon, it is not worth failing to open over.
        traceback.print_exc()
        print("Retrying without the window icon.")
        webview.start(private_mode=False)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        # The launcher captures this into runtime\last-run.log and puts it on
        # screen. Dying quietly is what made the first failure take a round trip.
        traceback.print_exc()
        sys.exit(1)
