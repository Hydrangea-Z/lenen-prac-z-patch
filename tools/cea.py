#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile a Cheat Engine .cea (Auto Assemble) source into a patched practice exe.

Usage:
    python cea.py <source.cea> <original.exe> <output.exe> [--report] [--lenient]
                     [--json LAYOUT.json] [--cave-size 0x8000]

`--json` writes every label's absolute VA plus the cave base.  The live-probe
tools (probe.py / feattest.py / f12test.py) read that file instead of hard-coding
addresses: hard-coded VAs silently rot every time the cave layout shifts, and a
wrong VA reads *plausible* garbage rather than failing loudly.

Why this exists
---------------
BAN ships a hand-prepared Le03prac.exe plus a .cea that is a *newer* source than
the exe.  Hand-patching the exe byte-by-byte cannot reproduce what the source
says, so instead we rebuild the whole thing from source:

    Le03.exe (original)  +  Le03.cea  ->  a practice exe that matches the source

The rebuild is faithful because the .cea is self-describing:
  * `assert(game+XXXX, bytes...)` pins every .text patch site to its original bytes,
  * `cave:` + labels give the entire .leprac payload (code *and* data),
  * every address is derived from a label, so nothing is hard-coded twice.

Supported Auto Assemble subset (everything Le03.cea / Le02.cea use):
    define(NAME, EXPR)      EXPR may be a quoted string (only for `game`)
    label(NAME)             forward declaration
    assert(ADDR, BYTES...)  verified against the original exe
    [ENABLE] ...            the patch body: `addr:` directives, labels,
                            `db/dw/dd` data and x86 instructions
