# 03 — Audiobookshelf, Fable, audio↔text alignment (as of 2026-10-20)

Sources: ABS source (`server/routers/ApiRouter.js`, `MeController`, `models/User.js`, `models/MediaProgress.js`,
`objects/files/AudioTrack.js`, `utils/notifications.js`), ABS mobile app source, Fable help centre + ToS,
Hardcover docs, Storyteller blog, BookBridge source. **UNVERIFIED** marks unconfirmed items.
The old docs at api.audiobookshelf.org say they are out of date — use the source.

## 1. Audiobookshelf

- Latest **v2.37.1** (2026-09-29); 2.37.0 (09-28), 2.36.0 (07-27). Running here: 2.32.1.

### Bookmarks — YES, but no notes field

- Model `{libraryItemId, title, time (s), createdAt (ms)}` stored as JSON array on the user row.
- `POST /api/me/item/:id/bookmark` `{time, title}` (same time ⇒ updates title);
  `PATCH /api/me/item/:id/bookmark` (matches on `time`, changes `title` only);
  `DELETE /api/me/item/:id/bookmark/:time`; `GET /api/me/bookmarks` and `/api/me/bookmarks/:libraryItemId`
  (since 2.36.0); `GET /api/me` also returns them.
- `title` is the only text field — notes must live in it.
- Official mobile app (v0.14.2-beta): bookmarks are direct POST/PATCH/DELETE, **no offline queue** —
  a bookmark made offline never reaches the server.

### Progress — YES

- `PATCH /api/me/progress/:libraryItemId/:episodeId?`, `PATCH /api/me/progress/batch/update`,
  `GET`/`DELETE /api/me/progress/:id`.
- Fields: `currentTime, duration, progress, isFinished, hideFromContinueListening, ebookLocation,
  ebookProgress, finishedAt, lastUpdate`. Partial `set()`.
- `isFinished:true` ⇒ sets `finishedAt` + `progress=1`; `isFinished:false` clears `finishedAt` and **resets
  `currentTime` to 0**. Valid `lastUpdate` overwrites `updatedAt` (backdating possible). `startedAt` = `createdAt`.
  Auto-finish when <10 s remains or past a per-library %.
- `ebookLocation` = CFI from ABS's epub.js reader (UNVERIFIED in reader source).

### Listening time — YES

- `GET /api/me/listening-sessions?itemsPerPage=&page=`, `GET /api/me/item/listening-sessions/:libraryItemId`,
  `GET /api/sessions` (admin).
- `GET /api/me/listening-stats` → `{totalTime, items, days{YYYY-MM-DD: seconds}, dayOfWeek, today, recentSessions}`.
- Offline sessions uploaded later (`syncLocalSession`) overwrite `timeListening`; their progress applies only
  if newer than server `updatedAt`.

### Realtime — Socket.IO YES; webhooks NO

- Connect to server root, emit `auth` with token (or handshake `auth:{token}`) → `init` / `auth_failed`.
  **API keys authenticate sockets since 2.37.0.**
- Per-user delivery, so the token must belong to the reading user:
  - `user_item_progress_updated` `{id, sessionId, deviceDescription, data: mediaProgress}` — from playback-session syncs only
  - `user_updated` (full user JSON incl. `bookmarks`) — on bookmark create/update/delete and direct progress PATCH → diff the bookmarks array
  - `user_session_closed` (session id)
- Apprise notifications cover only podcast downloads, backups, RSS failures, test.

### Clip extraction without filesystem access — YES

- `GET /api/items/:id?expanded=1` → `media.audioFiles` (`ino, index, duration`), `media.chapters` (`id, title, start, end`).
- Playback-session tracks: `index, startOffset, duration, contentUrl="/api/items/{id}/file/{ino}"`.
- `GET /api/items/:id/file/:ino` streams via `res.sendFile` (HTTP Range honoured — inferred) ⇒
  `ffmpeg -ss <T−startOffset> -t 20 -i <url>` should work. `/download` variant needs `canDownload`.

### Auth

- 2.26.0: short-lived JWT (12 h) + rotating refresh (7 d) + `/auth/refresh`.
- **API keys** (`/api/api-keys`, admin-created, bound to one user, optional expiry) — use these for services.
- `?token=` on media URLs still working: UNVERIFIED.

