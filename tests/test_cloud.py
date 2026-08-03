"""What cloud backup is allowed to send, and that the round trip actually works.

Three properties are worth more than the rest of this file put together, so they are
asserted first and hardest:

* **It is off.** A fresh install does not talk to GitHub. Proven at the settings level and
  at the config level, because "off by default" is the claim that makes the whole feature
  safe to ship and it is one careless default away from being false.
* **Nothing secret can reach a repository.** Asserted against `manifest.DENY` itself, in the
  shape `tests/test_packaging.py` established: a decoy file is written into a real storage
  tree, a real snapshot is built from it, and the finished tree is walked through the same
  rule set the builder used. A file kind nobody has thought of yet is caught because it
  matches a rule, not because somebody added a case here.
* **The restore works.** Against a real bare git repository in a temporary directory, with
  no GitHub account and no network. A backup nobody has restored is a folder of hope, so the
  round trip — stage, commit, push, clone, restore — runs on every test run.

`git` is a real dependency of these tests and of nothing else in the suite, so the whole
file skips when it is absent rather than failing: a machine without git is a machine where
this feature reports `GitMissing`, which is tested separately and without a subprocess.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from forgecast.cloud import config as cloud_config
from forgecast.cloud import device, errors, manifest, repo, snapshot
from forgecast.config import Settings

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

needs_git = pytest.mark.skipif(
    not repo.git_available(), reason="git is not installed on this machine"
)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    """A storage tree shaped like a real one: run text, a style, a skill, and renders."""
    root = tmp_path / "storage"
    run = root / "runs" / "12"

    (run / "brief").mkdir(parents=True)
    (run / "brief" / "brief.json").write_text(
        json.dumps({"topic": "deep sea vents", "sources": []}), encoding="utf-8"
    )
    (run / "script").mkdir(parents=True)
    (run / "script" / "script.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    (run / "script" / "script.md").write_text("# Deep sea vents\n", encoding="utf-8")
    (run / "finalize").mkdir(parents=True)
    (run / "finalize" / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nhi\n",
                                                   encoding="utf-8")

    # The things that must never travel.
    (run / "finalize" / "final.mp4").write_bytes(b"\x00" * 4096)
    (run / "shots").mkdir(parents=True)
    (run / "shots" / "shot_001_plate.png").write_bytes(b"\x89PNG" + b"\x00" * 2048)
    (run / "voice").mkdir(parents=True)
    (run / "voice" / "take_1.mp3").write_bytes(b"ID3" + b"\x00" * 2048)

    (root / "styles").mkdir(parents=True)
    (root / "styles" / "calm.json").write_text(json.dumps({"cuts_per_minute": 8}),
                                               encoding="utf-8")
    (root / "skills").mkdir(parents=True)
    (root / "skills" / "hooks.md").write_text("---\nname: Hooks\n---\nOpen cold.\n",
                                              encoding="utf-8")
    (root / "agent_prefs.json").write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    (root / "voice_catalogue.json").write_text(json.dumps({"voices": []}), encoding="utf-8")
    (root / "voice_catalogue_all.json").write_text(json.dumps({"voices": []}),
                                                   encoding="utf-8")
    return root


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    """A bare git repository standing in for GitHub.

    This is what makes the round trip testable at all. Push and clone against a local bare
    repo exercise exactly the git plumbing that runs against github.com — the only untested
    part is the credential helper, which a local path does not need, and that is stated
    rather than pretended about.
    """
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(path)],
                   check=True, capture_output=True)
    return path


# ----------------------------------------------------------------------- off by default


def test_the_shipped_default_is_off():
    """The one setting whose default has to be the restrictive one.

    Read off a `Settings` built with no environment, the way `test_private_instance.py`
    asserts `allow_signup`. A default that flipped would mean an install nobody configured
    started sending scripts to a service nobody signed up for.
    """
    assert Settings(_env_file=None).cloud_sync is False
    assert Settings(_env_file=None).github_client_id == ""


def test_a_fresh_install_is_not_active(tmp_path: Path):
    fresh = cloud_config.load(tmp_path / "cloud.json")
    assert fresh.enabled is False
    assert fresh.active() is False
    assert fresh.authorised is False


def test_enabled_alone_is_not_active(tmp_path: Path):
    """Three conditions, not one.

    Enabled with no remote and no token must not count as active, or the first backup
    attempt on a half-configured install is a crash instead of a sentence.
    """
    half = cloud_config.CloudConfig(enabled=True)
    assert half.active() is False
    half.remote = "https://example.invalid/x.git"
    assert half.active() is False
    half.set_token("gho_pretend")
    assert half.active() is True


def test_config_round_trips_with_the_token_encrypted(tmp_path: Path):
    path = tmp_path / "cloud.json"
    original = cloud_config.CloudConfig(enabled=True, remote="https://example.invalid/x.git")
    original.set_token("gho_super_secret_value")
    original.save(path)

    raw = path.read_text(encoding="utf-8")
    assert "gho_super_secret_value" not in raw, "the token was written in the clear"

    reloaded = cloud_config.load(path)
    assert reloaded.token == "gho_super_secret_value"
    assert reloaded.enabled is True


def test_the_public_view_never_carries_the_token(tmp_path: Path):
    """Ciphertext is not for a page, an API body or a support log.

    All three get copied around, and an encrypted blob plus a leaked `.env` is the token.
    """
    current = cloud_config.CloudConfig(enabled=True, remote="x")
    current.set_token("gho_secret")
    public = current.public_dict()
    assert "token" not in public
    assert "gho_secret" not in json.dumps(public)
    assert current.as_dict()["token"] != "gho_secret"


def test_a_malformed_config_reads_as_off(tmp_path: Path):
    """This feature is not important enough to take the app down.

    A JSON file with a trailing comma must not be the reason Forgecast will not start.
    """
    path = tmp_path / "cloud.json"
    path.write_text("{not json at all", encoding="utf-8")
    assert cloud_config.load(path).active() is False


# ------------------------------------------------------------------------- the manifest


def test_renders_are_never_eligible():
    for name in ("runs/1/final.mp4", "runs/1/shot_001_clip.mov", "runs/1/plate.png",
                 "runs/1/take.mp3", "runs/1/avatar.webm", "runs/1/frame.avif"):
        assert not manifest.eligible(name), name
        assert manifest.reason(name)


def test_secrets_are_never_eligible():
    for name in (".env", ".env.local", "prod.env", "id_rsa", "server.pem", "tls.key",
                 "credentials.json", "client_secret_1.json", "token.json",
                 "connectors.json", "cloud.json", "secrets.yaml", "backup.secret"):
        assert not manifest.eligible(name), name


def test_the_database_and_every_sidecar_are_never_eligible():
    """The failure `package.py` records: `*.db` does not match `forgecast.db-wal`.

    The sidecars hold database pages, so one of them in a commit is rows in a commit.
    """
    for name in ("forgecast.db", "forgecast.db-wal", "forgecast.db-shm",
                 "forgecast.db-journal", "app.sqlite", "app.sqlite3"):
        assert not manifest.eligible(name), name


def test_a_deny_pattern_matches_at_any_depth():
    assert not manifest.eligible("runs/12/work/concat.txt")
    assert manifest.denied("runs/12/nested/.env") == ".env"
    assert manifest.denied("RUNS/12/.ENV") == ".env", "matching must be case-insensitive"


def test_an_unknown_extension_defaults_to_excluded():
    """The direction where being wrong is recoverable.

    The day a node writes `plate.heic` or a vendor returns `.mkv`, the allow-list keeps it
    out. A deny-list alone would let it through and the first sign would be a rejected push.
    """
    for name in ("runs/1/thing.heic", "runs/1/thing.bin", "runs/1/manifest", "runs/1/x.psd"):
        assert not manifest.eligible(name), name


def test_every_deny_pattern_is_enforced():
    """Turn each pattern into a concrete name and require the rule set to refuse it.

    Borrowed from `test_packaging.test_every_pattern_is_enforced` for the same reason: a
    pattern nothing tests is a pattern that can rot into decoration.
    """
    for pattern in manifest.DENY:
        concrete = pattern.replace("*", "x").replace("[cod]", "c").replace("?", "y")
        assert manifest.denied(f"runs/1/{concrete}"), pattern


def test_the_text_a_run_produces_is_eligible():
    for name in ("runs/12/brief/brief.json", "runs/12/script/script.md",
                 "runs/12/finalize/captions.srt", "styles/calm.json",
                 "skills/hooks.md", "agent_prefs.json"):
        assert manifest.eligible(name), name
        assert manifest.reason(name) == ""


def test_the_per_file_cap_is_below_githubs_warning():
    """25 MB, so GitHub's 50 MiB warning is never how a mistake is discovered."""
    assert manifest.MAX_FILE_BYTES < 50 * 1024 * 1024


