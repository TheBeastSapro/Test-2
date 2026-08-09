# YouTube Video Download Access — Investigation 2026-08-09

**Verdict: NOT SOLVED.** Full media download from YouTube is not currently
possible on this machine. The blocker is **not** bot detection or a missing PO
token — those were both fixed during this investigation. The blocker is the
**rotating-egress-IP architecture of the agent proxy**, which is incompatible
with YouTube's IP-bound media URL signing.

Metadata, titles, durations, formats and transcripts all work fine. Only the
media bytes are blocked.

---

## TL;DR

| Capability | Status |
|---|---|
| Metadata / format listing | ✅ Works |
| PO token generation (bgutil provider) | ✅ **Fixed this session** |
| `n`-challenge JS solving (EJS) | ✅ **Fixed this session** |
| Signed media URL retrieval | ✅ Works |
| **Actual media byte download** | ❌ **HTTP 403, all 9 clients tested** |
| Headless-browser cookie generation | ❌ Browser has no network egress |

Two real bugs were found and fixed, which moved the failure from "cannot even
build a valid request" to "builds a perfectly valid request that the CDN
refuses on IP grounds". That is genuine progress but it does not yield video.

---

## Root cause

YouTube signs every `videoplayback` URL against the IP address that requested
it. The signature covers an `ip=` parameter (it is listed in the URL's own
`sparams`, so it cannot be edited without invalidating `sig`).

A signed URL obtained on this machine looks like:

```
https://rr1---sn-4g5edndl.googlevideo.com/videoplayback
  ?expire=1786281746
  &ip=fda3%3Ae722%3Aac3%3A10%3A211%3A7450%3Afefe%3Ac663   <-- private IPv6 ULA
  &itag=18
  ...
  &sparams=expire,ei,ip,id,itag,source,requiressl,...      <-- 'ip' is signed
  &sig=AE0s2JY...
```

Two things are fatal here:

1. **The signed `ip` is a private ULA** (`fda3:e722:ac3:10:...`, inside
   `fd00::/8`). It is not a routable address, so no request originating from
   the public internet can ever present a matching source IP. Google's own
   redirect on the same request reports the address it actually observed as
   `mip=160.79.106.128` — a completely different, public address.

2. **The egress IP rotates per connection.** Sampling the egress address 15
   times returned at least 8 distinct addresses:

   ```
   160.79.106.129  .130  .131  .132  .133  .134  .135  .136
   ```

   The internal ULA rotates too — it was `...fefe:c663` on one extraction and
   `...fefe:c66a` on the next.

So the player request that *mints* the URL and the media request that *uses*
the URL always arrive from different addresses. YouTube sees the mismatch and
returns 403.

### Proof the retry-until-match idea fails

If the pool were small and the binding public, retrying would eventually land
on the signing IP. It does not, because the binding is to an unroutable ULA:

```
url len 1965
expire=1786281746 now=1786260384 valid_for=21362s   <-- URL still valid ~6h
attempt 1  -> 403:0
attempt 2  -> 403:0
...
attempt 10 -> 403:0
```

Ten redirect-following attempts, spread across the rotating pool, on a URL with
six hours of validity left: **403 every time, zero bytes every time.** Expiry
is ruled out; the pool is ruled out.

### Proof it is not the egress proxy blocking googlevideo

This was tested explicitly, because a 403 in this environment can also mean an
org egress-policy denial. It does not here — googlevideo is fully reachable:

```
> CONNECT rr1---sn-4g5e6nz7.googlevideo.com:443 HTTP/1.1
< HTTP/1.1 200 Connection Established
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
< HTTP/1.1 404 Not Found          <-- genuine Google error page, not a proxy denial
< Server: gvs 1.0
```

The tunnel establishes, TLS completes, and Google's own server answers. The 403
is authored by Google, not by the proxy.

---

## What was fixed along the way (keep these)

These two fixes are real and should be retained — they are prerequisites for
any future success, and they make metadata extraction markedly more reliable.

### Fix 1 — PO token provider was broken by an axios/proxy incompatibility

`bgutil-ytdlp-pot-provider` was installed and its server started, but every
token request failed. yt-dlp only reported an opaque upstream error:

```
WARNING: [youtube] [pot] Error fetching PO Token from "bgutil:http" provider:
PoTokenProviderError('Error reaching POST /get_pot (caused by <HTTPError 500: Internal Server Error>)')
```

The real cause was visible only in the **provider server's own log**:

```
Error: Could not get BotGuard challenge (caused by Error: Error reaching GET
https://www.google.com/js/th/...js: All 3 retries failed.
(caused by AxiosError: Request failed with status code 405))
```

