"""S2 helper: poll Kavita for one chapter (progress incl. bookScrollId) and a series (annotations) and print every change.
usage: s2_watch.py [--series 90] [--chapter 102] [--seconds 900]; needs KAVITA_URL, KAVITA_API_KEY. Read-only."""
import argparse, json, os, time
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--series", type=int, default=90)
ap.add_argument("--chapter", type=int, default=102)
ap.add_argument("--seconds", type=int, default=900)
a = ap.parse_args()
U = os.environ["KAVITA_URL"].rstrip("/")
tok = requests.post(f"{U}/api/Plugin/authenticate", params={"apiKey": os.environ["KAVITA_API_KEY"], "pluginName": "readsync"}).json()["token"]
H = {"Authorization": "Bearer " + tok}
last = None
lastann = None
t0 = time.time()
while time.time() - t0 < a.seconds:
    p = requests.get(f"{U}/api/Reader/get-progress", headers=H, params={"chapterId": a.chapter}).json()
    cur = (p.get("pageNum"), p.get("bookScrollId"))
    if cur != last:
        print(f"[{time.time()-t0:6.1f}s] progress page={cur[0]} scroll={cur[1]} modified={p.get('lastModifiedUtc')}", flush=True)
        last = cur
    ann = requests.get(f"{U}/api/Annotation/all-for-series", headers=H, params={"seriesId": a.series}).json()
    sig = [(x["id"], x["xPath"], x["endingXPath"], x["selectedText"][:40], x["pageNumber"], x.get("comment")) for x in ann]
    if sig != lastann:
        print(f"[{time.time()-t0:6.1f}s] annotations={json.dumps(sig)}", flush=True)
        lastann = sig
    time.sleep(1.5)
