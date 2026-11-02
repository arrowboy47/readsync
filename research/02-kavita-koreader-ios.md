# 02 — Kavita, KOReader, iOS clients, prior art (as of 2026-10-20)

Sources: Kavita GitHub + wiki + `openapi.json`, KOReader GitHub, project READMEs.
**UNVERIFIED** marks anything not confirmed from source or docs.

## 1. Kavita

- Latest stable **v0.9.1.4** (2026-09-02). History: 0.9.1 (08-28), 0.9.0.2 (05-14, security fix),
  0.9.0 (04-30), 0.8.9 (2026-01-14), **0.8.8 (2025-10-20) added annotations**. GPL-3.0.
- Local spec copy: `refs/kavita/openapi-v0.9.1.4.json` (its `info.version` reads `0.9.1.1`).

### Annotations / highlights — YES (EPUB only)

- Positions are **XPath, not CFI**.
- `AnnotationDto`: `id, xPath, endingXPath, selectedText, comment, commentHtml, commentPlainText,
  chapterTitle, context, highlightCount, containsSpoiler, pageNumber, selectedSlotIndex, likes[],
  chapterId, volumeId, seriesId, libraryId, libraryName, seriesName, ownerUserId, ownerUsername,
  ageRating, createdUtc, lastModifiedUtc`.
- **Required** on create (from spec): `chapterId, libraryId, ownerUserId, seriesId, volumeId, xPath`.
- Colour = per-user `HighlightSlot` (`slotNumber`, RGBA), referenced by `selectedSlotIndex`.
- Endpoints (confirmed in spec): `GET /api/Annotation/all`, `/all-for-series`, `/{annotationId}`;
  `POST /api/Annotation/create` (body `AnnotationDto`), `/update`, `/all-filtered`, `/like`, `/unlike`,
  `/bulk-delete`, `/export`, `/export-filter`; `DELETE /api/Annotation`; `GET /api/Series/series-with-annotations`.
- SignalR event `AnnotationUpdate` exists.
- Prior art: Obsidian "Kavita Sync" plugin pulls annotations out via this API (read only).

### Bookmarks — PARTIAL for EPUB

- `BookmarkDto`: `page, chapterId, volumeId, seriesId, imageOffset, xPath`. `POST /api/Reader/bookmark`,
  `/unbookmark`, `/all-bookmarks`, `/remove-bookmarks`, `/bulk-remove-bookmarks`; `GET /api/Reader/chapter-bookmarks`,
  `/volume-bookmarks`, `/series-bookmarks`. These are image/page bookmarks (v0.8.8 added image bookmarks to the EPUB reader).
- Text-position markers: Personal ToC — `GET`/`DELETE /api/Reader/ptoc`, `POST /api/Reader/create-ptoc`
  (`CreatePersonalToCDto`, fields UNVERIFIED).
- Practical choice: represent text bookmarks (B) as annotations; reserve Kavita bookmarks for manga pages.

### Progress — YES

- `POST /api/Reader/progress`, `GET /api/Reader/get-progress?chapterId=` — `ProgressDto`:
  `volumeId, chapterId, pageNum, seriesId, libraryId, bookScrollId (nullable XPath), lastModifiedUtc`.
- EPUB: `pageNum` = spine item; `bookScrollId` = element XPath like `//body/div/p[22]`, **no character offset**.
- Also: `continue-point`, `has-progress`, `mark-*-read/unread`, `time-left`, `first-progress-date`.
- Panels-specific: `POST /api/Panels/save-progress?apiKey=`, `GET /api/Panels/get-progress` (save also creates a reading session).

### KOReader sync (kosync) — YES, progress only

- `GET /api/Koreader/{apiKey}/users/auth`, `PUT /api/Koreader/{apiKey}/syncs/progress`
  (`document, device_id, device, percentage, progress, timestamp`),
  `GET /api/Koreader/{apiKey}/syncs/progress/{ebookHash}`.
- v0.8.7 EPUB; v0.8.9 added PDF + archives.
- Hash: KOReader binary partial MD5, stored as `MangaFile.KoreaderHash` (books before 0.8.7 need a forced scan).
- Conversion: `/body/DocFragment[N]/body/…` → `PageNum = N-1`, `bookScrollId = "//body/…"`. **Text offsets
  dropped**, `id()` and `<a>` targets become null, **incoming percentage ignored**. Back-conversion rebuilds
  `/body/DocFragment[n]/body/<xpath>.0`.
- No annotations/bookmarks/stats over kosync. Self-registration disabled. Wiki warns against KOReader auto-sync.
  Issue #4518: 400 errors on 0.8.9.1.

### OPDS — PARTIAL

- OPDS 1.x + OPDS-PSE at `/api/Opds/{apiKey}/…`. Page streaming (`/image`, `saveProgress=true` default) saves
  progress — image formats only. **No OPDS 2 / progression.**

### Events — webhooks NO; SignalR PARTIAL

- `MessageFactory` events include `UserProgressUpdate`, `ReadingSessionUpdate`, `ReadingSessionClose`,
  `AnnotationUpdate`. UI connects to `hubUrl + 'messages'` with JWT `accessTokenFactory`.
  Exact path believed `/hubs/messages` — **UNVERIFIED**, payloads **UNVERIFIED**.
- Scrobbling is Kavita+ only (AniList, MAL, MangaBaka, Hardcover since 0.9.1). No generic hook.

### Stats / history — YES, read-only

- `GET /api/Stats/reading-history`, `/reading-history/series/{id}`, `/user-read`, `/user-stats`,
  `/reading-activity`, `/reading-counts`, `/reading-pace`, `/total-reads`, `/reads-by-month`,
  `/avg-time-by-hour`, `/words-per-year`, `/pages-per-year`.
