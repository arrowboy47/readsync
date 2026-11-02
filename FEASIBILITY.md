# readsync — feasibility briefing (2026-10-20)

Evidence: `research/01`–`04`. Status: **planning; go/no-go after the Phase 1 spikes in `BUILD_PLAN.md`.**

## Verdict

**Feasible, and most of the hard parts already exist as open source.** The project to know is
**BookBridge** (`github.com/cporcellijr/bookbridge`, MIT, Python/Docker, v7.10.0 on 2026-10-15, very active).
Its source (`research/04`) shows it is already a sync hub with:

- its own **KOSync server** (KOReader and Readest point at it);
- ABS ↔ KOReader ↔ Kavita **progress** sync (ABS via Socket.IO, Kavita via Kavita's KOSync endpoint);
- **audio↔ebook alignment** stored per book (CPU forced alignment, Whisper fallback);
- a KOReader plugin (BridgeSync) that uploads **reading stats and sessions** and exchanges **annotations both
  ways** with an annotation hub that has pluggable "spokes" (BookOrbit, Grimmory, Readest, Hardcover, BookFusion).

**What nobody has built, and what readsync adds** (as new BookBridge spokes, ideally upstreamed):

1. **Kavita annotation spoke** — KOReader/Readest highlights ↔ Kavita annotations (Kavita has full CRUD since 0.8.8).
2. **ABS bookmark spoke** — ABS bookmarks ↔ Kavita annotations via the alignment map; the user's Whisper-clip
   lookup as fallback and cross-check.
3. **Fable writer** — ported from ShelfSync, which has working Fable login + a `reading_progress` POST.
4. **O roll-up** — reading/listening time and dates merged from BookBridge stats, Kavita history, ABS listening stats.
5. **Follow-along mode** — the Kindle page tracks ABS audio for immersion reading.

## Feasibility by data type

| Flow | Verdict | Why |
|---|---|---|
| P: ABS ↔ Kavita ↔ KOReader ↔ iOS | **High** | BookBridge does it today; Kavita and ABS APIs are solid |
| H/B: KOReader ↔ Kavita | **Medium** | API exists; XPath vs xpointer don't convert cleanly → anchor on text quote. Spike S1 decides |
| B/H: ABS ↔ Kavita | **Medium-high** | Alignment map gives time ↔ text both ways. ABS bookmarks carry only a `title` |
| O into Kavita | **Low** | Kavita stats are read-only. O lives in BookBridge's DB, not Kavita |
| Fable | **Low-medium** | Works via unofficial API; ToS forbids it; no reading-time field |
| Immersion on Kindle | **Medium-low** | No push to KOReader → plugin polls ~20 s with Wi-Fi on; page trails audio 20–60 s; battery cost |
| Manga/comics | **High, P only** | Panels writes progress natively; Kavita annotations are EPUB-only |

## Strengths

- Kavita can be the real source of truth for **P, B and H**: full CRUD plus SignalR events
  (`UserProgressUpdate`, `AnnotationUpdate`), so changes can be reacted to in seconds.
- Reuse over rebuild: alignment, KOSync server, device annotation exchange, stats upload (BookBridge); Fable
  client (ShelfSync).
- Homelab already has the pieces: Whisper large-v3-turbo on Jadu GPU1 behind an OpenAI-compatible shim
  (`192.168.1.158:9092`), Koinsight's KOReader history, thebigbox with 3.3 TB free and the house deploy pattern.
- ABS streams audio files over its API, so clips can be cut with no filesystem access.

## Shortcomings and risks

1. **Small overlap today:** 5 titles in both libraries, 4 as EPUB. Red Rising (5 books) and Deep Work have audio only.
   *Resolved by owner policy (2026-10-21):* from now on every book exists in both ABS and Kavita; today's gaps are
   transitional. Edition mismatches (abridged audio, different translation) can still happen, so the alignment
   coverage check stays as a safety net.
2. **Real-time ends at the device.** KOReader pulls on open/resume/Wi-Fi reconnect; the ABS app keeps its own
   position while playing. Server side is seconds; devices catch up on next open, unless follow-along polls.
3. **Lossy positions.** Kavita stores element XPath without char offset; xpointers can't be computed reliably outside
   crengine. Mitigation: text-quote anchors resolved natively at each end. Some highlights may land a few words
   off or fail into a review queue.
4. **Fable:** ToS explicitly bans scripts/reverse engineering → account-ban risk. Fragile (Everand-owned, may change).
   No reading-time field: Fable gets status, % and dates. **Hardcover** (official API, `progress_seconds`) is the
   reliable record.
5. **Version drift:** Kavita 0.8.9.1 (upstream 0.9.1.4; KOSync 400s reported on 0.8.9.1, issue #4518), ABS 2.32.1
   (upstream 2.37.1; API-key socket auth needs ≥2.37.0). Both on unpinned `:latest`.
6. **Security** (found in inventory, not in the vault): Kavita/ABS public on `*.thebigbox.duckdns.org` **and**
   `kavita.adduo.fyi` / `audiobookshelf.adduo.fyi` via the RackNerd relay, app login only; Kavita API keys in URL
   paths land in NPM logs; Koinsight public with no auth. Off-LAN Kindle sync needs a deliberate public endpoint
   (Kindle can't run WireGuard).
7. **Kavita library hygiene:** nested libraries index files twice; 2 Fiction files unindexed.
8. **Maintenance:** depends on BookBridge, Kavita, KOReader (fast-moving) and an undocumented Fable API.
   Expect breakage every few months. Upstreaming the spokes is the main defence.

## "Kavita as source of truth" — what it can and can't mean

| Data | Truth | Mechanism |
|---|---|---|
| P | Kavita | Every progress write lands in Kavita; Kavita wins ties |
| B, H | Kavita | Kavita annotations are the curated set; Kavita wins edit conflicts; deletes in Kavita propagate |
| O | readsync / BookBridge DB | Kavita has no write API for time/sessions; Kavita's own history is one input |

BookBridge's store still holds a relay copy of every annotation (that is how devices exchange deltas). The policy,
not the storage location, is what makes Kavita authoritative.

## Recommended iOS setup

- EPUB: Kavita web reader as a home-screen PWA → native B/H/P, zero integration (scenarios 4/7 collapse into 5/6).
- Offline EPUB: Readest via KOSync (highlights through BookBridge's Readest spoke — verify).
- Manga: Panels.
- True read-along for paired titles: Storyteller app (optional, later).
