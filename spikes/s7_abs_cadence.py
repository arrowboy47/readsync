"""S7: Audiobookshelf app behaviour. Logs every socket event with a timestamp while the owner follows a script in the iOS app,
and lets the script read or change server-side progress and read bookmarks.
usage: s7_abs_cadence.py --listen SECONDS [--log FILE]      log all socket events (JSON lines)
       s7_abs_cadence.py --show                              progress + bookmarks for the test book
       s7_abs_cadence.py --patch SECONDS                     set server-side currentTime (PATCH /api/me/progress)
       s7_abs_cadence.py --report research/spikes/S7.json    summarise a --log file (median interval between progress events)
Test book: This Is How You Lose the Time War. Needs ABS_URL, ABS_API_KEY."""
import argparse, json, os, statistics, sys, time
import requests
import socketio

ITEM = "2ea1f4a1-4b46-4d67-a4e0-42ef6458ab70"
ap = argparse.ArgumentParser()
ap.add_argument("--listen", type=int, default=0)
ap.add_argument("--log", default=os.path.expanduser("~/readsync-work/s7_events.jsonl"))
ap.add_argument("--show", action="store_true")
ap.add_argument("--patch", type=float, default=None)
ap.add_argument("--summarise", default="", help="path of the JSON report to write from --log")
a = ap.parse_args()
U = os.environ["ABS_URL"].rstrip("/")
KEY = os.environ["ABS_API_KEY"]
H = {"Authorization": "Bearer " + KEY}


def progress():
    r = requests.get(f"{U}/api/me/progress/{ITEM}", headers=H)
    return r.status_code, (r.json() if r.ok else r.text[:100])


if a.show:
    c, p = progress()
    print("progress", c, json.dumps({k: p.get(k) for k in ("currentTime", "progress", "duration", "isFinished", "lastUpdate")}) if isinstance(p, dict) else p)
    me = requests.get(f"{U}/api/me", headers=H).json()
    bm = [b for b in me.get("bookmarks", []) if b.get("libraryItemId") == ITEM]
    print("bookmarks on this book:", json.dumps(bm)[:600])

if a.patch is not None:
    r = requests.patch(f"{U}/api/me/progress/{ITEM}", headers=H, json={"currentTime": a.patch})
    print("PATCH currentTime", a.patch, "->", r.status_code, time.strftime("%H:%M:%S"))

if a.listen:
    sio = socketio.Client()
    t0 = time.time()
    f = open(a.log, "a")

    def rec(name):
        def h(*args):
            row = {"t": round(time.time() - t0, 2), "wall": time.strftime("%H:%M:%S"), "event": name, "data": args[0] if args else None}
            f.write(json.dumps(row, default=str) + "\n")
            f.flush()
            d = row["data"].get("data", row["data"]) if isinstance(row["data"], dict) else row["data"]
            ct = d.get("currentTime") if isinstance(d, dict) else None
            print(f"[{row['wall']}] {name} currentTime={ct}", flush=True)
        return h

    for n in ("user_item_progress_updated", "user_updated", "user_online", "user_offline", "item_updated", "playback_session", "stream_progress"):
        sio.on(n, rec(n))
    sio.on("init", lambda *x: print("socket authenticated", flush=True))
    sio.connect(U, transports=["websocket"])
    sio.emit("auth", KEY)
    time.sleep(a.listen)
    sio.disconnect()
    print("done", flush=True)

if a.summarise:
    rows = [json.loads(l) for l in open(a.log)]
    ts = [r["t"] for r in rows if r["event"] == "user_item_progress_updated"]
    gaps = [round(y - x, 1) for x, y in zip(ts, ts[1:])]
    out = {"events": len(ts), "gaps_s": gaps, "median_interval_s": statistics.median(gaps) if gaps else 0}
    json.dump(out, open(a.summarise, "w"), indent=1)
    print(out)
