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
    tools = {tool.key: tool for tool in toolchain.inventory(tmp_path)}
    assert set(tools) == {"ffmpeg", "node", "claude"}
    import shutil as _shutil
    if _shutil.which("ffmpeg") and _shutil.which("ffprobe"):
        assert tools["ffmpeg"].present
        assert tools["ffmpeg"].where


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
