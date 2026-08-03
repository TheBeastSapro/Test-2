"""The first-run installer: what it probes, what it unpacks, what it puts on PATH.

The downloads themselves are not exercised here — they are 30 MB from nodejs.org and a
test suite that needs the internet is a test suite that fails on a train. What *is*
exercised is everything around them, because that is where the mistakes live: picking
the wrong archive for the platform, looking for npm's shim in the wrong place, and
unpacking an archive whose top-level folder is not named what you expected.

The real download was verified by hand against a throwaway root: Node 22.14.0 in, its
own npm used to install the CLI with `--prefix`, and `claude --version` answering
2.1.220 from inside the app folder.
"""

from __future__ import annotations

import os
import sys
import tarfile
import zipfile

import pytest

from forgecast.desktop import toolchain


def test_the_node_archive_matches_this_machine():
    url, top = toolchain._node_asset()
    assert toolchain.NODE_VERSION in url
    assert top in url
    # The platform token has to be in the URL, or a Windows machine downloads a
    # Linux tarball and the failure is a confusing unpack error rather than a
    # missing feature.
    token = "win" if os.name == "nt" else ("darwin" if sys.platform == "darwin" else "linux")
    assert token in url
    assert url.endswith(".zip" if os.name == "nt" else (".tar.gz" if sys.platform == "darwin" else ".tar.xz"))


def test_the_cli_is_looked_for_where_npm_actually_puts_it(tmp_path):
    """npm's global layout differs by platform.

    Windows drops shims in the prefix root; everything else uses `prefix/bin`. Getting
    this wrong means installing the CLI successfully and then reporting it missing —
    which reads as a broken installer.
    """
    cli = toolchain.cli_exe(tmp_path)
    node = toolchain.node_bin(tmp_path)
    if os.name == "nt":
        assert cli == node / "claude.cmd"
        assert toolchain.npm_exe(tmp_path) == node / "npm.cmd"
    else:
        assert cli == node / "bin" / "claude"
        assert toolchain.npm_exe(tmp_path) == node / "bin" / "npm"


def test_unpack_strips_the_version_named_top_folder(tmp_path):
    """Node wraps everything in `node-vX.Y.Z-plat-arch/`.

    Left in place the binary lands at `runtime/node/node-v22.14.0-linux-x64/bin/node`,
    which nothing looks for.
    """
    archive = tmp_path / "node.tar.gz"
    inner = tmp_path / "node-v22.14.0-linux-x64" / "bin"
    inner.mkdir(parents=True)
    (inner / "node").write_text("#!/bin/sh\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(tmp_path / "node-v22.14.0-linux-x64", arcname="node-v22.14.0-linux-x64")

    into = tmp_path / "runtime" / "node"
    toolchain._unpack(archive, into, strip="node-v22.14.0-linux-x64")
    assert (into / "bin" / "node").exists()


def test_unpack_survives_a_top_folder_named_something_else(tmp_path):
    """The ffmpeg build's folder carries its version, and the version changes.

    Failing on that would mean the installer breaks the day upstream publishes a new
    build — so a single unexpected directory is taken as the one to strip.
    """
    archive = tmp_path / "ffmpeg.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ffmpeg-7.9-essentials_build/bin/ffmpeg.exe", "binary")

    into = tmp_path / "runtime" / "ffmpeg"
    toolchain._unpack(archive, into, strip="ffmpeg")
    assert (into / "bin" / "ffmpeg.exe").exists()


def test_a_partial_download_is_not_left_looking_finished(tmp_path, monkeypatch):
    """A dropped connection must not leave a file the next run tries to unpack."""
    import urllib.error

    def explode(*_args, **_kwargs):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(toolchain.urllib.request, "urlopen", explode)
    dest = tmp_path / "node.tar.xz"
    with pytest.raises(urllib.error.URLError):
        toolchain._download("https://example.invalid/node.tar.xz", dest)
    assert not dest.exists()


def test_inventory_counts_a_tool_already_on_path(tmp_path):
    """Downloading a second ffmpeg next to the one someone chose is not helpful."""
    import shutil as _shutil

    tools = {tool.key: tool for tool in toolchain.inventory(tmp_path)}
    assert {"ffmpeg", "claude"} <= set(tools)
    if _shutil.which("ffmpeg") and _shutil.which("ffprobe"):
        assert tools["ffmpeg"].present
        assert tools["ffmpeg"].where


