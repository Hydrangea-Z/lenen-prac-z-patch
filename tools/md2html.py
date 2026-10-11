#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Markdown -> standalone HTML, for the project's own docs.

Only the constructs our documents actually use are implemented (headings,
fenced code, tables, lists, blockquotes, rules, bold/italic/inline code).
Written by hand rather than pulling a dependency in, so the build stays offline
and deterministic.

Usage:  python tools/md2html.py <in.md> <out.html> ["<page title>"]
"""
import html
import os
import re
import sys

CSS = """
:root{--bg:#fbfbfa;--fg:#1f2328;--dim:#57606a;--line:#d8dee4;--code:#f2f3f5;
      --accent:#0b6bcb;--warn:#8a5a00;--warnbg:#fff8e5;--th:#f0f2f5}
@media (prefers-color-scheme:dark){
  :root{--bg:#1b1f24;--fg:#e6edf3;--dim:#9aa4b0;--line:#30363d;--code:#22272e;
        --accent:#58a6ff;--warn:#e3b341;--warnbg:#2b2416;--th:#22272e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:48px 28px 96px}
h1,h2,h3,h4{line-height:1.35;font-weight:650;margin:2em 0 .6em}
h1{font-size:1.85em;margin-top:0;padding-bottom:.4em;border-bottom:2px solid var(--line)}
h2{font-size:1.35em;padding-bottom:.3em;border-bottom:1px solid var(--line)}
h3{font-size:1.1em}
p,ul,ol,table,pre,blockquote{margin:.85em 0}
a{color:var(--accent)}
code{background:var(--code);padding:.15em .4em;border-radius:4px;
     font:0.9em/1.5 ui-monospace,Consolas,"Courier New",monospace}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;
    padding:14px 16px;overflow:auto}
pre code{background:none;padding:0;font-size:.88em}
table{border-collapse:collapse;width:100%;display:block;overflow:auto}
th,td{border:1px solid var(--line);padding:8px 12px;text-align:left;vertical-align:top}
th{background:var(--th);font-weight:650;white-space:nowrap}
tr:nth-child(even) td{background:color-mix(in srgb,var(--th) 45%,transparent)}
blockquote{margin-left:0;padding:10px 16px;border-left:4px solid var(--warn);
           background:var(--warnbg);border-radius:0 6px 6px 0}
blockquote p{margin:.3em 0}
hr{border:0;border-top:1px solid var(--line);margin:2.5em 0}
ul,ol{padding-left:1.6em}
li{margin:.3em 0}
strong{font-weight:650}
"""


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def convert(md):
    out, i, lines = [], 0, md.split("\n")
    while i < len(lines):
        ln = lines[i]

        # fenced code -- tolerate indentation, so a fence inside a list item
        # is still a code block (it used to fall through to the paragraph
        # branch, where the guard rejected the line and the index never
        # advanced: an infinite loop).
        if ln.lstrip().startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>"
                       % html.escape("\n".join(buf), quote=False))
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}", ln.strip()):
            out.append("<hr>")
            i += 1
            continue

        # heading
        m = re.match(r"(#{1,6})\s+(.*)", ln)
        if m:
            n = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (n, inline(m.group(2)), n))
            i += 1
            continue

        # table
        if ln.lstrip().startswith("|") and i + 1 < len(lines) \
                and re.fullmatch(r"\|[\s:|-]+\|", lines[i + 1].strip()):
            def cells(row):
                row = row.strip()
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|"):
                    row = row[:-1]
                # Protect an escaped pipe BEFORE splitting, or a cell whose
                # whole content is `\|` (the vertical-dash marker row) falls
                # apart into two cells.
                row = row.replace("\\|", "\x00")
                return [c.strip().replace("\x00", "|") for c in row.split("|")]
            head = cells(ln)
            i += 2
            body = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                body.append(cells(lines[i]))
                i += 1
            t = ["<table><thead><tr>"]
            t += ["<th>%s</th>" % inline(c) for c in head]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # blockquote
        if ln.lstrip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % inline(" ".join(buf)))
            continue

        # list
        if re.match(r"\s*([-*]|\d+\.)\s+", ln):
            ordered = bool(re.match(r"\s*\d+\.\s+", ln))
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"\s*([-*]|\d+\.)\s+", "", lines[i], count=1))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag,
                       "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue

        if not ln.strip():
            i += 1
            continue

        # paragraph (join consecutive non-blank lines)
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"\s*(#{1,6}\s|[-*]\s|\d+\.\s|>|\||```)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if not buf:
            # A line the guard above rejects but no earlier branch claimed
            # (e.g. an indented fence).  Consume it, or this spins forever.
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))
    return "\n".join(out)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(src)
    body = convert(open(src, encoding="utf-8").read())
    doc = ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
           "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<main>\n%s\n</main>\n"
           "</body>\n</html>\n" % (html.escape(title), CSS, body))
    open(dst, "w", encoding="utf-8", newline="\n").write(doc)
    print("[+] wrote %s (%d bytes)" % (dst, len(doc)))


if __name__ == "__main__":
    main()
