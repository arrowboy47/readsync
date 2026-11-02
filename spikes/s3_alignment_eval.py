"""S3 accuracy gate: N random timestamps -> 20 s clip -> Whisper text -> must fuzzy-match (>=80)
the ebook text the alignment map says is spoken there.
usage: s3_alignment_eval.py --book time-war --samples 10 --min-hits 9 [--work DIR] [--seed 7]
Needs: ffmpeg, rapidfuzz, whisper shim on :9092 (text only), DIR with audio/, map.json, ebook_text.txt, stats.json."""
import argparse, bisect, glob, json, os, random, subprocess, sys, tempfile
import requests
from rapidfuzz import fuzz

ap = argparse.ArgumentParser()
ap.add_argument("--book", required=True); ap.add_argument("--samples", type=int, default=10)
ap.add_argument("--min-hits", type=int, default=9); ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--clip", type=float, default=20.0); ap.add_argument("--min-score", type=float, default=80.0)
ap.add_argument("--work", default=os.environ.get("S3_WORK", ""))
ap.add_argument("--whisper", default=os.environ.get("WHISPER_URL", "http://192.168.1.158:9092/v1/audio/transcriptions"))
ap.add_argument("--report", default="")
a = ap.parse_args()
W = a.work
amap = json.load(open(f"{W}/map.json")); text = open(f"{W}/ebook_text.txt").read()
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
rng = random.Random(a.seed); hits = 0; rows = []
for n in range(a.samples):
    t = rng.uniform(60, total - 60 - a.clip)
    k = bisect.bisect_right(starts, t) - 1; local = t - starts[k]
    if local + a.clip > durs[k]:  # keep clip inside one file; shift back
        local = max(0, durs[k] - a.clip); t = starts[k] + local
    with tempfile.TemporaryDirectory() as td:
        clip = f"{td}/c.wav"
        subprocess.run(["ffmpeg","-loglevel","error","-y","-ss",f"{local:.2f}","-t",f"{a.clip}","-i",mp3s[k],"-ar","16000","-ac","1",clip],check=True)
        r = requests.post(a.whisper, files={"file": open(clip,"rb")}, data={"model":"whisper-1"}, timeout=120); r.raise_for_status()
    heard = r.json()["text"].strip()
    c0, c1 = char_at(t - 3), char_at(t + a.clip + 3)   # 3 s slack either side
    expect = text[c0:c1]
    score = fuzz.partial_ratio(heard.lower(), expect.lower())
    ok = score >= a.min_score; hits += ok
    rows.append({"t": round(t,1), "file": os.path.basename(mp3s[k]), "score": round(score,1), "ok": ok, "heard": heard[:120], "expected": expect[:120]})
    print(f"{n+1:2d} t={t:8.1f}s score={score:5.1f} {'OK ' if ok else 'MISS'} | {heard[:70]!r}", flush=True)
res = {"samples": a.samples, "hits": hits, "min_hits": a.min_hits, "seed": a.seed, "rows": rows}
if a.report: json.dump(res, open(a.report, "w"), indent=1)
print(f"hits {hits}/{a.samples} (need {a.min_hits})")
sys.exit(0 if hits >= a.min_hits else 1)