def test_an_oversized_text_file_is_excluded_with_a_reason(tmp_path: Path):
    root = tmp_path / "storage"
    root.mkdir()
    (root / "huge.json").write_text("x" * (manifest.MAX_FILE_BYTES + 1), encoding="utf-8")
    included, excluded = manifest.classify(root)
    assert included == []
    assert excluded and "over the 25 MB cap" in excluded[0][1], (
        "the wording has to come from FileTooLarge, so the page and the log agree"
    )


def test_a_symlink_out_of_storage_is_excluded(tmp_path: Path):
    """A link inside `storage/` pointing at a home directory would otherwise be committed
    under its target's name — the traversal `api/routes_files.py:91` guards on the read
    side, guarded here on the write side."""
    root = tmp_path / "storage"
    root.mkdir()
    outside = tmp_path / "elsewhere.md"
    outside.write_text("private", encoding="utf-8")
    (root / "link.md").symlink_to(outside)
    included, excluded = manifest.classify(root)
    assert included == []
    assert any("symlink" in why for _, why in excluded)


def test_classify_splits_a_realistic_tree(storage: Path):
    included, excluded = manifest.classify(storage)
    names = {p.as_posix() for p in included}
    assert "runs/12/script/script.md" in names
    assert "runs/12/finalize/captions.srt" in names
    assert "skills/hooks.md" in names
    assert "voice_catalogue.json" in names

    left_out = {p.as_posix() for p, _ in excluded}
    assert "runs/12/finalize/final.mp4" in left_out
    assert "runs/12/shots/shot_001_plate.png" in left_out
    assert "runs/12/voice/take_1.mp3" in left_out
    assert "voice_catalogue_all.json" in left_out


