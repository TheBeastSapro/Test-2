# Running a private Forgecast instance

Three ways, in order of how much you have to trust the network:

| | reachable from | you need | TLS |
|---|---|---|---|
| [On your own machine](#1-on-your-own-machine) | that machine | Docker | not needed |
| [Tunnel](#2-your-phone-without-a-server) | anywhere, over Cloudflare | a free Cloudflare account | handled for you |
| [VPS](#3-a-vps-you-control) | anywhere, your domain | a host + a domain | Caddy, automatic |

All three run the same image. Start with the first — it takes about five minutes and
proves the thing works before any networking is involved.

---

## 1. On your own machine

```bash
git clone <this repo> && cd forgecast
./docker/first-run.sh you@example.com     # writes .env, prints your password
docker compose up -d
open http://localhost:8000
```

That is the whole thing. `first-run.sh` generates the two secrets, creates the owner
account on first boot, and leaves registration closed. The port is published on
`127.0.0.1` only, so nothing outside that machine can reach it.

**Write down the password it prints.** It lives in `.env` in plain text — acceptable
for a single operator, but there is no recovery flow, so if you lose it you reset it:

```bash
docker compose run --rm app bootstrap --email you@example.com \
    --password 'a-new-long-password' --reset-password
```

Useful from there:

```bash
docker compose logs -f app worker      # what it is doing
docker compose restart app             # after an .env change
docker compose down                    # stop; the volume survives
docker compose down -v                 # stop and delete everything
```

### It starts in mock mode

`FORGECAST_PROVIDER_MODE=mock` calls no provider and spends nothing — deterministic
placeholder media, a real render, the full graph. That is the right way to learn the
UI. Switch to `live` when you have added keys, and note that credits are then real
money at your providers, metered through the ledger.

### Keys

Either put them in `.env` (the instance uses them for everything) or add them in the
UI under **Settings → Provider keys** (encrypted at rest with
`FORGECAST_ENCRYPTION_KEY`, and preferred over the instance's own). Two work with no
key at all: `claude-cli` for text if the `claude` CLI is installed in the container,
and Openverse for stock imagery.

---

## 2. Your phone, without a server

A Cloudflare tunnel gives the container a hostname and TLS without opening a port or
renting anything. Run it next to the app:

```bash
docker run --rm --network host cloudflare/cloudflared:latest \
    tunnel --url http://127.0.0.1:8000
```

It prints a `https://<random>.trycloudflare.com` URL. Set that as your base URL so
generated links point at it, and tell the app to trust the tunnel's forwarded headers:

```bash
# .env
FORGECAST_BASE_URL=https://<random>.trycloudflare.com
FORGECAST_FORWARDED_ALLOW_IPS=*
```

then `docker compose restart app`.

**Before you do this, understand what you have just published.** The instance is now
on the internet behind nothing but your password. That is survivable because
registration is closed and media needs a signed URL — but a quick-tunnel hostname is
public, and a weak password is the only thing between it and a stranger. For anything
beyond a demo use a named tunnel with Cloudflare Access in front, which puts an
identity check ahead of the app.

`--forwarded-allow-ips=*` is deliberate here and only correct behind a proxy you
control: it tells uvicorn to believe `X-Forwarded-For`, which anything directly
reachable must never do.

---

## 3. A VPS you control

Any 2 vCPU / 4 GB box. Rendering is CPU-bound ffmpeg, so cores are what make runs
faster; 4 GB is comfortable for 1080p.

```bash
ssh you@your-server
git clone <this repo> && cd forgecast
./docker/first-run.sh you@example.com
```

Edit `.env` for a real hostname:

```bash
FORGECAST_BASE_URL=https://forgecast.example.com
FORGECAST_PUBLISH_ADDR=127.0.0.1          # keep it on loopback; Caddy fronts it
FORGECAST_FORWARDED_ALLOW_IPS=172.16.0.0/12
```

Add Caddy — it gets and renews a certificate on its own:

```yaml
# docker-compose.override.yml
services:
  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    restart: unless-stopped
volumes:
  caddy-data:
```

```
# Caddyfile
forgecast.example.com {
    reverse_proxy app:8000
    request_body {
        max_size 512MB
    }
}
```

Point the DNS record at the box, then `docker compose up -d`. Check
`docker compose logs caddy` for the certificate.

### Postgres, when SQLite stops being enough

SQLite in WAL mode is fine for one operator running a few concurrent renders. Move
when you see `database is locked` in the logs:

```bash
# .env
FORGECAST_DATABASE_URL=postgresql+psycopg://forgecast:<password>@postgres:5432/forgecast
POSTGRES_PASSWORD=<password>
```

```bash
docker compose --profile postgres up -d
```

Migrations run on start, so a fresh Postgres gets the schema automatically. There is
no data migration from SQLite — export what you care about first, or switch before you
have anything worth keeping.

---

## The checklist before you expose it

Everything here is the shipped default except the last two.

- [x] **Registration closed.** `FORGECAST_ALLOW_SIGNUP=false`. The `/login` page hides
      the button and both the API and the form refuse.
- [x] **Media needs a signature.** No static mount of the storage directory. Each
      artifact URL is an HMAC over path + owner + expiry, valid for
      `FORGECAST_MEDIA_URL_TTL_SECONDS` (6 h). A URL cannot be pointed at another file
      or another user, and it expires.
- [x] **Port on loopback.** `FORGECAST_PUBLISH_ADDR=127.0.0.1`.
- [x] **Bootstrap refuses a password under 12 characters.**
- [x] **Non-root in the container**, uid 10001.
- [ ] **Back up the volume.** `forgecast-data` holds the database and every render.
      `docker run --rm -v forgecast-data:/data -v "$PWD":/backup alpine tar czf /backup/forgecast-$(date +%F).tar.gz /data`
- [ ] **Back up `.env` separately, once.** Losing `FORGECAST_ENCRYPTION_KEY` makes
      every stored provider key permanently undecryptable — a database backup alone
      does not save you. Losing `FORGECAST_SECRET_KEY` logs everyone out and breaks
      outstanding media links, which is annoying rather than fatal.

A signed URL is shareable by whoever holds it until it expires. That is the trade
every signed-URL scheme makes; shorten the TTL if you paste links into places you do
not control.

---

## What is verified, and what is not

Verified by running it:

- `migrate`, `bootstrap`, `api` and `worker` roles of `docker/entrypoint.sh`, executed
  directly — including bootstrap being idempotent across restarts and exiting non-zero
  on a short password.
- The migration baseline applies to an empty database, matches the models with no
  drift, and adopts a database that already had tables.
- A full run driven over HTTP with every gate approved: 12 nodes completed, a
  1080×1920 H.264/AAC file exactly 20.0 s long, ledger closing exactly (183 reserved,
  2 spent).
- Signed media: served with no auth header, `206` on a range request, `403` on a
  tampered signature, `404` on the old `/files` path.
- The browser pages: login without a signup button, redirect when unauthenticated,
  dashboard and run page rendering with signed video URLs in the HTML.

**Not verified: the Docker image build and `docker compose up`.** The environment this
was developed in has the Docker CLI but no daemon, so those two commands have never
run. The compose file parses and the entrypoint is syntax-checked and behaviourally
tested outside a container, but the image layers are unproven. Expect to fix something
small on your first `docker compose build` — most likely a missing apt package — and
run that before you depend on it:

```bash
docker compose build && docker compose up -d && docker compose logs -f
```
