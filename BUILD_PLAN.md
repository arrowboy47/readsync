# readsync — BUILD_PLAN

**Status:** Phase 0–1 detailed. Phases 2–7 are coarse and get rewritten after the Phase 1 go/no-go.
**Gate:** `every-task` for Phase 0 (it changes the live stack); `on-failure` from Phase 1 on.
**Contractor:** `build-run` is not installed on Jadu (see `research/01`); until it is, tasks run through the
the local worker agent or a subagent, with the architect checking each `Verify:`.

**Locked shared state:** the canonical *Book identity*, *Annotation* and *Progress* records in `ARCHITECTURE.md`
(extended 2026-10-21 for the edge cases). Every spoke maps to them; changing them needs an architect edit here first.

**Edge cases:** `EDGE_CASES.md` lists ~120 cases (IDs A1…J4) and the rules R1–R14 they reduce to. Each `[NEW]` or
`[BB]` case becomes `tests/edge/test_<ID>.py` in the phase that builds it; owner questions Q1–Q8 should be answered
before Phase 3.

**Environment** (`.env`, mode 600, gitignored; values in Vaultwarden entry "readsync"):

```
KAVITA_URL=http://192.168.1.178:5000      KAVITA_API_KEY=…   # Kavita auth key, sent as x-api-key
ABS_URL=http://192.168.1.178:13378        ABS_API_KEY=…      # ABS API key bound to the reading user
WHISPER_URL=http://192.168.1.158:9092
FABLE_EMAIL=…  FABLE_PASSWORD=…           HARDCOVER_TOKEN=…  # optional
```

Spike outputs go in `research/spikes/S<n>.md`, each starting with `Result: PASS|FAIL` and the evidence.

---

## Phase 0 — Prerequisites (changes the live stack; owner approves each task)

## Task 01 — Back up Kavita and ABS databases
Create `/media/containers/kavita/backup-readsync-<date>/` on thebigbox holding a consistent copy of `kavita.db`
(WAL) and `absdatabase.sqlite`. Read nothing else, change nothing else. `sudo` on thebigbox needs a password, so the
copy runs in a throwaway `python:3.12-slim` container (`--network none`, sources mounted read-only, SQLite backup
API), and the copies are chowned to `glassslipper`, mode 600.

**Done 2026-10-21:** `backup-readsync-2026-10-21/` holds `kavita.db`, `absdatabase.sqlite` (integrity ok, row counts
equal to live: Kavita 5 progress rows / 46 files / 4 libraries; ABS 10 progress rows / 16 items / 2 users),
`docker-compose.yml.orig` and `IMAGES.txt` (pre-upgrade image digests, for rollback).

Verify: `ssh thebigbox 'for f in kavita.db absdatabase.sqlite; do sqlite3 -readonly /media/containers/kavita/backup-readsync-2026-10-21/$f "pragma integrity_check" | grep -qx ok || exit 1; done'`
Done when: both copies pass `integrity_check`.

## Task 02 — Upgrade and pin Kavita 0.9.1.4 and ABS 2.37.1
Edit `/media/containers/kavita/docker-compose.yml`: pin both images by tag + digest, then
`docker compose pull kavita audiobookshelf && docker compose up -d kavita audiobookshelf` (Bookshelf untouched).
Update the vault notes ([[Kavita]], [[Audiobookshelf]]) and Stack Log in the same session.

Tags checked 2026-10-21: Kavita release v0.9.1.4 is published on Docker Hub as `0.9.1` (same digest as `latest`;
the `0.9.1.x` tags are nightlies); ABS `2.37.1` = `latest` on ghcr.io.

```yaml
kavita:         image: jvmilazz0/kavita:0.9.1@sha256:31181a32f0dda73cae68721867028a7253d57881b58bea5754cd9e578e75421a
audiobookshelf: image: ghcr.io/advplyr/audiobookshelf:2.37.1@sha256:581d68b2a6fc7ebf58d81c878a9f387cbbc0d88ac9d37b298b9cee10168af85b
```

Rollback: restore `docker-compose.yml.orig` + both DBs from Task 01's folder, pin the old digests in `IMAGES.txt`.

**Done 2026-10-21:** both recreated in 20 s; Kavita logs `v0.9.1.4` after its migrations, ABS ran the 2.33.0/2.35.0
migrations; progress/annotation/file counts unchanged. Vault [[Kavita]], [[Audiobookshelf]] and Stack Log updated.

