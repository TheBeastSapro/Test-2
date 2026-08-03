# Cloud backup, on GitHub — the plan

This is the design for making a Forgecast install's work survive the machine it runs on,
by mirroring it into a private GitHub repository. It is written before the feature to
settle the decisions that are expensive to change later — chiefly what does *not* go in
the repository, because that is the decision a naive version gets wrong and cannot undo.

It is **off by default**. An install that never enables it never opens a socket to
GitHub, never grows a `.git` directory inside `storage/`, and behaves exactly as it does
today. That is not a courtesy; it is the property that makes the feature safe to ship.

---

## The split, and why there is one

**Your work syncs. Your renders do not.**

| Kind | Written by | Realistic size | Goes to GitHub |
| --- | --- | --- | --- |
| Brief JSON + markdown | `nodes/research.py:43,50` | 1–20 KB | yes |
| Script JSON + markdown | `nodes/content.py:74,113,117` | 5–60 KB | yes |
| Shot list | `nodes/media.py:385` | 2–30 KB | yes |
| Captions (`.srt`) | `nodes/finalize.py:122` | 2–20 KB | yes |
| Publish record | `nodes/finalize.py:222` | < 5 KB | yes |
| Learned editing styles | `style/editing.py:141` → `storage/styles/*.json` | 5–80 KB each | yes |
| Skills | `skills.py:199` → `storage/skills/*.md` | 1–15 KB each | yes |
| Agent prefs | `agent/prefs.py:38` → `storage/agent_prefs.json` | ~100 B | yes |
| Voice catalogue (curated) | `voice/catalogue.py` → `storage/voice_catalogue.json` | 33 KB observed | yes |
| Database rows, as JSON | this feature | 50 KB – 5 MB | yes |
| — | | | |
| Final render | `nodes/finalize.py:78` → `runs/<id>/final.mp4` | 15–40 MB for 60s; 150 MB–2 GB long-form | **no** |
| Generated shot clips | `nodes/media.py:513` → `shot_NNN_clip.mp4` | 2–10 MB × 20–80 per run | **no** |
| Stills and plates | `nodes/media.py:459,104` | 0.5–2 MB × 20–80 per run | **no** |
| Voice takes | `providers/media.py:204` → `.mp3` | ~1 MB per minute, several takes | **no** |
| Avatar render | `nodes/media.py:576` | 20–200 MB | **no** |
| Full voice catalogue | `voice/discover.py` → `voice_catalogue_all.json` | 967 KB observed | **no** — regenerated from ElevenLabs |
| `forgecast.db` and its `-wal`/`-shm` sidecars | `db.py:31` | 160 KB observed, grows | **no** — exported as rows instead |
| `.env`, encryption key | the installer | — | **never** |
| `storage/connectors.json` | `agent/connectors.py:326` | < 4 KB | **never** — see below |
| `attachments/`, `runtime/` | chat, toolchain | MB to GB | **no** |

### The sentence the operator is shown

> Forgecast backs up the work, not the renders. Scripts, briefs, research, shot lists,
> captions, learned styles, skills and the record of every run go to a private GitHub
> repository you own. The finished videos, voice takes and stills stay on this machine:
> GitHub refuses any file over 100 MB, and a repository that collects renders never gets
> smaller again, so putting them there would break the backup within weeks in a way that
> cannot be fixed without destroying its history. What is backed up is everything that
> took thinking. The renders are made again from it.

That sentence is shown at the moment the operator turns it on, not buried in a document,
because the surprise it prevents is "I turned on backup and my videos are not in it".

### Why not just commit the video

Because it works for three weeks and then stops working permanently.

* **GitHub blocks files larger than 100 MiB**, and warns from 50 MiB
  ([About large files on GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)).
  A ten-minute 1080p render clears both.
* The same page: *"We recommend repositories remain small, ideally less than 1 GB, and
  less than 5 GB is strongly recommended."* Twenty long-form runs pass 1 GB.
* Git keeps every version of every blob forever. Deleting `final.mp4` in a later commit
  does not shrink the repository — the object is still in the history, still cloned, and
  removing it means rewriting history, which invalidates every other machine's clone.
  A backup that has to be rewritten is not a backup.
