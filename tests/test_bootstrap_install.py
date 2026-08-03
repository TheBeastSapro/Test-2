"""When the first launch cannot install, what it says.

This exists because of a real report: the console showed three status lines, then
"dependency installation failed. Scroll up for pip's reason", and **there was nothing
above it**. pip's output had gone nowhere, so the message named information that did not
exist and sent the operator looking for it.

Two causes, both mine. `--quiet` suppressed pip's own account of what went wrong. And the
output was inherited rather than captured — which cannot work under the windowless
launcher, where there is no console to inherit, and is fragile even with one, because
child consoles are deliberately suppressed on Windows so that nothing black appears out of
nowhere. Removing the black box removed the error message with it.

So the rule these tests hold: **a failed install must carry its own reason.** Never a
pointer to somewhere else, on any platform, with or without a console.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgecast.desktop import bootstrap

# Captured before the autouse fixture below replaces it, so the two tests that are *about*
# reachability call the real thing rather than the stub the rest of the file needs.
REAL_UNREACHABLE = bootstrap._pypi_unreachable

# Every spelling pip and requests honour. The sandbox this suite runs in sets some of
# them, which is exactly the condition the skip-the-probe branch exists for — so a test of
# the probe has to clear all of them or it silently asserts nothing.
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY",
              "PIP_INDEX_URL", "PIP_PROXY")


class _Result:
    def __init__(self, code: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def _project(tmp_path: Path) -> Path:
    """The minimum `install_dependencies` reads: a pyproject and a venv interpreter."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    python = bootstrap.venv_python(tmp_path)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    return python


@pytest.fixture(autouse=True)
def _network_is_fine(monkeypatch):
    """Reachability is asserted separately; these tests are about pip's own failures."""
    monkeypatch.setattr(bootstrap, "_pypi_unreachable", lambda: "")


# ------------------------------------------------------- the reason is in the message


def test_pip_output_is_captured_not_inherited(tmp_path, monkeypatch):
    """The bug itself. Inherited output is invisible under a windowless launcher."""
    seen: dict = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return _Result(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    _project(tmp_path)

    bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    assert seen.get("capture_output") is True, \
        "pip's output must be captured — there may be no console to inherit"
    assert seen.get("text") is True


def test_quiet_is_gone(tmp_path, monkeypatch):
    """`--quiet` saved console noise that no longer goes to a console, and emptied the log
    in the one case a log matters."""
    recorded: dict = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        return _Result(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    _project(tmp_path)

    bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    assert "--quiet" not in recorded["command"]


def test_a_failure_carries_pips_own_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Result(
        1, stderr="ERROR: No matching distribution found for setuptools>=68"))
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    message = str(caught.value)
    assert "No matching distribution found for setuptools>=68" in message
    # The instruction that was a lie must not come back.
    assert "scroll up" not in message.lower()


def test_the_full_output_is_written_to_a_log(tmp_path, monkeypatch):
    """The windowless path has no console at all, so the file is the only record."""
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Result(
        1, stdout="line one\n", stderr="line two\n"))
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    log = tmp_path / "runtime" / "pip.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "line one" in text and "line two" in text
    assert str(log) in str(caught.value), "the message must say where the whole log is"


def test_a_successful_install_logs_too(tmp_path, monkeypatch):
    """Kept on success as well: the next failure is often explained by the last success."""
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Result(
        0, stdout="Successfully installed forgecast-0.1.0\n"))
    _project(tmp_path)

    assert bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    assert "Successfully installed" in (tmp_path / "runtime" / "pip.log").read_text(
        encoding="utf-8")


def test_pip_printing_nothing_says_so_rather_than_showing_a_blank(tmp_path, monkeypatch):
    """The exact shape of the original report: a failure with no output behind it.

    "pip printed nothing at all" is a fact the operator can report. A blank space under a
    heading is the bug being reproduced.
    """
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Result(1))
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    assert "printed nothing" in str(caught.value)


