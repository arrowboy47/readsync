"""S2: Kavita SignalR events. Connects to the messages hub, writes progress (and optionally an annotation) through the
REST API, and records which events arrive, their payload shapes and delay (echo of our own writes, rule R8).
Restores the original progress afterwards.
usage: s2_kavita_signalr.py --expect UserProgressUpdate,AnnotationUpdate [--series 90] [--report FILE] [--no-annotation]
Run with the venv that has signalrcore + requests: /home/Jadu/readsync-work/venv/bin/python"""
import argparse, json, os, sys, threading, time
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder

ap = argparse.ArgumentParser()
ap.add_argument("--expect", default="UserProgressUpdate,AnnotationUpdate")
ap.add_argument("--series", type=int, default=90)
ap.add_argument("--report", default="")
ap.add_argument("--no-annotation", action="store_true")
ap.add_argument("--listen", type=int, default=0, help="extra seconds to just listen (owner uses the browser meanwhile)")
a = ap.parse_args()
U = os.environ["KAVITA_URL"].rstrip("/")
login = requests.post(f"{U}/api/Plugin/authenticate", params={"apiKey": os.environ["KAVITA_API_KEY"], "pluginName": "readsync"}).json()
TOK = login["token"]; H = {"Authorization": f"Bearer {TOK}"}

events = []; t0 = time.time(); lock = threading.Lock()
def rec(name):
    def f(args):
        with lock: events.append({"t": round(time.time() - t0, 2), "event": name, "args": args})
        print(f"[{time.time()-t0:6.2f}s] {name}: {json.dumps(args)[:300]}", flush=True)
    return f

hub = (HubConnectionBuilder()
       .with_url(f"{U}/hubs/messages", options={"access_token_factory": lambda: TOK, "verify_ssl": False})
       .with_automatic_reconnect({"type": "raw", "keep_alive_interval": 10, "reconnect_interval": 5, "max_attempts": 3})
       .build())
NAMES = ["UserProgressUpdate", "AnnotationUpdate", "NotificationProgress", "ScanSeries", "SeriesAdded", "SeriesRemoved",
         "RefreshMetadata", "UserUpdate", "OnlineUsers", "ReadingList", "Error", "Info", "UserProgress", "SiteThemeProgress"]
for n in NAMES: hub.on(n, rec(n))
opened = threading.Event(); hub.on_open(lambda: opened.set()); hub.on_error(lambda e: print("hub error", e))
hub.start()
if not opened.wait(15): print("could not connect to /hubs/messages"); sys.exit(2)
print("connected"); time.sleep(2)

d = requests.get(f"{U}/api/Series/series-detail", headers=H, params={"seriesId": a.series}).json()
chap = None
for k in ("volumes", "chapters", "specials", "storylineChapters"):
    for x in d.get(k, []):
        for c in x.get("chapters", [x]): chap = chap or c
cid, vid = chap["id"], chap["volumeId"]; pages = chap["pages"]
lib = requests.get(f"{U}/api/Series/{a.series}", headers=H).json()["libraryId"]
orig = requests.get(f"{U}/api/Reader/get-progress", headers=H, params={"chapterId": cid}).json()
print("original progress", orig)

def post(page, scroll=None):
    body = {"libraryId": lib, "seriesId": a.series, "volumeId": vid, "chapterId": cid, "pageNum": page, "bookScrollId": scroll}
    r = requests.post(f"{U}/api/Reader/progress", headers=H, json=body); return r.status_code

try:
    mark = len(events); t1 = time.time()
    print("POST progress page 5 ->", post(5, "//body/div[1]/p[2]")); time.sleep(6)
    got = [e for e in events[mark:] if e["event"] == "UserProgressUpdate"]
    print("progress events:", len(got), "first after", (got[0]["t"] - (t1 - t0)) if got else None)
    if not a.no_annotation:
        mark = len(events)
        body = {"id": 0, "ownerUserId": 1, "ownerUsername": login["username"], "libraryId": lib, "seriesId": a.series, "volumeId": vid, "chapterId": cid, "pageNumber": 5,
                "xPath": "//body/div[1]/p[2]", "endingXPath": "//body/div[1]/p[2]", "selectedText": "readsync S2 test",
                "comment": "", "highlightCount": 16, "containsSpoiler": False, "selectedSlotIndex": 0}
        r = requests.post(f"{U}/api/Annotation/create", headers=H, json=body); print("create annotation ->", r.status_code, r.text[:200])
        time.sleep(4)
        if r.ok:
            ann = r.json(); aid = ann.get("id") if isinstance(ann, dict) else None
            if aid: print("delete ->", requests.delete(f"{U}/api/Annotation", headers=H, params={"annotationId": aid}).status_code)
            time.sleep(4)
    if a.listen:
        print(f"listening {a.listen}s - use the Kavita reader now"); time.sleep(a.listen)
finally:
    body = {"libraryId": lib, "seriesId": a.series, "volumeId": vid, "chapterId": cid, "pageNum": orig.get("pageNum", 0), "bookScrollId": orig.get("bookScrollId")}
    print("restore progress ->", requests.post(f"{U}/api/Reader/progress", headers=H, json=body).status_code)
    time.sleep(2); hub.stop()
    after = requests.get(f"{U}/api/Reader/get-progress", headers=H, params={"chapterId": cid}).json(); print("progress after restore", after)

seen = sorted({e["event"] for e in events})
print("events seen:", seen)
if a.report: json.dump({"original": orig, "events": events, "seen": seen}, open(a.report, "w"), indent=1, default=str)
need = [x for x in a.expect.split(",") if x]
missing = [x for x in need if x not in seen]
print("missing:", missing); sys.exit(1 if missing else 0)
