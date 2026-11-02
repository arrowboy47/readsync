# Device inventory (readsync Task 05)

Read from the devices' file systems over USB on 2026-11-02 (read-only; secrets not copied). Both KOReader devices were in hand.
Feeds EDGE_CASES A8, F1, I5 and owner questions Q6/Q7.

## Summary
| | Kobo | Kindle |
|---|---|---|
| Device | Kobo, hardware code `N778…`, firmware 4.38.23429 | Jailbroken Kindle (USB id: Paperwhite family; confirm model on device) |
| KOReader | **v2024.11** (`.adds/koreader`) | **v2026.07.2** (`/koreader`) |
| KOSync server set? | **No** (no server/credentials stored) | **No** (only the settings block) |
| Auto sync | off | off |
| Sync to newer state | `sync_forward = 1` (prompt) | `sync_forward = 1` (prompt) |
| Sync to older state | `sync_backward = 3` (disable) | `sync_backward = 3` (disable) |
| Document matching | `zsync = true` flag seen; method not stored | `checksum_method = 0` (binary partial-MD5; matches `tools/koreader_hash.py`) |
| Auto-suspend | never (`-1`) | 900 s |
| Wi-Fi on suspend | not set | `auto_disable_wifi` and `auto_restore_wifi` both on |
| Reading stats | `statistics.sqlite3`, 11 books, last read *Remain* (Jul 2026) | `statistics.sqlite3`, 67 entries (many web-novel chapters), last read Oct 2026 |
| Books | 13 files in `Books/` (EPUB, 1 PDF), 4 `.sdr` sidecars | 24 EPUB + 2 PDF in `Books/`, ~9 `.sdr` sidecars |
| Koinsight | no plugin | plugin installed, `server_url` points at `http://104.168.7.21:3000` (an old address, **stale**: Koinsight now lives on thebigbox, see vault note) |
| OPDS | `opds.koplugin` present, no list saved | Kavita OPDS feed saved as "bigboxonline" and "Ebooks" (`kavita.thebigbox.duckdns.org/api/opds/<key>`). **The Kavita API key is embedded in that URL; it is not recorded here.** |
| Other plugins | `agenda.koplugin` (the dashboard); stock plugins | stock plus rakuyomi (manga), wallabag, SSH, httpinspector, exporter |
| Device ID | `01CB5980…` | `67A1FAAE…` |

## What this means for readsync
- **Neither device syncs progress anywhere today.** No KOSync server on either. So there is no existing state to migrate and no risk from a pre-existing server; the hub will be the first.
- **Version gap:** Kobo KOReader is 18 months older than the Kindle's. Update the Kobo to match before the Phase 3 plugin goes on (the annotation exchange targets recent versions).
- **Safe defaults already in place:** auto sync off, newer = prompt, older = disable. Keep these for the first tests.
- **Kindle Wi-Fi:** it turns Wi-Fi off on suspend and restores it on wake, so progress must be pushed **before** suspend (EDGE_CASES B6). 900 s auto-suspend bounds how stale a push can be.
- **Stale Koinsight URL on the Kindle** (104.168.7.21): reading stats from the Kindle are going nowhere. Repoint when Koinsight is wired in.
- **Paired titles on the devices (both ebook and audiobook exist):** the Kindle has *Red Rising* in its stats; check which of the 5 paired titles are on the devices. Book bytes must be identical to Kavita's copy because matching is by hash.
- **Duplicate risk:** the Kindle and the Kobo carry different copies of some titles (e.g. *Remain*, *Building Applications with AI Agents*). Same title, different file = different hash = separate progress. Kavita's copy should be the one pushed to devices (OPDS), not sideloaded copies.

## iPhone
- Audiobook app: **Audiobookshelf** (iOS app). Version, server URL it uses, and downloads: still to confirm on the phone.
- No ebook reader connected to Kavita yet. Recommendation given 2026-11-02 (see chat / ARCHITECTURE.md → iOS reader).
- Fable app: to confirm.

## Books on the devices vs Kavita (2026-11-02, `tools/device_vs_kavita.py`, hash match, read-only)
- **Kobo:** 7 of 13 files are byte-identical to a Kavita copy. Not in Kavita (or a different file): *11/22/63*, *Psychology and Work*, 4 PDFs (Hogg/McKean/Craig, Raschka, *Deep Learning with Python*, Murach's JS).
- **Kindle:** 14 of 26 match. Not in Kavita or a different file: *Tress of the Emerald Sea*, *Rich Dad's Guide to Investing*, *Atomic Habits*, *Deep Learning with Python* (EPUB), *Dune*, *Fellowship of the Ring*, *Handmaid's Tale*, `RR.epub` (Red Rising?), *The Drowning Faith*, *House in the Cerulean Sea*, *Tomorrow ×3*, *Hands-On Machine Learning*.
- *Remain* and *GRE Prep* sit on both devices as the same bytes as Kavita, so progress will line up there from day one.
- Action before the first real sync: for each "no match" book either add it to Kavita (then push that exact file to the device via OPDS) or accept that it stays local-only. Same title with different bytes will not share progress.
