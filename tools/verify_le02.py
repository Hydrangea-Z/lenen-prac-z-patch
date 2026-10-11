#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural verification of the rebuilt le02 practice exe.

Usage:
    python verify_le02.py <built.exe> <original.exe>

Checks:
  * PE header: entry point / ImageBase unchanged, SizeOfImage +0x4000,
    one extra section, ASLR cleared (the cave uses absolute addresses)
  * a .leprac section exists, is RWX, and sits at VA 0xF92000 with VS=RAW=0x4000
  * the cave's trailing marker is intact
  * every byte that differs from the original lies inside the PE header block,
    a declared patch site, or the .leprac raw image -- nothing stray
  * each declared site holds a `jmp`/`call` into the cave (or the expected
    hand-written `db` bytes for the menu-frame geometry)
"""
import sys

import pefile

CAVE_RVA = 0xB92000   # game+B92000; absolute VA is 0xF92000
CAVE_SIZE = 0x8000    # grew from 0x4000 in v0.6.1 (hint file buffers)
MARKER = b"LEPRAC2:FIXED:1\x00"

# (rva, nbytes, kind)  kind: "jmp" = E9 + rel32 into the cave,
#                             "call" = E8 + rel32 into the cave,
#                             "db"  = raw bytes
SITES = [
    (0x74112, 5, "jmp"), (0xB264E, 5, "jmp"), (0xB32C6, 7, "jmp"),
    (0x27E90, 7, "jmp"), (0xB67E9, 5, "jmp"), (0xB37CE, 10, "jmp"),
    (0xB9091, 7, "jmp"), (0xC29A5, 6, "jmp"), (0xC29D0, 5, "jmp"),
    (0xC49FB, 7, "jmp"), (0xC4C92, 7, "jmp"), (0xC4DAE, 7, "jmp"),
    (0xC4F80, 7, "jmp"), (0xC513E, 7, "jmp"), (0x6B7BA, 10, "jmp"),
    (0x6B837, 6, "jmp"), (0x27724, 10, "jmp"), (0xD5DB, 7, "jmp"),
    (0xD698, 5, "jmp"), (0xD588, 5, "jmp"),
    # new for our build
    (0xB902B, 7, "jmp"), (0xB9064, 7, "jmp"),
    # --- F12 overlay (v0.3.3) -------------------------------------------------
    # 0xCFFCD  the real per-frame function, 10 bytes in (after the stack-cookie
    #          prologue and the re-entrancy guard).  Menu logic lives here.
    # 0x14BD50 the *present* function's entry; its 9-byte prologue
    #          (push ebp / mov ebp,esp / sub esp,0x4cc) is re-executed in the
    #          trampoline, so the patch covers all 9 bytes.  Drawing happens
    #          here because it is the last point where the game's own helpers
    #          still work AND nothing has been blitted yet.
    #          (v0.3.0 hooked 0xCFAF0 -- the *shutdown* routine -- and
    #           v0.3.1/v0.3.2 hooked the end of the frame, after the renderer
    #           had already been torn down.  Both are gone.)
    (0xCFFCD, 10, "jmp"), (0x14BD50, 9, "jmp"),
    # the four keyboard-refresh sites, all `call game+140CD0`; each is
    # redirected at one wrapper that runs the real refresh and then wipes the
    # game's key array while the menu is open.
    (0xCF255, 5, "call"), (0xCF2B5, 5, "call"),
    (0xCF445, 5, "call"), (0xCF7CD, 5, "call"),
    # --- v0.4.0: No-Miss and freeze-power -------------------------------
    # 0xB980C  `cmp [player+0x48],0 / jg respawn` -- the game-over decision.
    #          Six bytes, and the check runs BEFORE the shared
    #          `dec [player+0x48]` at 0xB9894, so handing the game a life of 1
    #          makes the decrement land on 0.  Only the case that would have
    #          been a GAME OVER changes path, which is what keeps a replay
    #          frame-accurate up to the first fatal hit.
    # 0xB9B05  the vanilla `clamp power into [0,500]` that already closes the
    #          player update every frame (33 bytes).  Freezing power here
    #          replaces an existing write instead of adding one.
    (0xB980C, 6, "jmp"), (0xB9B05, 33, "jmp"),
    # --- v0.5.0: the RNG seed ------------------------------------------
    # 0xB2BD9  the ONLY call to the seed wrapper (0xD04D0), and the seed
    #          global (0xEDDFF4) has exactly one reader -- this instruction.
    #          Both facts were established by a full .text sweep, which is
    #          what makes a single 5-byte patch sufficient.  It sits in the
    #          stage-scene constructor (0xB2620), i.e. it runs once per
    #          stage, not once per run.
    (0xB2BD9, 5, "call"),
    # menu-frame geometry (hand-written db patches)
    (0x73F67, 1, "db"), (0x7405F, 5, "db"), (0x7409B, 5, "db"),
]

# expected raw bytes for the db patches
DB_EXPECT = {
    0x73F67: b"\x00",
    0x7405F: b"\x68\x47\x01\x00\x00",
    0x7409B: b"\x68\x47\x01\x00\x00",
}


def rva2off(pe, rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None


def main():
    built, orig = sys.argv[1], sys.argv[2]
    b = pefile.PE(built, fast_load=True)
    o = pefile.PE(orig, fast_load=True)
    db = open(built, "rb").read()
    do = open(orig, "rb").read()
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print("  %s %-52s %s" % ("OK " if cond else "BAD", name, detail))

    print("== PE header ==")
    check("AddressOfEntryPoint unchanged",
          b.OPTIONAL_HEADER.AddressOfEntryPoint == o.OPTIONAL_HEADER.AddressOfEntryPoint)
    check("ImageBase unchanged", b.OPTIONAL_HEADER.ImageBase == o.OPTIONAL_HEADER.ImageBase,
          "0x%X" % b.OPTIONAL_HEADER.ImageBase)
    # the cave grew to 0x8000 in v0.6.1, so derive the expected size from the
    # section itself rather than pinning it
    lep = next((s for s in b.sections if b".leprac" in s.Name), None)
    want_img = o.OPTIONAL_HEADER.SizeOfImage + \
        (max(lep.Misc_VirtualSize, lep.SizeOfRawData) if lep else 0x4000)
    check("SizeOfImage = original + cave size",
          b.OPTIONAL_HEADER.SizeOfImage == want_img,
          "0x%X (want 0x%X)" % (b.OPTIONAL_HEADER.SizeOfImage, want_img))
    check("one extra section",
          b.FILE_HEADER.NumberOfSections == o.FILE_HEADER.NumberOfSections + 1,
          "%d -> %d" % (o.FILE_HEADER.NumberOfSections, b.FILE_HEADER.NumberOfSections))
    dllc_b = b.OPTIONAL_HEADER.DllCharacteristics
    dllc_o = o.OPTIONAL_HEADER.DllCharacteristics
    check("ASLR cleared", (dllc_b & 0x40) == 0 and (dllc_o & 0x40) != 0,
          "0x%X -> 0x%X" % (dllc_o, dllc_b))

    print("== .leprac section ==")
    secs = [s for s in b.sections if s.Name.startswith(b".leprac")]
    check("present", len(secs) == 1)
    if secs:
        s = secs[0]
        check("RVA == 0xB92000", s.VirtualAddress == CAVE_RVA, "0x%X" % s.VirtualAddress)
        check("RWX", s.Characteristics == 0xE0000060, "0x%X" % s.Characteristics)
        check("VS == RAW (and a power-of-two size)",
              s.Misc_VirtualSize == s.SizeOfRawData and
              (s.Misc_VirtualSize & (s.Misc_VirtualSize - 1)) == 0,
              "VS=0x%X RAW=0x%X" % (s.Misc_VirtualSize, s.SizeOfRawData))

    print("== cave marker ==")
    mo = rva2off(b, CAVE_RVA + 0x3FF0)
    check("LEPRAC2:FIXED:1 at cave+3FF0", db[mo:mo + len(MARKER)] == MARKER)

    print("== patch sites ==")
    allowed = set()
    for rva, n, kind in SITES:
        allowed.update(range(rva, rva + n))
        off = rva2off(b, rva)
        got = db[off:off + n]
        if kind in ("jmp", "call"):
            op = 0xE9 if kind == "jmp" else 0xE8
            good = got[0] == op
            tgt = rva + 5 + int.from_bytes(got[1:5], "little", signed=True) if len(got) >= 5 else -1
            good = good and (CAVE_RVA <= tgt < CAVE_RVA + CAVE_SIZE)
            check("site 0x%06X -> cave" % rva, good, got.hex())
        else:
            check("site 0x%06X == %s" % (rva, DB_EXPECT[rva].hex()),
                  got == DB_EXPECT[rva], got.hex())

    print("== stray-byte diff ==")
    # regions we are allowed to touch: the header + section table (first 0x400
    # bytes), the declared sites, and the whole .leprac raw image
    cave_sec = secs[0] if secs else None
    cave_lo = cave_sec.PointerToRawData if cave_sec else -1
    cave_hi = cave_lo + CAVE_SIZE if cave_sec else -1
    stray = []
    for i in range(min(len(db), len(do))):
        if db[i] != do[i]:
            # file offset -> rva
            rva = None
            for s in o.sections:
                if s.PointerToRawData <= i < s.PointerToRawData + s.SizeOfRawData:
                    rva = s.VirtualAddress + (i - s.PointerToRawData)
            if i < 0x400:
                continue                      # PE header + section table
            if cave_lo <= i < cave_hi:
                continue                      # our new section
            if rva is not None and rva in allowed:
                continue                      # a declared patch site
            stray.append((i, rva))
    check("no stray changes outside intended regions", not stray,
          "" if not stray else "%d bytes, first at file 0x%X rva %s"
          % (len(stray), stray[0][0], ("0x%X" % stray[0][1]) if stray[0][1] else "?"))

    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
