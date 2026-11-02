# readsync — edge cases and failure scenarios

**Written:** 2026-10-21, before Phase 0. **Feeds:** the sync rules in `ARCHITECTURE.md`, the spikes and tests in
`BUILD_PLAN.md`. Every case here becomes a test in `tests/edge/` (named by its ID) when its phase is built.

**Tags**

- **[BB]** BookBridge already handles it (code cited). Still gets a regression test: the fork must not break it.
- **[BB risk]** BookBridge's current behaviour causes the problem.
- **[NEW]** readsync has to build it.
- **[SPIKE]** behaviour unknown; a Phase 1 spike answers it (S-number given).
- **[NOTE]** expected behaviour to document, nothing to build.
- **[OUT]** out of v1 scope.

BookBridge code referred to below (commit `65f1cc2`, in `refs/bookbridge/`):

| What | Where | Default |
|---|---|---|
| Backward-move hold until corroborated | `src/sync_manager.py` `_should_hold_backward_leader`, `SYNC_REWIND_HOLD_SECONDS` | 300 s |
| Rollback veto for a behind candidate with an older service timestamp | `SYNC_ROLLBACK_VETO_SECONDS` | 600 s |
| Per-client trail of external positions ("did it keep moving?") | `src/services/observation_trail.py` | 600 s TTL |
| Which device row answers a KOSync GET | `src/services/kosync_device_arbiter.py`, `KOSYNC_ACTIVE_DEVICE_WINS` | `shadow` (log only) |
| Wait after the last KOReader PUT before fanning out | `src/api/kosync_server.py`, `KOSYNC_PUT_DEBOUNCE_SECONDS` | 300 s |
| Wait after ABS playback activity before fanning out | `ABS_SOCKET_DEBOUNCE_SECONDS` | 30 s |
| Minimum movement that counts | `SYNC_DELTA_KOSYNC_PERCENT`, `SYNC_DELTA_ABS_SECONDS`, `SYNC_DELTA_BETWEEN_CLIENTS_PERCENT` | 0.5 %, 60 s, 1 % |
| Periodic full cycle | `SYNC_PERIOD_MINS` | 5 min |
| Annotation exchange (device ⇄ hub) | `src/db/database_service.py` `exchange_koreader_annotations`; plugin `bridge_annotations.lua` | key = hash(datetime, pos0) |
| Plugin self-update | `plugins/bridgesync.koplugin/main.lua` `_installPluginZip` | on |

---

## 1. Cross-cutting rules (R1–R15)

The cases below collapse into these rules. They replace and extend the "Sync rules" in `ARCHITECTURE.md`.