- `ReadingHistoryItemDto` (session start/end, `durationSeconds`, `pagesRead`, `wordsRead`), `ChapterDto.wordCount`.
- Journal-style sessions since 0.8.9 (30-minute idle cutoff). **No endpoint to write time or sessions** —
  sessions only arise from progress saves and mark-read.

### Auth

- `POST /api/Plugin/authenticate?apiKey=&pluginName=` → `UserDto` with JWT ("not fully built out").
- Since 0.8.9: `x-api-key` header with named auth keys (`/api/Plugin/authkey-expires`).

## 2. KOReader

- Latest **2026.07.1** (2026-08-01). 2026.07 replaced SyncService with the Cloud storage plugin.
- **kosync:** `document` (binary partial MD5 or filename MD5), `progress` (xpointer or page), `percentage`,
  `device`, `device_id`. `auto_sync` off by default; `pages_before_update` pushes ~10 s after Nth page;
  `sync_forward` = prompt, `sync_backward` = disabled; 25 s debounce. Pull on open/resume/network-connected;
  push on close/suspend/network-disconnect; failed pushes queued. Auto-sync needs Wi-Fi action "turn on".
- **Native annotation sync: NO** — manual JSON export/import with merge (2025.08). Plugins:
  - AnnotationSync.koplugin (dani84bs, MIT, v2.0.0) — Cloud storage+/WebDAV, highlights+notes+bookmarks+progress, timestamp merge. Cloned in `refs/`.
  - highlightsync.koplugin (gitalexcampos, AGPL, beta) — WebDAV/Dropbox.
  - BookBridge `bridgesync.koplugin` — see `04-source-checks.md`.
- **Storage:** sidecar `<book>.sdr/metadata.epub.lua`, table `annotations`: `datetime, datetime_updated,
  drawer` (nil ⇒ page bookmark)`, color, text, note, note_format, chapter, pageno, pageref, page, pos0/pos1`
  (xpointers), `epubcfi`. Stats DB `settings/statistics.sqlite3`: `book(id, title, authors, notes, last_open,
  highlights, pages, series, language, md5, total_read_time, total_read_pages)`,
  `page_stat_data(id_book, page, start_time, duration, total_pages)`.
- **Stats sync:** PARTIAL — manual merge over Dropbox/WebDAV ("Sync now" / `SyncBookStats` action).
- **Kindle vs Kobo:** nothing runs while suspended; Wi-Fi drops on suspend (push happens first). Per-platform
  Wi-Fi details UNVERIFIED.
- **OPDSfoldersync.koplugin:** AGPL, 1 commit (2026-10-02). Auto-downloads OPDS catalog books on resume / Wi-Fi /
  timer; Android (Bigme) focus. **No progress or annotation sync.** Not useful here.

## 3. ShelfSync (Lyfts/ShelfSync)

- Lua KOReader plugin, MIT, v1.8.1 (2026-10-18), actively maintained.
- Pushes progress (time/percent/pages, ≤1/min default, offline queue ≤4 weeks), status, ratings, notes
  from the device to StoryGraph, Hardcover, Goodreads, **Fable**, Pagebound, LibraryThing.
- No server, no polling. Doesn't read Kavita, doesn't sync highlights.
- **Fit:** the only working Fable writer found → port its Fable client. Endpoints in `04-source-checks.md`.

## 4. iOS clients

| App | EPUB novels | Progress → Kavita/kosync | Highlights |
|---|---|---|---|
| Kavita web reader (PWA) | YES | Native | Native Kavita annotations |
| Readest (v0.12.16) | YES | kosync YES (custom server, "File Content" hash); vs Kavita's kosync UNVERIFIED | Readest cloud / self-host; export to Readwise/Notion/Hardcover |
| Panels | NO (comic EPUB only) | YES (OPDS-PSE + `/api/Panels/*`) | NO |
| Chunky | NO | YES (PSE) | NO |
| Paperback (Kavya ext.) | NO | per chapter; 0.9 compat UNVERIFIED | NO |
| Aidoku | NO | per chapter | NO |
| Komic | YES | chapter-level | not mentioned |
| Yomu, KyBook 3 | YES (OPDS) | NO | local only |
| Storyteller | YES (aligned EPUB3) | own server | own |

Recommendation: EPUB → Kavita PWA (offline: Readest); manga → Panels; true read-along → Storyteller.

## 5. Prior art

- **BookBridge** (cporcellijr/bookbridge; formerly abs-kosync-bridge-enhanced). Python/Docker, MIT, 543★,
  v7.10.0 (2026-10-15). ABS, KOReader/kosync, Storyteller, Grimmory, BookOrbit, Kavita, CWA, BookFusion,
  Hardcover, StoryGraph, Readest. Kavita = bidirectional **progress** via Kavita's kosync endpoint. Highlights via
  BridgeSync plugin relayed to Grimmory/BookOrbit/BookFusion/Readest/Hardcover — **not Kavita**. Strongest base.
- **J-Lich/abs-kosync-bridge:** MIT, ~70★, faster-whisper + ~400-char windows + rapidfuzz ≥80, polls ABS every 5 min.
- **Storyteller:** v3 beta, CTC forced aligner, EPUB3 Media Overlays, own apps.
- **BookOrbit** (NestJS/Vue, AGPL, 5.5k★): native bidirectional progress + annotations across its KOReader
  plugin, Kobo, web reader; iOS audio app.
- **Grimmory** (Booklore fork, AGPL, ~4.6k★): built-in kosync, Kobo sync, web annotations.
- No existing Kavita ↔ KOReader highlight bridge.

Unverified: SignalR path/payloads, annotation create body semantics (does an external xPath render?),
Readest ↔ Kavita kosync, KOReader stats auto-sync via Profiles, Paperback on 0.9, PocketBook iOS.
