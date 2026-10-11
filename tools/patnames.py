"""Extract the practice menu's own per-stage pattern names + boss ids from a .cea.

The `ids_N` table is exactly the value the game stores in [boss+0x44], i.e. the
number you write as P in `boss:P:F` -- so this is the authoritative pattern table.
"""
import sys

src = open(sys.argv[1], encoding="utf-8").read()
lines = src.split("\n")


def body(label):
    for i, ln in enumerate(lines):
        if ln.strip() == label + ":":
            out = []
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if not s.startswith(("dd ", "db ")):
                    break
                out.append(s)
            return out
    return None


def u16(tokens):
    return bytes.fromhex("".join(tokens).replace(" ", "")).decode("utf-16-le", "ignore").rstrip("\x00")


for st in range(8):
    nm, ids = body("names_%d" % st), body("ids_%d" % st)
    if nm is None or ids is None:
        continue
    ptrs = [t.split()[1] for t in nm]
    idv = [int(x, 16) for t in ids for x in t.split()[1:]]
    print("stage %d  (%d entries)" % (st + 1, len(ptrs)))
    row = []
    for k, p in enumerate(ptrs):
        b = body(p)
        name = u16([x[3:] for x in b]) if b else "?"
        pid = idv[k] if k < len(idv) else -2
        row.append("%s=%s" % ("-" if pid == -1 else pid, name))
    print("    " + " | ".join(row))
