#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a practice executable from YOUR OWN copy of the game.

    python build.py le03 --game "D:/Games/Le03/Le03.exe"
    python build.py le02 --game "D:/Games/Le02/Le02.exe"
    python build.py le01 --game "D:/Games/Le01/Le01.exe"

    # or point at the folder instead of the file:
    python build.py le03 --game "D:/Games/Le03"

The game executables are deliberately NOT part of this repository: a practice
build is a patched copy of the game, so you have to bring your own.  The file
you supply is checked against a known SHA-256 first, so a wrong version fails
loudly instead of silently producing a broken exe.

Two DLLs are compiled from src/ and embedded into the patched exe:

    src/hitbox/Le0Xhitbox.cpp   the hitbox renderer (D3D11)
    src/speed/Le03speed.cpp     the vsync-off helper (shared by all three)

They are written to out/, stripped, and pulled into the .cea with `incbin`;
the resulting exe carries them as data and extracts them to %TEMP% on first
use, so the release is a single file.

Requirements:
    pip install -r requirements.txt
    a 32-bit MinGW g++ + strip on PATH (or pass --cxx / --strip)

Output goes to  build/Le0Xprac.exe  (override with --out).  The layout JSON
written next to it lists every variable address inside the patch.
"""

from __future__ import print_function

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
#  One entry per game.  `sha256` is the exact base executable the patch source
#  was written against -- the patch sites are raw RVAs, so a different build of
#  the game would be patched in the wrong places.
#
#  Le03 has a second accepted base: 1.21a (the original) and 1.20a (what the
#  Chinese translation ships) differ only by a 16-byte relocation in .rdata,
#  so the same patch applies byte for byte to both.
# ---------------------------------------------------------------------------
TARGETS = {
    "le01": {
        "title": "连缘无现里  (Le01)",
        "cea": "work/Le01-prac.cea",
        "base_names": ("Le01.exe", "Le01prac.exe"),
        "sha256": "598752993abdd13a25ac9d0e3a1a5f581f6a1e4d455e418efc3ca0ff2944cf36",
        "also_ok": (),
        "note": "the Chinese-translated Le01.exe (汉化版).",
        "hitbox_src": "src/hitbox/Le01hitbox.cpp",
        "hitbox_dll": "Le01hitbox-v1",
        "out": "Le01prac.exe",
    },
    "le02": {
        "title": "连缘蛇丛剑  (Le02)",
        "cea": "work/Le02-prac.cea",
        "base_names": ("Le02.exe", "Le02prac.exe"),
        "sha256": "22bba60f6250f95437c08cdcf1e1114ea16aa1537f26c4334f1a699dc37cb8c9",
        "also_ok": (),
        "note": "the Chinese-translated Le02.exe (汉化版).",
        "hitbox_src": "src/hitbox/Le02hitbox.cpp",
        "hitbox_dll": "Le02hitbox-v1",
        "out": "Le02prac.exe",
    },
    "le03": {
        "title": "连缘灵烈传  (Le03)",
        "cea": "work/Le03-prac.cea",
        "base_names": ("Le03.exe", "Le03prac.exe"),
        "sha256": "955cd8fe51cd95813decf1d429578b9844a63ef9a5b8ebf048be5c2322ca1426",
        "also_ok": ("875639800ee6d8e8ec651f1d3e49148fb0af0dc19ce7918f42e51966fa40c44a",),
        "note": ("the original Japanese Le03.exe v1.21a -- its window title ends "
                 "in '.ver 1.21a'."),
        "hitbox_src": "src/hitbox/Le03hitbox.cpp",
        "hitbox_dll": "Le03hitbox-v11",
        "out": "Le03prac.exe",
    },
}

SPEED_SRC = "src/speed/Le03speed.cpp"
SPEED_DLL = "Le03speed"
CAVE_SIZE = "0x40000"

# 32-bit, no exceptions/rtti surprises: the renderer is plain C++11 + COM.
CXXFLAGS = ["-m32", "-std=c++11", "-O2", "-shared",
            "-static-libgcc", "-static-libstdc++", "-Wl,--kill-at"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_base(game, given):
    """Turn --game into a concrete exe path, or die with a helpful message."""
    if given:
        if os.path.isdir(given):
            for name in game["base_names"]:
                cand = os.path.join(given, name)
                if os.path.isfile(cand):
                    return cand
            raise SystemExit("[!] %s does not contain any of %s"
                             % (given, ", ".join(game["base_names"])))
        if not os.path.isfile(given):
            raise SystemExit("[!] no such file: %s" % given)
        return given
    raise SystemExit("[!] --game is required (your own copy of %s)"
                     % game["base_names"][0])


def run(cmd):
    print("    $ " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    return subprocess.run(cmd).returncode


def find_tool(explicit, name, fallback_dir=None):
    if explicit:
        return explicit
    found = shutil.which(name)
    if found:
        return found
    if fallback_dir:
        for suffix in ("", ".exe"):
            cand = os.path.join(fallback_dir, name + suffix)
            if os.path.isfile(cand):
                return cand
    raise SystemExit(
        "[!] %s not found. Install a 32-bit MinGW-w64 toolchain and put it on "
        "PATH, or pass --%s PATH." % (name, "cxx" if name.startswith("g++") else "strip"))


def build_dll(cxx, src, out_dll):
    rc = run([cxx] + CXXFLAGS + [src, "-o", out_dll, "-luuid"])
    if rc != 0:
        raise SystemExit("[!] compiling %s failed" % src)


def strip_dll(strip, dll, out_stripped):
    rc = run([strip, "-s", dll, "-o", out_stripped])
    if rc != 0:
        raise SystemExit("[!] stripping %s failed" % dll)


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="Patch your own copy of a Len'en game into a practice build.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="example:\n  python build.py le03 --game \"D:/Games/Le03/Le03.exe\"")
    ap.add_argument("game", choices=sorted(TARGETS), help="which game to build")
    ap.add_argument("--game", dest="game_path", metavar="PATH",
                    help="path to YOUR copy of the game exe (or its folder)")
    ap.add_argument("--out", metavar="PATH", help="where to write the patched exe")
    ap.add_argument("--cxx", metavar="PATH", help="32-bit g++ to use")
    ap.add_argument("--strip", metavar="PATH", help="strip to use")
    ap.add_argument("--skip-dll", action="store_true",
                    help="reuse the DLLs already in out/ instead of rebuilding them")
    ap.add_argument("--allow-wrong-base", action="store_true",
                    help="skip the SHA-256 check (produces a broken exe; debugging only)")
    args = ap.parse_args()

    game = TARGETS[args.game]
    base = resolve_base(game, args.game_path)
    cea = os.path.join(ROOT, game["cea"])
    if not os.path.isfile(cea):
        raise SystemExit("[!] missing patch source: %s" % cea)

    out = args.out or os.path.join(ROOT, "build", game["out"])
    layout = os.path.splitext(out)[0] + "-layout.json"
    outdir = os.path.join(ROOT, "out")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    print("[i] %s" % game["title"])
    print("[i] base exe    : %s" % base)
    print("[i] patch source: %s" % os.path.relpath(cea, ROOT))
    print("[i] output      : %s" % os.path.relpath(out, ROOT))

    got = sha256_of(base)
    if got != game["sha256"]:
        if got in game["also_ok"]:
            print("[i] SHA-256 matches an accepted alternative base")
            print("      %s" % got)
        else:
            print("[!] SHA-256 mismatch")
            print("      expected %s" % game["sha256"])
            print("      got      %s" % got)
            print("[i] the patch source was written against %s" % game["note"])
            if not args.allow_wrong_base:
                raise SystemExit("[!] refusing to patch the wrong executable")
            print("[!] --allow-wrong-base given: continuing anyway")

    # ---- 1. compile + strip the two embedded DLLs -------------------------
    if not args.skip_dll:
        cxx = find_tool(args.cxx, "g++")
        strip = find_tool(args.strip, "strip")
        print("[i] compiling embedded DLLs with %s" % cxx)
        for src_rel, name in ((game["hitbox_src"], game["hitbox_dll"]),
                              (SPEED_SRC, SPEED_DLL)):
            src = os.path.join(ROOT, src_rel)
            dll = os.path.join(outdir, name + ".dll")
            stripped = os.path.join(outdir, name + ".stripped.dll")
            if not os.path.isfile(src):
                raise SystemExit("[!] missing DLL source: %s" % src)
            build_dll(cxx, src, dll)
            strip_dll(strip, dll, stripped)
            print("[i] %-22s %8d bytes stripped" % (name + ".dll", os.path.getsize(stripped)))
    else:
        print("[i] --skip-dll: reusing out/*.stripped.dll")

    # ---- 2. assemble the patch -------------------------------------------
    print("[i] assembling + patching ...")
    cmd = [sys.executable, os.path.join(ROOT, "tools", "cea.py"),
           cea, base, out, "--cave-size", CAVE_SIZE, "--json", layout]
    if got != game["sha256"]:
        cmd.append("--lenient")
    if run(cmd) != 0:
        raise SystemExit("[!] cea.py failed")

    # ---- 3. the patch stores into .text every frame ----------------------
    rc = run([sys.executable, os.path.join(ROOT, "tools", "make_text_writable.py"), out])
    if rc != 0:
        raise SystemExit("[!] make_text_writable.py failed")

    # ---- 4. structural smoke check ---------------------------------------
    print("[i] structural verification ...")
    rc = run([sys.executable, os.path.join(ROOT, "tools", "verify_build.py"),
              out, base, "--game", args.game])
    if rc != 0:
        raise SystemExit("[!] verification FAILED -- do not use this build")

    print()
    print("[+] done: %s" % out)
    print("[i] it is self-contained: drop it next to the game's data files and run it.")
    print("[i] F12 opens the menu.  The hitbox overlay needs devmode in prac.cfg.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