# -------------------------------------------------------------------------- the snapshot


def test_the_plan_reports_before_anything_is_sent(storage: Path):
    """The first-enable dry run. Nothing is written and nothing is sent."""
    plan = snapshot.plan(storage)
    assert plan.file_count == 8
    assert plan.total_bytes > 0
    assert "stay on this machine" in plan.sentence()
    largest = plan.largest_exclusions()
    assert largest[0]["path"] == "runs/12/finalize/final.mp4", "sorted by size"
    assert largest[0]["reason"]


def test_a_built_snapshot_contains_the_work_and_no_renders(storage: Path, tmp_path: Path):
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={"channels": [{"id": 1}]},
                   machine="laptop")

    assert (staged / "storage" / "runs" / "12" / "script" / "script.md").exists()
    assert not (staged / "storage" / "runs" / "12" / "finalize" / "final.mp4").exists()
    assert not list((staged / "storage").rglob("*.png"))
    assert not list((staged / "storage").rglob("*.mp3"))

    header = json.loads((staged / "snapshot.json").read_text(encoding="utf-8"))
    assert header["schema"] == snapshot.SCHEMA
    assert header["machine"] == "laptop"
    assert header["files"] == 8
    assert header["tables"] == ["channels"]
    assert json.loads((staged / "db" / "channels.json").read_text(encoding="utf-8"))