def test_node_is_only_offered_when_it_would_actually_help(tmp_path, monkeypatch):
    """Node is a means to an end, and the end is sometimes already met.

    The claude-agent-sdk wheel bundles a native CLI and the SDK resolves it before
    PATH, so Claude alone often needs nothing installed. Listing a 30 MB JavaScript
    runtime anyway invites the reasonable question of why an app that makes videos
    needs one.

    Both CLIs are found here, deliberately: with either one missing Node is a
    prerequisite rather than a spare download, and this test is about the case where it
    is neither.
    """
    from forgecast.agent import auth, codex_auth

    monkeypatch.setattr(codex_auth, "find_cli", lambda: ["/somewhere/codex"])
    monkeypatch.setattr(auth, "find_cli", lambda: "/somewhere/claude")
    keys = [t.key for t in toolchain.inventory(tmp_path)]
    assert "node" not in keys

    monkeypatch.setattr(auth, "find_cli", lambda: None)
    tools = {t.key: t for t in toolchain.inventory(tmp_path)}
    assert not tools["claude"].present
    if os.name == "nt":
        # Windows gets its Claude CLI from the vendor installer, which brings its own
        # runtime — so a missing Claude alone is not a reason to download Node there.
        assert "node" not in tools
    else:
        assert "node" in tools


def test_ffmpeg_is_a_package_manager_job_off_windows(tmp_path):
    ok, detail = toolchain.install_ffmpeg(tmp_path, None)
    if os.name == "nt":
        return                       # would download; not exercised here
    assert not ok
    # A command to run, not a paragraph about how to find one.
    assert detail.startswith(("brew ", "sudo apt "))
    # And it is reported as needing you, so the setup page does not offer a step it
    # cannot perform.
    manual = {t.key: t.manual for t in toolchain.inventory(tmp_path)}
    assert manual["ffmpeg"] == "" or manual["ffmpeg"].startswith(("brew ", "sudo apt "))


def test_activate_puts_the_bundled_tools_first_and_drops_a_shadowing_key(tmp_path, monkeypatch):
    """The two things start-up has to get right before anything spawns a child.

    The PATH order matters because a system ffmpeg of a different version would
    otherwise win. Removing ANTHROPIC_API_KEY matters more: it outranks the Claude
    subscription login, so leaving it set means every message quietly bills an API
    account instead of the plan you already pay for.
    """
    bundled = toolchain.ffmpeg_bin(tmp_path)
    bundled.mkdir(parents=True)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")        # empty still counts as set

    result = toolchain.activate(tmp_path)
    assert os.environ["PATH"].startswith(str(bundled))
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert result["api_key_removed"] == "yes"


def test_needs_setup_is_false_when_only_a_manual_tool_is_missing(monkeypatch, tmp_path):
    """A setup screen you cannot complete is worse than a banner."""
    from forgecast.api import routes_setup

    monkeypatch.setattr(routes_setup, "app_root", lambda: tmp_path)
    monkeypatch.setattr(toolchain, "inventory", lambda _root: [
        toolchain.Tool("ffmpeg", "ffmpeg", 80, present=False, where="",
                       manual="sudo apt install ffmpeg"),
        toolchain.Tool("node", "Node.js", 30, present=True, where="/usr/bin/node"),
        toolchain.Tool("claude", "CLI", 12, present=True, where="/usr/bin/claude"),
    ])
    assert routes_setup.needs_setup() is False


def test_setup_state_is_safe_to_render_before_an_account_exists(tmp_path, monkeypatch):
    """The page is the first thing a fresh install shows, and there is no user yet."""
    from fastapi.testclient import TestClient

    from forgecast.api.main import create_app

    with TestClient(create_app()) as client:
        page = client.get("/setup")
        assert page.status_code == 200
        assert "install" in page.text.lower()
        body = client.get("/api/setup/state").json()
        assert {"tools", "ready", "runtime", "job"} <= set(body)


