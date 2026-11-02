# 01 — Homelab inventory (as of 2026-10-20)

Read-only sweep of [thebigbox] (`ssh thebigbox`, glassslipper@192.168.1.178) and Jadu, plus the
vault at `~/Documents/Notes/Reference/Guides/`. No secrets recorded here.

## thebigbox resources

- 8 cores, 15 GiB RAM (≈7.4 GiB available), swap 5.5/15 GiB used, load ≈1.8
- `/` 60 GB free; `/media` (8 TB `/dev/sda2`) 3.3 TB free
- GPU: GTX 1050 Ti 4 GB — NVENC only, not useful for ML
- 56 containers. None of: kosync, BookBridge, Booklore/Grimmory, Calibre-Web, Storyteller, Readest

## House deployment pattern (Operations/Homelab Service Deployment Playbook.md)

- Compose at `/media/containers/<stack>/docker-compose.yml`, external `proxy` network, no published ports,
  pinned image tag, SQLite, NPM in front, `<app>.lan` + Authentik forward-auth (+ TOTP)
- Phone/e-reader clients that need an API get a regex `/api` carve-out in NPM
- New Docker networks get `10.99.x.0/24` (collision fix 2026-10-15)
- Secrets in Vaultwarden, never in notes

## Kavita (the intended source of truth)

| | |
|---|---|
| Running version | **0.8.9.1** (`jvmilazz0/kavita:latest`, unpinned, image built 2026-01-18) |
| Upstream latest | **0.9.1.4** (2026-09-02) |
| Compose | `/media/containers/kavita/docker-compose.yml` (same stack also runs ABS + Bookshelf) |
| Port | `0.0.0.0:5000`, on `proxy` network, TZ America/Los_Angeles |
| Config / DB | `/media/containers/kavita/kavita/kavita.db` (WAL, root-owned) |
| Books | `/media/media/books` → `/books` (291 MB: 25 epub + 13 pdf on disk) |
| Indexed | 46 files (28 epub, 18 pdf), 1 user, 5 progress rows, 7 client devices |
| KOReader sync | Built in, `/api/koreader/{apiKey}/…`; `KoreaderHash` populated for all 46 files; **no KOReader traffic in logs** |
| OPDS | Enabled; `/api/opds/{apiKey}` |

Libraries:

| Library | Type | Path |
|---|---|---|
| NonFiction | Book | `/books/Nonfiction` |
| Fiction | Book | `/books/Fiction` |
| Manga | Manga (empty) | `/books/Fiction/Manga` |
| Study | Book | `/books/Nonfiction/Study` |

**Nested libraries:** Study is inside NonFiction and Manga inside Fiction, so files are indexed twice.
Two Fiction files are not indexed.

## Audiobookshelf

| | |
|---|---|
| Running version | **2.32.1** |
| Upstream latest | **2.37.1** (2026-09-29) |
| Port | `0.0.0.0:13378` → container 80 |
| DB | `/media/containers/kavita/audiobookshelf/config/absdatabase.sqlite` (+ `metadata/`) |
| Media | `/media/media/audiobooks` (6 GB), `/media/media/music` |
| Library | one ("audiobooks"), 16 items: 234 mp3, 5 m4b, 1 m4a; **no ebooks attached** |
| Usage | 2 users, 10 progress rows (latest 2026-10-15), 261 sessions, 9 devices, 1 API key |

## Library overlap (the titles audio↔text features can help)

| Title | Ebook format |
|---|---|
| This Is How You Lose the Time War | epub |
| The Mountain Is You | epub |
| Naked Statistics | epub |
| Remain | epub |
| Tress of the Emerald Sea | **pdf only** |

The other 11 audiobooks have no ebook, including all 5 Red Rising books and Deep Work.
Naming is inconsistent (underscores, "(z-library.sk…)" suffixes, narrator/bitrate tags in ABS folders,
"(Unabridged)") — matching must be fuzzy or ISBN/ASIN based.

## KOReader-adjacent services

- **Koinsight** (`/media/containers/koinsight/compose.yaml`, `:3000`, `./data/prod.sqlite3`): KOReader stats
  uploads. 2 devices ("Manual Upload", "KindlePaperWhite3"), 65 books, 1,955 page stats, 181 annotations.
  Last stat 2026-08-20. Has kosync-style `user`/`progress` tables, both **empty**. Public, **no auth**.
- **Kobo Dashboard** (`:3333`): calendar/weather API polled by a KOReader `main.lua`. Not reading-related.
- **Bookshelf** (`ghcr.io/pennydreadful/bookshelf:hardcover`, `:8787`): Readarr-style downloader using
  Hardcover metadata; writes into `/media/media/books`.
- Mochtop runbook mentions an SSH key `~/.ssh/kindlekeylol` → likely SSH access to the Kindle.

## Jadu (192.168.1.158) services usable here

| Service | Endpoint | Note |
|---|---|---|
| Whisper (whisper.cpp large-v3-turbo, GPU1) | `127.0.0.1:9093` | loopback |
| Whisper Shim (OpenAI-compatible) | `0.0.0.0:9092` `/v1/audio/transcriptions` | LAN-reachable from thebigbox |
| llama-swap | `:9090` (`chat-e4b`, `coder`, `qwen27b-g1`) | interactive lane |
| 27B | `:8080` | |
| llm-gate (scheduled lane) | `127.0.0.1:9096` | |
| nomic embeddings (768-d) | `:9091` | could help title matching |
| PDW Postgres | `127.0.0.1:5433` (SSH tunnel) | possible home for reading events |

## Build tooling

- `build-run` is **not installed**; `~/.config/build-run/` does not exist. Only an archived copy at
  `~/macmini-2026-08-07/home/.config/build-run/` (contractor `gemma4:31b-cloud`, gate `on-failure`).
- Current practice (vault `Workflow/` notes): contractor = a small subagent; local option = the local worker
  agent (`coder` model, 64K context).
- The older workflow note in the vault is out of date (still describes Gemma/Ollama).
- `vault_lint.py` lives only on mochtop (`~/Projects/automations/vault-lint/`), not on Jadu.

## Security findings (not recorded in the vault)

1. Kavita and ABS are public on `*.thebigbox.duckdns.org` (NPM hosts 10, 12) **and** on
   `kavita.adduo.fyi` / `audiobookshelf.adduo.fyi` (NPM hosts 33, 34), which resolve to the RackNerd relay
   (104.168.7.21). 13 `adduo.fyi` proxy hosts in total (28–40); the vault never mentions the domain. No
   Authentik or access list — app login only. The vault notes say `exposure: lan-only`, which is wrong.
2. Kavita puts its API key in the URL path for KOSync and OPDS → keys land in NPM access logs.
3. Koinsight is public with no auth and serves a kosync-style endpoint (registration behaviour unchecked).
4. Offsite backup covers `/media/containers` (both app DBs) but **not** book/audiobook files, and runs by hand.
