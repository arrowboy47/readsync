"""S4: locate a passage from a 20 s Whisper clip alone (no alignment map), then compare with the S3 map.
usage: s4_clip_lookup.py --book time-war --samples 10 --agree-with-s3 9 [--work DIR] [--seed 7] [--report FILE]
Same timestamps as s3_alignment_eval.py (same seed + sampling). Search window = +-10% of the book text around
the position implied by t/total (what a player knows: roughly how far through the audio it is).
Plus two hard cases (D2): the very start (credits/intro) and the first seconds of a mid-book file (chapter announcement).
Needs: ffmpeg, rapidfuzz, requests, whisper shim on :9092 (text only)."""
import argparse, bisect, glob, json, os, random, subprocess, sys, tempfile
import requests
from rapidfuzz import fuzz

ap = argparse.ArgumentParser()
ap.add_argument("--book", required=True); ap.add_argument("--samples", type=int, default=10)
ap.add_argument("--agree-with-s3", type=int, default=9); ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--clip", type=float, default=20.0); ap.add_argument("--window", type=float, default=0.10)
ap.add_argument("--tol", type=int, default=1500, help="max char distance from the map position to count as agreeing")
ap.add_argument("--work", default=os.environ.get("S3_WORK", "/home/Jadu/readsync-work/s3"))
ap.add_argument("--whisper", default=os.environ.get("WHISPER_URL", "http://192.168.1.158:9092") .rstrip("/") + "/v1/audio/transcriptions"
                if "/v1/" not in os.environ.get("WHISPER_URL", "") else os.environ["WHISPER_URL"])
ap.add_argument("--report", default="")
a = ap.parse_args()
W = a.work
amap = json.load(open(f"{W}/map.json")); text = open(f"{W}/ebook_text.txt").read(); low = text.lower()
ts = [p["ts"] for p in amap]; ch = [p["char"] for p in amap]

def char_at(t):
    i = bisect.bisect_right(ts, t)
    if i <= 0: return ch[0]
    if i >= len(ts): return ch[-1]
    t0, t1, c0, c1 = ts[i-1], ts[i], ch[i-1], ch[i]
    return int(c0 + (c1 - c0) * ((t - t0) / (t1 - t0))) if t1 > t0 else c0

mp3s = sorted(glob.glob(f"{W}/audio/*.mp3")); durs = []
for m in mp3s:
    durs.append(float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",m]).strip()))
total = sum(durs); starts = [sum(durs[:i]) for i in range(len(durs))]

def transcribe(t):
    k = bisect.bisect_right(starts, t) - 1; local = t - starts[k]
    with tempfile.TemporaryDirectory() as td:
        clip = f"{td}/c.wav"
        subprocess.run(["ffmpeg","-loglevel","error","-y","-ss",f"{local:.2f}","-t",f"{a.clip}","-i",mp3s[k],"-ar","16000","-ac","1",clip],check=True)
        r = requests.post(a.whisper, files={"file": open(clip,"rb")}, data={"model":"whisper-1"}, timeout=120); r.raise_for_status()
    return r.json()["text"].strip()

def locate(heard, frac):
    """Return (best_char, best_score, runner_up_score, margin) searching +-window of the text around frac."""
    n = len(low); lo = max(0, int((frac - a.window) * n)); hi = min(n, int((frac + a.window) * n))
    q = heard.lower()
    if len(q) < 20: return None
    size = int(max(len(q) * 1.3, 200)); step = max(size // 4, 20)
    cands = []
    for s in range(lo, max(lo + 1, hi - size), step):
        cands.append((fuzz.partial_ratio(q, low[s:s+size]), s))
    cands.sort(reverse=True)
    best = cands[0]
    runner = next((c for c in cands[1:] if abs(c[1] - best[1]) > size), (0.0, -1))
    return best[1] + size // 2, best[0], runner[0], best[0] - runner[0]

rng = random.Random(a.seed); rows = []; agree = 0
for n in range(a.samples):          # identical sampling to s3_alignment_eval.py
    t = rng.uniform(60, total - 60 - a.clip)
    k = bisect.bisect_right(starts, t) - 1; local = t - starts[k]
    if local + a.clip > durs[k]:
        local = max(0, durs[k] - a.clip); t = starts[k] + local
    heard = transcribe(t); want = char_at(t + a.clip / 2)
    res = locate(heard, t / total)
    if not res: rows.append({"t": round(t,1), "heard": heard, "found": None}); print(f"{n+1:2d} t={t:8.1f}s NO-TEXT {heard!r}"); continue
    got, sc, run, margin = res; dist = abs(got - want); ok = dist <= a.tol; agree += ok
    rows.append({"t": round(t,1), "heard": heard[:120], "map_char": want, "found_char": got, "dist": dist,
                 "score": round(sc,1), "runner_up": round(run,1), "margin": round(margin,1), "agree": ok})
    print(f"{n+1:2d} t={t:8.1f}s dist={dist:6d} score={sc:5.1f} runner={run:5.1f} margin={margin:5.1f} {'OK ' if ok else 'MISS'} | {heard[:60]!r}", flush=True)

hard = []
mid = len(durs) // 2
for label, t in (("intro/credits (t=2s)", 2.0), (f"file-start chapter announcement (file {mid+1}, t+1s)", starts[mid] + 1.0)):
    heard = transcribe(t); res = locate(heard, t / total); want = char_at(t + a.clip / 2)
    row = {"case": label, "t": round(t,1), "heard": heard[:160], "map_char": want}
    if res:
        got, sc, run, margin = res; row.update(found_char=got, dist=abs(got - want), score=round(sc,1), runner_up=round(run,1), margin=round(margin,1))
    else: row["found_char"] = None
    hard.append(row); print("HARD", json.dumps(row))

out = {"samples": a.samples, "agree": agree, "need": a.agree_with_s3, "tol_chars": a.tol, "window": a.window, "rows": rows, "hard": hard}
if a.report: json.dump(out, open(a.report, "w"), indent=1)
print(f"agree {agree}/{a.samples} (need {a.agree_with_s3})")
sys.exit(0 if agree >= a.agree_with_s3 else 1)
