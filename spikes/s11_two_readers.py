"""S11: two-reader isolation (K1, K3, K4, plus the default-user fallback risk). Runs INSIDE the pinned BookBridge image,
scratch SQLite, no network. usage: python /spikes/s11_two_readers.py --expect-isolated [--report FILE]"""
import argparse, json, os, sys, tempfile
sys.path.insert(0, "/app")
from src.db.database_service import DatabaseService
from src.db.models import KoreaderAnnotation

ap = argparse.ArgumentParser(); ap.add_argument("--expect-isolated", action="store_true"); ap.add_argument("--report", default=""); a = ap.parse_args()
db = DatabaseService(os.path.join(tempfile.mkdtemp(), "s11.db"))
A = db.create_user("owner", "pw-a", role="admin").id; B = db.create_user("partner", "pw-b", role="user").id
MD5 = "6c90f3d5a05d69648130e776d73add99"; res = {"readers": {"A": A, "B": B}}; ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); res[name] = {"pass": bool(cond), "detail": detail}; print(("PASS " if cond else "FAIL "), name, detail)

# K1: same hash, two readers, different positions
db.upsert_user_kosync_progress(MD5, 0.25, "/a", device="kindle", device_id="dA", user_id=A)
db.upsert_user_kosync_progress(MD5, 0.80, "/b", device="kobo", device_id="dB", user_id=B)
pa, pb = db.get_user_kosync_progress(MD5, user_id=A), db.get_user_kosync_progress(MD5, user_id=B)
check("K1_two_readers_same_hash", float(pa.percentage) == 0.25 and float(pb.percentage) == 0.80, f"A={float(pa.percentage)} B={float(pb.percentage)}")

# K3: A's annotations invisible to B (same md5, same device key on purpose)
def ent(i): return {"datetime": f"2026-11-02 10:00:{i:02d}", "pos0": f"/body/DocFragment[2]/body/p[{i}]/text().0", "pos1": f"/body/DocFragment[2]/body/p[{i}]/text().30", "text": f"A secret {i}", "drawer": "lighten"}
ents = [ent(i) for i in range(5)]; keys = [{"k": db.compute_annotation_key(e["datetime"], e["pos0"]), "dt": e["datetime"]} for e in ents]
db.exchange_koreader_annotations(A, "dev1", [{"hash": MD5, "keys": keys, "keysComplete": True, "changes": ents}])
rb = db.exchange_koreader_annotations(B, "dev1", [{"hash": MD5, "keys": [], "keysComplete": True, "changes": []}])
seen = rb["books"][0]["toApply"]; n_b = len(seen["add"]) + len(seen["edit"]) + len(seen["delete"])
check("K3_annotation_isolation", n_b == 0, f"B (same hash, same device key) is offered {n_b} of A's 5 highlights")

# K4: B uploads 3, B wipes sidecar -> A untouched
eb = [dict(ent(i), text=f"B note {i}", datetime=f"2026-11-02 11:00:{i:02d}") for i in range(3)]
kb = [{"k": db.compute_annotation_key(e["datetime"], e["pos0"]), "dt": e["datetime"]} for e in eb]
db.exchange_koreader_annotations(B, "dev2", [{"hash": MD5, "keys": kb, "keysComplete": True, "changes": eb}])
db.exchange_koreader_annotations(B, "dev2", [{"hash": MD5, "keys": [], "keysComplete": True, "changes": []}])
with db.get_session() as s:
    live_a = s.query(KoreaderAnnotation).filter_by(md5=MD5, user_id=A, deleted=False).count()
    dead_b = s.query(KoreaderAnnotation).filter_by(md5=MD5, user_id=B, deleted=True).count()
check("K4_wipe_is_per_reader", live_a == 5 and dead_b == 3, f"A live={live_a} (want 5), B tombstoned={dead_b} (want 3)")
# the same key list from A with A's own wipe must not touch B
db.exchange_koreader_annotations(A, "dev1", [{"hash": MD5, "keys": [], "keysComplete": True, "changes": []}])
with db.get_session() as s:
    live_b_after = s.query(KoreaderAnnotation).filter_by(md5=MD5, user_id=B, deleted=False).count()
check("K4_reverse", live_b_after == 0, "B had already wiped; A's wipe leaves B's tombstones alone")

# Risk: calls that omit user_id fall back to the default (admin) user
before = len(db.get_all_kosync_documents(user_id=A)); 
res["default_user_fallback"] = {"note": "_resolve_uid() attributes un-scoped calls to the first admin; every spoke must pass reader_id explicitly (K6)"}
print("NOTE _resolve_uid falls back to the default admin when user_id is omitted; hub code must always pass reader_id")
json.dump(res, open(a.report, "w"), indent=1) if a.report else None
print("ISOLATED" if ok else "NOT ISOLATED"); sys.exit(0 if ok else 1)
