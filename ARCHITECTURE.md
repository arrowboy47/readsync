# readsync — architecture

## Shape

```
 KOReader (Kindle/Kobo) ─ KOSync + BridgeSync plugin ─┐
 Readest (iOS, offline) ─ KOSync ─────────────────────┤
 ABS ─ Socket.IO (API key, ≥2.37.0) + REST ───────────┤
 Kavita ─ SignalR events + REST (x-api-key) ──────────┤
                                                      ▼
   ┌───────────────── thebigbox · docker · house pattern ─────────────────┐
   │ BookBridge fork (pinned)                                             │
   │   existing: KOSync server · device-sync API · ABS listener ·         │
   │             alignment maps (BookAlignment) · annotation hub          │
   │   NEW spokes / clients:                                              │
   │     • kavita_annotation_spoke   (Kavita ⇄ canonical annotations)     │
   │     • abs_bookmark_spoke        (ABS bookmarks ⇄ canonical, via map) │
   │     • kavita native progress    (REST + SignalR, replaces Kavita     │
   │                                  KOSync hop that drops offsets)      │
   │     • fable_sync_client         (ShelfSync port)                     │
   │     • o_rollup job              (stats + Kavita history + ABS stats) │
   │     • follow-along endpoint     (+ BridgeSync plugin mode)           │
   └──────────────────────────────────────────────────────────────────────┘
          │ Whisper fallback (clip lookup)              │ alerts
          ▼                                             ▼
   Jadu Whisper Shim 192.168.1.158:9092         Hermes → Telegram
```

**Base decision:** extend a BookBridge fork rather than build a hub. `research/04` shows BookBridge already owns
the KOSync server, device annotation exchange, stats upload and alignment. Spike S5 confirms the spoke contract
before Phase 3; if upstream won't accept the spokes, they run from the fork (or, worst case, as a sidecar that
reads BookBridge's DB).

## Canonical records (locked — every spoke maps to these)

*Extended 2026-10-21 with the fields the edge cases need (`EDGE_CASES.md` §3).*

### Book identity

| Field | Source |
|---|---|
| `doc_md5` | KOReader binary partial MD5 (= Kavita `KoreaderHash`) — primary key, as in BookBridge |
| `kavita_chapter_id`, `kavita_series_id`, `kavita_volume_id`, `kavita_library_id` | Kavita |
| `abs_item_id` | ABS library item (nullable) |
| `isbn`, `asin` | metadata, for fuzzy pairing |
| `fable_book_id`, `hardcover_id` | targets (nullable) |
| `alignment_id` | BookBridge `BookAlignment` row (nullable) |
| `alignment_coverage` | share of the text the map covers; pairing refused below 0.90 (EDGE_CASES B12) |
| `extra_hashes` | older/other `doc_md5`s of the same book (replaced EPUB, F4) |
| `link_positions` | default true; false stops progress fan-out for this book (B15) |

### Annotation (W3C-style selectors; resolved natively at each end)

```
annotation_id      uuid
doc_md5            book key
kind               highlight | note | bookmark
quote              exact selected text (may be empty for bookmark)
prefix / suffix    ~32 chars either side
spine_index        0-based
char_offset        offset into spine item's plain text
percent            0–1, sanity check only
koreader           pos0, pos1 (xpointers)      — when known
kavita             annotation id, xPath, endingXPath — when known
abs                bookmark time (s)           — when known
note               free text (B)
color              KOReader colour ↔ Kavita highlight slot
origin             surface that created it
updated_at         ms epoch
activity_at        when it happened at the source (device time, checked per R2)
received_at        when the hub got it
deleted            tombstone flag
archived_text      note text that lost a conflict (R9), kept for the digest
```

Each spoke locates a passage by `quote` (+ prefix/suffix) inside `spine_index`, using `char_offset` and
`percent` only to break ties — never by translating raw paths across engines.

### Progress

`doc_md5, spine_index, char_offset, percent, audio_seconds (if paired), source, device_id, session_id,
activity_at, received_at, updated_at`.

## Sync rules

Full set with the cases behind them: `EDGE_CASES.md` §1 (R1–R14). In short:

- **Echo suppression and deadband (R8):** every write records its origin + id; anything that comes back within
  tolerance of our own write is dropped. An idle book produces zero writes.
- **Progress:** newest *activity* time wins (R1, R2), Kavita wins exact ties. Implausible jumps in either direction
  are held until the same surface keeps advancing from there (R4). A backward move only becomes the truth if the
  device had seen the newer position (R5); otherwise furthest wins. Close/suspend skips the debounce (R6). Hand-offs
  land slightly early, never late (R7). Surfaces are compared by position, never by % (R13).
- **Writes:** never into a surface that's in use on that book (R3); outbox + idempotent keys + compare-and-set (R11).
- **Annotations:** union merge; near-duplicates merged; deletes propagate as tombstones, but no note text is lost
  (R9: keep both on edit conflicts; decided Q1/Q2) and mass deletes are quarantined (R10).
- **Recovery:** read-only reconcile after a restore or > 30 min outage (R12); one hub instance, one sync server per
  device (R14).