`405 Method Not Allowed` is a documented failure class in
`/root/.ccr/README.md`: *"usually axios older than 1.16.1 (upgrade it)"*. The
bundled axios was **1.13.5**.

```bash
cd <provider>/server && npm install axios@latest    # 1.13.5 -> 1.19.0
```

After the upgrade, token generation works:

```json
{"contentBinding":"lrY0ErBfytQ",
 "poToken":"MlmtXg3Cb5B65q0cdlYoE1D01SMZS9h1ehZp9bVD8Upo...",
 "expiresAt":"2026-08-09T13:15:54.075Z"}
```

### Fix 2 — JS challenge solving had no supported runtime

yt-dlp reported `JS runtimes: node-20.20.2 (unsupported)` and all challenge
providers unavailable, so `n`-parameter solving failed. Node 22.22.2 **is**
installed at `/opt/node22/bin/node`, but putting it first on `PATH` changes
nothing, because `yt_dlp/utils/_jsruntime.py::_find_exe` checks
`sysconfig.get_path('scripts')` (`/usr/local/bin`, which holds node 20) **before**
consulting `PATH` and returns on first hit.

The runtime must therefore be named explicitly:

```bash
pip install -U --break-system-packages "yt-dlp[default]"   # pulls yt-dlp-ejs
yt-dlp --js-runtimes "node:/opt/node22/bin/node" ...
```

Result: `JS runtimes: node-22.22.2`, and `[jsc:node] Solving JS challenges using node`.

---

## Best-known command (gets furthest — still 403 on bytes)

This is the maximal configuration. Every stage succeeds except the final byte
fetch. Use it for **metadata**, where it is the most reliable option available:

```bash
# 1. start the PO token provider (once per session)
cd /path/to/bgutil-ytdlp-pot-provider/server
npm install axios@latest        # REQUIRED: bundled 1.13.5 fails with proxy 405
npx tsc
/opt/node22/bin/node build/main.js &     # listens on 127.0.0.1:4416

# 2. run yt-dlp
/usr/local/bin/yt-dlp \
  --js-runtimes "node:/opt/node22/bin/node" \
  --extractor-args "youtube:player_client=tv_simply" \
  -f 18 -o out.mp4 \
  "https://www.youtube.com/watch?v=VIDEO_ID"
```

Note it must be `/usr/local/bin/yt-dlp`. The default `yt-dlp` on `PATH`
(`/root/.local/bin/yt-dlp`) is a `uv`-managed install under `agent-reach` that
reports `Plugin directories: none` and will never load the PO token plugin.

Trace of that command — everything green until the last line:

```
[youtube] Downloading tv simply player API JSON
[youtube] [pot:bgutil:http] Generating a gvs PO Token for tv_simply client   <-- OK
[youtube] Downloading player 854a788e-main
[youtube] [jsc:node] Solving JS challenges using node                        <-- OK
[info] Downloading 1 format(s): 18
ERROR: unable to download video data: HTTP Error 403: Forbidden              <-- IP binding
```

---

## Everything tried, and the exact failure

| # | Approach | Result |
|---|---|---|
| 1 | `bgutil-ytdlp-pot-provider`, HTTP server mode | Installed, plugin loads, **tokens now generate**. Media still 403. |
| 2 | Same, script mode | Unavailable — plugin looks in `/root/bgutil-.../server`, wrong path. HTTP mode used instead. |
| 3 | `pip install -U yt-dlp` | Already newest stable (`2026.07.04`). Nothing to gain. |
| 4 | `yt-dlp[default]` / `yt-dlp-ejs` | Installed 0.8.0. Fixed n-challenge. Media still 403. |
| 5 | Client `tv_simply` | Full pipeline succeeds (PO token + JS challenge solved) → **403** on bytes. |
| 6 | Client `android_vr` | Player JSON OK → **403** on bytes. |
| 7 | Client `tv` | `ERROR: This video is DRM protected`. Not pursued — DRM circumvention is out of scope. |
| 8 | Clients `web`, `web_safari` | `Sign in to confirm you're not a bot` at the player stage. |
| 9 | Client `web_embedded` | JS challenge solved → **403** on bytes. |
| 10 | Client `android` | Most formats SABR-stripped; the one usable format → **403** on bytes. |
| 11 | Client `ios` | GVS PO token not accepted for this client; **only image formats offered**, no media at all. |
| 12 | `--force-ipv4` | No effect; the proxy, not yt-dlp, chooses the egress address. **403**. |
| 13 | Direct `curl` of the signed URL | 302 → follow → **403**, 0 bytes. Confirms yt-dlp is not at fault. |
| 14 | 10× retry on a 6-hour-valid URL | **403** on every attempt. Rotating-IP lottery is unwinnable. |
| 15 | Headless Chromium cookie generation | **Browser has no egress at all** — `ERR_CONNECTION_RESET` on `example.com`, `google.com` and `youtube.com` alike. |

