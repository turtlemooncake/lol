# Step 10 — Deploy the engine to a Hetzner VPS under Docker Compose

**Goal:** host the always-on trading engine on the cheapest reliable box, ending
the cloud-hosting arc. Step 9 moved the biweekly `buy_universe` job to GitHub
Actions; this step puts the engine itself on a Hetzner VM running the Docker
image we already had. After this, both halves of the system are hosted: engine
on the VPS 24/7, job on GH Actions cron.

## Hosting decisions

| Decision           | Choice                                                                                   | Why                                                                                                                              |
| ------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Provider           | **Hetzner Cloud**                                                                         | Cheapest reliable VPS; no inbound traffic needed, state is external (Supabase), so the host is disposable                       |
| Server type        | **CX22** (x86 Intel, 2 vCPU / 4 GB), Ubuntu 26.04 LTS, **Helsinki**                       | ARM (CAX) is **EU-only** — not offered in Hetzner US. Went EU x86. Latency is irrelevant: strategies poll every 300s on daily bars |
| RAM                | 4 GB is ample                                                                            | The memory-heavy universe build (`buy_universe`) now runs on GH Actions, so the engine box only holds strategies + websockets (<1 GB) |
| Public IPv4        | **Kept** (~€0.50/mo) rather than IPv6-only                                                | IPv6-only risks: can't SSH from IPv4-only networks, and can't reach IPv4-only APIs (Alpaca/Supabase) — Hetzner has no NAT64. Worth the pennies |
| Deploy method      | **Docker Compose** (existing Dockerfile/compose)                                          | Already verified locally (Step 8), reproducible, `restart: unless-stopped` handles crashes + reboots                            |

Running cost: ~**€4.5/mo** (CX22) + ~**€0.50/mo** (IPv4) ≈ **~€5/mo**; the
GH Actions job is free. (ARM CAX11 in the EU would've been ~€1 cheaper, but x86
US was the original instinct; either is fine — arch is transparent to our stack.)

## Files touched

| File                | Change                                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| `deploy/deploy.sh`  | **New.** One-command code push + rebuild: `./deploy/deploy.sh root@<ip>`. rsyncs the tree to `/opt/lol` (skipping venv/caches/`.env`), then `docker compose up -d --build` over SSH |

No app code changed — this step is pure infrastructure.

## How the box was set up (manual, not cloud-init)

`deploy/cloud-init.yaml` automates first-boot setup (Docker + firewall + app
dir), but cloud-init only runs if pasted into the server's **user-data at
creation time**. This box was created in the Hetzner console **without** it, so
that window had passed — setup was done **manually over SSH** instead (the
equivalent commands, below). The file is kept as a **reference** for the next
time you provision a box: pasting it at creation would collapse steps 1–2.

1. **Create server** in the Hetzner console: Ubuntu 26.04, CX22, Helsinki, SSH
   key added, public IPv4 enabled.
2. **Install Docker** (as root over SSH): `curl -fsSL https://get.docker.com | sh`
   — auto-detects arch, installs engine + compose plugin (got Docker 29 / compose v5).
3. **Push code** from the Mac: `rsync -az --delete ... ~/Github/lol/ root@<ip>:/opt/lol/`
   (excludes `.git`, `.env`, `pyvenv/`, caches, `local/`).
4. **Copy secrets** separately: `scp .env root@<ip>:/opt/lol/.env` — `.env` is
   gitignored so it's excluded from the bulk sync and placed deliberately. Future
   re-syncs don't clobber it (rsync protects excluded files from `--delete`).
5. **Start** on the box: `cd /opt/lol && docker compose up -d --build`.

## Verifying

- **Clean boot:** `docker compose logs -f` shows "Trading Engine yee haw" and a
  clean startup — no `ModuleNotFoundError` (the Step 8 requirements fix holds on
  the real image) and the services reach Alpaca/Supabase.
- **`docker compose ps`:** `running`, not `restarting` (a crash-loop from a bad
  dep/secret would show `restarting` and silently relaunch under `unless-stopped`,
  so logs are the real check — not `ps` alone).
- **Reboot test PASSED:** `sudo reboot`, then after reconnect the container is
  `running` again with a fresh startup — Docker auto-starts it on host boot, so a
  Hetzner maintenance reboot won't leave the engine dark.

## Updating later

- **Code change:** re-run the rsync, then `docker compose up -d --build` — or
  just `./deploy/deploy.sh root@<ip>` which does both.
- **Secrets-only change:** re-`scp` `.env`, then `docker compose up -d` (no
  `--build` needed).

## Notes for later steps

- **Optional hardening, not yet done** (nothing blocking): unprivileged `deploy`
  user instead of root, `ufw` allowing only SSH. The box currently exposes only
  SSH inbound anyway (compose publishes **no** ports — the engine is outbound-only),
  so the attack surface is already small.
- **`.env` lives only on the box + your Mac** — there's no secret store. If the
  box is lost, re-scp `.env` from the Mac after re-provisioning. Don't commit it.
- Carried over from Step 8/9: no request timeout on `StockHistoricalDataClient`;
  `MAX_DAILY_LOSS` configured but still unenforced.