# ------------------------------------------------------------------ the Codex CLI
#
# Reported as "chatgpt cli isn't installing properly". It was not installing badly — it
# was not in this module at all, so nothing ever installed it and the ChatGPT backend
# only worked for someone who had run npm themselves. These pin the parts of that fix
# that a later edit could quietly undo.


def _fake_npm(root):
    """An npm that exists on disk, so the installer gets as far as running it.

    Only its existence is used — `run_watched` is replaced in every test below, because
    a real `npm install -g @openai/codex` is a network download and a suite that needs
    the internet is a suite that fails on a train.
    """
    npm = toolchain.npm_exe(root)
    npm.parent.mkdir(parents=True, exist_ok=True)
    npm.write_text("", encoding="utf-8")
    return npm


def test_the_codex_cli_is_offered_at_all(tmp_path):
    """The bug itself: no entry meant no installer, and no installer meant homework.

    `toolchain.py` exists to remove exactly the "go and run npm yourself" step, and the
    ChatGPT backend was the one thing still asking for it.
    """
    tools = {tool.key: tool for tool in toolchain.inventory(tmp_path)}
    assert "codex" in tools
    assert tools["codex"].weight == toolchain.WEIGHT_CODEX
    # No `manual` on any platform: one npm install is the whole story, and a tool marked
    # manual is one the setup page refuses to install.
    assert tools["codex"].manual == ""


def test_codex_presence_is_decided_by_the_module_that_runs_it(tmp_path, monkeypatch):
    """Asked through `codex_auth.find_cli`, never by looking for a file called codex.

    It knows three things a file check does not: the app's own runtime copy, PATH, and
    that the Windows `.cmd` shim cannot be spawned directly. Answering from disk instead
    reports connected on a machine where the first message dies with WinError 193.
    """
    from forgecast.agent import codex_auth

    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)
    tools = {tool.key: tool for tool in toolchain.inventory(tmp_path)}
    assert tools["codex"].present is False
    assert tools["codex"].where == ""

    monkeypatch.setattr(codex_auth, "find_cli",
                        lambda: ["/runtime/node/bin/node", "/runtime/codex/bin/codex.js"])
    tools = {tool.key: tool for tool in toolchain.inventory(tmp_path)}
    assert tools["codex"].present is True
    # The script, not the interpreter in front of it — "where it is" has to name the
    # thing someone could go and look at.
    assert tools["codex"].where == "/runtime/codex/bin/codex.js"


def test_node_is_offered_whenever_codex_is_missing_on_every_platform(tmp_path, monkeypatch):
    """Windows included, which is where the old condition was wrong.

    Node used to be offered only when the Claude CLI was missing *and* the platform was
    not Windows — right for Claude, whose Windows CLI comes from a vendor installer with
    its own runtime. The Codex CLI has no bundled build anywhere and arrives only through
    npm, so under the old condition Windows was offered a CLI with nothing to run it: an
    install that could only fail, reported as npm's fault.
    """
    import os as real_os
    from types import SimpleNamespace

    from forgecast.agent import auth, codex_auth

    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)
    monkeypatch.setattr(auth, "find_cli", lambda: "/somewhere/claude")
    assert "node" in {tool.key for tool in toolchain.inventory(tmp_path)}

    # `toolchain.os` is replaced rather than the real `os.name` patched: setting that to
    # "nt" on Linux makes pathlib instantiate WindowsPath and takes the session with it.
    monkeypatch.setattr(toolchain, "os",
                        SimpleNamespace(name="nt", environ=real_os.environ,
                                        pathsep=";"))
    assert "node" in {tool.key for tool in toolchain.inventory(tmp_path)}


def test_installing_codex_without_npm_refuses_and_names_npm(tmp_path, monkeypatch):
    """No npm is a fact worth stating, not a mystery to hand back.

    "The Codex CLI could not be installed" sends someone to look at Codex. npm is what
    is absent and Node is what provides it, so both are named — and nothing is spawned,
    because there is nothing to spawn.
    """
    def must_not_run(*_args, **_kwargs):                       # pragma: no cover
        raise AssertionError("no npm exists, so nothing may be started")

    monkeypatch.setattr(toolchain, "run_watched", must_not_run)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)

    ok, detail = toolchain.install_codex_cli(tmp_path)

    assert ok is False
    assert "npm" in detail
    assert "Node" in detail