def test_the_snapshot_is_audited_with_the_rule_set_that_built_it(storage: Path,
                                                                tmp_path: Path):
    """The second use of the one rule set — over the finished tree, not over the copy list.

    A file that arrived by some other route is caught too, which is the whole point:
    `package.py` asserts the archive rather than trusting the collector, for the same reason.
    """
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")

    (staged / "storage" / "smuggled.mp4").write_bytes(b"\x00" * 16)
    with pytest.raises(errors.SnapshotTooBig) as caught:
        snapshot.audit(staged)
    assert "smuggled.mp4" in caught.value.detail


def test_decoy_secrets_are_never_staged(storage: Path, tmp_path: Path):
    """Real files, a real snapshot, a real walk of the result.

    A rule set that is only tested against strings is a rule set that has never met the
    filesystem — `test_packaging.test_decoys_are_never_packaged` learned that first.
    """
    decoys = {
        ".env": "FORGECAST_ENCRYPTION_KEY=aGVsbG8td29ybGQtdGhpcy1pcy1hLWtleQ==",
        "connectors.json": '{"nexlev": {"token": "ciphertext"}}',
        "cloud.json": '{"token": "gho_leak"}',
        "id_rsa": "-----BEGIN OPENSSH PRIVATE KEY-----",
        "forgecast.db-wal": "sqlite page data",
        "client_secret_abc.json": '{"installed": {"client_secret": "x"}}',
    }
    for name, body in decoys.items():
        (storage / name).write_text(body, encoding="utf-8")
    (storage / "runs" / "12" / ".env").write_text("nested secret", encoding="utf-8")

    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")

    staged_names = {p.name for p in staged.rglob("*") if p.is_file()}
    for name in decoys:
        assert name not in staged_names, f"{name} reached the snapshot"

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in staged.rglob("*") if p.is_file()
    )
    assert "FORGECAST_ENCRYPTION_KEY" not in blob
    assert "gho_leak" not in blob
    assert "BEGIN OPENSSH PRIVATE KEY" not in blob


def test_staging_is_rebuilt_so_a_deletion_propagates(storage: Path, tmp_path: Path):
    """A skill the operator deleted must not be restored by the backup.

    An incremental copy leaves it behind, git sees no change, and the backup quietly
    disagrees with the machine it is backing up.
    """
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    assert (staged / "storage" / "skills" / "hooks.md").exists()

    (storage / "skills" / "hooks.md").unlink()
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    assert not (staged / "storage" / "skills" / "hooks.md").exists()


def test_a_surprisingly_large_snapshot_is_refused(storage: Path, tmp_path: Path,
                                                  monkeypatch):
    """The first-enable guard. Not GitHub's limit — the point where the manifest is wrong."""
    monkeypatch.setattr(snapshot, "MAX_TOTAL_BYTES", 10)
    with pytest.raises(errors.SnapshotTooBig):
        snapshot.build(tmp_path / "staged", storage_dir=storage, rows={})


# ------------------------------------------------------------------------- the row export


def test_the_row_export_drops_secret_columns_by_name(session, channel):
    """Column names, not table names.

    The failure this catches is a *new* table with a `ciphertext` column added by somebody
    who never read `snapshot.py`. A table-level allow-list would let it through.
    """
    from forgecast.crypto import encrypt

    channel.youtube_credentials = encrypt("refresh-token-worth-stealing")
    session.add(channel)
    session.commit()

    rows = snapshot.export_rows()
    assert rows["channels"], "the channel should be exported"
    exported = json.dumps(rows)
    assert "youtube_credentials" not in exported
    assert "refresh-token-worth-stealing" not in exported
    assert channel.youtube_credentials not in exported, "not even the ciphertext"
    assert "users" not in rows, "accounts and password hashes are local to an install"
    assert "provider_keys" not in rows


