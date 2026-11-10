"""S2 helper: connect to Kavita's messages hub and print every event for N seconds. Read-only.
usage: s2_listen.py [--seconds 180]"""
import argparse, json, os, threading, time
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder

ap = argparse.ArgumentParser()
ap.add_argument("--seconds", type=int, default=180)
a = ap.parse_args()
U = os.environ["KAVITA_URL"].rstrip("/")
TOK = requests.post(f"{U}/api/Plugin/authenticate", params={"apiKey": os.environ["KAVITA_API_KEY"], "pluginName": "readsync"}).json()["token"]
t0 = time.time()
hub = HubConnectionBuilder().with_url(f"{U}/hubs/messages", options={"access_token_factory": lambda: TOK, "verify_ssl": False}).build()
names = ["UserProgressUpdate", "AnnotationUpdate", "NotificationProgress", "ScanSeries", "SeriesAdded", "SeriesRemoved", "RefreshMetadata",
         "UserUpdate", "OnlineUsers", "Error", "Info", "ReadingList"]
for n in names:
    hub.on(n, (lambda name: lambda args: print(f"[{time.time()-t0:6.1f}s] {name}: {json.dumps(args)[:400]}", flush=True))(n))
opened = threading.Event()
hub.on_open(lambda: opened.set())
hub.start()
print("connected" if opened.wait(15) else "no connection", flush=True)
time.sleep(a.seconds)
hub.stop()
print("done", flush=True)