def test_a_read_only_folder_still_reports_the_reason(tmp_path, monkeypatch):
    """Losing the log must not lose the message — that would be the original bug again."""
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Result(
        1, stderr="ERROR: something specific"))

    original = Path.mkdir

    def refuse(self, *args, **kwargs):
        if self.name == "runtime":
            raise OSError("read-only")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse)
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    assert "something specific" in str(caught.value)


def test_only_the_tail_is_shown(tmp_path, monkeypatch):
    """pip prints the error last, and a thousand lines of resolution scroll the message
    it is attached to off the screen."""
    flood = "\n".join(f"noise {n}" for n in range(400)) + "\nERROR: the real reason"
    monkeypatch.setattr(subprocess, "run",
                        lambda command, **kwargs: _Result(1, stdout=flood))
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    message = str(caught.value)
    assert "ERROR: the real reason" in message
    assert "noise 0" not in message
    # And the whole thing is still on disk.
    assert "noise 0" in (tmp_path / "runtime" / "pip.log").read_text(encoding="utf-8")


# ------------------------------------------------------------------- the three causes


@pytest.mark.parametrize(("output", "expected"), [
    ("ERROR: No matching distribution found for setuptools>=68", "no network access"),
    ("Temporary failure in name resolution", "no network access"),
    ("error: Microsoft Visual C++ 14.0 or greater is required", "compile"),
    ("PermissionError: [WinError 5] Access is denied", "permissions"),
])
def test_the_likely_cause_is_named_with_its_remedy(output, expected):
    """Three causes account for nearly every real occurrence, and each has a different
    fix. Naming the class of problem is what turns a stack trace into an action."""
    assert expected in bootstrap._pip_failure(output, None)


def test_an_unrecognised_failure_gets_no_invented_diagnosis():
    """Better to show pip's words and stop than to guess wrong confidently."""
    message = bootstrap._pip_failure("ERROR: something nobody has seen before", None)

    assert "something nobody has seen before" in message
    for guess in ("no network access", "compile", "permissions"):
        assert guess not in message


# --------------------------------------------------------------- the pre-flight check


def test_no_network_is_reported_before_pip_runs(tmp_path, monkeypatch):
    """Knowable in three seconds, and otherwise discovered after two minutes of waiting."""
    monkeypatch.setattr(bootstrap, "_pypi_unreachable",
                        lambda: "[Errno 11001] getaddrinfo failed")

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("pip must not be started when pypi is unreachable")

    monkeypatch.setattr(subprocess, "run", must_not_run)
    _project(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as caught:
        bootstrap.install_dependencies(tmp_path, bootstrap.venv_python(tmp_path))

    message = str(caught.value)
    # The OS's own words, because "[Errno 11001] getaddrinfo failed" says DNS where
    # "network error" says nothing.
    assert "getaddrinfo failed" in message
    assert "HTTPS_PROXY" in message
    # And that this is a one-time cost, so it does not read as "needs the internet to run".
    assert "first launch" in message


def test_a_configured_proxy_skips_the_check(monkeypatch):
    """The proxy is what would be connected to, and its host is not reliably knowable
    from here. A false "no network" on a machine that has one is the worse error."""
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")

    import socket

    def must_not_connect(*_args, **_kwargs):
        raise AssertionError("pypi must not be probed directly when a proxy is set")

    monkeypatch.setattr(socket, "create_connection", must_not_connect)
    assert REAL_UNREACHABLE() == ""


def test_the_check_uses_the_standard_library_only(monkeypatch):
    """It runs before the virtualenv exists, so `httpx` is one of the things it is
    checking whether it can install."""
    import socket

    calls: list = []

    def fake_connect(address, timeout=None):
        calls.append((address, timeout))
        raise OSError("[Errno 111] Connection refused")

    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket, "create_connection", fake_connect)

    reason = REAL_UNREACHABLE()

    assert calls == [(("pypi.org", 443), bootstrap.REACHABILITY_TIMEOUT)]
    assert "Connection refused" in reason