## 2. Fable

- **No public API**, no Zapier/IFTTT/webhooks. Acquired by Everand (Scribd) June 2025; Everand activity syncs into Fable when linked.
- No Kindle/Kobo/KOReader integration. Imports: Goodreads CSV (beta), Kindle lists.
- Tracking: progress by page or %, streaks, goals, stats by finish date. **No reading-time field found** (UNVERIFIED).
- **ToS** (fable.co/terms, 2021-06-17): bans access "through automated or non-human means… bot, script",
  data mining, reverse engineering. Automating it is a ToS violation; account-ban risk is real.
- Writers found: **ShelfSync** (working, Firebase email/password login — endpoints in `04-source-checks.md`,
  including a `reading_progress` POST). `itchysudo/shelfbridge` reads lists only and replays browser headers via Playwright.

### Fallbacks

- **Hardcover — official GraphQL API.** `https://api.hardcover.app/v1/graphql`, 60 req/min; tokens expire every
  Jan 1 and may be reset during beta. `user_book_reads` has `started_at, finished_at, progress_pages,
  progress_seconds`; journal events include `progress_updated`, `quote`. KOReader plugin: Billiam/hardcoverapp.koplugin.
- **StoryGraph — no API**; BookBridge drives it with cookies + CSRF (`/update-status.js`, `/update-progress`).
- The running "Bookshelf (hardcover)" container uses Hardcover for metadata only (UNVERIFIED that it never syncs progress).

## 3. Audio↔text alignment

- **BookBridge** (v7.10.0): ABS Socket.IO listener on `user_item_progress_updated`, 30 s debounce,
  self-write suppression. Alignment: QuartzNet CTC forced alignment on CPU (English); MMS optional; Whisper
  fallback (faster-whisper or any OpenAI-compatible endpoint — **our shim at `192.168.1.158:9092` qualifies**).
  Reuses Storyteller transcripts. Output: persistent time ↔ epub char-offset map with quality scoring
  (`BookAlignment` table). **No ABS-bookmark → annotation feature.**
  Text location (`src/utils/ebook_utils.py`): unique 10-word anchor → exact → normalized alphanumeric →
  `rapidfuzz.fuzz.partial_ratio_alignment` cutoff 80 within ±10 % of expected % → optional embedding fallback.
- **Storyteller** v3: MMS (wav2vec2 CTC) at 20 ms frames; chapters located by 10-char n-grams + RANSAC; Viterbi
  between anchors every ~2,000 chars; per-letter timing → word → sentence; tolerates reordered/missing chapters.
  Output EPUB3 Media Overlays (SMIL `clipBegin/clipEnd` ↔ text fragment id) = a sentence-level time↔text map.
  Older Whisper pipeline: 1–4 h/book on CPU.
- whisperX 3.8.6 (word timestamps), aeneas (old DTW/TTS, weak on mismatched text).

### Notes on the user's per-bookmark Whisper-clip idea

- Valid as a **fallback and cross-check**: once a book has an alignment map, a bookmark at T is a lookup.
- Clip 15–20 s **ending at T** (users bookmark *after* hearing the passage), set language, enable VAD;
  ~30 words gives a unique match. Require the best match to beat the runner-up by a clear margin and to sit
  within the ±% window.
- Intros, credits, abridged or different editions break a plain "same percentage" check — anchors + piecewise mapping fix that.

### Position formats

- **CFI:** `epubcfi(/6/{2N}!/4/…/{text step}:{offset})` (even = element, odd = text). Python tooling thin.
- **KOReader xpointer:** `/body/DocFragment[N]/body/div/p[M]/text().K`, N = 1-based spine index. Maintainers:
  can't be computed reliably outside crengine (koreader discussion #9099). BookBridge uses "crengine-safe"
  paragraph xpaths ending `.0` and resolves by text match with neighbour-fragment fallback.
- **Kavita:** `pageNum` (spine, 0-based) + element XPath, no char offset (see `02`).
- Design consequence: carry **text quote + prefix/suffix + spine index + char offset** and resolve natively at each end.
