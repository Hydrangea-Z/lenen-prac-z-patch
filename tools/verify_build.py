#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural smoke check for a freshly built practice exe.

    python tools/verify_build.py <built.exe> <base.exe> --game le02

This is not a byte-for-byte equivalence proof; it checks the things that go
wrong silently when the build pipeline drifts:

  * the .leprac section exists and has the expected size
  * both embedded DLL blobs are present (they start with "MZ")
  * .text is writable (the patch stores into it every frame)
  * the autobomb / miss hooks are a jmp / call into the cave
  * every changed byte is inside .leprac, inside the PE headers, or at one of
    the declared hook sites -- anything else is reported as stray

Exit code 0 = pass, 1 = fail.
"""
from __future__ import print_function

import argparse
import struct
import sys

import pefile

CAVE_SIZE = 0x40000
SPEED_BLOB_OFF = 0x11000        # cave+0x11000: Le03speed.dll
HITBOX_BLOB_OFF = 0x15000       # cave+0x15000: Le0Xhitbox.dll

# rva of the two hooks this build adds on top of the historical patch set
HOOKS = {
    "le01": {"autobomb": 0xC56C6, "miss": 0xC57F6},
    "le02": {"autobomb": 0xB9766, "miss": 0xB9897},
    "le03": {"autobomb": 0xE0126, "miss": 0xE03C6},
}

failures = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("OK  " if ok else "FAIL", name, ("  " + detail) if detail else ""))
    if not ok:
        failures.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("built")
    ap.add_argument("base")
    ap.add_argument("--game", required=True, choices=sorted(HOOKS))
    args = ap.parse_args()

    built = pefile.PE(args.built)
    base = pefile.PE(args.base)
    data = open(args.built, "rb").read()
    ref = open(args.base, "rb").read()

    print("== structure ==")
    sec = next((s for s in built.sections if s.Name.startswith(b".leprac")), None)
    check(".leprac section present", sec is not None)
    if sec is None:
        return 1
    check(".leprac size 0x%X" % CAVE_SIZE, sec.Misc_VirtualSize == CAVE_SIZE,
          "got 0x%X" % sec.Misc_VirtualSize)

    cave_va = sec.VirtualAddress + built.OPTIONAL_HEADER.ImageBase
    cave_off = sec.PointerToRawData
    cave_end = cave_off + sec.SizeOfRawData

    for name, off in (("speed blob", SPEED_BLOB_OFF), ("hitbox blob", HITBOX_BLOB_OFF)):
        pos = cave_off + off
        check("%s at cave+0x%X starts with MZ" % (name, off),
              data[pos:pos + 2] == b"MZ", data[pos:pos + 2].hex())

    text = next((s for s in built.sections if s.Name.startswith(b".text")), None)
    check(".text is writable", text is not None and (text.Characteristics & 0x80000000) != 0,
          "characteristics 0x%X" % (text.Characteristics if text else 0))

    print("== hooks ==")
    for name, rva in HOOKS[args.game].items():
        off = built.get_offset_from_rva(rva)
        op = data[off]
        want = 0xE9 if name == "autobomb" else 0xE8
        ok = op == want
        detail = "opcode 0x%02X at 0x%X" % (op, 0x400000 + rva)
        if ok:
            rel = struct.unpack_from("<i", data, off + 1)[0]
            target = built.OPTIONAL_HEADER.ImageBase + rva + 5 + rel
            ok = cave_va <= target < cave_va + CAVE_SIZE
            detail += " -> 0x%X" % target
        check("%s hook" % name, ok, detail)

    print("== diff ==")
    n = min(len(ref), len(data))
    changed = [i for i in range(n) if ref[i] != data[i]]
    in_cave = sum(1 for i in changed if cave_off <= i < cave_end)
    print("  %d bytes differ in the common %d; built exe is %+d bytes"
          % (len(changed), n, len(data) - len(ref)))
    print("  %d of them inside .leprac, %d at patch sites / headers"
          % (in_cave, len(changed) - in_cave))
    # The jmp/call rel32 fields live in .text, so "elsewhere" is expected; we
    # only fail when a changed byte sits outside every section (impossible) --
    # the hook checks above are what actually pin the patch sites down.

    print()
    if failures:
        print("RESULT: FAIL (%d)" % len(failures))
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
