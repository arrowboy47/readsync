"""S6: Fable login and progress write (port of ShelfSync's fable/api.lua calls).
usage: s6_fable.py --explore                     read-only: login, profile, currently-reading shelf
       s6_fable.py --add "Title Author" [--pct N] search, put the first hit on 'currently reading', post N percent, read back
       s6_fable.py --roundtrip [--book ID]       re-post the CURRENT percentage of a shelved book (idempotent) and read it back
       s6_fable.py --remove --book ID            take a book off every list
Env: FABLE_EMAIL, FABLE_PASSWORD (from .env). The Firebase web key is public (it ships in Fable's own client) and is read from the
ShelfSync checkout unless FIREBASE_API_KEY is set. No token or password is printed or written."""
import argparse, json, os, re, sys, urllib.parse
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--explore", action="store_true")
ap.add_argument("--add", default="")
ap.add_argument("--pct", type=int, default=12)
ap.add_argument("--roundtrip", action="store_true")
ap.add_argument("--remove", action="store_true")
ap.add_argument("--book", default="")
ap.add_argument("--report", default="")
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
key = os.environ.get("FIREBASE_API_KEY")
if not key:
    src = open(os.path.join(here, "..", "refs", "ShelfSync", "shelfsync", "lib", "fable", "api.lua")).read()
    key = re.search(r'FIREBASE_API_KEY\s*=\s*"([^"]+)"', src).group(1)
BASE = "https://api.fable.co"
r = requests.post(f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={key}",
                  json={"email": os.environ["FABLE_EMAIL"], "password": os.environ["FABLE_PASSWORD"], "returnSecureToken": True}, timeout=30)
if r.status_code != 200:
    print("login failed:", r.status_code, r.json().get("error", {}).get("message"))
    sys.exit(2)
H = {"Authorization": "JWT " + r.json()["idToken"], "Content-Type": "application/json", "User-Agent": "readsync-spike"}


def api(path, method="GET", body=None):
    x = requests.request(method, BASE + path, headers=H, json=body, timeout=30)
    try:
        return x.status_code, x.json()
    except Exception:
        return x.status_code, x.text[:200]


c, me = api("/api/settings/profile/")
uid = me["id"]
c, lists = api(f"/api/v2/users/{uid}/book_lists?limit=20&offset=0&media_type=book")
sysl = {l["system_type"]: l["id"] for l in lists["results"] if l.get("type") == "system"}
out = {"system_lists": sorted(sysl)}


def current():
    c, cur = api(f"/api/v2/users/{uid}/book_lists/{sysl['current_reading']}/books?limit=100&offset=0")
    return cur.get("results", cur) if isinstance(cur, dict) else cur


def progress_of(bid):
    # the viewer's progress lives at /reading_progress (the book detail only carries status and page_count)
    c, d = api(f"/api/books/{bid}/reading_progress")
    resp = d if isinstance(d, dict) else {}
    return c, resp, dict(resp)


if a.explore:
    for e in current():
        b = e.get("book", e)
        print(b.get("id"), "|", (b.get("title") or "")[:50])

if a.add:
    c, s = api("/api/books/search/?auto=" + urllib.parse.quote(a.add) + "&include=out_of_catalog&type=book&limit=5&offset=0")
    hits = (s.get("response", {}) or {}).get("books", []) if isinstance(s, dict) else []
    print("search", c, [(h.get("id"), h.get("title"), (h.get("authors") or [{}])[0].get("name") if h.get("authors") else None) for h in hits[:5]])
    if not hits:
        sys.exit(3)
    bid = hits[0]["id"]
    others = [v for k, v in sysl.items() if k != "current_reading"]
    c, _ = api(f"/api/v2/users/{uid}/book_lists/book", "POST", {"type": "multiselect", "book_id": bid, "book_list_ids": [sysl["current_reading"]], "exclude_from": others})
    print("shelve ->", c)
    c, _ = api(f"/api/books/{bid}/reading_progress", "POST", {"status": "reading", "social_accounts": [], "current_percentage": a.pct, "selected_mode": "percentage"})
    print(f"post {a.pct}% ->", c)
    c, resp, prog = progress_of(bid)
    print("book", c, "progress-ish:", json.dumps(prog, default=str)[:500])
    out["added"] = {"book": bid, "title": hits[0].get("title"), "posted_pct": a.pct, "progress_fields": prog}

if a.roundtrip:
    books = current()
    bid = a.book or (books[0].get("book", books[0]).get("id") if books else "")
    if not bid:
        print("nothing on the shelf")
        sys.exit(3)
    c, resp, prog = progress_of(bid)
    print("before", json.dumps(prog, default=str)[:400])
    pct = resp.get("current_percentage")
    if pct is None:
        print("no current_percentage in the detail; refusing to write")
        sys.exit(3)
    c2, _ = api(f"/api/books/{bid}/reading_progress", "POST", {"status": "reading", "social_accounts": [], "current_percentage": int(pct), "selected_mode": "percentage"})
    c3, resp2, prog2 = progress_of(bid)
    after = resp2.get("current_percentage")
    print("re-post", pct, "->", c2, "after", after)
    out["roundtrip"] = {"book": bid, "before": pct, "after": after, "post_status": c2}
    if a.report:
        json.dump(out, open(a.report, "w"), indent=1, default=str)
    sys.exit(0 if c2 in (200, 201) and after == pct else 1)

if a.remove and a.book:
    c, _ = api(f"/api/v2/users/{uid}/book_lists/book", "POST", {"type": "co.fable.data.BookListRequest.RemoveFromLibrary", "book_id": a.book, "remove_from_all_lists": True})
    print("remove ->", c)

if a.report:
    json.dump(out, open(a.report, "w"), indent=1, default=str)
