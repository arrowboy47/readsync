"""S9: mass-delete reproduction. Runs INSIDE the pinned BookBridge image, scratch SQLite DB, no network.
Device A uploads 10 highlights and acks; device B pulls and acks them. Then A sends a COMPLETE but EMPTY key list
(a wiped sidecar, E8). Records tombstones created and what B would be told to delete.
usage (in container): python /spikes/s9_mass_delete.py --expect-tombstones 10 [--report /work/s9.json]"""
import argparse, json, os, sys, tempfile
sys.path.insert(0, "/app")
from src.db.database_service import DatabaseService
from src.db.models import KoreaderAnnotation

ap = argparse.ArgumentParser(); ap.add_argument("--expect-tombstones", type=int, required=True); ap.add_argument("--report", default="")
ap.add_argument("--n", type=int, default=10); a = ap.parse_args()
db = DatabaseService(os.path.join(tempfile.mkdtemp(), "s9.db"))
MD5, USER = "6c90f3d5a05d69648130e776d73add99", 1
def entry(i):
    return {"datetime": f"2026-10-30 12:00:{i:02d}", "pos0": f"/body/DocFragment[3]/body/div/p[{i+1}]/text().0",
            "pos1": f"/body/DocFragment[3]/body/div/p[{i+1}]/text().40", "text": f"highlight {i}", "drawer": "lighten", "color": "yellow", "chapter": "Ch 1", "pageno": 10 + i}
ents = [entry(i) for i in range(a.n)]
keys = [{"k": db.compute_annotation_key(e["datetime"], e["pos0"]), "dt": e["datetime"]} for e in ents]

r = db.exchange_koreader_annotations(USER, "A", [{"hash": MD5, "keys": keys, "keysComplete": True, "changes": ents}])
print("A upload ->", {k: len(v) for k, v in r["books"][0]["toApply"].items()})
rb = db.exchange_koreader_annotations(USER, "B", [{"hash": MD5, "keys": [], "keysComplete": True, "changes": []}])
adds = rb["books"][0]["toApply"]["add"]; print("B pull: adds", len(adds))
db.ack_koreader_annotations(USER, "B", [{"hash": MD5, "applied": [{"serverId": x["serverId"], "version": x.get("version", 1)} for x in adds]}])
# A's sidecar is wiped: complete key list with no keys, no changes
r2 = db.exchange_koreader_annotations(USER, "A", [{"hash": MD5, "keys": [], "keysComplete": True, "changes": []}])
with db.get_session() as s:
    tomb = s.query(KoreaderAnnotation).filter(KoreaderAnnotation.md5 == MD5, KoreaderAnnotation.deleted == True).count()  # noqa: E712
    live = s.query(KoreaderAnnotation).filter(KoreaderAnnotation.md5 == MD5, KoreaderAnnotation.deleted == False).count()  # noqa: E712
rb2 = db.exchange_koreader_annotations(USER, "B", [{"hash": MD5, "keys": keys, "keysComplete": True, "changes": []}])
b_del = len(rb2["books"][0]["toApply"]["delete"])
res = {"uploaded": a.n, "tombstones": tomb, "live": live, "device_B_told_to_delete": b_del,
       "A_response_delete": len(r2["books"][0]["toApply"]["delete"])}
print(json.dumps(res))
if a.report: json.dump(res, open(a.report, "w"), indent=1)
sys.exit(0 if tomb == a.expect_tombstones else 1)
