"""S3 step 1: transcribe the Time War mp3s with whisper.cpp directly (loopback :9093, GPU1).
The :9092 shim drops timestamps, so alignment needs this direct path. Output matches
BookBridge's provider format: [{start,end,text,words:[{word,start,end}]}] with cumulative offsets.
usage: s3_transcribe_jadu.py <audio_dir> <out.json>"""
import json, subprocess, sys, time, tempfile, math
from pathlib import Path
import requests

audio_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
URL = "http://127.0.0.1:9093/inference"

def words_ok(ws):
    ok, last = [], -1.0
    for w in ws:
        t = (w.get("word") or "").strip()
        s, e = float(w["start"]), float(w["end"])
        if not t or not math.isfinite(s) or not math.isfinite(e) or e < s or s < last:
            return None
        ok.append({"word": w["word"], "start": s, "end": e}); last = s
    return ok or None

segments, offset, t0 = [], 0.0, time.time()
for mp3 in sorted(audio_dir.glob("*.mp3")):
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)], check=True)
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)]).strip())
        with open(wav, "rb") as f:
            r = requests.post(URL, files={"file": f}, data={"response_format": "verbose_json", "temperature": "0.0"}, timeout=3600)
        r.raise_for_status()
    for s in r.json().get("segments", []):
        d = {"start": float(s["start"]) + offset, "end": float(s["end"]) + offset, "text": s["text"].strip()}
        ws = words_ok(s.get("words") or [])
        if ws:
            for w in ws: w["start"] += offset; w["end"] += offset
            d["words"] = ws
        segments.append(d)
    offset += dur
    print(f"{mp3.name}: +{dur:.0f}s total {offset:.0f}s wall {time.time()-t0:.0f}s segs {len(segments)}", flush=True)
out.write_text(json.dumps(segments))
print(json.dumps({"audio_seconds": round(offset, 1), "wall_s": round(time.time() - t0, 1), "segments": len(segments)}))