- **Immersion:** audio leads; state machine in `EDGE_CASES.md` §C.
- **Fable:** debounced ≥ 30 min per book; start/finish sent immediately once they pass the H7/H9 gates.

## Audio ↔ text

1. **Primary:** BookBridge alignment map (time ↔ char offset), built once per paired book.
2. **Fallback / cross-check:** cut a 15–20 s clip ending at T from `GET /api/items/:id/file/:ino` with `ffmpeg`,
   transcribe via the Whisper Shim, rapidfuzz-match within ±10 % of the expected position. Accept only if the best
   match beats the runner-up by a clear margin; otherwise → review queue + Telegram alert.
3. Kavita → ABS: char offset → time via the map → `POST /api/me/item/:id/bookmark` with a title built from the note
   or the first ~60 chars of the quote.

## Ingress latency

| Surface | Mechanism | Expected |
|---|---|---|
| ABS | Socket.IO `user_item_progress_updated`, `user_updated` | seconds after the app's own upload (measure in S7) |
| KOReader | KOSync push every N pages / close / suspend; BridgeSync exchange | event-driven |
| Kavita web | SignalR `UserProgressUpdate`, `AnnotationUpdate`; 60 s poll fallback | seconds |
| Readest | KOSync | event-driven |
| Fable | scheduled | ≤ 30 min |
| O roll-up | nightly | daily |

## Exposure (decided 2026-10-21)

Exposure decision: option 1. One public hostname behind the existing NPM proxy serving only the KOReader sync paths (`/koreader/*`: KOSync + device-sync). The sync server's own login is the only protection on that host. Everything else (web UI, admin, API) stays on LAN/WireGuard plus Authentik. Exact hostname chosen at deploy time (Phase 2); no live change made yet.

- KOReader off-LAN must reach the KOSync + device-sync paths; a Kindle can't run WireGuard.
- Proposed: BookBridge on the `proxy` network with no published ports; one NPM host exposing **only**
  `/koreader/*` (KOSync + device-sync) with BookBridge's own auth; everything else (web UI) LAN/WireGuard +
  Authentik. No API keys in URL paths on the public host.
- Separately (not this project's change, tracked in Stack Backlog): decide whether Kavita/ABS stay public on
  `adduo.fyi` / duckdns, and put Koinsight behind auth.

## Where things run

| Piece | Host | Notes |
|---|---|---|
| BookBridge fork | thebigbox | compose `/media/containers/bookbridge/`, SQLite, pinned image |
| Alignment jobs | thebigbox CPU (measure in S3) | fall back to Whisper on Jadu GPU1 if too slow |
| Whisper | Jadu `:9092` | already serving Mealie; clip calls are seconds |
| Alerts | Hermes cron / Telegram | low-confidence matches, sync failures |
| Secrets | Vaultwarden + `.env` (600) | Kavita auth key, ABS API key, Fable login, Hardcover token |

## Risks to watch

- Kavita annotation render from external XPaths (S1).
- BookBridge upstream churn → pin versions, keep spokes small, upstream them.
- Fable API change or account action → Hardcover keeps the reliable record.

## Kindle readiness (added 2026-10-30; the PW3 is not in hand yet)
Done ahead of the device so the crossover is one sitting:
- **Hash parity proven.** `tools/koreader_hash.py` reproduces KOReader's partial-MD5 and matches Kavita's stored `koreaderHash` for *Time War* (`6C90F3D5…ADD99`). Any EPUB can be checked against Kavita before it ever reaches a device. KOReader quirk: the first sample offset wraps to 0 (LuaJIT `lshift(1024,-2)`).
- **The Kobo stands in for the Kindle** for everything that is KOReader behaviour (kosync settings, sync dialogs, annotation plugin, follow-along page turns). Only Kindle-specific facts remain: Wi-Fi/suspend behaviour, e-ink refresh, jailbreak/firmware. Those are the device checklist in `research/devices.md` and spikes S8-on-device and S10.
- **Same server, same user for both KOReader devices**, so the hub sees one reader with two devices (Q6/Q7 defaults). Kindle uses the identical KOSync URL as the Kobo.
- **Matching is by hash, not filename**, so the same EPUB bytes must be on Kobo, Kindle and Kavita. Never re-export through Calibre between devices.

## Readers (multi-user, added 2026-11-02)
- A **reader** is a person. Each has a `reader_id`, their own Kavita user + API key, ABS user + API key, KOSync credentials, optional Fable login, devices, and Telegram chat. Config lives per reader, never as one global key (K6).
- **Shared:** book identity, files, alignment maps (read-only). **Never shared:** progress, annotations, bookmarks, stats, queue items, alerts, devices (R15).
- Every canonical record (Book identity excepted) gets `reader_id` in its primary key; every query filters on it; the test suite runs each scenario with two readers and asserts zero cross-visibility (K1, K3, K4).
- BookBridge 7.10 already isolates progress, KOSync documents and stats per user (changelog "properly isolated"); we keep that and add the same to the Kavita and ABS spokes and the annotation exchange.
