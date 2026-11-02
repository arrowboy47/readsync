# 04 — Source checks against cloned refs (2026-10-20)

Read-only greps against `refs/` (nothing executed). These confirm or correct claims in `02` and `03`.

| Ref | Commit |
|---|---|
| `refs/bookbridge` | `65f1cc2` (2026-10-15) |
| `refs/ShelfSync` | `b6980a7` (2026-10-18) |
| `refs/kavita/openapi-v0.9.1.4.json` | tag v0.9.1.4 (`info.version` = `0.9.1.1`) |

## Kavita API (confirmed in spec)

- Annotation paths exist as listed in `02`. `POST /api/Annotation/create` takes `AnnotationDto`.
- Required fields: `chapterId, libraryId, ownerUserId, seriesId, volumeId, xPath`.
  `selectedText`, `endingXPath`, `comment`, `selectedSlotIndex`, `pageNumber` optional.
- Still open (spike S1): whether an externally created annotation with only `xPath`/`endingXPath` + `selectedText`
  re-renders as a highlight in the reader.

## BookBridge — preliminary answer to spike S5

BookBridge is a hub, not just a bridge:

- **Runs its own kosync server** (`src/api/kosync_server.py`): `/users/auth`, `/users/create`, `/users/login`,
  `GET /syncs/progress/<doc_id>`, `PUT /syncs/progress` (also under `/koreader/…`). Devices point **at BookBridge**.
- **Device-sync API for its BridgeSync plugin** (`plugins/bridgesync.koplugin`): `/device-sync/manifest`,
  `/books/<abs_id>/download`, `/statistics` + `/statistics/merged`, `/status` + `/status/merged`,
  **`/annotations/exchange` + `/annotations/exchange-ack`**, `/sessions`, `/logs`, plugin version/download.
  ⇒ it already collects **KOReader stats and sessions (O)** and relays annotations **both ways** with devices.
- **Annotation hub** (`src/services/annotation_sync_service.py`): canonical KOReader-format annotations
  (xpointer + highlighted text) per (user, document md5); "spokes" exchange deltas with key-omission deletes and
  version bumps so devices pull changes on next exchange. Spokes today: BookOrbit, Grimmory/Booklore (+ notes),
  Readest, Hardcover, BookFusion. CFI↔xpointer helpers: `src/utils/grimmory_cfi.py`, `src/utils/ebook_dom_map.py`,
  `src/utils/bookfusion_offsets.py`.
- **Kavita** (`src/sync_clients/kavita_sync_client.py`, `src/api/kavita_client.py`): progress only, through Kavita's
  kosync endpoint. No annotation spoke.
- **ABS bookmarks:** no code references. **Fable:** none.
- Alignment maps persisted in `BookAlignment` (`src/db/models.py`).

**Implication:** the Kavita annotation relay, ABS-bookmark relay and Fable writer fit as new spokes / sync clients
**inside BookBridge** (fork, offer upstream). A separate companion service is only needed for anything BookBridge's
maintainer won't take. S5 still needs a proper read of the spoke contract before Phase 3 starts.

## ShelfSync — Fable client (`shelfsync/lib/fable/api.lua`)

- Base `https://api.fable.co`. Auth = Firebase: `identitytoolkit/v3/relyingparty/verifyPassword?key=<app key>`
  for login, `securetoken.googleapis.com/v1/token?key=<app key>` for refresh. (App key is embedded in source;
  not copied here.) Password cached encrypted on device for silent re-login.
- Endpoints used:
  - `GET /api/settings/profile/`
  - `GET /api/books/search/?auto=<q>&include=out_of_catalog&type=book&limit=20&offset=0`
  - `GET /api/books/{id}`, `GET /api/books/{id}/editions/`
  - `GET /api/v2/users/{uid}/book_lists?limit=20&offset=0&media_type=book`
  - `GET /api/v2/users/{uid}/book_lists/{list_id}/books?limit=&offset=`
  - `/api/v2/users/{uid}/book_lists/book` (shelve / move between lists; status via list `system_type`)
  - **`POST /api/books/{id}/reading_progress`** — `{current_percentage, selected_mode:"percentage"}` or
    `{current_page, selected_mode:"page"}` (confirmed by the author from a HAR capture)
  - `GET /api/users/{uid}/reviews/{book_id}`, `POST /api/books/{id}/reviews`
- No reading-time field anywhere in the client. Fable gets: status (to-read / reading / finished / DNF),
  progress % or page, review/rating.
- Corrects `03`: a progress **write** endpoint exists.