def test_the_row_export_is_json_serialisable(session, channel):
    """Datetimes and enums have to survive `json.dumps` or the snapshot cannot be written."""
    rows = snapshot.export_rows()
    text = json.dumps(rows)
    assert channel.name in text


# ------------------------------------------------------------------ the git round trip


@needs_git
def test_push_then_clone_then_restore(storage: Path, tmp_path: Path, bare_remote: Path):
    """The feature, end to end, with no GitHub account and no network.

    Restore is what the rest of this package exists to make possible, so it is exercised
    every run rather than trusted.
    """
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={"runs": [{"id": 12, "topic": "vents"}]},
                   machine="laptop")

    repository = repo.Repository(staged, remote=str(bare_remote))
    repository.ensure()
    commit = repository.commit("initial snapshot: 1 run")
    assert commit is not None
    repository.push(machine="laptop")

    clone_at = tmp_path / "clone"
    restored_into = tmp_path / "restored"
    repo.Repository(clone_at, remote=str(bare_remote)).clone()
    result = snapshot.restore(clone_at, restored_into)

    assert (restored_into / "runs" / "12" / "script" / "script.md").read_text(
        encoding="utf-8") == "# Deep sea vents\n"
    assert (restored_into / "skills" / "hooks.md").exists()
    assert result.tables == {"runs": 1}
    assert result.rows_applied is False
    assert "restored-rows" in result.note
    assert not list(restored_into.rglob("*.mp4")), "a restore must not invent renders"


@needs_git
def test_a_second_commit_with_no_change_is_nothing_to_do(storage: Path, tmp_path: Path,
                                                        bare_remote: Path):
    """The caller has to be able to say "nothing changed" rather than claim a backup."""
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    repository = repo.Repository(staged, remote=str(bare_remote))
    repository.ensure()
    assert repository.commit("first") is not None
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    assert repository.commit("second") is None


@needs_git
def test_a_diverged_push_goes_to_its_own_branch_and_says_so(storage: Path, tmp_path: Path,
                                                            bare_remote: Path):
    """Two machines, two truths, no automatic merge.

    A `--force` here would work for months and then overwrite the afternoon somebody spent
    on the other laptop, exactly once.
    """
    first = tmp_path / "machine-a"
    snapshot.build(first, storage_dir=storage, rows={}, machine="a")
    a = repo.Repository(first, remote=str(bare_remote))
    a.ensure()
    a.commit("from a")
    a.push(machine="a")

    # A second machine that never saw a's commit: its own history from scratch.
    second = tmp_path / "machine-b"
    snapshot.build(second, storage_dir=storage, rows={}, machine="b")
    (second / "storage" / "skills" / "other.md").write_text("different", encoding="utf-8")
    b = repo.Repository(second, remote=str(bare_remote))
    b.ensure()
    b.commit("from b")

    with pytest.raises(errors.Diverged) as caught:
        b.push(machine="b")
    assert caught.value.branch == "machine/b"
    assert "machine/b" in caught.value.sentence

    # The work reached the remote before the operator was told anything.
    branches = subprocess.run(["git", "branch", "--list"], cwd=bare_remote,
                              capture_output=True, text=True, check=True).stdout
    assert "machine/b" in branches
    assert "main" in branches


@needs_git
def test_restore_refuses_a_populated_target(storage: Path, tmp_path: Path,
                                            bare_remote: Path):
    """Panic plus overwrite is how the copy you were recovering replaces what you had."""
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    repository = repo.Repository(staged, remote=str(bare_remote))
    repository.ensure()
    repository.commit("snapshot")
    repository.push(machine="laptop")

    clone_at = tmp_path / "clone"
    repo.Repository(clone_at, remote=str(bare_remote)).clone()

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "already_here.md").write_text("do not lose me", encoding="utf-8")
    with pytest.raises(errors.RestoreTargetNotEmpty):
        snapshot.restore(clone_at, occupied)
    assert (occupied / "already_here.md").read_text(encoding="utf-8") == "do not lose me"