Verify: `curl -s http://192.168.1.178:13378/status | jq -e '.serverVersion=="2.37.1"' && ssh thebigbox "docker inspect kavita --format '{{.Config.Image}}'" | grep -q 'sha256:31181a32f0dd' && curl -sf http://192.168.1.178:5000/api/health`
Done when: both up, versions match, Kavita progress rows ≥ 5 and ABS progress rows ≥ 10, and the owner can open a
book in each web UI.

## Task 03 — Fix nested Kavita libraries
Unnest so no library path contains another (e.g. move Study / Manga to sibling folders, or drop the nested
libraries). Rescan. Investigate the 2 unindexed Fiction files. This must happen before any book mapping exists
(EDGE_CASES F2, F3: a rescan after moves changes Kavita's ids).

**Owner decision 2026-10-21 — runs after Task 04:** keep the `Study` library and add exclude patterns (Study out of
NonFiction, Manga out of Fiction); no files move. State found: 11 Study files indexed twice; the Manga library has 0
files. Before excluding, copy what exists only on the NonFiction copies onto the Study copies via the API:
*Automate the Boring Stuff* progress (p. 205, NonFiction only) and the July annotation on *Building Applications with
AI Agents* (NonFiction copy; the Study copy's progress p. 22 is newer and stays). The other annotation and progress
rows are already on Study copies.

**Progress 2026-10-21:** progress + annotation copied to the Study copies (`tools/task03_migrate_dupes.py`), excludes set
(`**/Study/**` on NonFiction, `**/Manga/**` on Fiction), NonFiction rescanned: 35 files / 35 distinct. **Finished:** the two
loose root-level EPUBs in `/books/Fiction/` (Time War, Remain) moved into their own folders (owner OK) and are now
indexed: 37 files / 37 distinct, Fiction 18/18.

Verify: `ssh thebigbox "docker run --rm --network none -v /media/containers/kavita/kavita:/k:ro python:3.12-slim python -c \"import sqlite3,sys; c=sqlite3.connect('file:/k/kavita.db?mode=ro',uri=True); sys.exit(c.execute('select count(*)-count(distinct FilePath) from MangaFile').fetchone()[0])\""`
Done when: no duplicate files, every EPUB on disk is indexed (table/column names to confirm against the 0.9.1.4 schema).

## Task 04 — API keys and `.env`
Owner creates a Kavita auth key (user settings) and an ABS API key bound to their user (Settings → API Keys),
stores both in Vaultwarden. Write `.env` (mode 600) and `.gitignore`.

**Done 2026-10-21:** keys loaded from owner-supplied files without printing, source files shredded, verify PASS.
ABS key belongs to user `glassslipper` (root). The keys were pasted into the session transcript when attached, so
rotate them after the project if that matters.

Verify: `set -a && . ./.env && curl -sf -H "x-api-key: $KAVITA_API_KEY" "$KAVITA_URL/api/Library/libraries" >/dev/null && curl -sf -H "Authorization: Bearer $ABS_API_KEY" "$ABS_URL/api/me" >/dev/null && test "$(stat -c %a .env)" = 600`

## Task 05 — Exposure decision and device inventory
*Exposure half done 2026-10-21 (owner chose option 1, recorded in ARCHITECTURE.md). Device inventory: skeleton + Kindle checklist written 2026-10-30; Kobo and iPhone fields need the owner at the devices; Kindle section waits for the device.*
Owner decides how off-LAN KOReader reaches the hub (proposal in `ARCHITECTURE.md` → Exposure). Record the decision
there as a line starting `Exposure decision:`. Also record, per device (Kindle PW3, Kobo, iPhone), in `research/devices.md`: KOReader version, which
progress-sync server it points at today (Kavita, Koinsight, other), the kosync settings (auto sync on/off, pages
before update, "sync to a newer state", "sync to an older state", checksum method), Wi-Fi behaviour on suspend, and
how books get onto it (OPDS, Calibre, sideload). Feeds EDGE_CASES A8, F1, I5 and Q6/Q7.

Verify: `grep -qiE 'exposure decision:' ARCHITECTURE.md && test "$(grep -c '^## ' research/devices.md)" -ge 2`
Done when: `ARCHITECTURE.md` Exposure section states the chosen option, the owner has signed off, and every device has
its section in `research/devices.md`.

---

## Phase 1 — Spikes (read-mostly; each writes `research/spikes/S<n>.md`)

## Task 06 — S1: Kavita annotation create + render
*Done 2026-11-10: PASS, research/spikes/S1.md.*
`spikes/s1_kavita_annotation.py`: read one annotation the owner makes by hand in Kavita on *This Is How You Lose
the Time War* (template), then create a second one via `POST /api/Annotation/create` on a different paragraph
using only `xPath`, `endingXPath`, `selectedText`, `pageNumber`, ids. Read it back; delete it with `--cleanup`.
Also try: an annotation with empty `selectedText` (E12) and one whose range crosses into the next page (E5); record
what Kavita does with each.

Verify: `python3 spikes/s1_kavita_annotation.py --verify`
Done when: the script exits 0 **and** the owner confirms the API-made highlight renders in the Kavita reader on the
right words (screenshot in `S1.md`).

## Task 07 — S2: Kavita SignalR events and reader behaviour
*Done 2026-11-10: PASS, `research/spikes/S2.md`. Echo confirmed; AnnotationUpdate never fires (poll); open reader ignores then overwrites server changes.*
`spikes/s2_kavita_signalr.py`: connect to the messages hub (path to confirm), then post a progress update for a
test book and wait for `UserProgressUpdate`; create/delete an annotation and wait for `AnnotationUpdate`. Record
payload shapes, and whether events fire for our own API writes (echo, R8). Restore the original progress afterwards.
With the owner at the browser, also record (B9, B19):
- which reader modes (scroll, 1-column, 2-column) save `bookScrollId` and which save only the page;
- what an open Kavita reader does when the progress is changed server-side (ignores it, jumps, prompts, or
  overwrites it on its next save).

Verify: `timeout 120 python3 spikes/s2_kavita_signalr.py --expect UserProgressUpdate,AnnotationUpdate && grep -qi 'bookScrollId' research/spikes/S2.md`

## Task 08 — S3: BookBridge alignment on one paired title
*Done 2026-10-21: PASS 10/10, `research/spikes/S3.md`. Whisper shim drops timestamps (fix in Task 17).*
Run the pinned BookBridge image in a throwaway compose project (no published ports, sync disabled, copies of the
EPUB + audio only) and align *This Is How You Lose the Time War*. Record wall time and CPU/RAM on thebigbox, and the
map's coverage of the text (B12); if > 3 h, repeat with its Whisper backend pointed at `WHISPER_URL`.

Verify: `python3 spikes/s3_alignment_eval.py --book time-war --samples 10 --min-hits 9`
(10 random timestamps → 20 s clip → Whisper → text must fuzzy-match (≥ 80) the map's text at that time)

## Task 09 — S4: Whisper-clip lookup without a map
*Done 2026-10-30: PASS 10/10, `research/spikes/S4.md`.*
`spikes/s4_clip_lookup.py`: for the same 10 timestamps, locate the passage from the clip alone (±10 % window,
runner-up margin) and compare against S3's map. Include 2 timestamps that fall in silence or a chapter announcement
(D2) and report how they fail.

Verify: `python3 spikes/s4_clip_lookup.py --book time-war --samples 10 --agree-with-s3 9`

## Task 10 — S5: BookBridge spoke contract
*Done 2026-10-21: `research/spikes/S5.md`, Decision: fork.*
Read `refs/bookbridge/src/services/annotation_sync_service.py` and the spokes it calls, the device exchange in
`src/api/kosync_server.py` and `src/db/database_service.py` (`exchange_koreader_annotations`), and
`src/sync_clients/`. Write the contract a Kavita spoke and an ABS-bookmark spoke must implement, how conflicts and
tombstones work, and whether annotations flow hub → device for spoke-originated items. Also answer: does anything in
BookBridge skip the 300 s KOSync PUT debounce on close/suspend (B6), and does it listen for ABS
`user_session_closed` (B7)? Decide fork-and-upstream vs sidecar.

Verify: `grep -qE '^Decision: (fork|sidecar)' research/spikes/S5.md`

## Task 11 — S6: Fable login and progress write
*Done 2026-11-10: PASS, research/spikes/S6.md. Fable progress lives at /reading_progress.*
`spikes/s6_fable.py` (Python port of ShelfSync's `fable/api.lua` calls): log in, list the "currently reading" shelf,
re-post the **current** % for one book already there (idempotent), read it back. Note in `S6.md` whether Fable has
any notion of a re-read or of finish dates (H8). ToS risk accepted by owner.

Verify: `python3 spikes/s6_fable.py --roundtrip`

## Task 12 — S7: ABS app behaviour
*Done 2026-11-10: PASS, research/spikes/S7.md (tested with the AudioBooth iOS client).*
`spikes/s7_abs_cadence.py`: subscribe to the ABS socket with the API key and log every event with timestamps; the
owner follows a short script in the iOS app on a paired title:
1. Play 5 minutes → interval between `user_item_progress_updated` events (lag floor for immersion, C7).
2. Pause → time until the server sees the pause (C8).
3. While paused, the script PATCHes server progress +2 min; press play → does the app start from the new spot? Repeat
   with a downloaded copy (B6).
4. While playing, PATCH server progress → does the app jump, ignore it, or overwrite it? (B20)
5. Airplane mode, play 3 minutes, add a bookmark, reconnect → what arrives, with which `lastUpdate`, and does the
   bookmark survive? (A9, A10)
6. Add a bookmark with a 200-character title → stored or truncated? (D11)

Verify: `python3 spikes/s7_abs_cadence.py --minutes 5 --report research/spikes/S7.json && jq -e '.median_interval_s > 0' research/spikes/S7.json`
Done when: `S7.md` answers steps 2–6.

## Task 13 — S8: On-device anchor resolution
*Done 2026-11-10: PASS on the Kindle, 20/20, `research/spikes/S8.md`. Emulator skipped (not packaged); ran on the device directly.*
Prove the KOReader side of E10: given `quote`, `prefix`, `suffix` and `spine_index`, find the passage with crengine and
produce `pos0`/`pos1` xpointers. Build a minimal test plugin and run it in the KOReader desktop emulator on Jadu first,
then on the PW3: 20 passages picked at random from *Time War* (including ones with smart quotes, soft hyphens and
italics, E6). Also confirm live apply into an open book works on the PW3 (A16).

Verify: `python3 spikes/s8_anchor_eval.py --book time-war --samples 20 --min-exact 18`
Done when: ≥ 18/20 resolve to the same xpointers a manual highlight produces, and the PW3 result is in `S8.md`.

## Task 14 — S9: Mass-delete reproduction
*Done 2026-10-30: PASS, 10 tombstones reproduced, `research/spikes/S9.md`.*
In the S3 throwaway BookBridge (sync off, no real devices): exchange 10 annotations as a fake device, ack them, then
send a complete key list with none of them (a wiped sidecar, E8). Record how many tombstones the hub creates and what
it would send other devices. This confirms the risk the R10 guard in Phase 3 exists for.

Verify: `python3 spikes/s9_mass_delete.py --expect-tombstones 10`

## Task 15 — S10: Follow-along on the Kindle
*Done in part 2026-11-10: PARTIAL, `research/spikes/S10.md`. Page turns, battery, ghosting and suspend measured. Network half to repeat on the home Wi-Fi.*
A throwaway plugin turns a page every 30 s on the PW3 for 30 minutes with Wi-Fi on and a request to the S3 container
every 20 s. Record: does the device auto-suspend, does Wi-Fi stay up, battery % used, any e-ink ghosting complaints
(C9, C10).

Done when: `S10.md` records suspend behaviour, Wi-Fi uptime and battery drain per hour, and the owner judges it usable
or not.

## Task 15b — S11: Two-reader isolation (K1, K3, K4, K6)
*DB layer done 2026-11-02: PASS, `research/spikes/S11.md`. HTTP layer + Kavita/ABS spokes move to Phase 2 tests.*
In the throwaway BookBridge: create reader A and B, same book hash. Run `K1`, `K3` and `K4` (script `spikes/s11_two_readers.py`): both PUT different positions, upload annotations as A, expect B sees none, A's wiped sidecar leaves B untouched. Also check what happens in Kavita and ABS with two users (each their own key).

Verify: `python3 spikes/s11_two_readers.py --expect-isolated`
Done when: `S11.md` records that nothing crosses between readers, or lists exactly what does.

## Task 16 — Spike report and go/no-go
Summarise S1–S10 in `research/spikes/REPORT.md` with the recommended scope for Phases 2–7, and update every
`[SPIKE]` case in `EDGE_CASES.md` with its answer.

Done when: the owner records go / no-go / re-scope at the top of `REPORT.md`. (Q1–Q8 answered 2026-10-21: defaults.)

---

## Phase 2 — Progress (P)  *(coarse — rewrite after Task 16)*

## Task 17 — Deploy BookBridge on thebigbox (house pattern)
*Prereq from S3: make the Whisper shim on Jadu pass through `verbose_json` word timestamps (it currently returns text only).*
Pinned image, `/media/containers/bookbridge/`, `proxy` network, NPM host per Task 05, Uptime Kuma monitor,
vault Service note + Stack Log. KOReader (Kindle, Kobo) and Readest point at its KOSync and nothing else (R14);
BridgeSync self-update off (I10).

Verify: `curl -sf http://bookbridge:<port>/koreader/healthcheck` (from a container on `proxy`) `&& curl -sf https://<public-host>/koreader/healthcheck`

## Task 18 — Pair titles and build alignments
Pair the 4 EPUB titles across Kavita/ABS/KOReader hash; build alignment maps; refuse pairs under 90 % coverage.

Verify: `python3 tools/check_pairs.py --min-paired 4 --min-aligned 4`

## Task 19 — Progress rules and end-to-end tests (scenarios 1, 3, 5, 6)
Implement R1–R8, R11, R13 on top of BookBridge's leader selection. Golden tests: write progress on the source
surface, poll targets within the latency budget, assert agreement within one paragraph / 15 s.

Verify: `pytest tests/edge -k "A1 or A2 or A3 or B2 or B3 or B5 or B6 or B8 or B10 or B16 or B17 or B21" && pytest tests/e2e/test_progress.py -m live`

## Phase 3 — Annotations (B/H)

## Task 20 — Kavita annotation spoke (canonical ⇄ Kavita)
Includes R9, R10, R11 and the on-device resolution from S8.

Verify: `pytest tests/test_kavita_spoke.py tests/edge -k "A5 or A7 or E1 or E2 or E3 or E6 or E8 or E15" && pytest tests/e2e/test_annotations.py -m live -k "koreader_to_kavita or kavita_to_koreader"`

## Task 21 — Kavita native progress (REST + SignalR) instead of Kavita's KOSync hop
Includes R3 for the Kavita web reader (B19).

Verify: `pytest tests/test_kavita_progress.py tests/edge -k "B9 or B19" && pytest tests/e2e/test_progress.py -m live -k kavita`

## Phase 4 — ABS bookmarks ↔ Kavita annotations

## Task 22 — ABS bookmark spoke (map first, Whisper clip fallback, confidence gate)
Verify: `pytest tests/test_abs_bookmark_spoke.py tests/edge -k "D1 or D2 or D3 or D4 or D5 or D6 or D8 or D12" && pytest tests/e2e/test_abs_bookmarks.py -m live`

## Task 23 — Review queue + Telegram alert for low-confidence matches
Verify: `pytest tests/test_review_queue.py tests/edge -k "D10 or I8"`

## Phase 5 — O roll-up + Fable (+ Hardcover)

## Task 24 — O roll-up (BookBridge stats + Kavita reading-history + ABS listening-stats)
Verify: `pytest tests/test_o_rollup.py tests/edge -k "H1 or H2 or H3 or H4 or H5 or H6"`

## Task 25 — Fable sync client (debounced, status immediate) and optional Hardcover
Verify: `pytest tests/test_fable_client.py tests/edge -k "H7 or H8 or H9 or H10 or H11 or H12" && python3 tools/fable_status.py --expect-current`

## Phase 6 — Immersion follow-along

## Task 26 — Follow-along endpoint + BridgeSync plugin mode
State machine and rules from `EDGE_CASES.md` §C, dead reckoning per C7.

Verify: `pytest tests/test_follow_along.py tests/edge -k "C1 or C2 or C3 or C4 or C5 or C7 or C8 or C9 or C11 or C13"`
Done when: on the Kindle, with audio playing on the phone, the page trails the audio by ≤ S7 interval + 20 s over a 10-minute session.

## Phase 7 — Hardening

## Task 27 — Monitoring, backups, recovery, vault docs
Uptime Kuma checks, backup of `/media/containers/bookbridge`, R12 read-only reconcile tested by restoring a backup
into a scratch copy, R14 DB lease, vault Service + Project notes current, Stack Log.

Verify: `ssh thebigbox 'docker ps --filter name=bookbridge --format "{{.Status}}"' | grep -q healthy && pytest tests/edge -k "A11 or A12 or I1 or I2 or I3 or I4 or I6"`

## Task 28 — Full suite
Verify: `pytest -m "not live" && pytest tests/edge && pytest -m live`
