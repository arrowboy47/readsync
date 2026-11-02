"""KOReader 'binary' document hash (partial MD5): 1024 bytes sampled at offsets 1024 << (2*i) for i in 0..10, plus offset 0 (KOReader: lshift(1024,-2) wraps to 0).
usage: koreader_hash.py book.epub [...]"""
import hashlib, sys
def partial_md5(path):
    m = hashlib.md5()
    with open(path, "rb") as f:
        for i in range(-1, 11):
            f.seek(1024 << (2 * i) if i >= 0 else 0)  # LuaJIT lshift(1024,-2) wraps to 0
            b = f.read(1024)
            if not b: break
            m.update(b)
    return m.hexdigest()
for p in sys.argv[1:]: print(partial_md5(p), p)
