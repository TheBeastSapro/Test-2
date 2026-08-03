"""
Windows-only workarounds, applied before anything heavy is imported.

SYMLINKS — WinError 1314
    Hugging Face's cache stores one copy of each file in blobs\\ and links it
    into snapshots\\. Creating a symlink on Windows needs either Developer Mode
    or an elevated process, so on a normal account the first model download
    dies part-way with:

        OSError: [WinError 1314] A required privilege is not held by the client

    huggingface_hub is supposed to detect this and copy instead. That check is
    cached per cache-directory and gets it wrong often enough to matter -- and
    when it does, the failure lands minutes into a 1 GB download.

    So os.symlink falls back to copying. It costs disk (the blob is stored
    twice) and nothing else. Copying a model file is not slow next to
    downloading it, and a working app on an unprivileged account is worth more
    than the space.
"""
import os
import shutil


def patch_symlinks() -> None:
    """Make os.symlink degrade to a copy instead of raising WinError 1314."""
    if os.name != "nt":
        return
    if getattr(os.symlink, "_vostudio_patched", False):
        return

    real_symlink = os.symlink

    def symlink(src, dst, target_is_directory=False, *, dir_fd=None):
        try:
            return real_symlink(src, dst, target_is_directory, dir_fd=dir_fd)
        except OSError as exc:
            # 1314 only. Everything else is a real error and must still raise —
            # swallowing, say, a missing directory would turn a clear failure
            # into a corrupt cache.
            if getattr(exc, "winerror", None) != 1314:
                raise

            # HF passes src RELATIVE to the link's own directory
            # ('..\\..\\blobs\\<sha>'), not to the working directory. Resolving
            # it against cwd is how a "fix" for this turns into
            # FileNotFoundError somewhere else entirely.
            source = src if os.path.isabs(src) else os.path.normpath(
                os.path.join(os.path.dirname(os.path.abspath(dst)), src))

            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            if os.path.isdir(source):
                shutil.copytree(source, dst, dirs_exist_ok=True)
            else:
                shutil.copyfile(source, dst)
            return None

    symlink._vostudio_patched = True
    os.symlink = symlink

    # Silences the "cache-system uses symlinks by default" notice, which is now
    # answered rather than merely repeated.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


# Windows only. Nothing else allocates a console for a child process.
CREATE_NO_WINDOW = 0x08000000


def patch_consoles() -> None:
    """
    Stop child processes opening their own console window.

    VOStudio.exe is a windowless build, and on Windows a child process started
    from a parent with no console gets a BRAND NEW one -- a black box that
    appears over the app, unasked, for as long as the child runs. Three things
    do it here: the Claude Code CLI the agent SDK spawns (that is the window
    titled "claude"), every ffmpeg call, and ffprobe.

    The SDK reaches the CLI through anyio.open_process, which offers no way to
    pass creation flags, so the flag is added at the one place they all
    converge: Popen itself.

    An explicit creationflags is never overridden. start_login() opens a
    console ON PURPOSE -- /login is interactive and hiding it would mean
    nothing happening -- and this must not take that away.
    """
    if os.name != "nt":
        return
    import subprocess
    if getattr(subprocess.Popen.__init__, "_vostudio_patched", False):
        return

    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        # creationflags is the 14th positional parameter and nobody passes 13
        # positionals; if someone does, leave their call completely alone.
        if len(args) < 14 and not kwargs.get("creationflags"):
            kwargs["creationflags"] = CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    __init__._vostudio_patched = True
    subprocess.Popen.__init__ = __init__


def apply() -> None:
    patch_symlinks()
    patch_consoles()
