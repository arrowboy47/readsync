# readsync

Kavita-centred reading sync across Audiobookshelf, KOReader (Kindle/Kobo), iOS and Kavita's web reader, with
progress mirrored to Fable. Status: **planning** (2026-10-21) — go/no-go after the Phase 1 spikes.

| File | What |
|---|---|
| `FEASIBILITY.md` | The briefing: verdict, strengths, shortcomings |
| `PRODUCT_BRIEF.md` | What / why / who, data types, user stories, scope |
| `ARCHITECTURE.md` | BookBridge-based design, canonical records, sync rules, exposure |
| `EDGE_CASES.md` | 123 failure scenarios (offline, divergence, immersion, …), rules R1–R14, owner questions Q1–Q8 |
| `BUILD_PLAN.md` | Tasks 01–28 with `Verify:` lines (Phase 0–1 detailed) |
| `research/` | Inventory, Kavita/KOReader/iOS, ABS/Fable/alignment, source checks |
| `refs/` | Shallow clones for reading only — **never execute**: BookBridge, ShelfSync, AnnotationSync.koplugin, OPDSfoldersync.koplugin, Kavita `openapi.json` v0.9.1.4 |

Vault note: `Reference/Guides/Projects/readsync.md`.

## Next session: start here

1. Read `FEASIBILITY.md`, then `ARCHITECTURE.md`, then the Phase 0 tasks in `BUILD_PLAN.md`. `EDGE_CASES.md` is
   reference; it matters from Phase 1 on.
2. **Phase 0 changes the live stack on thebigbox** (Kavita and ABS). Gate is `every-task`: ask the owner before each
   of Tasks 01–05, run its `Verify:`, report, then ask again.
3. Order matters: Task 01 (backups) before Task 02 (upgrade); Task 03 (unnest libraries) before anything maps books.
4. Task 04 needs the owner to create the API keys in the web UIs; never print, log or commit them. `.env` is mode 600.
5. After any stack change: update the vault notes ([[Kavita]], [[Audiobookshelf]]) and append to `Stack Log.md` in
   the same session (vault: `~/Documents/Notes/Reference/Guides/`, rules in `Documentation Maintenance.md`).
6. Nothing in `refs/` is ever executed; BookBridge runs only from its pinned image (Phase 1, Task 08).
