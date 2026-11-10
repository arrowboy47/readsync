"""S1: create a Kavita annotation through the API using only xPath, endingXPath, selectedText, pageNumber and ids.
usage: s1_kavita_annotation.py --create     create one highlight (page 23, p[13]) with a Quill note, print it, leave it for a visual check
       s1_kavita_annotation.py --edge       try empty selectedText, end-before-start, missing paragraph; record status; delete what was created
       s1_kavita_annotation.py --cleanup    delete every annotation whose note contains 'readsync API test'
       s1_kavita_annotation.py --verify     exit 0 if an API-made annotation exists and reads back with the same xPath/text
Needs KAVITA_URL, KAVITA_API_KEY. Series 90 / chapter 102 / volume 90 / library 4 (This Is How You Lose the Time War)."""
import argparse, json, os, sys
import requests

ap = argparse.ArgumentParser()
for f in ("--create", "--edge", "--cleanup", "--verify"):
    ap.add_argument(f, action="store_true")
ap.add_argument("--report", default="")
a = ap.parse_args()
U = os.environ["KAVITA_URL"].rstrip("/")
login = requests.post(f"{U}/api/Plugin/authenticate", params={"apiKey": os.environ["KAVITA_API_KEY"], "pluginName": "readsync"}).json()
H = {"Authorization": "Bearer " + login["token"]}
IDS = {"libraryId": 4, "seriesId": 90, "volumeId": 90, "chapterId": 102}
TAG = "readsync API test"

def note(text):  # Kavita stores notes as a Quill delta string
    return json.dumps({"ops": [{"insert": text + "\n"}]})

def body(xpath, end, text, page=23, comment=TAG):
    return {"id": 0, "ownerUserId": login.get("id") or 1, "ownerUsername": login["username"], **IDS, "pageNumber": page,
            "xPath": xpath, "endingXPath": end, "selectedText": text, "comment": note(comment) if comment else "{}",
            "highlightCount": len(text), "containsSpoiler": False, "selectedSlotIndex": 0}

def mine():
    r = requests.get(f"{U}/api/Annotation/all-for-series", headers=H, params={"seriesId": IDS["seriesId"]}); r.raise_for_status()
    return [x for x in r.json() if TAG in (x.get("comment") or "")]

def delete(aid):
    return requests.delete(f"{U}/api/Annotation", headers=H, params={"annotationId": aid}).status_code

if a.create:
    r = requests.post(f"{U}/api/Annotation/create", headers=H, json=body("//body/p[13]", "//body/p[13]", "Blue tears out its throat."))
    print("create ->", r.status_code, r.text[:160])
    if r.ok:
        x = r.json(); print(json.dumps({k: x.get(k) for k in ("id", "pageNumber", "xPath", "endingXPath", "selectedText", "comment", "highlightCount", "context")}))
elif a.edge:
    out = {}
    cases = {
        "empty_selectedText": body("//body/p[5]", "//body/p[5]", ""),
        "end_before_start": body("//body/p[14]", "//body/p[12]", "Her teeth are very sharp."),
        "missing_paragraph": body("//body/p[99]", "//body/p[99]", "no such paragraph"),
        "range_two_paragraphs": body("//body/p[12]", "//body/p[13]", "It steps out onto the cold, sharp ground. It sniffs the air"),
    }
    for name, b in cases.items():
        r = requests.post(f"{U}/api/Annotation/create", headers=H, json=b)
        row = {"status": r.status_code, "body": r.text[:200]}
        if r.ok:
            x = r.json(); row["stored"] = {k: x.get(k) for k in ("id", "xPath", "endingXPath", "selectedText", "highlightCount")}; row["deleted"] = delete(x["id"])
        out[name] = row; print(name, "->", row["status"], row.get("stored", row["body"][:100]))
    if a.report: json.dump(out, open(a.report, "w"), indent=1)
elif a.cleanup:
    for x in mine(): print("delete", x["id"], delete(x["id"]))
elif a.verify:
    xs = mine(); ok = any(x["xPath"] == "//body/p[13]" and x["selectedText"] == "Blue tears out its throat." for x in xs)
    print("API-made annotations:", [x["id"] for x in xs], "reads back ok:", ok); sys.exit(0 if ok else 1)
else:
    ap.print_help()
