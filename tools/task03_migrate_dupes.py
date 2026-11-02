"""Task 03 helper: copy the two items that exist only on the NonFiction duplicates onto the Study copies.

Idempotent. Reads KAVITA_URL / KAVITA_API_KEY from the environment (source .env first). Never prints keys or note text.
  python3 -I tools/task03_migrate_dupes.py          # dry run
  python3 -I tools/task03_migrate_dupes.py --apply
"""
import json, os, sys, urllib.request

URL, KEY = os.environ["KAVITA_URL"], os.environ["KAVITA_API_KEY"]
APPLY = "--apply" in sys.argv


def call(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method, headers={"x-api-key": KEY, "Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req) as r:
        raw = r.read()
        return json.loads(raw) if raw else None

# 1) Automate the Boring Stuff: NonFiction copy (lib 3, series 89, vol 89, chap 98, p.205) -> Study copy (lib 6, 83/83/86)
dst = dict(libraryId=6, seriesId=83, volumeId=83, chapterId=86)
cur = call("GET", "/api/Reader/get-progress?chapterId=86")
print("automate: study progress now", cur.get("pageNum") if cur else None, "-> want 205")
if (cur or {}).get("pageNum", 0) < 205:
    print("  apply" if APPLY else "  dry-run: would post progress")
    if APPLY:
        call("POST", "/api/Reader/progress", {**dst, "pageNum": 205, "bookScrollId": None})
        print("  now", call("GET", "/api/Reader/get-progress?chapterId=86").get("pageNum"))

# 2) AI Agents annotation id 1 (chap 95) -> Study copy chap 80 (lib 6, series 77, vol 77)
src = call("GET", "/api/Annotation/1")
existing = call("GET", "/api/Annotation/all-for-series?seriesId=77") or []
dup = [a for a in existing if a.get("xPath") == src["xPath"] and a.get("selectedText") == src["selectedText"]]
print("annotation: source chap", src["chapterId"], "| already on study copy:", len(dup))
if not dup:
    keep = {k: src[k] for k in ("chapterTitle", "comment", "commentHtml", "commentPlainText", "containsSpoiler", "context",
                                "endingXPath", "highlightCount", "pageNumber", "selectedSlotIndex", "selectedText", "xPath", "ownerUserId")
            if k in src}
    new = {**keep, "libraryId": 6, "seriesId": 77, "volumeId": 77, "chapterId": 80}
    print("  apply" if APPLY else "  dry-run: would create annotation")
    if APPLY:
        r = call("POST", "/api/Annotation/create", new)
        print("  created id", (r or {}).get("id"))
