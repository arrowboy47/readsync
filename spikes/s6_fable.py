"""S6: Fable login and progress write (port of ShelfSync's fable/api.lua calls).
usage: s6_fable.py --explore            read-only: login, profile, currently-reading shelf, per-book detail keys
       s6_fable.py --roundtrip          re-post the CURRENT percentage for one book already on the shelf, read it back (idempotent)
Env: FABLE_EMAIL, FABLE_PASSWORD (from .env). Firebase web key is public (ships in Fable's own client); read from the
ShelfSync checkout unless FIREBASE_API_KEY is set. No token or password is printed or written."""
import argparse, json, os, re, sys
import requests

ap = argparse.ArgumentParser(); ap.add_argument("--explore", action="store_true"); ap.add_argument("--roundtrip", action="store_true")
ap.add_argument("--book", default=""); ap.add_argument("--report", default=""); a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
key = os.environ.get("FIREBASE_API_KEY")
if not key:
    src = open(os.path.join(here, "..", "refs", "ShelfSync", "shelfsync", "lib", "fable", "api.lua")).read()
    key = re.search(r'FIREBASE_API_KEY\s*=\s*"([^"]+)"', src).group(1)
BASE = "https://api.fable.co"
r = requests.post(f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={key}",
                  json={"email": os.environ["FABLE_EMAIL"], "password": os.environ["FABLE_PASSWORD"], "returnSecureToken": True}, timeout=30)
if r.status_code != 200: print("login failed:", r.status_code, r.json().get("error", {}).get("message")); sys.exit(2)
H = {"Authorization": "JWT " + r.json()["idToken"], "Content-Type": "application/json", "User-Agent": "readsync-spike"}
def api(path, method="GET", body=None):
    x = requests.request(method, BASE + path, headers=H, json=body, timeout=30); 
    try: return x.status_code, x.json()
    except Exception: return x.status_code, x.text[:200]
out = {}
c, me = api("/api/settings/profile/"); print("profile", c, "id" in me if isinstance(me, dict) else me); uid = me["id"]
c, lists = api(f"/api/v2/users/{uid}/book_lists?limit=20&offset=0&media_type=book")
sysl = {l["system_type"]: l["id"] for l in lists["results"] if l.get("type") == "system"}; print("system lists:", sorted(sysl))
c, cur = api(f"/api/v2/users/{uid}/book_lists/{sysl['current_reading']}/books?limit=100&offset=0")
books = cur.get("results", cur) if isinstance(cur, dict) else cur
print("currently reading:", len(books))
for e in books[:10]:
    b = e.get("book", e); print("  ", b.get("id"), "|", (b.get("title") or "")[:50], "| entry keys:", sorted(e.keys())[:14])
out["currently_reading"] = [{"id": (e.get("book", e)).get("id"), "title": (e.get("book", e)).get("title")} for e in books]
if books:
    bid = a.book or (books[0].get("book", books[0])).get("id")
    c, d = api(f"/api/books/{bid}"); print("book detail", c, "keys:", sorted(d.keys()) if isinstance(d, dict) else d)
    if isinstance(d, dict):
        prog = {k: v for k, v in d.items() if any(t in k.lower() for t in ("progress", "percent", "page", "status", "read", "finish", "start"))}
        print("progress-ish fields:", json.dumps(prog, default=str)[:600]); out["detail_progress_fields"] = prog
    if a.roundtrip:
        rp = (d.get("reading_progress") or d.get("user_book") or {}) if isinstance(d, dict) else {}
        pct = rp.get("current_percentage") if isinstance(rp, dict) else None
        if pct is None: print("no current_percentage found; refusing to write"); sys.exit(3)
        print("re-posting same percentage", pct)
        c2, _ = api(f"/api/books/{bid}/reading_progress", "POST", {"status": "reading", "social_accounts": [], "current_percentage": int(pct), "selected_mode": "percentage"})
        c3, d2 = api(f"/api/books/{bid}"); rp2 = (d2.get("reading_progress") or d2.get("user_book") or {}) if isinstance(d2, dict) else {}
        print("post", c2, "after", rp2.get("current_percentage") if isinstance(rp2, dict) else None)
        out["roundtrip"] = {"book": bid, "before": pct, "post_status": c2, "after": rp2.get("current_percentage") if isinstance(rp2, dict) else None}
        ok = c2 in (200, 201) and out["roundtrip"]["after"] == pct
        if a.report: json.dump(out, open(a.report, "w"), indent=1, default=str)
        sys.exit(0 if ok else 1)
if a.report: json.dump(out, open(a.report, "w"), indent=1, default=str)
