"""S8: pick passages from an EPUB for the on-device anchor test.
usage: s8_make_samples.py BOOK.epub OUT.json [--n 20] [--seed 8]
Each sample: spine_index, quote (40 to 90 chars), prefix (30), suffix (30), flags (smart_quotes, soft_hyphen, italic, dash)."""
import argparse, json, random, re, zipfile, posixpath
from xml.etree import ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument("epub"); ap.add_argument("out")
ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=8)
a = ap.parse_args()
z = zipfile.ZipFile(a.epub)
ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "o": "http://www.idpf.org/2007/opf"}
opf = ET.fromstring(z.read("META-INF/container.xml")).find(".//c:rootfile", ns).get("full-path")
root = ET.fromstring(z.read(opf))
man = {i.get("id"): i.get("href") for i in root.find("o:manifest", ns)}
spine = [posixpath.normpath(posixpath.join(posixpath.dirname(opf), man[r.get("idref")])) for r in root.find("o:spine", ns)]


def paras(html):
    out = []
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", html, re.S):
        raw = m.group(1)
        txt = re.sub(r"<[^>]+>", "", raw)
        txt = re.sub(r"&#(\d+);", lambda x: chr(int(x.group(1))), txt)
        txt = txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
        out.append((re.sub(r"\s+", " ", txt).strip(), bool(re.search(r"<(i|em)\b", raw)) or 'class="txit"' in raw))
    return out


cands = []
for si, f in enumerate(spine):
    try:
        html = z.read(f).decode("utf8")
    except KeyError:
        continue
    for pi, (t, ital) in enumerate(paras(html)):
        if len(t) < 140:
            continue
        for start in range(0, len(t) - 90, 45):
            s = t.find(" ", start) + 1 if start else 0
            q = t[s:s + 70]
            q = q[:q.rfind(" ")] if len(q) == 70 else q
            if len(q) < 40:
                continue
            fl = {"smart_quotes": bool(re.search("[‘’“”]", q)), "soft_hyphen": "­" in q,
                  "italic": ital, "dash": bool(re.search("[–—]|\\. \\. \\.", q))}
            cands.append({"spine_index": si, "file": f, "para": pi, "quote": q, "prefix": t[max(0, s - 30):s],
                          "suffix": t[s + len(q):s + len(q) + 30], "flags": fl})
random.seed(a.seed)
random.shuffle(cands)
pick, seen = [], set()
for want in ("soft_hyphen", "smart_quotes", "italic", "dash"):
    k = 3 if want != "soft_hyphen" else 2
    for c in cands:
        if c["flags"][want] and c["quote"] not in seen and sum(1 for p in pick if p["flags"][want]) < k:
            pick.append(c); seen.add(c["quote"])
for c in cands:
    if len(pick) >= a.n: break
    if c["quote"] not in seen and not any(p["file"] == c["file"] and p["para"] == c["para"] for p in pick):
        pick.append(c); seen.add(c["quote"])
pick = pick[:a.n]
for i, p in enumerate(pick): p["id"] = i
json.dump({"book": a.epub.split("/")[-1], "samples": pick}, open(a.out, "w"), ensure_ascii=False, indent=1)
print(len(cands), "candidates;", len(pick), "picked;", {k: sum(p["flags"][k] for p in pick) for k in pick[0]["flags"]})