def test_a_failed_npm_hands_back_npms_own_words(tmp_path, monkeypatch):
    """A failure whose reason went nowhere is a failure with nothing to act on."""
    _fake_npm(tmp_path)
    monkeypatch.setattr(toolchain, "run_watched", lambda *a, **k: (
        1, "npm error code E404\nnpm error 404 Not Found - GET @openai/codex"))

    ok, detail = toolchain.install_codex_cli(tmp_path)

    assert ok is False
    assert "404 Not Found" in detail


def test_an_npm_that_exits_zero_with_nothing_runnable_is_not_a_success(tmp_path, monkeypatch):
    """The exact failure `auth.py` documents for Windows shims, refused here.

    An install reported as successful when nothing findable came out of it takes the
    setup page green, the chip to "connected", and the first message to a crash. npm's
    exit code is not evidence that this app can run what npm wrote, so the answer to
    "can it be found" is the one that decides — and the detail says which of the two
    happened, an empty prefix or a package the lookup missed.
    """
    from forgecast.agent import codex_auth

    _fake_npm(tmp_path)
    monkeypatch.setattr(toolchain, "run_watched", lambda *a, **k: (0, "added 1 package"))
    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)

    ok, detail = toolchain.install_codex_cli(tmp_path)
    assert ok is False
    assert "nothing was written" in detail

    # And with the package on disk the message has to change, because the fix does: one
    # is a failed download, the other is a lookup that did not look where npm put it.
    entry = (toolchain.node_bin(tmp_path) / "lib" / "node_modules" / "@openai" / "codex"
             / "bin" / "codex.js")
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/usr/bin/env node\n", encoding="utf-8")

    ok, detail = toolchain.install_codex_cli(tmp_path)
    assert ok is False
    assert "_bundled_js" in detail
    assert str(entry.parent) in detail


def test_a_working_install_reports_where_it_landed(tmp_path, monkeypatch):
    """And installs into the one prefix the app looks in.

    `--prefix runtime/node` is not tidiness: `codex_auth._bundled_js` looks for the
    package under that folder and spawns its `bin/codex.js` with the bundled node. A
    copy installed anywhere else works from a terminal and is invisible to the app.
    """
    from forgecast.agent import codex_auth

    _fake_npm(tmp_path)
    seen: dict = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return 0, "added 1 package"

    monkeypatch.setattr(toolchain, "run_watched", fake_run)
    monkeypatch.setattr(codex_auth, "find_cli",
                        lambda: ["/node", "/prefix/@openai/codex/bin/codex.js"])

    ok, detail = toolchain.install_codex_cli(tmp_path)

    assert ok is True
    assert detail == "/prefix/@openai/codex/bin/codex.js"
    assert toolchain.CODEX_PACKAGE in seen["command"]
    assert seen["command"][seen["command"].index("--prefix") + 1] == str(
        toolchain.node_bin(tmp_path))


def test_what_npm_writes_is_what_the_agent_goes_looking_for(tmp_path, monkeypatch):
    """The silent miss this prevents: installed, working, and reported as absent.

    npm's `--prefix` layout differs by platform — `lib/node_modules` on POSIX, plain
    `node_modules` on Windows — so the installer and `codex_auth._bundled_js` have to
    agree about both. They are checked against each other here rather than each against
    its own idea of the layout, which is how they drift apart.
    """
    import shutil as _shutil

    from forgecast.agent import codex_auth

    runtime = toolchain.node_bin(tmp_path)
    node = toolchain.node_exe(tmp_path)
    node.parent.mkdir(parents=True, exist_ok=True)
    node.write_text("", encoding="utf-8")
    monkeypatch.setattr(codex_auth, "APP_ROOT", tmp_path)

    for layout in (runtime / "lib" / "node_modules", runtime / "node_modules"):
        entry = layout / "@openai" / "codex" / "bin" / "codex.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("#!/usr/bin/env node\n", encoding="utf-8")

        assert toolchain.codex_entry(tmp_path) == entry
        assert codex_auth.find_cli() == [str(node), str(entry)]
        assert toolchain.codex_where(tmp_path) == str(entry)

        _shutil.rmtree(layout)
