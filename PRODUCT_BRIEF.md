# readsync — product brief

## What

One reading state across every surface the user reads or listens on, with **Kavita as the source of truth**,
and the current book's progress mirrored to **Fable**.

## Why

The same book gets read in Kavita's web reader, on KOReader (Kindle PW3 and a Kobo), on iOS, and listened to in
Audiobookshelf. Today each keeps its own position, highlights and history. Switching surfaces means hunting for
the place, and highlights stay stuck on whichever device made them.

## Who

Two readers in v1: the owner and a partner, each with their own Kavita user, ABS user, Fable account and KOReader credentials, fully isolated from each other (rule R15, cases K1–K13). The design must not assume a single user anywhere; it need not support more than a handful.

## Data types

| Code | Meaning | Kavita representation |
|---|---|---|
| **B** | Bookmark / annotation with a note | Annotation with `comment` |
| **H** | Highlight (text selection, no note) | Annotation with `selectedText`, empty `comment` |
| **P** | Progress | `ProgressDto` (`pageNum` + `bookScrollId`) |
| **O** | Other: dates started/finished, reading time, word count | Not writable in Kavita → readsync DB |

## Which data flows where

| Pair | Types |
|---|---|
| ABS ↔ Kavita | B, H, P |
| Kavita ↔ KOReader | B, H, P, O |
| Kavita ↔ iOS client | B, H, P, O (native when iOS client = Kavita PWA) |
| → Fable | O + status + progress % (Fable records nothing richer) |

## User stories

1. **ABS only** — I listen in the car; when I open the Kindle or Kavita later, it's at the matching passage.
   A bookmark I drop in ABS shows up in Kavita as a note on the right sentence.
2. **Immersion (KOReader + ABS)** — Audio plays on my phone while I read the same book on the Kindle; the Kindle
   page keeps up with the audio (within about half a minute) without me pressing anything.
3. **KOReader only** — Highlights and notes I make on the Kindle appear in Kavita; reading time is recorded.
4. **iOS + ABS** — Same as 5, on the phone.
5. **Kavita + ABS** — Where I stop in Kavita's reader is where the audiobook resumes, and vice versa.
6. **Kavita only** — Highlights I make in Kavita appear on the Kindle next time I open the book there.
7. **iOS only** — Same as 6, on the phone.
8. **Fable** — My Fable profile shows what I'm currently reading and how far in, and marks it finished when I finish.

## Success criteria (v1)

- Progress hand-off between any two surfaces lands within one paragraph (EPUB) or 15 s (audio), on the next
  open of the target surface.
- ≥ 9 of 10 ABS bookmarks on paired titles land on the right paragraph in Kavita; the rest go to a review queue,
  never silently to a wrong spot.
- Highlights round-trip KOReader → Kavita → KOReader without duplicates.
- Fable shows the right book and % within 30 minutes of reading.

## Explicit don'ts

- Don't write Fable more than every 30 minutes per book.
- Don't let a stale device drag progress backwards silently.
- Don't store secrets in the repo or the vault (Vaultwarden + `.env`, mode 600).
- Don't widen public exposure beyond what device sync strictly needs.

## Scope

- **V1:** P sync (scenarios 1, 3, 5, 6), Kavita annotation spoke, ABS bookmark spoke, Fable writer, O roll-up.
- **Next:** follow-along mode for immersion, Hardcover target, Storyteller read-along on iOS.
- **Out:** cross-reader sharing (shared highlights, "she is on ch 9"), more than a handful of readers, PDFs for annotations (Kavita annotations are EPUB-only), Kindle native reader (non-KOReader).
- **Owner policy (2026-10-21):** every book is kept in both ABS and Kavita. Today's audio-only titles (Red Rising ×5,
  Deep Work, …) get EPUBs as the library is brought in line; until then they sync P to Fable only.