| # | Rule |
|---|---|
| **R1** | **Activity time, not arrival time.** Every position and annotation carries `activity_at` (when the reading happened, from the source: ABS `lastUpdate`, the KOReader session log, Kavita `lastModified`) and `received_at`. Ordering uses `activity_at` when R2 trusts it, otherwise `received_at`. KOSync itself only gives arrival time. |
| **R2** | **Device clocks are suspect.** KOReader writes local time with no zone; a Kobo resets its clock after a dead battery; a Kindle off Wi-Fi drifts. Device time is trusted only inside `[received_at − 30 d, received_at + 5 min]`, otherwise arrival time is used and the record is flagged. Device time orders events *from that device*; across devices, corroboration (R5) decides. |
| **R3** | **Never write into a surface that is in use.** If the target has an active session on that book (ABS playback session open or a progress event < 2 min old; a Kavita web progress save < 2 min old), the write waits in the outbox until it goes idle. KOReader can't be pushed anyway. The only exception is follow-along, which the device pulls on purpose. |
| **R4** | **Implausible jumps are held, both directions.** Backward > 2 % (existing rule) **and** forward faster than plausible: text > 3× the measured reading pace, or > 5 % in < 1 min; audio scrub > 10 min. A held jump applies once the same surface keeps advancing from the new spot (BookBridge's observation trail). Pace for an offline batch comes from the device's session log, not from the gap between arrivals. |
| **R5** | **A rewind only counts if the device knew.** A backward position becomes the truth only when the device had already pulled the newer position and moved away from it. A device that never saw the newer position (offline, stale) is on a *divergent branch*: furthest wins silently, and if that device keeps advancing on the old branch (> 20 pages), the owner is asked. |
| **R6** | **Close and suspend flush.** Debounces apply only to mid-session pushes. A KOReader close or suspend, an ABS session close, or leaving the Kavita reader triggers the fan-out at once. |
| **R7** | **Err backward on hand-off.** Converted positions land at the start of the paragraph, or ≤ 15 s before the matching audio, never after. Re-hearing a sentence is fine; skipping one is not. |
| **R8** | **Deadband and echo.** A position that comes back within tolerance of what we wrote (same paragraph, 0.5 %, 60 s) is our echo and is dropped. An idle book produces zero writes in 30 minutes (test). |
| **R9** | **Never lose text** (decided, Q1/Q2). An edit-vs-edit conflict on a note keeps both texts. A delete that loses to a later edit resurrects the edited annotation; a delete that wins still archives the losing note text in the hub. |
| **R10** | **Mass-delete guard.** Any one exchange or diff that would delete > 3 annotations, or > 20 % of a book's annotations, is quarantined: not propagated, owner alerted, and the device gets them back as adds after the owner says so. |
| **R11** | **Outbox and idempotency.** Every outward write goes through an outbox row with a deterministic key. Before re-sending after a crash, the target is searched for the key or quote, so a retry never creates a duplicate. Writes use compare-and-set: re-read the target's `lastModified` just before writing and re-decide if it moved. |
| **R12** | **Read-only reconcile after a restore or long outage.** After the hub is down > 30 min, or any restore (hub, Kavita, ABS), the first cycle pulls every surface, writes nothing, and reports the diff. Writing resumes once R4, R5 and R10 pass. |
| **R13** | **Compare positions, never percents.** Each surface computes % differently (front and back matter, credits, page layout, narration). The hub compares canonical positions, and never maps audio ↔ text by %. Fable and Hardcover get the canonical text %. |
| **R14** | **Single writer, single sync server.** One hub instance holds a DB lease; spike and test containers run with sync off. Each device points at exactly one KOSync server (the hub), never also Kavita's or Koinsight's. |
| **R15** | **One reader, one island.** Every record (progress, annotation, bookmark, stats, review item, alert, credential, device) carries a `reader_id` and every query filters on it. Only book identity, files and alignment maps are shared (they describe the book, not a person). Nothing a reader did is visible to, or written by, another reader's sync. Cross-reader features (shared highlights, "she is on ch 9") are opt-in per reader and out of v1. |

---

## 2. Cases

### A. Offline and connectivity

**A1 — Kindle offline for a session, behind the truth when it reconnects.** Monday: Kindle offline, reads ch 5→8.
Tuesday: ABS ch 8→12, synced. Wednesday: Kindle Wi-Fi comes on and pushes ch 8. KOSync stamps arrival time, so
"newest wins" would drag everything back to ch 8.
*Rule:* R1 (activity Monday, from the session log) + R5 (Kindle never saw ch 12) → ignored; Kindle offered ch 12 on
its next pull. *Status:* [BB] holds uncorroborated backward moves; [NEW] activity time. *Test:* `A1_offline_stale_push`

**A2 — Kindle offline, ahead when it reconnects.** Kindle reads ch 5→10 offline; everyone else is at ch 4. It arrives
as one push that looks like "5 chapters in one second", which R4 would wrongly hold.
*Rule:* R4 pace from the device's session log (3 h of sessions) → plausible → applied. *Status:* [NEW]

**A3 — Both advanced independently from the same point.** Kindle offline 5→8, ABS 5→9. The Kindle arrives behind.
*Rule:* R5 divergent branch, furthest wins, no alert (one reader consumed both). *Status:* [BB] furthest wins.

**A4 — Highlights made offline on the Kindle.** Uploaded at the next exchange with their device datetime; union merge.
*Status:* [BB] the watermark advances only when every chunk and ack succeeded (`bridge_annotations.lua`).

**A5 — Offline note edit vs an online delete.** Kavita deletes highlight X on Tuesday; the Kindle added a note to X on
Monday night while offline and uploads Wednesday.
*Rule:* R9: the delete is newer, so it wins, but the Monday note text is archived in the hub and listed in the
digest. If the edit had been newer, the annotation comes back. *Status:* [NEW], see Q2.

**A6 — Connection drops mid-exchange.** Partial upload. *Status:* [BB] plugin replays all chunks; hub upserts by
`hash(datetime, pos0)`, no duplicates. The Kavita spoke must be just as idempotent (R11). [NEW]

**A7 — Hub crashes after Kavita accepted an annotation but before saving the mapping.** A naive retry creates a
duplicate in Kavita. *Rule:* R11 outbox, then search Kavita by chapter + quote before creating. *Status:* [NEW]
*Test:* `A7_crash_between_post_and_commit`

**A8 — Wi-Fi drops at suspend, so the last push fails.** On resume KOReader pulls a server position *behind* its own.
*Rule:* KOReader "Sync to an older state" must be **Prompt** or **Never**, never Silent (Q7). Our side holds the stale
row until the next push. *Status:* [SPIKE] on the PW3: does KOReader retry a failed push, or wait for the next one?

**A9 — ABS app listening offline (car, plane, downloaded book).** Two hours of listening reach the server later as
local sessions. If ABS keeps the original `lastUpdate`, R1 works; if it stamps arrival time, this becomes A1.
*Status:* [SPIKE S7]

**A10 — ABS bookmark while offline.** Does the app allow it, queue it, or drop it? *Status:* [SPIKE S7]

**A11 — Hub down while devices are in use** (thebigbox reboot, image upgrade). KOSync pushes fail (progress is state,
so the next push carries it), the plugin retries annotations, and ABS socket events are lost.
*Rule:* catch-up on start: ABS items-in-progress and a bookmark-snapshot diff, Kavita progress and annotations for
mapped books; R12 if down > 30 min. *Status:* [BB] 5-min periodic cycle covers progress; [NEW] bookmark diff and R12.

**A12 — Kavita down (including the Phase 0 upgrade itself).** ABS ↔ KOReader keeps syncing; Kavita writes wait in the
outbox; on return, read Kavita first, then replay (newest only for progress, all for annotations).
*Meaning of "source of truth":* Kavita wins ties and conflicts; the hub ledger is the memory while Kavita is away.
*Status:* [NEW]

**A13 — ABS down.** Same as A12 with an ABS outbox. *Status:* [NEW]

**A14 — Whisper unavailable** (Jadu rebooting after a GPU wedge, GPU1 busy). Clip-fallback jobs queue with backoff for
up to 24 h through the llm-gate scheduled lane; the alignment-map path is unaffected; no bookmark is ever dropped.
*Status:* [NEW]

**A15 — Battery dies before KOReader saves the sidecar.** The highlight is lost on the device itself; nothing
downstream can recover it. *Status:* [NOTE] shorten KOReader's document-settings save interval.

**A16 — Kindle never closes books, only suspends.** Server-side annotations for an open book apply live
(`applyLive`), otherwise deferred to close. *Status:* [BB]; confirm on the PW3 in S8.

### B. Progress differences between surfaces

**B1 — Two e-readers at different points.** Kobo at 20 %, Kindle at 60 %; opening the Kobo pulls 60 %.
*Status:* [BB] arbiter in `shadow` mode; leave it there until Phase 2 logs show its choices are right.

**B2 — The stale-device trap.** The Kobo is opened offline at 20 % and read for 15 pages without noticing. Wi-Fi comes
on; it pushes 21 %, then 21.5 %. BookBridge's corroborated-rewind rule sees "same device, advancing" and accepts it,
dragging Kindle, ABS and Kavita back to 21 %.
*Rule:* R5: the Kobo never pulled 60 %, so it's a divergent branch; 60 % stays; after 20 pages the owner is asked
"Kobo is at 21 % while the book is at 60 %: keep 60 % or move to 21 %?". *Status:* [BB risk] → [NEW] guard.
*Test:* `B2_stale_device_corroborated_rewind`

**B3 — Looking back.** Flip back three chapters to check a name, then return. Backward pushes are held 300 s and
resolve when reading continues. If the book is closed on the look-back page, that single sample is never corroborated
and is dropped. *Status:* [BB]

**B4 — Fell asleep listening.** The audio ran two hours past; the user rewinds in the morning. The forward run looked
plausible (1× pace) so it propagated; the rewind from an audio client is trusted and propagates back.
*Rule:* audio progress reaches text surfaces at session close or the next debounce (KOReader only pulls on open
anyway). Fable is protected by the 30-min debounce and the finish gate (H7). *Status:* [BB] + [NOTE] use the ABS sleep
timer.

**B5 — Peek at the ending, TOC mis-tap, accidental far jump.** 40 % → 98 % in one push.
*Rule:* R4 hold; applied only if reading continues from there; never triggers "finished". *Status:* [NEW] (BookBridge
holds backward moves only). *Test:* `B5_peek_at_ending`

**B6 — Fast hand-off inside the debounce.** Close the Kindle, start ABS in the car 2 minutes later. The 300 s KOSync
PUT debounce hasn't fired, so ABS plays the old spot.
*Rule:* R6, BridgeSync sends a close/suspend signal that triggers the cycle immediately. Also needs the ABS app to
fetch server progress when play is pressed. *Status:* [NEW] + [SPIKE S7]

**B7 — The reverse hand-off.** Stop ABS in the driveway, open the Kindle a minute later. ABS's 30 s debounce plus the
cycle may not be done when KOReader pulls on open, and KOReader won't pull again until the next resume.
*Rule:* ABS `user_session_closed` triggers the cycle at once (BookBridge doesn't listen for it). *Status:* [NEW] +
[NOTE] "if the page is wrong, suspend/resume once".

**B8 — Precision ping-pong.** Kavita stores element-level positions, KOReader page-top xpointers, ABS seconds; each
conversion snaps slightly, comes back as a change, and loops.
*Rule:* R8. *Status:* [BB] deltas + own-write window; [NEW] idle test. *Test:* `B8_idle_book_zero_writes`

**B9 — Kavita progress is chapter-only.** If `bookScrollId` is empty (some reading mode?), hand-off lands at chapter
start, up to a chapter of re-reading. *Status:* [SPIKE S2] which Kavita reader modes fill `bookScrollId`.

**B10 — Every surface shows a different % for the same spot** (KOReader 43 %, ABS 47 %, Kavita 41 %).
*Rule:* R13, expected and not a bug. *Status:* [NOTE] in the user guide.

**B11 — Extra material on one side.** Audio has an intro, credits or an author's note; the EPUB has an appendix,
glossary, acknowledgements or a preview of the next book. Positions outside the alignment map clamp to the nearest
anchor; "finished" from text means reaching the last narrative spine item, not 100 %. *Status:* [NEW]

**B12 — Alignment coverage too low** (abridged audio, a different edition or translation). Pairing is refused below
90 % coverage; text and audio keep separate positions and the book is flagged. *Status:* [NEW], coverage measured in S3.

**B13 — Multi-file audiobook.** ABS time is book-global; clips map it to track + offset, and a clip that crosses a file
boundary is cut from two files or the window is shifted. *Status:* [NEW]

**B14 — Playback speed.** Media time is speed-independent, so positions are fine; listening *time* for O must be wall
clock (H4). *Status:* [NOTE]

**B15 — Deliberately different positions** (audio ahead on the commute, text re-reading an earlier part).
*Rule:* per-book `link_positions: off` stops progress fan-out for that book; highlights still sync. *Status:* [NEW]

**B16 — Two active readers on one account** (someone else using ABS). Two surfaces advancing at once > 5 % apart →
progress frozen for that book, owner alerted. *Status:* [BB] falls back to furthest wins; [NEW] freeze.

**B17 — Kavita "mark as read" / "mark unread".** Instant 100 % or 0 %. An explicit action in the truth surface is
applied, not held; "finished" still goes through the finish gate (H7), and "unread" after a finish starts a new read
(H8). *Status:* [NEW]

**B18 — Font or margin change on KOReader.** Page numbers change, xpointers don't; page numbers never cross surfaces.
*Status:* [BB]

**B19 — Kavita web reader open while the hub writes its progress.** The reader may overwrite it on its next save, or
jump under the user. *Rule:* R3. *Status:* [SPIKE S2] does an open reader react to a server-side progress change?

**B20 — Writing ABS progress while the app is playing.** The app's next sync overwrites it, or the audio jumps.
*Rule:* R3. *Status:* [SPIKE S7]

**B21 — The target moves while the hub is deciding.** *Rule:* R11 compare-and-set. *Status:* [NEW]

### C. Immersion reading (KOReader + ABS on the same book, at the same time)

Session state per book: `solo` → `immersion` → `paused` → `solo`. **Enter** when an ABS session is open on a paired
book, the KOReader device has follow-along on for it, and the two positions are within 2 pages. **Paused** when the
audio is paused > 2 min. **Exit** when the audio session closes or follow-along is turned off.

**C1 — Who leads.** Audio. Kindle pushes during immersion corroborate, they don't compete. ABS is never written during
the session (R3). Kavita gets the position at most every 5 min and at session end. *Status:* [NEW]

**C2 — Eyes ahead of the audio** (fast reader, manual page turn forward). Follow-along never pulls the page back; it
only advances once the audio passes the end of the current page. *Status:* [NEW] *Test:* `C2_never_pull_back`

**C3 — Eyes behind on purpose** (flip back to re-read). Follow-along pauses until the reader returns to the audio's
page or 2 min pass; a small on-screen marker shows it's paused. *Status:* [NEW]

**C4 — Audio skip-back 30 s.** No page change unless the audio goes back more than a page; more than 2 pages back
counts as a deliberate rewind and the page jumps back once. *Status:* [NEW]

**C5 — Pause the audio, keep reading.** State `paused`; the Kindle leads after 2 min. Once the ABS session is idle,
ABS gets the text position (R7 back-off) so audio resumes where the eyes are. *Status:* [NEW], see Q5.

**C6 — Press play again before C5's write lands.** The audio is behind the page; follow-along won't pull back (C2), so
a few sentences are heard again. *Status:* [NOTE] acceptable.

**C7 — Lag floor.** The page trails by ABS's progress interval + poll interval + e-ink refresh. At 2× a page lasts
20–40 s, so the Kindle could always be 1–2 pages behind.
*Rule:* dead reckoning: the plugin downloads the chapter's word timings once and advances from
`last audio position + rate × elapsed`, capped at one progress interval past the last event, and stops when no fresh
event arrives. *Status:* [NEW] + [SPIKE S7, S10]

**C8 — Paused audio while dead reckoning.** The Kindle overshoots by at most the cap in C7, then holds. *Status:*
[SPIKE S7] how fast a pause reaches the server.

**C9 — Kindle Wi-Fi drops, or KOReader turns Wi-Fi off to save power.** Follow-along stops and shows "follow paused
(offline)", resumes on reconnect, and never jumps backward on reconnect. *Status:* [NEW]

**C10 — Programmatic page turns don't reset the auto-suspend timer.** The Kindle sleeps mid-chapter and Wi-Fi drops.
The plugin must hold off auto-suspend while following; battery cost measured. *Status:* [SPIKE S10]

**C11 — Different books** (audio on book A, Kindle on book B). No immersion; both solo. *Status:* [NEW]

**C12 — Third surface open** (Kavita web also open). Only the follow-along device follows; Kavita web is left alone
(R3). *Status:* [NOTE]

**C13 — Alignment gaps** (narrator reads headings or footnotes; text has tables or images that aren't read). Dead
reckoning interpolates across unmapped spans instead of stalling. *Status:* [NEW]

**C14 — The map is a page off in one passage.** If S3's accuracy gate passes this should be rare; a later "I'm here"
tap on the Kindle could re-anchor the session. *Status:* [OUT v1]

**C15 — Reading time counted twice** (listening and reading the same minutes). O merges time as a union of intervals
per book (H1). *Status:* [NEW]

**C16 — Highlight made on the Kindle during immersion.** Uploaded at suspend or close; doesn't count as navigation; the
canonical annotation also records the audio time, ready for an ABS bookmark. *Status:* [NEW]

**C17 — ABS bookmark during immersion.** Resolved via the map, lands in Kavita, reaches the open Kindle by live apply
or at close. *Status:* [BB] + [NEW]

**C18 — Immersion in the iOS PWA / Kavita web.** Kavita's reader can't follow audio. *Status:* [OUT v1]; Storyteller is
the "Next" option.

### D. ABS bookmarks → Kavita

**D1 — Reaction delay.** The bookmark is tapped 2–10 s after the moment. Quote = the sentence(s) spanning
`[T − 15 s, T]`; the anchor sits at `T − 3 s`; the clip ends at T. *Status:* [NEW]

**D2 — Bookmark in silence, music or a chapter announcement.** The map path doesn't need the clip's words; the clip
fallback widens back to `T − 30 s`, else review queue. *Status:* [NEW]

**D3 — Repeated text** (a refrain, "Chapter One", stock dialogue). ±10 % window, runner-up margin, map first.
*Status:* [NEW]

**D4 — Whisper hallucinates on music or noise.** No match clears the threshold → review queue, never a guess.
*Status:* [NEW]

**D5 — Bookmark renamed later in ABS** (a note added after the fact). ABS keys bookmarks by time, so a title change is
an edit → the Kavita annotation's comment updates. *Status:* [NEW]

**D6 — Bookmark deleted in ABS.** The Kavita copy is deleted only if it wasn't edited in Kavita after the last sync;
otherwise it stays and is flagged (R9). *Status:* [NEW]

**D7 — Two bookmarks at the same second.** ABS's time key collides; treated as one bookmark edited. *Status:* [NOTE]

**D8 — Bookmark on an unpaired title** (Red Rising, Deep Work). Kept in the hub as an orphan with its time and the
clip's transcript; placed automatically when an EPUB is added later ("late pairing backfill"). *Status:* [NEW]

**D9 — A burst of bookmarks.** Clip jobs are rate-limited through llm-gate's scheduled lane. *Status:* [NEW]

**D10 — The review queue is never reviewed.** Weekly digest; after 30 days the item is placed as a chapter-level note
marked "approximate". *Status:* [NEW], see Q8.

**D11 — Kavita → ABS.** Which annotations become ABS bookmarks is Q3. Title = the note, else the first ~60 chars of the
quote; ABS's title length limit is unknown. *Status:* [SPIKE S7]

**D12 — Alignment map rebuilt** (BookBridge upgrade or EPUB replaced). Stored bookmark times are re-resolved against the
new map; the quote anchor wins over a cached offset. *Status:* [NEW]

### E. Highlights and notes

**E1 — Same passage highlighted on two surfaces.** Merged when they're in the same spine item and the quotes overlap
≥ 80 %: union of the ranges, notes joined. *Status:* [NEW] *Test:* `E1_dedupe_overlapping`

**E2 — KOReader highlight extended at its start.** The hub keys annotations by `hash(datetime, pos0)`, so a new pos0
arrives as delete + add, and a note added in Kavita would be lost with the delete. *Rule:* pair a delete and an add
with the same datetime and overlapping text into one edit. *Status:* [BB risk] → [NEW]

**E3 — Note edited on two surfaces between syncs.** The current rule "Kavita wins" silently drops the other text.
*Rule:* R9, keep both. *Status:* rule change, Q1.

**E4 — Colours and styles don't map 1:1** (KOReader lighten/underline/strikeout/invert + colours vs Kavita's
highlight slots). Each side keeps its own original style; mapping applies only when creating the copy; a round trip
never rewrites the original. *Status:* [NEW]

**E5 — Highlight across a chapter (spine) boundary.** A Kavita annotation lives inside one page; split into linked
parts. *Status:* [NEW], check in S1.

**E6 — Text that differs invisibly.** Soft hyphens from KOReader's hyphenation, ligatures, smart quotes, non-breaking
spaces, zero-width characters, footnote markers inside the selection. Normalised for matching only; the original is
kept for display. *Status:* [NEW] *Test:* `E6_normalisation`

**E7 — Highlight in a footnote pop-up, table or caption** with no Kavita equivalent. Kept in the hub, flagged
"unplaced". *Status:* [NEW]

**E8 — Sidecar lost** (book deleted and re-downloaded, `.sdr` folder wiped, settings reset). The device sends a complete
key list without its old keys, and the hub tombstones every annotation that device had
(`exchange_koreader_annotations`: "tombstones entries the device deleted (key missing from a complete key list)").
Those deletes then spread to Kavita and every other device.
*Rule:* R10. *Status:* [BB risk] → [NEW] guard; S9 reproduces it. *Test:* `E8_sidecar_loss_mass_delete`

**E9 — Device reinstalled with a new device id.** Full download; its re-uploaded annotations match by
`hash(datetime, pos0)`, no duplicates. *Status:* [BB]

**E10 — Kavita-made highlight going to KOReader.** KOReader needs xpointers, and its maintainers say they can't be
computed reliably outside crengine. *Rule:* the plugin resolves quote + prefix/suffix + spine index on the device with
crengine's own search. *Status:* [NEW] + [SPIKE S8]

**E11 — First run.** 181 existing KOReader annotations (Koinsight) plus whatever Kavita has. The first run is a dry-run
report; the owner approves; books not in Kavita become orphans. *Status:* [NEW]

**E12 — KOReader page bookmark** (dog-ear, no text). The first sentence of the page becomes the anchor, kind
`bookmark`, own colour. *Status:* [SPIKE S1] whether Kavita accepts an annotation with empty `selectedText`.

**E13 — Note text with markup, HTML, emoji or huge length.** Escaped before it reaches Kavita or Telegram; BridgeSync
already caps notes at 5,000 and text at 10,000 chars. *Status:* [NEW]

**E14 — Kavita edit to a highlight on a book open on the Kindle.** Applied live or at close. *Status:* [BB]

**E15 — Kavita-side delete seen only as absence** (polling diff) rather than an `AnnotationUpdate` event. Prefer
events; absence-based deletes go through R10. *Status:* [NEW]

**E16 — EPUB replaced with a corrected edition.** Re-anchor every annotation by quote; failures are flagged, never
dropped. *Status:* [NEW]

### F. Book identity and files

**F1 — Device copy isn't byte-identical to Kavita's** (Calibre send with metadata embedding, a conversion, a sideload).
A different `doc_md5`, so nothing matches. *Rule:* devices get books from Kavita's OPDS (OPDSfoldersync) and use
KOReader's binary hash; anything else is mapped by hand in BookBridge's UI. *Status:* [BB] manual map; policy Q6.

**F2 — Same file in two Kavita libraries** (the nested libraries). One md5, two chapter ids. *Status:* Phase 0 Task 03,
which runs before any mapping exists.

**F3 — Kavita rescan changes ids** (Phase 0's unnesting does exactly this). Writes 404 → re-resolve by md5
(`KoreaderHash`) and retry. *Status:* [NEW]

**F4 — EPUB replaced in Kavita.** New md5; KOReader sees a new book. Old and new hashes are linked to one book and the
annotations re-anchored (E16). *Status:* [BB] multiple hashes per book; [NEW] migration.

**F5 — Omnibus ebook ↔ separate audiobooks, or one ebook ↔ multi-part ABS items.** *Status:* [OUT v1], flagged at
pairing.

**F6 — ABS item re-added with a new id.** *Status:* [BB] stale-item probe; re-pair by ASIN/ISBN.

**F7 — Same title, different translation.** Pairing refused (ISBN mismatch or coverage < 90 %). *Status:* [NEW]

**F8 — PDF and fixed-layout** (Tress). Progress by page only, no annotations. *Status:* [OUT]

### G. Manga and comics

**G1 — Spreads.** One reader counts a double page as one page, another as two, so pages drift. Map by image index in
the archive. *Status:* [SPIKE] in Phase 2.

**G2 — Chapter files vs volume files** for the same series. Different md5s; map through Kavita's chapter ids.
*Status:* [NEW]

**G3 — "Mark volume read" in Kavita vs page progress on KOReader.** The explicit mark wins (B17). *Status:* [NEW]

**G4 — Panels read offline, synced later.** As A1/A2, using activity time if Panels sends it. *Status:* [SPIKE]

### H. Reading time, dates, Fable

**H1 — Immersion double count.** Time is a union of intervals per book across surfaces, not a sum. *Status:* [NEW]
*Test:* `H1_interval_union`

**H2 — Two collectors of KOReader stats** (Koinsight and BookBridge). BookBridge becomes the O source; Koinsight stays
as read-only history. Dedupe on (md5, device, page, start time), BookBridge's own key. *Status:* [BB]

**H3 — Combined device stats re-uploaded.** BookBridge can inject other devices' stats into each device; they must not
be counted again when they come back. *Status:* [BB] excludes other device keys; verify in Phase 5.

**H4 — Different meanings of "time".** KOReader caps time per page (idle filter), Kavita estimates from words read, ABS
counts wall-clock listening. O stores per-source and merged values and never silently mixes estimated with measured.
*Status:* [NEW]

**H5 — Kobo clock reset** (sessions dated 1970 or 2000). Out-of-range sessions are dropped and flagged (R2).
*Status:* [NEW]

**H6 — Finished at 00:30.** Stored as UTC, shown and sent as the local date. *Status:* [NEW]

**H7 — False "finished".** Slept through the audio to the end, peeked at the last page, or mis-clicked "mark read".
*Rule:* Fable "finished" only when text reached the last narrative spine item; or audio reached the end and wasn't
rewound within 24 h; or an explicit mark-read (Q4). *Status:* [NEW]

**H8 — Re-read.** After a finish, progress back under 5 % and advancing = a new read with a new start date. Fable may
not support re-reads; Hardcover keeps dates per read. *Status:* [SPIKE S6]

**H9 — Browsing samples.** Six books opened for a page each. Fable "currently reading" only after ≥ 2 % and ≥ 10 min
of reading. *Status:* [NEW]

**H10 — Fable login fails** (token expiry, password change, captcha, 429). Keep only the newest state per book,
exponential backoff, alert after 3 failures, never a burst (ban risk). *Status:* [NEW]

**H11 — Fable matches the wrong edition, or nothing.** Match once (ISBN, then title + author), store `fable_book_id`,
allow a manual override, never auto-create a book. *Status:* [NEW]

**H12 — Fable and Hardcover disagree** because one write failed. Each target is independently idempotent and
state-based; only the newest state is sent. *Status:* [NEW]

**H13 — Abandoned book.** Never auto-marked DNF; > 60 days idle appears in the digest only. *Status:* [NEW]

**H14 — Fable trails by up to 30 min.** By design (debounce); status changes go out immediately after the gates.
*Status:* [NOTE]

### I. Server, operations, restore

**I1 — Hub DB restored from a backup** older than the devices. R12, then newest-with-guards. *Status:* [NEW]

**I2 — Kavita restored from a backup** (for example a Phase 0 rollback). Kavita looks like it regressed and "deleted"
newer annotations. R12 + R10; the hub re-pushes its newer state after the owner approves. *Status:* [NEW]

**I3 — Kavita or ABS upgraded with API changes.** Startup contract check (version + DTO fields); unknown version →
read-only until checked. Versions pinned. *Status:* [NEW]

**I4 — Two hub instances** (a spike container left running). R14 DB lease; spike containers run with sync off and no
production write credentials (S1 excepted). *Status:* [NEW]

**I5 — A device still points at Kavita's or Koinsight's KOSync.** Split brain. R14; Task 05 records each device's sync
server. *Status:* [NEW]

**I6 — API key revoked or rotated.** 401 → that spoke pauses, the outbox keeps everything, one alert. *Status:* [NEW]

**I7 — Alignment jobs saturate thebigbox during streaming.** `nice`/`ionice`, one at a time, at night. *Status:* [NEW]

**I8 — Telegram alert storm.** Rate-limited per type, plus a daily digest. *Status:* [NEW]

**I9 — The hub DB holds every note and highlight.** Personal data: backed up, never exposed, never copied to the vault.
*Status:* [NEW]

**I10 — BridgeSync updates itself on the Kindle.** An upstream plugin update would overwrite our follow-along mode or
speak a newer protocol than the pinned hub. Plugin self-update off (or pointed at our fork); hub and plugin upgraded
together. *Status:* [BB risk] → [NEW]

### J. Security

**J1 — Public `/koreader/*` gets scanned or brute-forced.** NPM rate limit + BookBridge auth; nothing else public.
*Status:* [NEW]

**J2 — Kindle lost or stolen.** The KOSync credentials sit in plain text on the device. Rotate the key; use per-device
keys if BookBridge supports them. *Status:* [SPIKE] in Phase 2.

**J3 — Note text injected into Kavita or Telegram.** Same as E13. *Status:* [NEW]

**J4 — Fable credentials and token.** `.env` (600) + Vaultwarden; the cached token file is mode 600. *Status:* [NEW]

### K. Multiple readers (the owner and a partner, separate accounts)

Both people have their own Kavita user, ABS user, Fable account and KOReader credentials; the hub maps each to one `reader_id` (R15). Kavita and ABS are already per-user; BookBridge 7.10 is multi-user with per-user progress, KOSync documents and stats, plus an opt-in "Shared Library" that makes *matches* visible to everyone but never progress. Test every case with two readers on the same book.

**K1 — Same book, both reading, different places.** Reader A is on ch 5, reader B on ch 11, same EPUB hash. Each KOSync PUT is stored under the sender's `reader_id`; a GET returns the caller's own position only. *Status:* [BB] verify. *Test:* `K1_two_readers_same_hash`
**K2 — Wrong credentials on a shared device.** One Kindle, one KOSync login. If both use the same device the hub cannot tell who is reading. *Rule:* one device = one reader, recorded at pairing; a second reader gets their own device or their own KOReader profile (Profiles plugin) with their own credentials. A device is never "whoever synced last". *Status:* [NEW]; Q9.
**K3 — Annotation isolation.** A's highlights never reach B's devices, B's Kavita annotations, or B's review queue, including after a hash change (E16) and after a restore (I-series). The exchange key `(md5, reader_id, ann_key)` already includes the reader; add a test that replays A's upload as B and expects 0 rows visible. *Status:* [BB] + [NEW] test.
**K4 — Mass-delete guard (R10) is per reader.** B's wiped sidecar must not park or tombstone A's annotations, and one reader's parked exchange must not block the other's. *Status:* [NEW]
**K5 — Alignment maps are shared, cost is not duplicated.** The map for a paired title is built once (it depends on the book, not the reader). Position lookups (ts ⇄ char) are read-only on the shared map. A reader-specific correction (A fixes a wrong anchor) must not change B's mapping unless an admin promotes it. *Status:* [NEW]
**K6 — Both listen to the same ABS book.** ABS keeps progress per user already; the hub's ABS API key per reader must be that reader's key, never the admin key (the admin key can read everyone and would write to the wrong user). *Status:* [NEW]; config check at startup fails if two readers share a key.
**K7 — Credential leak surface.** KOSync credentials, Kavita OPDS URLs (they embed the API key) and the public `/koreader/*` host (J-series) are per reader; revoking one reader's key must not affect the other. Per-reader rate limits on the public host. *Status:* [NEW]
**K8 — Review queue and alerts.** Low-confidence matches, parked mass-deletes and failures go to the reader they belong to, labelled with the reader's name. Each reader has a `telegram_chat_id`; two readers may share one chat (decided 2026-11-02: both go to the owner's chat because the partner will not use Telegram). Shared-chat alerts show titles and counts, never note text; text is visible only on the web review page. The owner, as admin, resolves the partner's queue items; unresolved ones fall back to the safe defaults (Q8 chapter-level placement after 30 days; mass deletes never auto-applied). *Status:* [NEW]; Q10.
**K9 — New reader onboarding.** Adding a reader creates their Kavita/ABS links and an empty state. Option: backfill from what they already have in ABS/Kavita (progress yes, annotations none). It must not copy the first reader's data. *Status:* [NEW]
**K10 — Removing a reader.** Deleting B removes B's rows, devices, keys and queue items; A's data and the shared maps stay. Export B's annotations first. *Status:* [NEW]
**K11 — Fable.** Each reader's progress mirrors to their own Fable account; a reader without Fable is skipped, not defaulted to the other's. *Status:* [NEW]; Q11.
**K12 — Shared books, separate files.** Both readers' devices fetch the same Kavita file through OPDS (identical hash, Q6) but under their own Kavita user, so "currently reading" lists stay separate. Age/library restrictions on a Kavita user must also limit what the hub exposes to that reader. *Status:* [NEW]
**K13 — Clock and time-zone differences.** Devices in different zones: activity time (R1/R2) is per device, per reader; a late device of A never reorders B's history. *Status:* covered by R1/R2 once `reader_id` is in the key.

---

## 3. What this changes in the plan

- **Rules:** R1–R14 replace "Sync rules" in `ARCHITECTURE.md`; the canonical records gain `activity_at`,
  `received_at`, `device_id`, `session_id`, `link_positions`, `alignment_coverage` and an archived-text field.
- **Spike additions** (`BUILD_PLAN.md`):
  - S2 also records which Kavita reader modes fill `bookScrollId`, and whether an open reader reacts to a server-side
    progress change (B9, B19).
  - S7 also tests offline listening, offline bookmarks, pause latency, whether the app picks up a server-side change
    on play, and what happens when the server is written mid-playback (A9, A10, B6, B20, C8, D11).
  - **S8 (new):** resolve a quote to xpointers on the device with crengine (E10, A16).
  - **S9 (new):** reproduce the sidecar-loss mass delete in a throwaway BookBridge (E8).
  - **S10 (new):** follow-along on the PW3: auto-suspend, Wi-Fi, battery per hour (C10).
- **Task 05** also records which sync server and KOReader sync settings each device uses (I5, A8).
- **Tests:** each `[NEW]` and `[BB]` case gets `tests/edge/test_<ID>.py` replaying recorded events; Phase 7 runs them
  all.

## 4. Questions for the owner (Q1–Q11)

**Answered 2026-10-21: all defaults accepted.** The owner also set a library policy: every book exists in both ABS and
Kavita. So D8 orphans and the "audio-only" state are transitional, not permanent; B12/F7 coverage checks stay as a
safety net for edition mismatches.

| # | Question | Decision (= proposed default) |
|---|---|---|
| Q1 | A note edited on two surfaces between syncs: keep both texts, or Kavita wins? | Keep both |
| Q2 | A delete vs an edit: resurrect when the edit is newer, archive the text when the delete is newer? | Yes |
| Q3 | Which Kavita annotations become ABS bookmarks: all highlights, or only ones with a note? | Only with a note |
| Q4 | Fable "finished": automatic behind the H7 gates, or only when you mark it finished? | Automatic with gates |
| Q5 | After immersion, you stop the audio and keep reading: should audio resume where your eyes are? | Yes |
| Q6 | Devices get books only from Kavita's OPDS (byte-identical files)? | Yes |
| Q7 | KOReader sync settings: newer = Silently, older = Prompt? | Yes |
| Q8 | Unreviewed low-confidence bookmarks: after 30 days place them at chapter level marked "approximate", or keep them queued? | Place at chapter level |
| Q9 | Does she use her own e-reader and phone, or share any device with you? (K2: one device = one reader) | Own devices; a shared device uses a separate KOReader profile |
| Q10 | Her alerts: sent to your Telegram chat (she will not use it), labelled with her name, titles and counts only? | Yes (decided 2026-11-02) |
| Q11 | Does she use Fable (mirror her progress there)? Which hub features does she want beyond progress sync? | Her choice; off by default |