@needs_git
def test_a_repository_edited_by_hand_cannot_smuggle_a_render_into_a_restore(
    storage: Path, tmp_path: Path, bare_remote: Path
):
    """A repository is writable by anyone with push access, including a future version of
    this app with a wider manifest. So the restore re-checks rather than trusting the
    snapshot's claim about its own contents."""
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    (staged / "storage" / "sneaky.mp4").write_bytes(b"\x00" * 32)
    (staged / "storage" / ".env").write_text("FORGECAST_ENCRYPTION_KEY=leak", encoding="utf-8")
    repository = repo.Repository(staged, remote=str(bare_remote))
    repository.ensure()
    repository.commit("hand-edited")

    restored_into = tmp_path / "restored"
    result = snapshot.restore(staged, restored_into)
    assert not (restored_into / "sneaky.mp4").exists()
    assert not (restored_into / ".env").exists()
    assert "sneaky.mp4" not in result.files


@needs_git
def test_a_newer_snapshot_restores_files_but_not_rows(storage: Path, tmp_path: Path):
    """Refusing part of the job beats silently dropping fields.

    A newer schema can hold things this version would discard, so the text is written and
    the rows are not — and the note says which.
    """
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={"runs": []}, machine="laptop")
    header = json.loads((staged / "snapshot.json").read_text(encoding="utf-8"))
    header["schema"] = snapshot.SCHEMA + 5
    (staged / "snapshot.json").write_text(json.dumps(header), encoding="utf-8")

    result = snapshot.restore(staged, tmp_path / "restored")
    assert result.files, "the files still restore"
    assert result.rows_applied is False
    assert "newer" in result.note.lower()


@needs_git
def test_the_token_is_never_written_into_the_repository(storage: Path, tmp_path: Path,
                                                       bare_remote: Path):
    """Not in `.git/config`, not in the remote URL, not anywhere in the tree.

    A token in a remote URL ends up in `git remote -v`, in every error message git prints
    about that remote, and therefore in the log somebody pastes into a chat.
    """
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    repository = repo.Repository(staged, remote=str(bare_remote), token="gho_secret_token")
    repository.ensure()
    repository.commit("snapshot")
    repository.push(machine="laptop")

    config_text = (staged / ".git" / "config").read_text(encoding="utf-8")
    assert "gho_secret_token" not in config_text
    assert repo.TOKEN_ENV in repo.CREDENTIAL_HELPER, (
        "the helper must read the token from the environment, not carry it"
    )
    assert "gho_secret_token" not in repo.CREDENTIAL_HELPER


@needs_git
def test_git_cannot_prompt(tmp_path: Path):
    """A backup that hangs is diagnosed as a hung application, not as a bad credential."""
    environment = repo._environment("t")
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null" or "null" in \
        environment["GIT_CONFIG_GLOBAL"].lower()
    assert repo._environment("")["GIT_AUTHOR_NAME"] == "Forgecast"
    assert repo.TOKEN_ENV not in repo._environment("")


@needs_git
def test_the_repository_size_check_reads_the_history_not_the_checkout(storage: Path,
                                                                     tmp_path: Path):
    """A 4 MB working tree can have 3 GB of objects behind it — which is the exact failure
    this whole design avoids, so the number measured has to be the history's."""
    staged = tmp_path / "staged"
    snapshot.build(staged, storage_dir=storage, rows={}, machine="laptop")
    repository = repo.Repository(staged)
    repository.ensure()
    repository.commit("snapshot")
    assert repository.size_bytes() > 0
    repository.check_size()  # nowhere near 1 GB
    with pytest.raises(errors.RepositoryTooBig):
        repository.check_size(limit_bytes=1)