* **Git LFS does not rescue it.** Free and Pro include *10 GB* of LFS storage and *10 GB*
  of bandwidth per month ([product usage included](https://docs.github.com/en/billing/reference/product-usage-included));
  with a $0 budget, *"You are not charged for overages, but Git LFS usage is blocked for
  the rest of the calendar month"*
  ([Git LFS billing](https://docs.github.com/billing/managing-billing-for-git-large-file-storage/about-billing-for-git-large-file-storage)).
  Blocked LFS means `git clone` cannot get the files — so the failure lands on the
  restore, which is the one moment the operator has no alternative. Per-file caps are
  2 GB on Free and Pro, 4 GB on Team, 5 GB on Enterprise Cloud
  ([About Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)).

### Where the renders could go later, and why not now

Releases are the one GitHub blob store that does not touch repository size:
`POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets`
with `Authorization: Bearer`, the asset as raw body
([Release assets REST API](https://docs.github.com/en/rest/releases/assets)). The docs
note that releases do not limit total binary size or bandwidth, but each file must be
under the LFS per-file cap for the plan. So a single `final.mp4` per run is a legitimate
release asset, and *that* is the eventual home for the finished video.

It is deferred rather than dismissed because it is a second, independent mechanism —
different endpoint, different failure modes, different quota, and an upload that has to
resume — and shipping it alongside the git path would mean two half-tested transports
instead of one that works. The plan is: git for the work now, release assets for
`final.mp4` next, and the split above stays true either way because the intermediate
clips and plates are never worth uploading.

---

## Authorisation: the operator types no token

We already know what happens when this app asks for a credential the operator has never
been shown. `agent/connectors.py:88-96` records it: being asked for a URL you have never
seen is being asked for something that does not exist from where you are standing. A
GitHub personal access token is worse — it is a form with nine checkboxes on a page the
operator has to be told how to find, and the failure mode of picking the wrong checkbox
is a 403 twenty minutes later.

So: **OAuth device flow**. Forgecast shows an eight-character code, the operator opens
`https://github.com/login/device`, types it, and clicks approve. No token is ever seen,
copied or pasted.

### The exact flow

1. `POST https://github.com/login/device/code` with `client_id` and `scope`, and
   `Accept: application/json`. Response: `device_code` (40 chars), `user_code`
   (8 chars with a hyphen), `verification_uri` (`https://github.com/login/device`),
   `expires_in` (900 s), `interval` (minimum seconds between polls).
2. Show `user_code` and `verification_uri`. Offer to open the browser; do not require it,
   because the operator may be authorising from their phone.
3. `POST https://github.com/login/oauth/access_token` with `client_id`, `device_code`,
   and `grant_type=urn:ietf:params:oauth:grant-type:device_code`, polled at `interval`.
   Errors: `authorization_pending` (keep waiting), `slow_down` (*"5 extra seconds are
   added to the minimum interval"*), `expired_token` (the 15 minutes ran out),
   `access_denied` (the operator declined).

Source: [Authorizing OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).

**There is no `client_secret` in step 3.** That is the property that makes this the right
choice for an app that ships as a zip: the only GitHub credential inside the archive is a
public client ID, which is not a secret and cannot be used to impersonate anything. A
web-redirect flow would need a client secret in the archive, and shipping one to every
operator would mean every operator holds the key to every other operator's OAuth app.

### Scope

`repo`. Not because it is comfortable — it is *"full access to public and private
repositories"* — but because it is the floor:
[Scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
has no narrower scope with private write, and
[Create a repository for the authenticated user](https://docs.github.com/en/rest/repos/repos)
states *"OAuth app tokens and personal access tokens (classic) need the public_repo or
repo scope to create a public repository, and repo scope to create a private
repository."* `POST /user/repos` with `private: true` is how the backup repository is
created, so the app never asks the operator to create one.

The honest cost of `repo` is stated at the consent screen: the token can read and write
every repository on the account. The mitigation is that Forgecast only ever addresses the
one repository it created, and the operator can revoke the authorisation from GitHub
settings at any time, which is a page they can find.

### OAuth app or GitHub App?

Both support device flow — *"If your app does not have access to a web interface, you
should use device flow instead"*
([Login with GitHub button with a GitHub App](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-login-with-github-button-with-a-github-app)).
We use an **OAuth app**, for two reasons:

* A GitHub App must be *installed* on the account before its user token can touch a
  repository, which is a second consent step on a second page — and the repository does
  not exist yet at that point, so the operator is being asked to install an app onto a
  thing that has not been created.
* GitHub App user tokens *"expire after eight hours"* unless expiration is opted out of,
  with a refresh token to rotate. That is correct security and wrong ergonomics for a
  desktop app that may sit closed for a fortnight; an OAuth app token stays valid until
  revoked, so the operator authorises once.

**Registered in advance, by us, once:** an OAuth app on the Forgecast account, with
*Enable Device Flow* ticked — the docs are explicit that device flow *"must first be
enabled in your app's settings"*. Its client ID is compiled into the app as
`FORGECAST_GITHUB_CLIENT_ID`, overridable so an operator who prefers their own OAuth app
can use it. Until a client ID is set, the feature reports that it is not configured
rather than showing a device code that cannot work.

### The token over git

Git speaks HTTPS with the token in place of a password
([Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)).
It is passed per-invocation through an `askpass` helper, never written into
`.git/config`, never into a remote URL, and never into a log line — a token in a remote
URL ends up in `git remote -v`, in error messages, and in the crash report someone
pastes into a chat.

### If device flow is unachievable

It is achievable, so this is the fallback rather than the plan: a **fine-grained personal
access token** scoped to the single backup repository with `Contents: write`. Fine-grained
tokens *"can be further limited to only access specific repositories"* and `Contents`
write is what push needs. It is strictly better security and strictly worse ergonomics —
the operator must create the repository first, then the token, then paste it — so it is
offered as the alternative for someone who refuses `repo`, not as the default.

---

## Failure states, each with the sentence

Every one of these is a state the app can be in, not an exception message. The rule is
that the sentence names what happened, what is safe, and what to do — in that order.

| State | Sentence |
| --- | --- |
| Feature never enabled | *Cloud backup is off. Everything is on this machine only.* |
| No client ID configured | *This build has no GitHub app configured, so backup cannot authorise. Set FORGECAST_GITHUB_CLIENT_ID, or paste a fine-grained token for the repository instead.* |
| No network | *Could not reach GitHub. Nothing was lost — the snapshot is on disk and will go up on the next attempt.* |
| Not authorised yet | *Backup is not authorised. Open github.com/login/device and enter the code shown to connect it.* |
| Device code expired | *That code expired after 15 minutes. Here is a new one.* |
| Operator declined | *You declined the authorisation on GitHub. Backup stays off; nothing changed.* |
| Token expired or revoked | *GitHub rejected the stored authorisation — it was revoked or expired. Re-authorise and the backup resumes from where it stopped; nothing on this machine was touched.* |
| Repository near the size limit | *The backup repository is past 1 GB, which GitHub warns about. Something large is being included that should not be — run the size report before it becomes unpushable.* |
| A file too large for the manifest | *`<name>` is `<size>`, over the 25 MB cap for a backed-up file, so it was left out of this snapshot and everything else went up. Renders are never included; if this is not a render, it belongs on the exclude list.* |
| Push rejected for a large file | *GitHub refused the push because one file is over its 100 MB limit. The snapshot is unchanged on disk and nothing was lost; this is a bug in the manifest, not in your work.* |
| Conflict with a second machine | *Another machine backed up since this one last did. Both snapshots are kept — this one is on the branch `machine/<id>` — because guessing which is newer is how a merge loses an afternoon.* |
| Restore onto a newer app version | *This backup was written by Forgecast `<x>`; you are running `<y>`, which is older. Files were restored; the row export was not applied because a newer schema can hold fields this version would drop. Update Forgecast and restore again.* |
| Restore onto an older backup | *This backup was written by Forgecast `<x>`; you are running `<y>`. It restores, and anything the newer version added will be missing rather than wrong.* |
| Git not installed | *Backup needs git and this machine does not have it. Everything else in Forgecast works without it.* |
| Nothing to back up | *Nothing has changed since the last backup, so nothing was sent.* |

Two of these are load-bearing and worth naming as decisions rather than as messages:

**The conflict never merges automatically.** Two machines editing the same script produce
two truths and git cannot pick. A second machine's push that is not a fast-forward goes
to `machine/<id>` and the operator is told both exist. A silent `--force` would be the
last thing that ever went wrong in this feature, once.

**A failed push never destroys the staged snapshot.** Every failure above leaves the
staging tree on disk with a note, so "the backup failed" is recoverable by retrying
rather than by re-doing the work.

---

## Turning it on for the first time, on months of work

The first snapshot is the only one that is not incremental, and it has to be honest about
that before it starts. The sequence:

1. **Count first, upload nothing.** Walk `storage/`, apply the manifest, and report: how
   many files would sync, their total size, how many were excluded and why, and the ten
   largest exclusions by name. This is a dry run and it is always run — the first
   snapshot is never the first time the operator learns what the manifest does.
2. **Refuse loudly on a surprise.** If the syncable set is over 200 MB or 20,000 files,
   stop and say so. That is not a limit GitHub imposes; it is the threshold where
   something is being included that should not be, and finding out now is much cheaper
   than finding out on push three.
3. **One initial commit, not one per run.** Months of history in git-shaped increments is
   fiction — the commit dates would be today either way. The first commit says
   `initial snapshot: N runs, M files`, and the honest history starts from there.
4. **The database export is part of that commit**, so the first snapshot is restorable on
   its own rather than only in combination with a local database.

---

## Turning it off

Switching it off must never make work unreachable. Concretely, off means:

* The `enabled` flag in `storage/cloud.json` goes false. Nothing is deleted — not the
  staging tree, not the stored authorisation, not the remote.
* **The GitHub repository is not touched.** It stays in the operator's account, private,
  complete, and readable in a browser without Forgecast. This is the property that makes
  the whole design defensible: the backup is plain JSON, markdown and `.srt` in a
  directory tree, so its value does not depend on this app existing.
* The local `storage/` tree is not touched either. Turning off backup is not a delete.
* The message says where things are: *Backup is off. Your work is still on this machine,
  and the last snapshot is still in `github.com/<owner>/<repo>` — nothing was removed.*
* Revoking is separate and named separately, because "stop syncing" and "forget my GitHub
  authorisation" are different intentions and conflating them means one of them is a
  surprise.

---

## Restore is the feature

A backup nobody has restored is a folder of hope. So the restore path is built first and
exercised on every test run, against a real git remote, with no GitHub account involved.

`restore(remote, into)` clones the repository into a temporary directory, reads
`snapshot.json`, checks the schema version, and materialises the text tree into a target
storage directory — **never over the top of a populated one.** A restore writes into an
empty target, or into a named subdirectory of a populated one, and reports what it wrote.
Restore that clobbers is a data-loss feature with a reassuring name.

What restore gives back today: every script, brief, research note, shot list, caption
file, learned style, skill, the agent prefs, and the row export as readable JSON —
enough to see every run that ever happened and re-render any of them.

What it does not yet do: insert those rows back into a live database. That is left out on
purpose. Re-importing rows into a database that may already hold work is a merge with ID
remapping, not a copy, and getting it wrong loses the runs that were already there. It
ships when it can be tested against a populated database, which is a different piece of
work from the transport — and the transport is what has to be right first, because a
restore that cannot fetch the files is not improved by having somewhere to put them.

---

## What is enforced, not intended

The secret rules are asserted by code and by tests, in the same shape as
`tools/package.py`. That script has one exclusion rule set, `EXCLUDE`, used twice — to
filter what it collects and to assert what ended up in the archive — and its docstring
records why: the last leak of that class happened because two lists disagreed, `.gitignore`
naming `*.db` but not `*.db-wal`. This feature copies that shape exactly rather than
inventing a second one.

* **One rule set.** `forgecast/cloud/manifest.py` holds `DENY` — every pattern from
  `package.EXCLUDE`'s secrets and state sections, plus every media extension. It is used
  to filter the snapshot *and* to assert the finished snapshot, and a test walks the built
  tree through the same rule set the builder used. A file nobody has thought of yet is
  caught because it matches a pattern.
* **Allow-list on top of deny-list.** Only known-good extensions are eligible at all:
  `.md`, `.json`, `.jsonl`, `.srt`, `.vtt`, `.txt`, `.csv`. Anything else is excluded
  whether or not a deny pattern names it, so a new binary artifact kind defaults to
  *excluded* rather than to *committed*.
* **Two independent reasons `.env` cannot reach the repository.** It is outside
  `storage/`, which is the only tree the snapshot walks; and `.env`, `.env.*` and `*.env`
  are in `DENY`, so a copy that ends up inside `storage/` is still refused. The
  encryption key exists only inside `.env`, so the same two reasons cover it.
* **A size cap, checked per file.** 25 MB, well under GitHub's 50 MB warning, so the
  warning is never the thing that discovers a mistake.
* **The stored GitHub token is ciphertext**, `crypto.encrypt`, keyed from
  `FORGECAST_ENCRYPTION_KEY` in `.env` — the same envelope as provider keys and
  connector tokens. Which means the token cannot be restored from a backup onto another
  machine, and that is correct: a credential that travels with a backup is a credential
  that leaks with the backup.
* **`storage/connectors.json` is excluded by name**, even though it is small JSON, because
  it holds encrypted service tokens. Committing ciphertext whose key is on one machine is
  a liability with no benefit — it cannot be decrypted after a restore anyway.
* **The database file never syncs.** `*.db`, `*.db-*`, `*.sqlite*` are in `DENY` for the
  reason `package.py` gives: the `-wal` and `-shm` sidecars hold database pages, so
  shipping one ships rows. Rows travel as an export with secret columns dropped —
  `hashed_password`, `ciphertext`, `youtube_credentials` — by column name, and a test
  asserts no exported value round-trips through `crypto.decrypt`.
* **The token never reaches git's own storage.** It is handed to git through a credential
  helper that reads an environment variable, so `.git/config` and `git remote -v` never
  contain it and neither does `ps`. `https://<token>@github.com/...` is the obvious
  approach and it puts the credential in the text of every error message git prints about
  that remote — which is the log somebody pastes into a chat when asking why backup broke.
* **The staging tree cannot be shipped or committed.** `.forgecast-cloud` and
  `.forgecast-restore` are added to `package.EXCLUDE` and to `.gitignore`. They are a git
  working copy of one install's scripts sitting beside `storage/`, and a nested `.git`
  inside a tracked tree is its own kind of mess. `package.EXCLUDE` was extended, never
  narrowed — `test_packaging.test_every_pattern_is_enforced` materialises every pattern in
  it and requires the check to refuse the result, so the additions carry their own proof.

### And two things the tests assert that the code cannot

* **`test_nothing_in_the_app_imports_cloud_while_it_is_off`** greps the whole `forgecast/`
  tree for an import of this package and requires none. That is the real content of "the
  local path is untouched when it is off": not a flag checked in twenty places, but no call
  site at all. The day this is wired into the pipeline that test changes deliberately,
  which makes the wiring a decision somebody made rather than a diff nobody noticed.
* **`test_the_staging_tree_is_never_inside_storage`** asserts the git working copy is not
  under `storage_dir`. A `.git` directory inside the tree the render pipeline writes into
  means a checkout can rewrite a file mid-render, and that is a corruption invisible from
  both sides.

---

## Layout

```
forgecast/cloud/
  __init__.py     the surface: enabled(), dry_run(), backup(), restore(), status()
  errors.py       every failure state, each carrying its operator sentence
  config.py       storage/cloud.json — enabled flag off, remote, encrypted token
  manifest.py     the one rule set: ALLOW_SUFFIX, DENY, MAX_FILE_BYTES
  snapshot.py     stage the syncable tree + snapshot.json + the row export
  repo.py         git over subprocess: ensure, commit, push, clone, size
  device.py       the GitHub device flow
tests/test_cloud.py   62 tests, including a real push/clone/restore round trip
```

Nothing else in the app imports it while the flag is off, which is why the local path
cannot change when the feature is not in use: there is no call site to change it.

## Built, and not

**Built and tested.** The manifest and its audit; the config store with the token
encrypted; the snapshot builder including the database row export with secret columns
dropped; the git transport with every failure classified into a state with a sentence; the
restore path; the device flow including every documented error. The push/clone/restore round
trip runs against a real bare git repository in a temporary directory on every test run —
no GitHub account, no network, no fixtures pretending to be git.

**Deliberately not built.** Loading the row export back into a live database (a merge with
ID remapping, not a copy — the reason is above). Release assets as the home for
`final.mp4`. The settings page and the API routes that drive the device flow from a browser.
A schedule, so backup happens without being asked. Git LFS, which the limits above rule out
for this use.

**The one untested path.** The credential helper. A local bare repository needs no
credential, so the round trip exercises every git operation but not the authentication in
front of it. That is stated rather than papered over: the first real push to GitHub is where
the helper is proven, and `TokenRejected` is the state it fails into.
