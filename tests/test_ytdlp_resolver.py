"""Finding yt-dlp, which on Windows is not where `which` looks.

The bug this holds shut: yt-dlp is a *base* dependency, installed into the app's own
virtualenv on every install. Three modules looked for it with `shutil.which`, which
searches `PATH` — and the `.vbs` that starts the app on Windows never puts the
virtualenv's `Scripts` directory there. So the app reported the tool missing while the
package sat importable in its own environment, and the agent, believing it, tried to
`pip install` it four times against a machine whose policy blocks shell execution.
"""

from __future__ import annotations

import sys

from forgecast import ytdlp


def test_the_module_answers_when_nothing_is_on_the_path(monkeypatch):
    """The Windows case. `python -m yt_dlp` runs through the interpreter the package was
    installed into, so it cannot miss the way a `PATH` search can."""
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: None)
    found = ytdlp.command()
    assert found == [sys.executable, "-m", "yt_dlp"]
    assert ytdlp.available()


def test_an_executable_on_the_path_is_preferred(monkeypatch):
    """A machine that installed yt-dlp system-wide may have a newer one than the pin."""
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: "/usr/local/bin/yt-dlp")
    assert ytdlp.command() == ["/usr/local/bin/yt-dlp"]


def test_genuinely_absent_is_reported_as_absent(monkeypatch):
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: None)
    monkeypatch.setattr(ytdlp.importlib.util, "find_spec", lambda name: None)
    assert ytdlp.command() is None
    assert not ytdlp.available()


def test_the_missing_message_names_a_button_and_never_a_pip_command():
    """This app installs its own tooling. An operator handed `pip install yt-dlp` has
    been handed the maintainer's job — and on a managed machine, one policy forbids."""
    said = ytdlp.why_missing()
    assert "pip install" not in said
    assert "Setup" in said or "Settings" in said


def test_every_caller_resolves_through_this_one_place(monkeypatch):
    """Three modules used to answer this question separately, and one of them answered it
    at import time — so a machine that gained yt-dlp after start was told it had none
    until the app was restarted."""
    import importlib

    from forgecast.providers import sfx
    from forgecast.research import keyless

    # By path, not by attribute: `forgecast/vision/__init__` binds the name `acquire` to
    # the function it exports, which shadows the submodule of the same name.
    acquire = importlib.import_module("forgecast.vision.acquire")

    monkeypatch.setattr(ytdlp, "command", lambda: ["fake-yt-dlp"])
    assert keyless._executable() == ["fake-yt-dlp"]
    assert sfx._ytdlp() == ["fake-yt-dlp"]
    assert acquire._yt_dlp() == ["fake-yt-dlp"]
