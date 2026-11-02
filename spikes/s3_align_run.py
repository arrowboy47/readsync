"""S3 driver. Runs INSIDE the pinned BookBridge image (throwaway, no network to ABS/Kavita).

Transcribes each mp3 via the Whisper shim, offsets timestamps, aligns with BookBridge's
AlignmentService against the EPUB text, writes /work/out/{segments,map,stats}.json.
Env: WHISPER_CPP_URL, WHISPER_MODEL. Mounts: /work (rw)."""
import json, os, subprocess, sys, time, resource
from pathlib import Path

sys.path.insert(0, "/app")
os.environ.setdefault("DATA_DIR", "/work/data")
from src.db.database_service import DatabaseService
from src.services.alignment_service import AlignmentService
from src.utils.ebook_utils import EbookParser
from src.utils.polisher import Polisher
from src.utils.transcription_providers import WhisperCppServerProvider

W = Path("/work"); OUT = W / "out"; OUT.mkdir(exist_ok=True)
ABS_ID = "s3-time-war"
t0 = time.time(); stats = {"phases": {}}

def lap(name, since):
    stats["phases"][name] = round(time.time() - since, 1)

# 1. transcript (cached so a rerun does not redo audio)
seg_path = OUT / "segments.json"
if seg_path.exists():
    segments = json.loads(seg_path.read_text())
else:
    prov = WhisperCppServerProvider()
    segments, offset = [], 0.0
    t = time.time()
    for mp3 in sorted((W / "audio").glob("*.mp3")):
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)]).strip())
        for s in prov.transcribe(str(mp3)):
            s = dict(s); s["start"] += offset; s["end"] += offset
            for w in s.get("words") or []:
                w["start"] += offset; w["end"] += offset
            segments.append(s)
        offset += dur
        print(f"{mp3.name}: +{dur:.0f}s (total {offset:.0f}s, wall {time.time()-t:.0f}s)", flush=True)
    seg_path.write_text(json.dumps(segments))
    stats["audio_seconds"] = round(offset, 1)
    lap("transcribe", t)

# 2. ebook text
t = time.time()
parser = EbookParser(str(W))
text, _ = parser.extract_text_and_map(W / "timewar.epub")
stats["ebook_chars"] = len(text)
lap("extract_text", t)

# 3. align
t = time.time()
db = DatabaseService(str(W / "data" / "s3.db"))
svc = AlignmentService(db, Polisher())
ok = svc.align_and_store(ABS_ID, segments, text)
lap("align", t)
stats["align_ok"] = bool(ok)
amap = svc._get_alignment(ABS_ID) or []
stats["anchors"] = len(amap)
if amap:
    stats["map_last_char"] = max(p["char"] for p in amap)
    stats["coverage_chars"] = round(stats["map_last_char"] / max(1, len(text)), 4)
    stats["map_last_ts"] = max(p["ts"] for p in amap)
(OUT / "map.json").write_text(json.dumps(amap))
(OUT / "ebook_text.txt").write_text(text)
stats["wall_total_s"] = round(time.time() - t0, 1)
stats["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
(OUT / "stats.json").write_text(json.dumps(stats, indent=1))
print(json.dumps(stats, indent=1))