All numeric literals are hexadecimal (CE convention), and identifiers are
case-insensitive in CE but we keep them verbatim here.
"""
import json
import os
import re
import struct
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32

# --------------------------------------------------------------------------- #
# PE access
# --------------------------------------------------------------------------- #
SECTION_ALIGN = 0x1000
FILE_ALIGN = 0x200


class PE:
    def __init__(self, path):
        self.data = bytearray(open(path, "rb").read())
        self._parse()

    def _u16(self, off):
        return struct.unpack_from("<H", self.data, off)[0]

    def _u32(self, off):
        return struct.unpack_from("<I", self.data, off)[0]

    def _parse(self):
        self.e_lfanew = self._u32(0x3C)
        lf = self.e_lfanew
        assert self.data[lf:lf + 4] == b"PE\0\0", "not a PE file"
        self.file_hdr = lf + 4
        self.num_sections = self._u16(self.file_hdr + 2)
        self.size_opt = self._u16(self.file_hdr + 16)
        self.opt = self.file_hdr + 20
        self.sectab = self.opt + self.size_opt
        self.image_base = self._u32(self.opt + 28)
        self.sect_align = self._u32(self.opt + 32)
        self.file_align = self._u32(self.opt + 36)
        self.size_image = self._u32(self.opt + 56)
        self.dll_char = self._u16(self.opt + 70)
        self.sections = []
        for i in range(self.num_sections):
            off = self.sectab + i * 40
            self.sections.append({
                "hdr": off,
                "name": bytes(self.data[off:off + 8]).rstrip(b"\0").decode("latin1"),
                "vs": self._u32(off + 8),
                "va": self._u32(off + 12),
                "raw": self._u32(off + 16),
                "ptr": self._u32(off + 20),
                "chars": self._u32(off + 36),
            })

    def section(self, name):
        for s in self.sections:
            if s["name"] == name:
                return s
        return None

    def va_to_offset(self, va):
        rva = va - self.image_base
        for s in self.sections:
            if s["va"] <= rva < s["va"] + max(s["vs"], s["raw"]):
                return s["ptr"] + (rva - s["va"]), s
        raise KeyError("VA 0x%08X is outside every section" % va)

    def read_va(self, va, n):
        off, _ = self.va_to_offset(va)
        return bytes(self.data[off:off + n])

    def write_va(self, va, blob):
        off, s = self.va_to_offset(va)
        self.data[off:off + len(blob)] = blob

    def add_section(self, name, size, chars):
        last = self.sections[-1]
        va = _align(last["va"] + max(last["vs"], last["raw"]), self.sect_align)
        ptr = _align(len(self.data), self.file_align)
        if ptr < len(self.data):
            ptr = _align(len(self.data), self.file_align)
        self.data.extend(b"\0" * (ptr - len(self.data)))
        self.data.extend(b"\0" * size)
        hdr = self.sectab + self.num_sections * 40
        self.data[hdr:hdr + 40] = b"\0" * 40
        self.data[hdr:hdr + 8] = name.encode("latin1")[:8].ljust(8, b"\0")
        struct.pack_into("<I", self.data, hdr + 8, size)      # VirtualSize
        struct.pack_into("<I", self.data, hdr + 12, va)       # VirtualAddress
        struct.pack_into("<I", self.data, hdr + 16, size)     # SizeOfRawData
        struct.pack_into("<I", self.data, hdr + 20, ptr)      # PointerToRawData
        struct.pack_into("<I", self.data, hdr + 36, chars)    # Characteristics
        self.num_sections += 1
        struct.pack_into("<H", self.data, self.file_hdr + 2, self.num_sections)
        self.size_image = _align(va + size, self.sect_align)
        struct.pack_into("<I", self.data, self.opt + 56, self.size_image)
        self._parse()
        return va

    def save(self, path):
        open(path, "wb").write(bytes(self.data))


def _align(v, a):
    return (v + a - 1) // a * a


# --------------------------------------------------------------------------- #
# Auto Assemble subset
# --------------------------------------------------------------------------- #
COMMENT = re.compile(r"//.*$")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9A-Fa-f]+")
HEXONLY = re.compile(r"^[0-9A-Fa-f]+$")
CONST_RUN = re.compile(r"(?<![0-9A-Fa-fxX*])0x[0-9A-Fa-f]+(?:\s*[-+]\s*0x[0-9A-Fa-f]+)+")

# Placeholder for a symbol we cannot resolve yet.  It must be *above* every real
# address in the image so that pass 1 classifies forward references as forward.
DUMMY = 0x7F000000

JCC = {    "jo": 0x0, "jno": 0x1,
    "jb": 0x2, "jnae": 0x2, "jc": 0x2, "jae": 0x3, "jnb": 0x3, "jnc": 0x3,
    "je": 0x4, "jz": 0x4, "jne": 0x5, "jnz": 0x5,
    "jbe": 0x6, "jna": 0x6, "ja": 0x7, "jnbe": 0x7,
    "js": 0x8, "jns": 0x9, "jp": 0xA, "jpe": 0xA, "jnp": 0xB, "jpo": 0xB,
    "jl": 0xC, "jnge": 0xC, "jge": 0xD, "jnl": 0xD,
    "jle": 0xE, "jng": 0xE, "jg": 0xF, "jnle": 0xF,
}

# `cmp [edi], 0` style: memory operand, no size keyword, immediate other side.
AMBIGUOUS = re.compile(
    r"^(cmp|mov|add|sub|test|and|or|xor|inc|dec)\s+(\[[^\]]+\])\s*,\s*(0x[0-9A-Fa-f]+|[0-9A-Fa-f]+)\s*$",
    re.I,
)

# Registers keystone must see verbatim: `call eax`, `jmp dword ptr [x]` are
# indirect, so the direct-branch encoder (which needs an address expression)
# must not swallow them.
REGS = {
    "eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp",
    "ax", "bx", "cx", "dx", "si", "di", "bp", "sp",
    "al", "bl", "cl", "dl", "ah", "bh", "ch", "dh",
}
INDIRECT_PREFIX = ("dword ptr", "word ptr", "byte ptr", "qword ptr")


def is_direct_operand(rest):
    """True when a jmp/call/jcc operand is a plain address expression."""
    r = rest.strip().lower()
    if not r or r.startswith("[") or r in REGS:
        return False
    return not r.startswith(INDIRECT_PREFIX)


class Block:
    """A contiguous run of output starting at a known VA."""

    def __init__(self, va):
        self.va = va
        self.ops = []          # ('label', name) | ('asm', text) | ('data', size, [int])
        self.end_va = va

    def size(self):
        return self.end_va - self.va


class Compiler:
    def __init__(self, text, image_base, base_dir=None):
        self.text = text
        self.image_base = image_base
        self.base_dir = base_dir or os.getcwd()
        self.defines = {}      # name -> expr string
        self.declared = set()  # label(NAME)
        self.labels = {}       # name -> VA
        self.blocks = []
        self.asserts = []      # (va, bytes)
        self.ks = Ks(KS_ARCH_X86, KS_MODE_32)
        self._parse()

    # ---------------- parsing ---------------- #
    def _parse(self):
        raw = self.text.splitlines()
        # defines and label declarations live at top level, outside [ENABLE]
        for ln in raw:
            s = COMMENT.sub("", ln).strip()
            if not s:
                continue
            m = re.match(r"^define\(\s*([A-Za-z_]\w*)\s*,\s*(.+?)\s*\)$", s, re.I)
            if m:
                self.defines[m.group(1)] = m.group(2)
                continue
            m = re.match(r"^label\(\s*([A-Za-z_]\w*)\s*\)$", s, re.I)
            if m:
                self.declared.add(m.group(1))

        in_enable = False
        cur = None
        for ln in raw:
            s = COMMENT.sub("", ln).strip()
            if s.startswith("[") and s.endswith("]"):
                in_enable = s.upper() == "[ENABLE]"
                cur = None
                continue
            if not in_enable or not s:
                continue

            m = re.match(r"^assert\(\s*(.+?)\s*,\s*(.*?)\s*\)$", s, re.I)
            if m:
                va = self.eval_addr(m.group(1), phase1=True)
                blob = bytes(int(t, 16) for t in m.group(2).split())
                self.asserts.append((va, blob))
                continue

            m = re.fullmatch(r"([A-Za-z_]\w*(?:\+[0-9A-Fa-f]+)?)\s*:", s)
            if m:
                name = m.group(1)
                base = name.split("+")[0]
                if base in self.defines:
                    # address directive: `cave:` or `game+827B2:`
                    cur = Block(self.eval_addr(name, phase1=True))
                    self.blocks.append(cur)
                else:
                    # label definition at the current cursor
                    if cur is None:
                        raise SyntaxError("label %s outside any block" % name)
                    cur.ops.append(("label", name))
                continue

            if cur is None:
                continue
            cur.ops.append(("line", s))

    # ---------------- symbol evaluation ---------------- #
    def is_symbol(self, tok):
        return tok == "game" or tok in self.labels or tok in self.defines or tok in self.declared

    def symval(self, name, phase1):
        if name == "game":
            return self.image_base
        if name in self.labels:
            return self.labels[name]
        if name in self.defines:
            expr = self.defines[name]
            if expr.startswith('"'):
                return None            # module-name define
            v = self.eval_addr(expr, phase1=phase1)
            return v
        return None

    def subst(self, text, phase1, dummy=DUMMY):
        out = []
        pos = 0
        for m in TOKEN_RE.finditer(text):
            out.append(text[pos:m.start()])
            tok = m.group(0)
            v = None
            if self.is_symbol(tok):
                v = self.symval(tok, phase1)
            if v is not None:
                out.append("0x%X" % v)
            elif HEXONLY.match(tok):
                out.append("0x%X" % int(tok, 16))
            elif self.is_symbol(tok):
                # known symbol we cannot resolve yet -> force the long form
                out.append("0x%X" % dummy)
            else:
                out.append(tok)
            pos = m.end()
        out.append(text[pos:])
        return collapse("".join(out))

    def eval_addr(self, expr, phase1):
        s = self.subst(expr.strip(), phase1)
        v = eval_const(s)
        if v is None:
            raise SyntaxError("cannot evaluate address expression: %r -> %r" % (expr, s))
        return v

    # ---------------- assembly ---------------- #
    def _encode_line(self, s, va, phase1):
        """Return the bytes for one source line placed at `va`."""
        # incbin("relative/path"): raw file bytes, resolved against the .cea's
        # directory first and the process CWD second.  Missing files are fatal:
        # silently padding would ship an exe that extracts a truncated DLL.
        m = re.match(r'^incbin\(\s*"([^"]+)"\s*\)$', s, re.I)
        if m:
            rel = m.group(1)
            for base in (self.base_dir, os.getcwd()):
                p = os.path.join(base, rel)
                if os.path.isfile(p):
                    return open(p, "rb").read()
            raise FileNotFoundError("incbin: cannot find %r (base %r)" % (rel, self.base_dir))
        # res N: N zero bytes (path buffers, scratch space).
        m = re.match(r"^res\s+([0-9A-Fa-f]+)$", s, re.I)
        if m:
            return b"\x00" * int(m.group(1), 16)
        m = re.match(r"^(db|dw|dd)\s+(.+)$", s, re.I)
        if m:
            width = {"db": 1, "dw": 2, "dd": 4}[m.group(1).lower()]
            out = bytearray()
            # CE accepts comma-separated data, and `dd A, B, C` is by far the
            # most natural way to write a table.  Split on both commas and
            # whitespace, otherwise "A," is not recognised as a symbol and
            # silently degrades to the 0x1000000 placeholder.
            for tok in m.group(2).replace(",", " ").split():
                v = None
                if self.is_symbol(tok):
                    v = self.symval(tok, phase1)
                if v is None:
                    v = int(tok, 16) if HEXONLY.match(tok) else 0x1000000
                out += (v & ((1 << (width * 8)) - 1)).to_bytes(width, "little")
            return bytes(out)

        parts = s.split(None, 1)
        mnem = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if (mnem in ("jmp", "call", "loop") or mnem in JCC) and is_direct_operand(rest):
            target = self.eval_addr(rest, phase1)
            # CE's assembler emits the *short* form only for backward jumps whose
            # distance is already known, and the long form for every forward jump.
            # Reproducing that keeps our bytes comparable with the shipped exe and
            # keeps every size independent of the final layout.
            if mnem == "jmp":
                rel = target - (va + 2)
                if target <= va and -128 <= rel <= 127:
                    return b"\xEB" + struct.pack("<b", rel)
                return b"\xE9" + struct.pack("<i", target - (va + 5))
            if mnem == "call":
                return b"\xE8" + struct.pack("<i", target - (va + 5))
            if mnem == "loop":
                rel = target - (va + 2)
                if not -128 <= rel <= 127:
                    raise ValueError("loop out of range at 0x%X" % va)
                return b"\xE2" + struct.pack("<b", rel)
            rel = target - (va + 2)
            if target <= va and -128 <= rel <= 127:
                return bytes([0x70 | JCC[mnem]]) + struct.pack("<b", rel)
            return b"\x0F" + bytes([0x80 | JCC[mnem]]) + struct.pack("<i", target - (va + 6))

        text = self.subst(rest, phase1)
        text = self._fix_ambiguous(mnem + " " + text)
        try:
            enc, cnt = self.ks.asm(text, va)
        except Exception as exc:
            raise SyntaxError("keystone rejected %r  (source: %r) at 0x%X: %s"
                              % (text, s, va, exc))
        if enc is None or cnt != 1:
            raise SyntaxError("keystone could not assemble %r at 0x%X (cnt=%s)" % (text, va, cnt))
        return _demoffs(bytes(enc))

    @staticmethod
    def _fix_ambiguous(text):
        m = AMBIGUOUS.match(text)
        if m and "ptr" not in text.lower():
            return "%s dword ptr %s, %s" % (m.group(1), m.group(2), m.group(3))
        return text

    def layout(self):
        """Pass 1: assign every label a VA (sizes are address-independent)."""
        for blk in self.blocks:
            va = blk.va
            sizes = []
            for kind, *payload in blk.ops:
                if kind == "label":
                    self.labels[payload[0]] = va
                else:
                    blob = self._encode_line(payload[0], va, phase1=True)
                    sizes.append(len(blob))
                    va += len(blob)
            blk.end_va = va
            blk.sizes = sizes

        # A `label(NAME)` with no matching `NAME:` resolves to None, and the
        # branch that uses it is then encoded with a *garbage* displacement
        # rather than failing -- e.g. `jmp` to 0x7F000000.  That is exactly the
        # silent-garbage failure mode this project keeps hitting, so refuse it.
        # (It happens for real: concatenating a code block that does not end in
        # a newline onto the next label glues them into `retcustomMenuRender:`,
        # which quietly deletes the label the block was supposed to define.)
        #
        # Only labels that are actually *used* matter: a stray `label(NAME)`
        # with no definition and no reference is dead weight, not a bug.
        used = set()
        for blk in self.blocks:
            for kind, *payload in blk.ops:
                if kind != "line":
                    continue
                for tok in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", payload[0]):
                    if tok in self.declared:
                        used.add(tok)
        missing = sorted(n for n in used if n not in self.labels)
        if missing:
            raise SystemExit(
                "declared and referenced but never defined: %s\n"
                "  check that the preceding block ends with a newline -- "
                "`...ret` + `NAME:` becomes the single label `retNAME:`."
                % ", ".join(missing))

    def emit(self):
        """Pass 2: assemble with real label values."""
        out = {}
        for blk in self.blocks:
            va = blk.va
            buf = bytearray()
            i = 0
            for kind, *payload in blk.ops:
                if kind == "label":
                    continue
                blob = self._encode_line(payload[0], va, phase1=False)
                if len(blob) != blk.sizes[i]:
                    raise SystemExit(
                        "layout drifted for %r at 0x%X: pass1=%d pass2=%d"
                        % (payload[0], va, blk.sizes[i], len(blob)))
                i += 1
                buf += blob
                va = blk.va + len(buf)
            out[blk.va] = bytes(buf)
        return out


# CE's assembler always encodes `mov r32, [abs32]` as ModRM (8B 05), whereas
# LLVM prefers the one-byte-shorter moffs form (A1).  Both are functionally
# identical, but normalising keeps our output comparable with BAN's shipped cave.
MOFFS = {
    0xA0: bytes([0x8A, 0x05]),   # mov al,  moffs8
    0xA1: bytes([0x8B, 0x05]),   # mov eax, moffs32
    0xA2: bytes([0x88, 0x05]),   # mov moffs8,  al
    0xA3: bytes([0x89, 0x05]),   # mov moffs32, eax
}


def _demoffs(enc):
    if len(enc) == 5 and enc[0] in MOFFS:
        return MOFFS[enc[0]] + enc[1:]
    return enc


def collapse(text):
    def rep(m):
        v = eval_const(m.group(0))
        return "0x%X" % v if v is not None else m.group(0)
    return CONST_RUN.sub(rep, text)


def eval_const(s):
    s = s.strip()
    if not re.fullmatch(r"[0-9A-Fa-fxX+\-*/() ]+", s):
        return None
    try:
        return int(eval(s, {"__builtins__": {}}, {}))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
LENIENT = [False]


def build(cea_path, orig_path, out_path, report=False, json_path=None,
          cave_size_opt=None):
    pe = PE(orig_path)
    ib = pe.image_base
    comp = Compiler(open(cea_path, encoding="utf-8").read(), ib,
                    os.path.dirname(os.path.abspath(cea_path)))

    # --- .leprac section (create it if the input does not have one) ---
    cave_expr = comp.defines.get("cave")
    cave_size = cave_size_opt or 0x4000
    sec = pe.section(".leprac")
    if sec is None:
        cave_va = comp.eval_addr(cave_expr, phase1=True)
        pe.add_section(".leprac", cave_size, 0xE0000060)
        pe.dll_char &= ~0x0040           # DYNAMIC_BASE off (cave uses absolute VAs)
        struct.pack_into("<H", pe.data, pe.opt + 70, pe.dll_char)
        sec = pe.section(".leprac")
        print("[+] created .leprac  VA=0x%08X  %d bytes" % (cave_va, cave_size))
    cave_va = pe.image_base + sec["va"]
    if comp.eval_addr(cave_expr, phase1=True) != cave_va:
        raise SystemExit("cave define 0x%08X != section VA 0x%08X"
                         % (comp.eval_addr(cave_expr, phase1=True), cave_va))

    # --- layout + emit ---
    comp.layout()
    blobs = comp.emit()

    # every block must stop before the next declared address boundary, so a stub
    # can never spill over the original instruction that follows it
    starts = sorted(b.va for b in comp.blocks)
    for blk in comp.blocks:
        nxt = next((v for v in starts if v > blk.va), None)
        if nxt is None and blk.va >= cave_va:
            nxt = cave_va + cave_size
        if nxt is not None and blk.end_va > nxt:
            raise SystemExit("block at game+%X overflows: ends 0x%X, next boundary 0x%X"
                             % (blk.va - ib, blk.end_va, nxt))

    # --- verify asserts against the input ---
    n_ok = 0
    bad = []
    for va, blob in comp.asserts:
        if cave_va <= va < cave_va + cave_size:
            continue                      # we own the cave; nothing to verify
        got = pe.read_va(va, len(blob))
        if got != blob:
            bad.append((va, blob, got))
        else:
            n_ok += 1
    if bad:
        print("[!] %d assert() mismatch(es) -- the .cea targets a different build:"
              % len(bad))
        for va, blob, got in bad:
            print("      game+%X\n        want %s\n        got  %s"
                  % (va - ib, blob.hex(" "), got.hex(" ")))
        if not LENIENT[0]:
            raise SystemExit("refusing to patch: pass --lenient to override")
    print("[+] %d/%d assert() sites verified against the original"
          % (n_ok, len(comp.asserts)))

    # --- write everything ---
    cave = bytearray(cave_size)
    cave_used = 0
    for va, blob in sorted(blobs.items()):
        if not (cave_va <= va < cave_va + cave_size):
            pe.write_va(va, blob)
            continue
        off = va - cave_va
        if off + len(blob) > cave_size:
            raise SystemExit("cave overflow: 0x%X + %d > 0x%X" % (off, len(blob), cave_size))
        cave[off:off + len(blob)] = blob
        if off < 0x3FF0:                       # the trailing marker is not payload
            cave_used = max(cave_used, off + len(blob))

    # the 'LEPRAC3:FIXED:1' marker assert doubles as "write this into the cave"
    for va, blob in comp.asserts:
        if cave_va <= va < cave_va + cave_size:
            off = va - cave_va
            cave[off:off + len(blob)] = blob
    pe.write_va(cave_va, bytes(cave))

    pe.save(out_path)
    print("[+] cave used 0x%X / 0x%X bytes (%.1f%%), free 0x%X"
          % (cave_used, cave_size, 100.0 * cave_used / cave_size, cave_size - cave_used))
    print("[+] wrote %s" % out_path)
    if json_path:
        import hashlib
        h = hashlib.sha256()
        with open(out_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        doc = {
            "exe": os.path.basename(out_path),
            "sha256": h.hexdigest(),
            "image_base": pe.image_base,
            "cave_va": cave_va,
            "cave_size": cave_size,
            "labels": {n: v for n, v in comp.labels.items()},
            "cave_labels": {n: v - cave_va for n, v in comp.labels.items()
                            if cave_va <= v < cave_va + cave_size},
        }
        os.makedirs(os.path.dirname(os.path.abspath(json_path)) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        print("[+] wrote %s (%d labels)" % (json_path, len(comp.labels)))
    if report:
        print("[i] cave labels:")
        for name, va in sorted(comp.labels.items(), key=lambda kv: kv[1]):
            if cave_va <= va < cave_va + cave_size:
                print("      cave+0x%04X  %s" % (va - cave_va, name))
    return comp, pe, cave_va


if __name__ == "__main__":
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    json_path = None
    if "--json" in argv:
        i = argv.index("--json")
        if i + 1 >= len(argv):
            raise SystemExit("--json needs a path")
        json_path = argv[i + 1]
        args = [a for a in args if a != json_path]
    if len(args) < 3:
        print(__doc__)
        raise SystemExit(2)
    LENIENT[0] = "--lenient" in flags
    cs = None
    if "--cave-size" in argv:
        i = argv.index("--cave-size")
        if i + 1 >= len(argv):
            raise SystemExit("--cave-size needs a value")
        cs = int(argv[i + 1], 0)
        args = [a for a in args if a != argv[i + 1]]
    build(args[0], args[1], args[2], report="--report" in flags, json_path=json_path,
          cave_size_opt=cs)
