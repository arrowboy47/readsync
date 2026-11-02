"""Compare every EPUB/PDF on mounted KOReader devices with Kavita's copies by KOReader hash.
usage: device_vs_kavita.py DEVICE_ROOT... ; needs KAVITA_URL, KAVITA_API_KEY. Read-only on devices."""
import os, sys, hashlib, requests
def partial_md5(path):
    m = hashlib.md5()
    with open(path, "rb") as f:
        for i in range(-1, 11):
            f.seek(1024 << (2 * i) if i >= 0 else 0); b = f.read(1024)
            if not b: break
            m.update(b)
    return m.hexdigest()
U = os.environ["KAVITA_URL"].rstrip("/")
tok = requests.post(f"{U}/api/Plugin/authenticate", params={"apiKey": os.environ["KAVITA_API_KEY"], "pluginName": "readsync"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
series = requests.post(f"{U}/api/Series/v2", headers=H, params={"PageNumber": 1, "PageSize": 1000}, json={"statements": [], "combination": 1, "limitTo": 0}).json()
kav = {}
for s in series:
    d = requests.get(f"{U}/api/Series/series-detail", headers=H, params={"seriesId": s["id"]}).json()
    for k in ("volumes", "chapters", "specials", "storylineChapters"):
        for x in d.get(k, []):
            for c in x.get("chapters", [x]):
                for f in c.get("files", []):
                    if f.get("koreaderHash"): kav[f["koreaderHash"].lower()] = (s["name"], os.path.basename(f["filePath"]))
print(f"Kavita: {len(kav)} hashed files")
for root in sys.argv[1:]:
    print("==", root); n = hit = 0
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if not d.startswith(".") and d not in ("koreader", "system", "extensions", "documents")]
        for f in fs:
            if f.lower().endswith((".epub", ".pdf")):
                n += 1; h = partial_md5(os.path.join(r, f)); m = kav.get(h)
                hit += bool(m); print(("MATCH   " if m else "no match"), f[:70], "->", m[0][:40] if m else "")
    print(f"{hit}/{n} on this device are byte-identical to a Kavita copy")
