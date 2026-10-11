#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a practice executable from YOUR OWN copy of the game.

    python build.py le03 --game "D:/Games/Le03/Le03.exe"
    python build.py le02 --game "D:/Games/Le02/Le02.exe"

    # or point at the folder instead of the file:
    python build.py le03 --game "D:/Games/Le03"

The game executables are deliberately NOT part of this repository: a practice
build is a patched copy of the game, so you have to bring your own.  The file
you supply is checked against a known SHA-256 first, so a wrong version fails
loudly instead of silently producing a broken exe.

Requirements:  pip install -r requirements.txt

Output goes to  build/Le03prac.exe  /  build/Le02prac.exe  (override with
--out).  The layout JSON written next to it lists every variable address, which
is what the test scripts in work/ use to poke the running game.
"""

from __future__ import print_function

import argparse
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
#  The two targets.  `sha256` is the exact base executable the patch source was
#  written against -- the patch sites are raw RVAs, so a different build of the
#  game would be patched in the wrong places.
# ---------------------------------------------------------------------------
TARGETS = {
    "le03": {
        "title": "Reactivate majestical imperial  (Le03)",
        "cea": "work/Le03-prac.cea",
        "base_names": ("Le03.exe", "Le03prac.exe"),
        "sha256": "875639800ee6d8e8ec651f1d3e49148fb0af0dc19ce7918f42e51966fa40c44a",
        "out": "Le03prac.exe",
        "note": ("the Chinese-translated Le03.exe (汉化版).  The patch targets "
                 "that build; the original Japanese exe has different offsets."),
        "verify": None,
    },
    "le02": {
        "title": "Earthen Miraculous Sword  (Le02)",
        "cea": "work/Le02-prac.cea",
        "base_names": ("Le02.exe", "Le02prac.exe"),
        "sha256": "22bba60f6250f95437c08cdcf1e1114ea16aa1537f26c4334f1a699dc37cb8c9",
        "out": "Le02prac.exe",
        "note": "the Chinese-translated Le02.exe (汉化版).",
        "verify": "tools/verify_le02.py",
    },
}

CAVE_SIZE = "0x8000"


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
            raise SystemExit(
                "[!] %s does not contain any of %s"
                % (given, ", ".join(game["base_names"])))
        if not os.path.isfile(given):
            raise SystemExit("[!] no such file: %s" % given)
        return given
    # nothing given: look next to this script, then in the usual local spots
    for cand in list(game["base_names"]) + ["work/_orig.exe", "backup/Le02.exe.orig"]:
        p = os.path.join(ROOT, cand)
        if os.path.isfile(p):
            return p
    raise SystemExit("[!] --game is required (your own copy of %s)" % game["base_names"][0])


def run(cmd):
    print("    $ " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    proc = subprocess.run(cmd)
    return proc.returncode


def main():
    # keep our progress lines in order with the sub-processes' output
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
    ap.add_argument("--allow-wrong-base", action="store_true",
                    help="skip the SHA-256 check (produces a broken exe; for debugging only)")
    args = ap.parse_args()

    game = TARGETS[args.game]
    base = resolve_base(game, args.game_path)
    cea = os.path.join(ROOT, game["cea"])
    if not os.path.isfile(cea):
        raise SystemExit("[!] missing patch source: %s" % cea)

    out = args.out or os.path.join(ROOT, "build", game["out"])
    layout = os.path.splitext(out)[0] + "-layout.json"
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    print("[i] %s" % game["title"])
    print("[i] base exe   : %s" % base)
    print("[i] patch source: %s" % os.path.relpath(cea, ROOT))
    print("[i] output     : %s" % os.path.relpath(out, ROOT))

    got = sha256_of(base)
    if got != game["sha256"]:
        print("[!] SHA-256 mismatch")
        print("      expected %s" % game["sha256"])
        print("      got      %s" % got)
        print("[i] the patch source was written against %s" % game["note"])
        if not args.allow_wrong_base:
            raise SystemExit("[!] refusing to patch the wrong executable")
        print("[!] --allow-wrong-base given: continuing anyway")

    print("[i] assembling + patching ...")
    rc = run([sys.executable, os.path.join(ROOT, "tools", "cea.py"),
              cea, base, out,
              "--cave-size", CAVE_SIZE, "--json", layout, "--lenient"])
    if rc != 0:
        raise SystemExit("[!] cea.py failed (exit %d)" % rc)

    if game["verify"]:
        print("[i] structural verification ...")
        rc = run([sys.executable, os.path.join(ROOT, game["verify"]), out, base])
        if rc != 0:
            raise SystemExit("[!] verification FAILED -- do not use this build")

    print()
    print("[+] done: %s" % out)
    print("[i] drop it next to your game's data files (it is self-contained; the")
    print("    game loads its assets from its own folder) and run it.")
    print("[i] press F12 in game for the menu; see the hint manual for the rest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
