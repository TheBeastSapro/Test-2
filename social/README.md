# Full Twitter (X) + Reddit access for the agent

## First: nothing was previously installed

If you remember being asked about cookies in an earlier session, there is no
half-finished install waiting for them. Verified in this container:

| Checked | Result |
|---|---|
| `mcpServers` for this project (`~/.claude.json`) | `{}` — empty |
| Connectors on the account | Epidemic Sound, Gmail, Google Calendar, Google Drive, Idea Phantom, NexLev, vidIQ, Windsor.ai — **no X, no Reddit** |
| Python packages (praw, tweepy, snscrape, twscrape) | none installed |
| Cookie files / cookie jars on disk | none except Python's stdlib `http/cookies.py` |
| Only "cookie" reference anywhere | `~/.claude/skills/analyse/references/visual-engine.md:92` |

That one reference is about **video downloading**, not API access. It says
YouTube returns HTTP 403 to datacenter IPs, so acquisition needs "residential
egress, or supply cookies." If a past session asked you for cookies, that was
almost certainly this — the media-download path in the `analyse` skill.

Also worth knowing: **this container is wiped between sessions.** It was created
fresh, and `~/.claude/projects/` holds exactly one session. Anything not
committed to git is gone. So a tool installed in a past session would not
survive to this one regardless — which is why the setup below lives in the repo.

## Why cookies are the wrong tool here

Cookies were never needed for what you actually want. Measured from this
container just now:

```
reddit.com/r/*/top.json   (anonymous)  -> 403   blocked, datacenter IP
reddit.com/api/v1/access_token         -> 401   reachable, wants credentials
api.x.com/2/tweets                     -> 401   reachable, wants credentials
```

Both official API endpoints are reachable. The blocker is credentials, not the
network — and the proper credential path is better than cookies on every axis:

- **Reddit needs no cookies at all.** A free "script" app gives an OAuth token
  that works fine from this IP. Two minutes to set up, no account password
  required for public reads.
- **X session cookies are fragile here.** X binds sessions to IP and device
  fingerprint, and this container's egress IP changes every session — an
  exported cookie will typically get challenged or invalidated on first use.
- **Cookie scraping of X violates its Terms of Service** and risks your account
  being locked or banned. Your call to make, but make it knowing that.
- **A session cookie is full account access** — it bypasses your password and
  2FA entirely. An API token is scoped and revocable.

So: API credentials for both. Cookies stay available for one narrow legitimate
job (downloading media you can already watch), documented at the bottom.

## Setup

```bash
cd /home/user/Test-2
cp .env.example .env
chmod 600 .env
# edit .env, then:
python3 social/check.py
```

`check.py` reports every credential as set/unset, live-tests each one, and
prints the exact setup steps for whatever is missing.

### Reddit — free, works immediately

1. Go to <https://www.reddit.com/prefs/apps> → **create another app**
2. Type: **script**. Redirect uri: `http://localhost:8080` (required, unused)
3. `client_id` is the short string under the app name; `client_secret` is the
   `secret` field
4. In `.env`:
   ```
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   REDDIT_USER_AGENT=linux:sapro-agent:0.1 (by /u/yourname)
   ```
   `REDDIT_USER_AGENT` is not optional — Reddit rejects generic agents.

That gives public read access. To also reach *your* account (saved posts, votes,
inbox, submitting), add `REDDIT_USERNAME` and `REDDIT_PASSWORD`. The password
grant fails if 2FA is on; send the password as `password:123456` with a current
OTP if you need it.

### X / Twitter — read access depends on your tier

1. <https://developer.x.com> → create a project + app
2. **Keys and tokens** → copy the **Bearer Token** → `X_BEARER_TOKEN` in `.env`
3. For posting as your account, set the app to **Read and Write**, generate an
   Access Token + Secret, and fill in all four of `X_API_KEY`, `X_API_SECRET`,
   `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`

**Be prepared for tier limits.** The free tier is mainly write access plus a
very small read quota; recent-search and user-timeline reads generally require a
paid tier. A `403` mentioning `client-not-enrolled` is a billing state, not a
broken script — `x.py` says so explicitly when it sees one. Check current quotas
and pricing at <https://developer.x.com/en/portal/products> before paying.

## Usage

```bash
# Reddit
python3 social/reddit.py whoami
python3 social/reddit.py top youtube --limit 10 --time week
python3 social/reddit.py hot NewTubers --limit 5
python3 social/reddit.py search "faceless channel" --subreddit NewTubers
python3 social/reddit.py comments <post_id>
python3 social/reddit.py saved                 # needs username+password

# X
python3 social/x.py user elonmusk
python3 social/x.py tweets elonmusk --limit 10
python3 social/x.py search "faceless youtube" --limit 20
python3 social/x.py tweet <tweet_id>
python3 social/x.py whoami                     # needs the 4 OAuth1 creds
python3 social/x.py post "hello"               # needs the 4 OAuth1 creds
```

Everything prints JSON, so it composes with `jq` and is easy for the agent to
read. Both modules are importable too — `import reddit; reddit.top("youtube")`.

## Secret hygiene

This matters more than usual here: **`TheBeastSapro/Test-2` is a public repo.**

- `.env` and `*cookies*` are gitignored. Do not force-add them.
- **Do not paste credentials into the chat.** The transcript is stored. Write
  them into `.env` yourself, then tell me to run `check.py`.
- The container is ephemeral, so `.env` disappears when the session ends. That
  is a feature for secrets, an annoyance for you — keep the values in your own
  password manager and re-paste per session. If you want them to persist, set
  them as environment variables on the Claude Code environment instead
  (`_env.py` never overwrites an already-exported variable).
- If a credential ever does land in a commit, treat it as burned: rotate it at
  the provider. Removing it from git history is not enough.

## Cookies, if you still want them

The one legitimate use is downloading media you already have access to, via
`yt-dlp`'s documented `--cookies` flag (already installed at
`/usr/local/bin/yt-dlp`).

1. In your browser, use a "Get cookies.txt LOCALLY" style extension to export
   **Netscape format** cookies for the site
2. Save the file **outside the repo** — e.g. the session scratchpad — or inside
   it with a `cookies` in the name so `.gitignore` catches it
3. Point `X_COOKIES_FILE` / `REDDIT_COOKIES_FILE` at it in `.env`
4. Use it:
   ```bash
   yt-dlp --cookies "$X_COOKIES_FILE" "<url>"
   ```

Expect this to be flaky from a datacenter IP — that is the platform blocking the
IP range, not a configuration mistake. If it fails, run the download on your own
machine, where residential egress and the cookie's origin IP match.