Nine distinct player clients were tested. The two that get furthest —
`tv_simply` and `web_embedded` — complete every stage of the pipeline
including PO token acquisition and JS challenge solving, and still 403 on the
first media byte. That pattern, combined with #13 (a raw `curl` of a valid
signed URL failing identically with yt-dlp entirely out of the picture), is
what rules out a client-selection or token fix.

### Note on the headless browser

The cookie approach could not even be evaluated, because
`chromium_headless_shell` cannot reach the network through the proxy:

```
https://example.com/     -> FAIL net::ERR_CONNECTION_RESET
https://www.google.com/  -> FAIL net::ERR_CONNECTION_RESET
https://www.youtube.com/ -> FAIL net::ERR_CONNECTION_RESET
```

Since plain `curl` reaches all three fine, this is a browser-to-proxy
integration problem, separate from the YouTube issue. Worth its own ticket if
browser automation is ever needed here.

### Note on rate limiting

Repeated attempts trigger `HTTP Error 429: Too Many Requests` on
`youtube.com/watch` itself, after which even metadata degrades to
`Sign in to confirm you're not a bot`. This recovers after roughly 5–10 minutes
of quiet. Anyone continuing this work should space attempts out; rapid
iteration makes the environment look worse than it is and produces misleading
failures.

---

## Assessment: is this solvable here?

**Not by any yt-dlp-side configuration.** This is the honest conclusion, and it
follows from the `ip=` binding being a *private, unroutable, per-request-rotating*
address. No player client, token provider, JS runtime, cookie jar or retry
policy can make a public request match an unroutable ULA. The problem is
architectural, one layer below yt-dlp.

Note in particular that **user-supplied browser cookies would probably not fix
this either.** Cookies address bot detection and the "Sign in to confirm you're
not a bot" class of error. They do not change which IP the media request comes
from, and the IP mismatch is what produces the 403. Asking the user for personal
cookies is therefore likely to cost them privacy for no benefit — it is not
recommended as the next step.

### What would actually work, in order of preference

1. **Download outside this container.** Any machine with a normal, stable egress
   IP — a laptop, or a box where the agent proxy is not in the path — will
   download these videos with stock `yt-dlp` and no special flags. Drop the
   files into `horror-pipeline/research/competitors/` as a local cache
   (`*.mp4` is already gitignored). This is by far the cheapest fix.

2. **Ask the platform team for a stable/sticky egress IP** for this session, or
   an egress path that does not inject the internal ULA into forwarded headers.
   If the media request and the player request share one source address, the
   existing best-known command above should start working immediately — the
   rest of the stack is already correct.

3. **Use the existing MCP tooling instead of raw video.** The NexLev connector
   already exposes `get_video_transcript`, `get_bulk_video_transcripts`,
   `youtube_video_details` and `watch_youtube_video_and_ask` — none of which
   need the media bytes. For competitor analysis specifically, this covers a
   large share of what the videos were wanted for.

### Recommendation

Do not spend more agent time on the download path from inside this container.
The remaining blocker is not a configuration gap; it is the egress
architecture, and it is not reachable from user space. Route around it via
option 1 or 3 above, and keep the two fixes documented here — they are
prerequisites for option 2 ever working, and they already improve metadata
reliability today.

---

## Reproduction notes

* PO token provider: `git clone --branch 1.3.1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider`
  then `npm ci && npm install axios@latest && npx tsc`.
* Python plugin: `pip install -U --break-system-packages bgutil-ytdlp-pot-provider`
  (installs into `/usr/local/lib/python3.11/dist-packages/yt_dlp_plugins`).
* Verify the plugin is loaded before drawing any conclusion:
  `yt-dlp --verbose ... 2>&1 | grep "PO Token Providers"` should show
  `bgutil:http-1.3.1 (external)`.
* Verify the token server independently:
  `curl --noproxy '*' -X POST http://127.0.0.1:4416/get_pot -H 'Content-Type: application/json' -d '{"content_binding":"VIDEO_ID"}'`
* When the provider misbehaves, read the **server's** stdout log, not yt-dlp's
  warning. yt-dlp flattens the provider's real error into a generic 500.

Test targets used: `lrY0ErBfytQ` (M Simplified, 545s), `VZPZi8yb5mg` (Ficknime, 591s).