# ----------------------------------------------------------------- classifying failures


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("fatal: unable to access ...: Could not resolve host: github.com", errors.Offline),
        ("fatal: Failed to connect to github.com port 443", errors.Offline),
        ("remote: Invalid username or password.\nfatal: Authentication failed",
         errors.TokenRejected),
        ("remote: Repository not found.", errors.TokenRejected),
        ("! [rejected] main -> main (non-fast-forward)", errors.Diverged),
        ("hint: Updates were rejected because the remote contains work", errors.Diverged),
        ("remote: error: GH001: Large files detected.", errors.PushRejectedTooLarge),
        ("remote: error: This repository is over its data quota.", errors.RepositoryTooBig),
        ("fatal: something nobody has seen before", errors.RemoteFailed),
    ],
)
def test_git_failures_become_states_with_sentences(stderr: str, expected: type):
    """Git returns 128 for a DNS failure, a rejected password and a missing repository
    alike, so the only signal is the message text. The fallback still carries a sentence:
    an unrecognised git error must not escape into a request handler as a
    `CalledProcessError`."""
    classified = repo._classify(["push"], stderr, 128)
    assert isinstance(classified, expected)
    assert classified.sentence


def test_every_failure_state_has_a_sentence():
    """Exhaustive over the module, so a new state added without one fails the suite."""
    states = [
        value for name, value in vars(errors).items()
        if isinstance(value, type) and issubclass(value, errors.CloudError)
        and value is not errors.CloudError
    ]
    assert len(states) >= 15
    for state in states:
        assert state.sentence, state.__name__
        assert state.sentence != errors.CloudError.sentence, (
            f"{state.__name__} did not say anything specific"
        )
        assert state.sentence[0].isupper() and state.sentence.rstrip().endswith(
            (".", "?")), state.__name__


def test_the_file_too_large_sentence_names_the_file():
    error = errors.FileTooLarge("runs/12/huge.json", 40 * 1024 * 1024)
    assert "runs/12/huge.json" in error.sentence
    assert "40.0 MB" in error.sentence
    assert error.as_dict()["state"] == "FileTooLarge"


# ------------------------------------------------------------------------- device flow


def _transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url="https://github.com")


def test_a_build_with_no_client_id_says_so_instead_of_showing_a_code(monkeypatch):
    """`NotConfigured` and `NotAuthorised` are separate because only one of them is
    something the operator can act on."""
    with pytest.raises(errors.NotConfigured):
        device.client_id("")


def test_request_code_returns_what_the_operator_is_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/login/device/code"
        assert request.headers["Accept"] == "application/json"
        body = request.content.decode()
        assert "client_id=Iv1.test" in body
        assert "scope=repo" in body
        return httpx.Response(200, json={
            "device_code": "d" * 40, "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900, "interval": 5,
        })

    with _transport(handler) as client:
        code = device.request_code(override_client_id="Iv1.test", client=client)
    assert code.user_code == "WDJB-MJHT"
    assert "WDJB-MJHT" in code.sentence()
    assert "15 minutes" in code.sentence()
    assert "device_code" not in code.public_dict(), (
        "the redemption code belongs on the server, not in a browser"
    )


def test_device_flow_sends_no_client_secret():
    """The property that makes this the only flow suitable for an app that ships as a zip."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, json={"access_token": "gho_ok"})

    with _transport(handler) as client:
        assert device.poll_once("d" * 40, override_client_id="Iv1.test",
                                client=client) == "gho_ok"
    assert seen and "client_secret" not in seen[0]
    assert "grant_type=urn" in seen[0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("authorization_pending", errors.AuthorisationPending),
        ("slow_down", errors.AuthorisationPending),
        ("expired_token", errors.CodeExpired),
        ("access_denied", errors.Declined),
        ("incorrect_device_code", errors.RemoteFailed),
    ],
)
def test_every_device_flow_error_becomes_a_state(error: str, expected: type):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": error, "interval": 10})

    with _transport(handler) as client, pytest.raises(expected):
        device.poll_once("d" * 40, override_client_id="Iv1.test", client=client)


def test_slow_down_carries_the_new_interval():
    """Reported as pending rather than as its own type: the caller's job is still to wait,
    only slower, and two exception types for one instruction get handled as two cases."""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "slow_down", "interval": 15})

    with _transport(handler) as client:
        try:
            device.poll_once("d" * 40, override_client_id="Iv1.test", client=client)
        except errors.AuthorisationPending as pending:
            assert getattr(pending, "retry_after", 0) == 15
        else:  # pragma: no cover
            pytest.fail("slow_down should raise AuthorisationPending")


def test_a_form_encoded_reply_is_a_failure_not_an_infinite_poll():
    """Without `Accept: application/json` GitHub answers with a url-encoded body, which a
    JSON caller reads as empty — and empty looks exactly like "not authorised yet"."""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="access_token=gho_x&token_type=bearer",
                              headers={"content-type": "application/x-www-form-urlencoded"})

    with _transport(handler) as client, pytest.raises(errors.RemoteFailed):
        device.poll_once("d" * 40, override_client_id="Iv1.test", client=client)


def test_an_unreachable_github_is_offline_not_a_crash():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with _transport(handler) as client, pytest.raises(errors.Offline):
        device.request_code(override_client_id="Iv1.test", client=client)


def test_a_rejected_token_is_reported_as_needing_reauthorisation():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
            pytest.raises(errors.TokenRejected):
        device.whoami("gho_revoked", client=client)


def test_the_backup_repository_is_created_private():
    """So the operator never has to create one, and never has to notice it is private."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={"full_name": "someone/forgecast-backup",
                                         "private": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        created = device.create_repository("gho_ok", "forgecast-backup", client=client)
    assert created["private"] is True
    assert seen[0]["private"] is True
    assert seen[0]["auto_init"] is False, (
        "a remote with a commit on it turns the first push into a divergence"
    )


def test_a_name_clash_explains_itself_rather_than_retrying():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text='{"message": "name already exists"}')

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
            pytest.raises(errors.RemoteFailed) as caught:
        device.create_repository("gho_ok", "forgecast-backup", client=client)
    assert "already exists" in caught.value.sentence


# ------------------------------------------------------------------- the package surface


def test_nothing_in_the_app_imports_cloud_while_it_is_off():
    """The strongest available form of "the local path is untouched when it is off".

    Not a flag checked in twenty places — no call site at all. The day this feature is
    wired into the pipeline this test changes deliberately, which is the point: it makes
    the wiring a visible decision rather than a diff nobody noticed.
    """
    import subprocess as sp

    root = Path(__file__).resolve().parents[1]
    # Import statements only. A prose mention of the module in a comment is not a call
    # site, and a test that cannot tell the difference is a test somebody deletes.
    found = sp.run(
        ["grep", "-rnE", "--include=*.py",
         r"^[[:space:]]*(from[[:space:]]+[.a-zA-Z_]*cloud|import[[:space:]]+.*cloud)",
         str(root / "forgecast")],
        capture_output=True, text=True,
    ).stdout.strip().splitlines()
    outside = [line for line in found if "/forgecast/cloud/" not in line]
    assert outside == [], f"cloud is imported by the app: {outside}"


def test_the_staging_tree_is_never_inside_storage():
    """A `.git` directory inside the tree the pipeline writes into means a checkout can
    rewrite a file mid-render — a corruption invisible from both sides."""
    import forgecast.cloud as cloud
    from forgecast.config import get_settings

    staging = cloud.staging_dir().resolve()
    storage = get_settings().storage_dir.resolve()
    assert not staging.is_relative_to(storage)


def test_status_needs_no_network_and_leaks_nothing():
    import forgecast.cloud as cloud

    payload = cloud.status()
    assert payload["enabled"] is False
    assert payload["active"] is False
    assert "token" not in payload
    assert cloud.enabled() is False
