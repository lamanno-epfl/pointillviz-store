#!/usr/bin/env python3
"""Build the Tool Store's data from the PointillViz tool registry's index.

    pixi run --manifest-path _build/pixi.toml build           # the public registry, into this site
    python -I _build/build_store_data.py --index PATH|URL     # any other index.json
    python -I _build/build_store_data.py --index PATH --registry DIR --out DIR
                                                     # a test copy, from a registry checkout

The rebuild workflow runs the first line every hour and commits what changed. It
needs rsvg-convert and Pillow: the environment of _build/pixi.toml, whose lock
pins them, so that the same index always gives the same bytes.

Reads, never writes:
    <index>                               the registry's index.json: each tool's latest
                                          version (manifest, bundle URL and size, gate
                                          report, release date) and the Coming soon list
    <registry>/tools/<id>/README.md       the tool's page text   } when the registry checkout
    <registry>/tools/<id>/preview.svg     its card artwork       } has them; otherwise the
                                                                 } index's readme_url, preview_url

Writes (into store/, or --out):
    data/tools.json                       one record per tool, latest version
    data/tools-index.json                 the same tools, card fields only (what the gallery loads)
    assets/media/tools/<id>.webp          card artwork, 720 x 420
    assets/media/tools/<id>@2x.webp       card artwork, 1440 x 840
    assets/media/social/<id>.jpg          1200 x 630 link preview of a tool
    assets/media/social/store.jpg         1200 x 630 link preview of the gallery

The site copies no tool's code: a tool page links to its bundle (the index's
bundle.url) and to its folder in the public registry (source_url).

Every string in the registry is author-controlled. The README is converted with a
small Markdown subset (a port of the local store's renderer) that escapes all
text and allows only http(s) links; its formulas become MathML built from our
own element names around escaped text. The SVG artwork is rasterized (from
stdin, so it cannot reach other files) instead of being served as SVG, after a
full-size backdrop the author drew first is dropped, so that every artwork sits
on the store's own plate.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# realpath: a link to this file elsewhere still finds the site and the fonts.
HERE = os.path.dirname(os.path.realpath(__file__))
STORE = os.path.dirname(HERE)                   # the store site: this repository
DEFAULT_INDEX = "https://raw.githubusercontent.com/lamanno-epfl/pointillviz-registry/main/index.json"
FONTS = os.path.join(HERE, "fonts")             # DM Sans and JetBrains Mono, OFL

GATE_ORDER = ["bundle", "manifest", "environment", "entry", "imports", "fixture", "result",
              "edge", "no_mutation"]
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ART_W, ART_H = 720, 420            # 12:7, the 240 x 140 preview.svg at 3x
MAX_INDEX = 16 * 1024 * 1024
MAX_README = 256 * 1024
MAX_SVG = 4 * 1024 * 1024
INK = (6, 7, 13)
INK_1 = (10, 12, 24)

# Output kinds, badges and disclosures, in the words of brief/CONTENT.md (B5).
OUTPUT_HELP = {
    "cells": "paints the spatial view",
    "labels": "paints categories on the spatial view",
    "vectors": "draws arrows over the tissue",
    "table": "returns a table",
    "matrix": "returns a heatmap",
    "series": "returns a line chart",
    "chord": "returns a chord diagram",
    "radar": "returns a radar plot",
    "images": "returns figures",
    "views": "returns a custom interactive view",
    "files": "returns files to download",
    "summary": "writes a summary",
}
# The outputs a reader can filter by: what the tool will draw. "table" and
# "summary" come with nearly every tool and tell a reader nothing.
OUTPUT_FILTERS = ["cells", "labels", "vectors", "matrix", "series", "chord", "radar", "images",
                  "views", "files"]
LANGUAGES = {"python": "Python", "r": "R"}
GPU_TEXT = {"optional": "GPU optional", "required": "GPU required"}
RISK_SHORT = {"network": "network", "subprocess": "subprocess", "filesystem_write": "writes files",
              "dynamic_exec": "eval", "env": "environment"}
RISK_TEXT = {"network": "opens network connections", "subprocess": "starts other programs",
             "filesystem_write": "writes to the filesystem",
             "dynamic_exec": "builds and runs code at runtime",
             "env": "reads or changes environment variables"}


# --------------------------------------------------------------------------- helpers

def esc(s) -> str:
    return html.escape(str(s), quote=True)


EMAIL = re.compile(r"\s*<[^<>\s]*@[^<>\s]*>")


def strip_email(s: str) -> str:
    """'Name <a@b>' -> 'Name'. Manifests carry addresses that are not for publication."""
    return re.sub(r"\s{2,}", " ", EMAIL.sub("", s or "")).strip()


def fmt_int(n) -> str:
    n = int(n)
    return f"{n:,}" if abs(n) >= 1000 else str(n)


def fmt_num(x) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "on" if x else "off"
    if isinstance(x, int):
        return fmt_int(x)
    if isinstance(x, float):
        if x.is_integer():
            return fmt_int(int(x))
        s = ("%.10f" % x).rstrip("0").rstrip(".")
        return s
    return str(x)


NBSP = "\xa0"


def fmt_bytes(n: int) -> str:
    if not n:
        return "—"
    if n < 1024:
        return f"{n}{NBSP}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}{NBSP}kB"
    return f"{n / 1048576:.2f}{NBSP}MB"


def smart(s: str) -> str:
    """Typographer's quotes in author prose: apostrophes, single and double quotes.
    Applied to text only, never to code spans, gate messages or identifiers."""
    s = re.sub(r"(?<=[A-Za-z0-9])'(?=[A-Za-z])", "\N{RIGHT SINGLE QUOTATION MARK}", s)   # type's
    s = re.sub(r"(?<=[A-Za-z])'(?=[\s.,;:!?)]|$)", "\N{RIGHT SINGLE QUOTATION MARK}", s)  # tools'
    s = re.sub(r"(?:(?<=\s)|^)'(?=\S)", "\N{LEFT SINGLE QUOTATION MARK}", s)               # 'word
    s = re.sub(r'"([^"\n]*)"', "\N{LEFT DOUBLE QUOTATION MARK}\\1\N{RIGHT DOUBLE QUOTATION MARK}", s)
    return s


def fmt_date(iso: str) -> str:
    """'2026-10-27', the index's release date, as '27 Oct 2026'."""
    try:
        d = datetime.strptime((iso or "")[:10], "%Y-%m-%d")
    except ValueError:
        return (iso or "")[:10]
    return f"{d.day} {d.strftime('%b')} {d.year}"


def short_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:10]


# --------------------------------------------------------------------------- markdown
#
# A port of the local store's renderMarkdown (APP/store/web/app.js): the same
# small subset, emitting escaped HTML instead of DOM nodes. Headings are pushed
# below the page's own: the page's sections are h2, so README headings start at
# h3, and a leading "# <tool name>" is dropped because the page already says it.

INLINE = re.compile(r"(`[^`]+`)|(\*\*[\s\S]+?\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]*\]\([^)\s]*\))")


def safe_href(url: str):
    return url if re.match(r"^https?://", url, re.I) else None


def md_inline(text: str) -> str:
    out, last = [], 0
    for m in INLINE.finditer(text):
        if m.start() > last:
            out.append(esc(smart(text[last:m.start()])))
        tok = m.group(0)
        if tok.startswith("`"):
            out.append(f"<code>{esc(tok[1:-1])}</code>")
        elif tok.startswith("**"):
            out.append(f"<strong>{esc(smart(tok[2:-2]))}</strong>")
        elif tok.startswith("*"):
            # READMEs set inline maths as emphasis: *xⱼ*, *K(A,B)(r) = πr²*.
            inner = tok[1:-1]
            out.append(math_inline(inner) if is_mathy(inner) else f"<em>{esc(smart(inner))}</em>")
        else:
            cut = tok.index("](")
            label, url = tok[1:cut], tok[cut + 2:-1]
            href = safe_href(url)
            out.append(f'<a class="pv-link" href="{esc(href)}" rel="noopener noreferrer nofollow">{esc(smart(label or url))}</a>'
                       if href else esc(tok))
        last = m.end()
    if last < len(text):
        out.append(esc(smart(text[last:])))
    return "".join(out)


# --------------------------------------------------------------------------- maths
#
# READMEs write display formulas between $$ lines in the local store's compact
# subset (\frac{}{}, \sum_{}, \set{}, \paren{}, ^{}, _{}) mixed with Unicode
# (xⱼ, r², x̄, √(…)), and inline maths as *emphasis*. Both become MathML Core,
# which browsers lay out natively; store.css sets it in the vendored math font.
#
# Three passes: lex (commands, brackets, words and scripts, as markers), group
# (brackets into fences, so that each stretches only to its own content) and
# finish (runs of words into mtext, then roots, primes and scripts attach to
# what precedes them). Every string is escaped; only element names we chose are
# emitted, so author text cannot add markup.

SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₔₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥᵦᵧᵨᵩᵪ",
               "0123456789+−=()aeoxəhklmnpstijruvβγρφχ"))
SUP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+−=()ni"))
ACCENT = {
    "\N{COMBINING MACRON}": "\N{MACRON}",
    "\N{COMBINING OVERLINE}": "\N{MACRON}",
    "\N{COMBINING CIRCUMFLEX ACCENT}": "\N{MODIFIER LETTER CIRCUMFLEX ACCENT}",
    "\N{COMBINING TILDE}": "\N{SMALL TILDE}",
    "\N{COMBINING DOT ABOVE}": "\N{DOT ABOVE}",
    "\N{COMBINING DIAERESIS}": "\N{DIAERESIS}",
    "\N{COMBINING CARON}": "\N{CARON}",
    "\N{COMBINING RIGHT ARROW ABOVE}": "\N{RIGHTWARDS ARROW}",
}
PRIMES = "′″‴"
FENCE = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
RELATIONS = {"=", "∝", "≈", "≡"}
# Operators that bring their own spacing: a run of words beside one needs no more.
SPACED = set("=+−×·/,:;<>≤≥∝≈≡∈∉⊂⊆→⟶|‖*∑")
# Function names stay identifiers even when a space follows them (log P).
FUNCTIONS = {"log", "ln", "exp", "sin", "cos", "tan", "min", "max", "mean", "var", "softmax",
             "argmax", "argmin", "det", "tr"}
MATH_COMMANDS = ("\\frac{", "\\sum_{", "\\set{", "\\paren{", "^{", "_{")
MATHY = set("=()[]∇√∑±×·−+/<>≤≥∈∞∂′|‖%…") | set(SUB) | set(SUP)


def _match_brace(text: str, open_i: int) -> int:
    depth = 0
    for i in range(open_i, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _latin(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def _script_node(s: str):
    """A script written in Unicode (ᵢⱼ, ₚₐᵢᵣₛ, ⁻¹): up to two letters are separate
    variables (pᵢⱼ), a longer run of letters is a word (Nₚₐᵢᵣₛ)."""
    if s.isalpha() and len(s) <= 2:
        return ("row", [("mi", c) for c in s])
    return ("row", _parse(s))


def _lex_text(text: str, out: list) -> None:
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            while i < n and text[i].isspace():
                i += 1
            out.append(("_sp",))
            continue
        if c in SUB or c in SUP:
            table, kind = (SUB, "sub") if c in SUB else (SUP, "sup")
            j = i
            while j < n and text[j] in table:
                j += 1
            out.append(("_script", kind, _script_node("".join(table[ch] for ch in text[i:j]))))
            i = j
            continue
        if c in PRIMES:
            out.append(("_prime", c))
        elif c == "√":
            out.append(("_sqrt",))
        elif c in FENCE:
            out.append(("_open", c))
        elif c in FENCE.values():
            out.append(("_close", c))
        elif c.isdigit():
            j = i + 1
            while j < n and (text[j].isdigit() or (text[j] == "." and j + 1 < n and text[j + 1].isdigit())):
                j += 1
            out.append(("mn", text[i:j]))
            i = j
            continue
        elif c in "_^" and i + 1 < n and (text[i + 1].isalnum()):
            # A bare one-character script, as in TeX: P_c, e^x.
            out.append(("_script", "sub" if c == "_" else "sup", ("row", _parse(text[i + 1]))))
            i += 2
            continue
        elif c == "*" and i > 0 and not text[i - 1].isspace():
            out.append(("_script", "sup", ("mo", "*")))          # Gᵢ*
        elif c == "Σ" and not (i + 1 < n and text[i + 1].isalpha()):
            out.append(("mo", "∑"))                               # a sum written as Σ
        elif c == "∞":
            out.append(("mi", "∞"))
        elif c == "∇":
            out.append(("mi", "∇", "normal"))
        elif c == "∂":
            out.append(("mi", "∂"))
        elif unicodedata.category(unicodedata.normalize("NFD", c)[0]).startswith("L"):
            decomposed = unicodedata.normalize("NFD", c)          # ā -> a + macron
            base, marks, j = decomposed[0], decomposed[1:], i + 1
            while j < n and unicodedata.category(text[j]) == "Mn":
                marks += text[j]
                j += 1
            if not marks and _latin(base):
                # A Latin word: letters without marks, so that x̄ stays a variable.
                while j < n and _latin(text[j]) and not (j + 1 < n and unicodedata.category(text[j + 1]) == "Mn"):
                    j += 1
                word = text[i:j]
                if len(word) > 1:
                    if j < n and text[j] == "." and (j + 1 == n or text[j + 1].isspace()):
                        word, j = word + ".", j + 1                # an abbreviation: vs.
                    out.append(("_word", word))
                    i = j
                    continue
            node = ("mi", base)
            for mark in marks:
                node = ("over", node, ACCENT.get(mark, mark))
            out.append(node)
            i = j
            continue
        elif unicodedata.category(c) != "Mn":                       # a stray mark is dropped
            out.append(("mo", "−" if c == "-" else c))
        i += 1


def _lex(src: str) -> list:
    out, i = [], 0
    while i < len(src):
        nxt = None
        for prefix in MATH_COMMANDS:
            idx = src.find(prefix, i)
            if idx != -1 and (nxt is None or idx < nxt[0]):
                nxt = (idx, prefix)
        if nxt is None:
            _lex_text(src[i:], out)
            break
        idx, prefix = nxt
        if idx > i:
            _lex_text(src[i:idx], out)
        open_b = idx + len(prefix) - 1
        close_b = _match_brace(src, open_b)
        if close_b == -1:
            _lex_text(src[idx:], out)
            break
        arg, i = src[open_b + 1:close_b], close_b + 1
        if prefix == "\\frac{":
            den_close = _match_brace(src, i) if i < len(src) and src[i] == "{" else -1
            if den_close == -1:
                _lex_text(src[idx:i], out)
                continue
            out.append(("frac", ("row", _parse(arg)), ("row", _parse(src[i + 1:den_close]))))
            i = den_close + 1
        elif prefix == "\\sum_{":
            out.append(("under", ("mo", "∑"), ("row", _parse(arg))))
        elif prefix == "\\set{":
            out.append(("fence", "{", _parse(arg), "}"))
        elif prefix == "\\paren{":
            out.append(("fence", "(", _parse(arg), ")"))
        else:
            out.append(("_script", "sup" if prefix == "^{" else "sub", ("row", _parse(arg))))
    return out


def _group(items: list) -> list:
    stack = [(None, [])]
    for it in items:
        if it[0] == "_open":
            stack.append((it[1], []))
        elif it[0] == "_close":
            if len(stack) > 1 and FENCE.get(stack[-1][0]) == it[1]:
                opener, kids = stack.pop()
                stack[-1][1].append(("fence", opener, kids, it[1]))
            else:
                stack[-1][1].append(("mo", it[1]))
        else:
            stack[-1][1].append(it)
    while len(stack) > 1:  # an opener that never closes stays a plain character
        opener, kids = stack.pop()
        stack[-1][1].extend([("mo", opener)] + kids)
    return stack[0][1]


def _prose(nodes: list) -> list:
    """Words beside other words or variables are prose (cells in the largest patch,
    k in B, ∞ and d): they become mtext, with a no-break space where a space
    separates them from a variable. A word against a bracket or an operator is an
    identifier (softmax(, Lw =)."""
    n = len(nodes)

    def across(k, step):
        j, gap = k + step, False
        if 0 <= j < n and nodes[j][0] == "_sp":
            gap, j = True, j + step
        return (nodes[j] if 0 <= j < n else None), gap

    def spaced(nd):
        return nd is not None and nd[0] == "mo" and nd[1] in SPACED

    def is_prose(k):
        if nodes[k][1].lower() in FUNCTIONS:
            return False
        if k + 1 < n and nodes[k + 1][0] in ("fence", "_script", "_prime"):
            return False
        left, lgap = across(k, -1)
        right, rgap = across(k, +1)
        return bool((lgap and left is not None and not spaced(left)) or (rgap and right is not None and not spaced(right)))

    prose = [nodes[k][0] == "_word" and is_prose(k) for k in range(n)]
    out, k = [], 0
    while k < n:
        nd = nodes[k]
        if nd[0] == "_sp":
            k += 1
            continue
        if prose[k]:
            words, j = [nd[1]], k + 1
            while j + 1 < n and nodes[j][0] == "_sp" and prose[j + 1]:
                words.append(nodes[j + 1][1])
                j += 2
            text = " ".join(words)
            left, lgap = across(k, -1)
            right, rgap = across(j - 1, +1)
            if lgap and left is not None and not spaced(left):
                text = NBSP + text
            if rgap and right is not None and not spaced(right):
                text += NBSP
            out.append(("mtext", text))
            k = j
            continue
        if nd[0] == "_word":
            out.append(("mi", nd[1]))
            right, rgap = across(k, +1)
            if nd[1].lower() in FUNCTIONS and rgap and right is not None and not spaced(right):
                out.append(("space",))  # log P: a thin space, as TeX sets it
            k += 1
            continue
        out.append(nd)
        k += 1
    return out


def _finish(nodes: list) -> list:
    nodes = [("fence", nd[1], _finish(nd[2]), nd[3]) if nd[0] == "fence" else nd for nd in nodes]
    nodes = _prose(nodes)
    out, k = [], 0
    while k < len(nodes):
        nd = nodes[k]
        if nd[0] == "_sqrt":
            if k + 1 < len(nodes):
                nxt = nodes[k + 1]
                out.append(("sqrt", nxt[2] if nxt[0] == "fence" and nxt[1] == "(" else [nxt]))
                k += 2
            else:
                out.append(("mo", "√"))
                k += 1
            continue
        if nd[0] == "_prime":
            out.append(("prime", out.pop() if out else ("row", []), nd[1]))
        elif nd[0] == "_script":
            kind, arg = nd[1], nd[2]
            base = out.pop() if out else ("row", [])
            if base[0] == "sub" and kind == "sup":
                out.append(("subsup", base[1], base[2], arg))
            elif base[0] == "sup" and kind == "sub":
                out.append(("subsup", base[1], arg, base[2]))
            else:
                out.append((kind, base, arg))
        else:
            out.append(nd)
        k += 1
    return out


def _parse(src: str) -> list:
    return _finish(_group(_lex(src)))


def _tall(nd, display: bool) -> bool:
    """Whether a node rises above a line of text: a fraction, or a sum set large in
    display style. Brackets stretch only around such content; around anything
    else they keep their text size and spacing."""
    kind = nd[0]
    if kind == "frac":
        return True
    if kind == "under" or (kind == "mo" and nd[1] == "∑"):
        return display
    if kind in ("sqrt", "fence"):
        return any(_tall(k, display) for k in nd[2 if kind == "fence" else 1])
    if kind == "row":
        return any(_tall(k, display) for k in nd[1])
    if kind in ("sub", "sup", "subsup", "over", "prime"):
        return _tall(nd[1], display)
    return False


def _mml_list(nodes: list, display: bool) -> str:
    tall = any(_tall(k, display) for k in nodes)
    return "".join(_mml(k, display, tall) for k in nodes)


def _mml(nd, display: bool = True, tall_row: bool = False) -> str:
    """One node as MathML. display is the math style (fraction parts and scripts
    are set smaller, in compact style); tall_row says whether the row holding a
    bare | or ‖ rises above the text, so that it may stretch."""
    kind = nd[0]
    if kind == "mi":
        variant = ' mathvariant="normal"' if len(nd) > 2 and nd[2] == "normal" else ""
        return f"<mi{variant}>{esc(nd[1])}</mi>"
    if kind == "mo":
        if nd[1] == "/":
            return '<mo lspace="0" rspace="0">/</mo>'  # a solidus sets tight, as in TeX
        if nd[1] in "|‖" and not tall_row:
            return f'<mo stretchy="false">{esc(nd[1])}</mo>'
        return f"<mo>{esc(nd[1])}</mo>"
    if kind in ("mn", "mtext"):
        return f"<{kind}>{esc(nd[1])}</{kind}>"
    if kind == "space":
        return '<mspace width="0.1667em"></mspace>'
    if kind == "row":
        return _arg(nd, display)
    if kind == "frac":
        return f"<mfrac>{_arg(nd[1], False)}{_arg(nd[2], False)}</mfrac>"
    if kind == "sqrt":
        return f"<msqrt>{_mml_list(nd[1], display)}</msqrt>"
    if kind in ("sub", "sup"):
        return f"<m{kind}>{_arg(nd[1], display)}{_arg(nd[2], False)}</m{kind}>"
    if kind == "subsup":
        return f"<msubsup>{_arg(nd[1], display)}{_arg(nd[2], False)}{_arg(nd[3], False)}</msubsup>"
    if kind == "over":
        return f'<mover accent="true">{_arg(nd[1], display)}<mo>{esc(nd[2])}</mo></mover>'
    if kind == "under":
        return f"<munder>{_arg(nd[1], display)}{_arg(nd[2], False)}</munder>"
    if kind == "fence":
        stretch = "" if any(_tall(k, display) for k in nd[2]) else ' stretchy="false"'
        return (f"<mrow><mo{stretch}>{esc(nd[1])}</mo>{_mml_list(nd[2], display)}"
                f"<mo{stretch}>{esc(nd[3])}</mo></mrow>")
    if kind == "prime":
        return f"<mrow>{_arg(nd[1], display)}<mo>{esc(nd[2])}</mo></mrow>"
    return ""


def _arg(nd, display: bool = True) -> str:
    """Exactly one element, as script and fraction slots require."""
    if nd[0] == "row":
        kids = nd[1]
        return _mml(kids[0], display, _tall(kids[0], display)) if len(kids) == 1 else f"<mrow>{_mml_list(kids, display)}</mrow>"
    return _mml(nd, display)


def math_linear(text: str) -> str:
    """A formula as one line of text, for its aria-label: fractions as (a) / (b),
    sums as "sum over j of", scripts as _j and ^2."""
    out, i = [], 0
    while i < len(text):
        nxt = None
        for prefix in MATH_COMMANDS:
            idx = text.find(prefix, i)
            if idx != -1 and (nxt is None or idx < nxt[0]):
                nxt = (idx, prefix)
        if nxt is None:
            out.append(text[i:])
            break
        idx, prefix = nxt
        out.append(text[i:idx])
        open_b = idx + len(prefix) - 1
        close_b = _match_brace(text, open_b)
        if close_b == -1:
            out.append(text[idx:])
            break
        arg, i = text[open_b + 1:close_b], close_b + 1
        if prefix == "\\frac{":
            den_close = _match_brace(text, i) if i < len(text) and text[i] == "{" else -1
            if den_close == -1:
                out.append(text[idx:i])
                continue
            out.append(f"({math_linear(arg)}) / ({math_linear(text[i + 1:den_close])})")
            i = den_close + 1
        elif prefix == "\\sum_{":
            out.append(f"sum over {math_linear(arg)} of ")
        elif prefix in ("\\set{", "\\paren{"):
            body = math_linear(arg)
            out.append("{" + body + "}" if prefix == "\\set{" else f"({body})")
        else:
            body = math_linear(arg)
            out.append(("^" if prefix == "^{" else "_") + (body if len(body) == 1 else f"({body})"))
    return "".join(out)


def is_mathy(s: str) -> bool:
    """Whether a README's *emphasis* is inline maths, which is how READMEs set it:
    a single letter or number, or text with operators, brackets, Greek letters,
    scripts or accents that is not mostly words."""
    s = s.strip()
    if not s or len(s) > 80:
        return False
    if re.fullmatch(r"[A-Za-z]|\d+(\.\d+)?", s):
        return True
    words = [t for t in s.split() if re.fullmatch(r"[A-Za-z]{3,}[.,;:!?]?", t) and t.strip(".,;:!?").lower() not in FUNCTIONS]
    if len(words) >= 3:
        return False
    return any(c in MATHY or unicodedata.category(c) == "Mn"
               or "\N{GREEK CAPITAL LETTER ALPHA}" <= c <= "\N{GREEK SMALL LETTER OMEGA}" for c in s)


def math_inline(src: str) -> str:
    return f"<math>{_mml_list(_parse(src), False)}</math>"


def _pieces(nodes: list) -> list:
    """Split one equation before each top-level relation, so that a chain can wrap
    at its = on a narrow screen. Brackets keep their contents together."""
    pieces, cur = [], []
    for nd in nodes:
        is_vs = nd[0] == "mtext" and nd[1].strip(" " + NBSP) == "vs."
        if cur and ((nd[0] == "mo" and nd[1] in RELATIONS) or is_vs):
            pieces.append(cur)
            cur = []
            if is_vs:
                nd = ("mtext", NBSP + "vs." + NBSP)
        cur.append(nd)
    if cur:
        pieces.append(cur)
    return pieces


def _words_only(row) -> bool:
    kids = row[1]
    return (any(k[0] == "mtext" for k in kids)
            and all(k[0] == "mtext" or (k[0] == "mi" and len(k[1]) == 1) or (k[0] == "mo" and k[1] in "−+")
                    for k in kids))


def _verbal_html(row) -> str:
    out = []
    for k in row[1]:
        if k[0] == "mtext":
            out.append(esc(k[1]))
        elif k[0] == "mi":
            out.append(f"<math><mi>{esc(k[1])}</mi></math>")
        else:
            out.append(f" <math><mo>{esc(k[1])}</mo></math> ")
    return "".join(out).strip()


def _piece_html(piece: list) -> str:
    """One part of an equation as its own <math>. A fraction of words (cells in
    the largest patch / all cells in group c) is set in HTML instead, so that its
    lines can wrap on a phone; MathML does not break lines."""
    lead, rest = ([piece[0]], piece[1:]) if piece[0][0] == "mo" and piece[0][1] in RELATIONS else ([], piece)
    if len(rest) == 1 and rest[0][0] == "frac" and _words_only(rest[0][1]) and _words_only(rest[0][2]):
        frac = rest[0]
        rel = f'<math displaystyle="true">{_mml(lead[0])}</math>' if lead else ""
        return (f'<span class="st-formula__piece st-vf">{rel}<span class="st-vf__frac">'
                f'<span class="st-vf__num">{_verbal_html(frac[1])}</span>'
                f'<span class="st-vf__den">{_verbal_html(frac[2])}</span></span></span>')
    return f'<span class="st-formula__piece"><math displaystyle="true">{_mml_list(piece, True)}</math></span>'


def formula_block(src: str) -> str:
    """A display formula. READMEs separate the equations of a formula line with
    runs of spaces; each equation is split again at its top-level relations, and
    the parts wrap on a narrow screen. Screen readers get the formula as text."""
    eqs = [t.strip() for t in re.split(r"\s{3,}", src.strip()) if t.strip()]
    arrows = ("⟶", "→")
    lins = []
    for k, e in enumerate(eqs):
        lin = math_linear(e).strip()
        if k + 1 < len(eqs) and not lin.endswith(",") and lin not in arrows and eqs[k + 1] not in arrows:
            lin += ","
        lins.append(lin)
    linear = re.sub(r"\s+", " ", " ".join(lins)).strip()
    html_eqs = "".join('<span class="st-formula__eq">' + "".join(_piece_html(p) for p in _pieces(_parse(e))) + "</span>"
                       for e in eqs)
    return (f'<div class="st-formula" role="img" aria-label="{esc(linear)}">'
            f'<div class="st-formula__row">{html_eqs}</div></div>')


def is_table_rule(line: str) -> bool:
    return "|" in line and re.match(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$", line) is not None


def table_cells(line: str):
    s = line.strip()
    s = re.sub(r"^\|", "", s)
    s = re.sub(r"\|$", "", s)
    return [c.strip() for c in s.split("|")]


STOP = re.compile(r"^\s*(```|#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\$\$)")


NO_TRANSLATE = re.compile(r"<(code|pre|math)(?=[\s>])")


def markdown_html(text: str, tool_name: str = "") -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, i, first_block = [], 0, True
    bullet, numbered = re.compile(r"^\s*[-*+]\s+"), re.compile(r"^\s*\d+[.)]\s+")
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        img = re.match(r"^\s*!\[([^\]\n]*)\]\(([^)\s]*)\)\s*$", line)
        if img:  # bundled README images are not published; keep their words
            alt = img.group(1) or ""
            if alt:
                out.append(f'<p class="st-md-imgalt">{esc(alt)}</p>')
            i += 1
            first_block = False
            continue
        if re.match(r"^\s*\$\$\s*$", line):
            buf, i = [], i + 1
            while i < len(lines) and not re.match(r"^\s*\$\$\s*$", lines[i]):
                buf.append(lines[i].strip())
                i += 1
            if i < len(lines):
                i += 1
            out.append(formula_block(" ".join(buf)))
            first_block = False
            continue
        if re.match(r"^\s*```", line):
            buf, i = [], i + 1
            while i < len(lines) and not re.match(r"^\s*```", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f'<pre class="st-md-pre" tabindex="0"><code>{esc(chr(10).join(buf))}</code></pre>')
            first_block = False
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level, words = len(h.group(1)), h.group(2).strip()
            if not (first_block and level == 1 and norm(words) == norm(tool_name)):
                tag = "h3" if level <= 2 else "h4"
                out.append(f"<{tag}>{md_inline(words)}</{tag}>")
            i += 1
            first_block = False
            continue
        first_block = False
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and is_table_rule(lines[i + 1]):
            head = "".join(f'<th scope="col">{md_inline(c)}</th>' for c in table_cells(line))
            rows, i = [], i + 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in table_cells(lines[i])) + "</tr>")
                i += 1
            out.append('<div class="pv-table-wrap" role="region" tabindex="0" aria-label="Table">'
                       f'<table class="pv-table pv-table--compact"><thead><tr>{head}</tr></thead>'
                       f'<tbody>{"".join(rows)}</tbody></table></div>')
            continue
        if bullet.match(line) or numbered.match(line):
            ordered = bool(numbered.match(line))
            rx = numbered if ordered else bullet
            items = []
            while i < len(lines) and rx.match(lines[i]):
                item = [rx.sub("", lines[i], count=1)]
                i += 1
                while (i < len(lines) and lines[i].strip() and not bullet.match(lines[i])
                       and not numbered.match(lines[i]) and not re.match(r"^\s*(```|#{1,6}\s|>)", lines[i])):
                    item.append(lines[i].strip())
                    i += 1
                items.append(f"<li>{md_inline(' '.join(item))}</li>")
                if i + 1 < len(lines) and not lines[i].strip() and rx.match(lines[i + 1]):
                    i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        if re.match(r"^\s*>\s?", line):
            buf = []
            while i < len(lines) and re.match(r"^\s*>\s?", lines[i]):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote><p>{md_inline(' '.join(buf))}</p></blockquote>")
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not STOP.match(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if not buf:  # a line STOP refused but no block took: keep it as text
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{md_inline(' '.join(buf))}</p>")
    # Code and formulas are not prose: a page translator leaves them as written.
    # Every author string above is escaped, so these are only our own tags.
    return NO_TRANSLATE.sub(r'<\1 translate="no"', "\n".join(out))


# --------------------------------------------------------------------------- artwork

def svg_label(svg: str) -> str:
    m = re.search(r'<svg\b[^>]*\baria-label="([^"]*)"', svg)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r"<title>([\s\S]*?)</title>", svg)
    return html.unescape(m.group(1)).strip() if m else ""


BACKDROP = re.compile(r"^(\s*(?:<\?xml[^>]*>\s*)?(?:<!--[\s\S]*?-->\s*)*<svg\b[^>]*>\s*)(<rect\b[^>]*?/>|<rect\b[^>]*>\s*</rect>)", re.I)


def strip_backdrop(svg: str) -> tuple[str, bool]:
    """Drop a backdrop the author painted first: a plain filled <rect> that covers
    the whole viewBox, square or rounded. Without it the artwork sits on the
    store's own plate like every other tool's, instead of as a darker rectangle
    nested inside it. Anything else is left exactly as drawn."""
    m = BACKDROP.match(svg)
    if not m:
        return svg, False
    root = re.search(r"<svg\b[^>]*>", svg).group(0)
    attrs = dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', m.group(2)))
    if any(k in attrs for k in ("transform", "style", "stroke", "filter", "mask", "clip-path", "opacity", "fill-opacity")):
        return svg, False
    fill = attrs.get("fill", "").strip().lower()
    if not fill or fill in ("none", "transparent") or fill.startswith("url("):
        return svg, False
    vb = re.search(r'\bviewBox\s*=\s*"\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)\s*"', root)
    if not vb:
        return svg, False
    vx, vy, vw, vh = (float(v) for v in vb.groups())

    def num(v):
        try:
            return float(re.sub(r"px$", "", v.strip()))
        except ValueError:
            return None

    def covers(v, start, size):
        return v.strip() == "100%" or (num(v) is not None and abs(num(v) - size) < 0.5)

    x, y = num(attrs.get("x", "0")), num(attrs.get("y", "0"))
    if (x is not None and y is not None and abs(x - vx) < 0.5 and abs(y - vy) < 0.5
            and covers(attrs.get("width", ""), vx, vw) and covers(attrs.get("height", ""), vy, vh)):
        return svg[:m.start(2)] + svg[m.end(2):], True
    return svg, False


def hash32(s: str) -> int:
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def mulberry32(a: int):
    state = [a & 0xFFFFFFFF]

    def rnd():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rnd


def constellation_svg(tool_id: str) -> str:
    """The stand-in art for a tool without preview.svg, as the local store drew
    it: a seeded field of points in one accent, the same for the same id."""
    accents = ["#6FE0BD", "#E2B25A", "#5B7BFF", "#FF7A6B", "#B98CFF"]
    rnd = mulberry32(hash32(tool_id) ^ 0x9E3779B9)
    color = accents[hash32(tool_id) % len(accents)]
    dots = []
    for _ in range(7):
        cx, cy = 26 + rnd() * 188, 20 + rnd() * 100
        spread, n = 14 + rnd() * 36, 22 + int(rnd() * 26)
        for _ in range(n):
            a, r = rnd() * math.pi * 2, math.sqrt(rnd()) * spread
            dots.append(f'<circle cx="{cx + math.cos(a) * r:.2f}" cy="{cy + math.sin(a) * r:.2f}" '
                        f'r="{1.1 + rnd() * 2.4:.2f}" fill="{color}" opacity="{0.2 + rnd() * 0.7:.2f}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 140">{"".join(dots)}</svg>'


def rasterize(svg: str, width: int, height: int) -> Image.Image:
    """SVG -> RGBA image. librsvg reads from stdin: with no base file there is
    nothing relative for the author's markup to reach."""
    exe = shutil.which("rsvg-convert")
    if not exe:
        sys.exit("rsvg-convert not found: run this in _build/pixi.toml's environment.")
    run = subprocess.run([exe, "--format=png", f"--width={width}", f"--height={height}",
                          "--keep-aspect-ratio"], input=svg.encode("utf-8"),
                         capture_output=True, timeout=60)
    if run.returncode != 0:
        raise RuntimeError(run.stderr.decode("utf-8", "replace")[:300])
    im = Image.open(io.BytesIO(run.stdout)).convert("RGBA")
    if im.size != (width, height):  # centre on a transparent canvas of the slot's size
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(im, ((width - im.width) // 2, (height - im.height) // 2), im)
        im = canvas
    return im


def webp_bytes(im: Image.Image) -> bytes:
    """The smaller of lossy and lossless, with a bias towards lossless: line art
    (charts, labels) stays crisp, point clouds stay small."""
    lossy, lossless = io.BytesIO(), io.BytesIO()
    im.save(lossy, "WEBP", quality=86, alpha_quality=92, method=6)
    im.save(lossless, "WEBP", lossless=True, quality=100, method=6)
    a, b = lossy.getvalue(), lossless.getvalue()
    return b if len(b) <= len(a) * 1.3 else a


def write_if_changed(path: str, data: bytes) -> bool:
    try:
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return True


def flatten(im: Image.Image, bg=INK_1) -> Image.Image:
    base = Image.new("RGB", im.size, bg)
    base.paste(im, (0, 0), im)
    return base


def dot_grid(size, step=24, color=(239, 230, 210), alpha=20, bg=INK_1, offset=(12, 12)) -> Image.Image:
    w, h = size
    im = Image.new("RGBA", (w, h), bg + (255,))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(offset[1], h, step):
        for x in range(offset[0], w, step):
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=color + (alpha,))
    return Image.alpha_composite(im, layer)


def font(name: str, size: int, weight: int | None = None):
    path = os.path.join(FONTS, name)
    try:
        f = ImageFont.truetype(path, size)
        if weight is not None:
            try:
                f.set_variation_by_axes([min(max(size, 9), 40), weight])
            except Exception:
                pass
        return f
    except OSError:
        return ImageFont.load_default()


def draw_tracked(d: ImageDraw.ImageDraw, xy, text: str, f, fill, tracking: float):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tracking
    return x


def social_tool(art: Image.Image, name: str) -> Image.Image:
    """1200 x 630: the tool's artwork on the store's ink, its name in the corner."""
    W, H = 1200, 630
    im = dot_grid((W, H))
    pic = art.resize((960, 560), Image.LANCZOS)
    im.alpha_composite(pic, ((W - 960) // 2, 18))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 66, W, H], fill=INK + (235,))
    f_name = font("DMSans.ttf", 28, 600)
    f_lab = font("JetBrainsMono-Medium.ttf", 15)
    d.text((48, H - 48), name, font=f_name, fill=(239, 230, 210))
    label = "THE TOOL STORE · POINTILLVIZ"
    tw = sum(d.textlength(c, font=f_lab) + 2.4 for c in label)
    draw_tracked(d, (W - 48 - tw, H - 41), label, f_lab, (185, 177, 160), 2.4)
    return im.convert("RGB")


def wordmark(height: int) -> Image.Image:
    """The PointillViz wordmark of the design system (shared/pv/logo.svg, the
    paper's own vector logo tinted for ink), rasterized at a height."""
    path = os.path.join(STORE, "assets", "pv", "logo.svg")
    with open(path, encoding="utf-8") as fh:
        svg = fh.read()
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    w = round(height * float(m.group(1)) / float(m.group(2)))
    big = rasterize(svg, w * 3, height * 3)          # drawn large, then reduced: crisp dots
    return big.resize((w, height), Image.LANCZOS)


def social_gallery(arts: list[Image.Image], count: int) -> Image.Image:
    """1200 x 630: the masthead's eyebrow (the PointillViz wordmark · COMMUNITY
    TOOLS) and the store's wordmark over the first twelve artworks."""
    W, H = 1200, 630
    im = dot_grid((W, H), bg=INK)
    d = ImageDraw.Draw(im)
    f_mark = font("JetBrainsMono-Medium.ttf", 46)
    f_lab = font("JetBrainsMono-Medium.ttf", 15)
    lx = (W - 4 * round(((H - 146 - 30 - 28) // 3) * 12 / 7) - 3 * 14) // 2
    logo = wordmark(20)
    im.alpha_composite(logo, (lx, 33))
    draw_tracked(d, (lx + logo.width + 12, 36), "· COMMUNITY TOOLS", f_lab, (185, 177, 160), 3.0)
    draw_tracked(d, (lx - 2, 64), "THE TOOL STORE", f_mark, (239, 230, 210), 9.0)
    cols, rows, gap, top, bottom = 4, 3, 14, 146, 30
    ch = (H - top - bottom - (rows - 1) * gap) // rows
    cw = round(ch * 12 / 7)
    left = (W - cols * cw - (cols - 1) * gap) // 2
    for k, art in enumerate(arts[:cols * rows]):
        r, c = divmod(k, cols)
        x, y = left + c * (cw + gap), top + r * (ch + gap)
        tile = Image.new("RGBA", (cw, ch), (16, 19, 42, 255))
        tile.alpha_composite(art.resize((cw, ch), Image.LANCZOS))
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=10, fill=255)
        im.paste(tile, (x, y), mask)
    return im.convert("RGB")


# --------------------------------------------------------------------------- registry
#
# The index's URLs may be relative: they resolve against the index's own
# location, a URL or a file (as PointillViz resolves them). An index on the web
# leads only to http(s) addresses; one on this computer may also name its own
# files, which is how a local test registry carries its bundles and READMEs.

def read_url(url: str, limit: int, local: bool) -> bytes | None:
    """At most `limit` bytes behind an http(s) URL (or a file: URL when the index
    is a local file), or None."""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https") and not (local and scheme == "file"):
        return None
    try:
        with urllib.request.urlopen(url, timeout=60) as fh:
            data = fh.read(limit + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= limit else None


def load_index(ref: str) -> tuple[dict, str]:
    """The index, and the URL its relative URLs resolve against."""
    base = ref if re.match(r"^https?://", ref, re.I) else Path(os.path.abspath(ref)).as_uri()
    data = read_url(base, MAX_INDEX, base.startswith("file:"))
    if data is None:
        sys.exit(f"No index at {ref}: build one with the registry's scripts/build_index.py, "
                 "or pass --index.")
    try:
        return json.loads(data), base
    except ValueError:
        sys.exit(f"{ref} is not JSON.")


def link(url, base: str) -> str:
    """A URL from the index, made absolute, for an href: http(s) only, or a file:
    URL for a local index. '' for anything else."""
    url = urllib.parse.urljoin(base, str(url or ""))
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    return url if url and (scheme in ("http", "https") or (scheme == "file" and base.startswith("file:"))) else ""


def tool_text(registry: str, tid: str, name: str, url, base: str, limit: int) -> str:
    """A tool's README.md or preview.svg: from the registry checkout's tools/<id>/
    when it has the file, else from the URL the index gives; '' if there is none."""
    path = os.path.join(registry, "tools", tid, name) if registry else ""
    if path and os.path.isfile(path):
        with open(path, "rb") as fh:
            data = fh.read(limit + 1)
        data = data if len(data) <= limit else None
    else:
        url = link(url, base) if url else ""
        data = read_url(url, limit, base.startswith("file:")) if url else None
    return data.decode("utf-8", "replace") if data else ""


def param_record(p: dict) -> dict:
    t = p.get("type", "")
    rec = {"name": p.get("name", ""), "label": smart(p.get("label") or p.get("name", "")), "type": t,
           "default": p.get("default"), "optional": bool(p.get("optional")), "help": smart(p.get("help", ""))}
    for k in ("min", "max", "step"):
        if p.get(k) is not None:
            rec[k] = p[k]
    if p.get("options"):
        rec["options"] = [{"label": o.get("label", o.get("value")), "value": o.get("value")}
                          if isinstance(o, dict) else {"label": str(o), "value": o} for o in p["options"]]
    # Display strings, in the words of CONTENT.md B7.
    if t in ("int", "float") and p.get("min") is not None and p.get("max") is not None:
        rec["type_text"] = f"{t}, {fmt_num(p['min'])}–{fmt_num(p['max'])}"
    elif t == "select" and rec.get("options"):
        rec["type_text"] = f"select, {len(rec['options'])} options"
    else:
        rec["type_text"] = t
    d = p.get("default")
    if d is None or d == "":
        rec["default_text"] = "optional" if rec["optional"] else "—"
    elif t == "select" and rec.get("options"):
        match = next((o for o in rec["options"] if str(o["value"]) == str(d)), None)
        rec["default_text"] = smart(str(match["label"])) if match else str(d)
    elif isinstance(d, (bool, int, float)):
        rec["default_text"] = fmt_num(d)
    else:
        rec["default_text"] = str(d)
    return rec


def needs_of(req: dict) -> list[str]:
    out = []
    if req.get("genes"):
        out.append("gene expression")
    if req.get("cell_types"):
        out.append("cell types")
    if req.get("categoricals"):
        out.append("a categorical column")
    sp = str(req.get("spatial") or "").lower()
    if sp == "2d":
        out.append("2D coordinates")
    elif sp == "3d":
        out.append("3D coordinates")
    if req.get("min_cells"):
        out.append(f"{fmt_int(req['min_cells'])}+{NBSP}cells")
    return out


def gate_records(report: dict) -> list[dict]:
    """The gate report the index carries with a release (none in an index built
    without reports), in the order the gates ran."""
    by_id = {g.get("id"): g for g in (report.get("gates") or []) if isinstance(g, dict)}
    ids = [g for g in GATE_ORDER if g in by_id] + [g for g in by_id if g not in GATE_ORDER]
    return [{"id": gid, "required": bool(by_id[gid].get("required", gid != "imports")),
             "status": by_id[gid].get("status") or "skip",
             "message": strip_email(by_id[gid].get("message") or "")} for gid in ids]


def build(index_ref: str, registry: str, out_root: str) -> dict:
    index, base = load_index(index_ref)
    media = os.path.join(out_root, "assets", "media", "tools")
    social = os.path.join(out_root, "assets", "media", "social")
    tools, arts_for_gallery, backdrops, changed = [], [], [], 0
    for entry in index.get("tools") or []:
        tid = str(entry.get("id") or "") if isinstance(entry, dict) else ""
        if not SAFE_ID.match(tid):
            continue
        manifest = entry.get("manifest") or {}
        report = entry.get("report") or {}
        bundle = entry.get("bundle") or {}
        readme = tool_text(registry, tid, "README.md", entry.get("readme_url"), base, MAX_README)
        svg = tool_text(registry, tid, "preview.svg", entry.get("preview_url"), base, MAX_SVG)
        name = smart(entry.get("name") or tid)
        language = entry.get("language") or "python"
        gpu = entry.get("gpu") if entry.get("gpu") in GPU_TEXT else None

        # Artwork: the tool's own preview.svg, else the local store's constellation.
        generated = not svg
        art_svg, dropped = strip_backdrop(svg) if svg else (constellation_svg(tid), False)
        if dropped:
            backdrops.append(tid)
        alt = svg_label(svg) if svg else ""
        im1 = rasterize(art_svg, ART_W, ART_H)
        im2 = rasterize(art_svg, ART_W * 2, ART_H * 2)
        b1, b2 = webp_bytes(im1), webp_bytes(im2)
        changed += write_if_changed(os.path.join(media, f"{tid}.webp"), b1)
        changed += write_if_changed(os.path.join(media, f"{tid}@2x.webp"), b2)
        sbuf = io.BytesIO()
        social_tool(im2, name).save(sbuf, "JPEG", quality=86, optimize=True, progressive=True)
        changed += write_if_changed(os.path.join(social, f"{tid}.jpg"), sbuf.getvalue())
        arts_for_gallery.append((tid, generated, im2))

        outputs = list(entry.get("outputs") or [])
        optional_outputs = list(entry.get("optional_outputs") or [])
        req = entry.get("requires") or {}
        published = str(entry.get("published") or "")[:10]
        tools.append({
            "id": tid,
            "name": name,
            "version": str(entry.get("version") or ""),
            "author": strip_email(entry.get("author", "")),
            "description": smart(entry.get("description", "")),
            "readme_html": markdown_html(readme, name) if readme.strip() else "",
            "citation": smart((entry.get("citation") or "").strip()),
            "tags": list(entry.get("tags") or []),
            "icon": entry.get("icon") or "extension",
            "language": language,
            "language_label": LANGUAGES.get(language, language),
            "gpu": gpu,
            "gpu_label": GPU_TEXT.get(gpu, ""),
            "parameters": [param_record(p) for p in (manifest.get("params") or []) if isinstance(p, dict)],
            "sweep": manifest.get("sweep") or None,
            "outputs": outputs,
            "optional_outputs": optional_outputs,
            "output_help": {o: OUTPUT_HELP.get(o, o) for o in outputs + optional_outputs},
            "requires": req,
            "needs": needs_of(req),
            "license": entry.get("license") or "",
            "bundle_url": link(bundle.get("url"), base),
            "bundle_size": fmt_bytes(int(bundle.get("size") or 0)),
            "source_url": link(entry.get("source_url"), base),
            "published": published,
            "published_date": fmt_date(published),
            "gates": gate_records(report),
            "risks": [{"kind": r, "label": RISK_SHORT.get(r, r), "text": RISK_TEXT.get(r, r)}
                      for r in (report.get("risks") or [])],
            "art": {"src": f"assets/media/tools/{tid}.webp?v={short_hash(b1)}",
                    "src2x": f"assets/media/tools/{tid}@2x.webp?v={short_hash(b2)}",
                    "width": ART_W, "height": ART_H, "alt": alt, "generated": generated},
            "social": f"assets/media/social/{tid}.jpg",
            "url": f"tools/{tid}/",
        })

    # Newest first, as the store opens: the release date, then name (stable
    # sorts, last key first). store.js orders the same way.
    tools.sort(key=lambda t: t["name"].lower())
    tools.sort(key=lambda t: t["published"], reverse=True)
    keep = {t["id"] for t in tools}
    # Announced, not published: a name and one line (the registry's placeholders.json).
    placeholders = [{"id": p["id"], "name": smart(str(p.get("name") or p["id"])),
                     "description": smart(str(p.get("description") or "")), "url": f"tools/{p['id']}/"}
                    for p in index.get("placeholders") or []
                    if isinstance(p, dict) and SAFE_ID.match(str(p.get("id") or "")) and p["id"] not in keep]
    counts = {}
    for t in tools:
        for tag in t["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    tags = [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]

    # The gallery's filters: tags that two or more tools share but not every tool
    # (a tag on every tool filters nothing; a tag on one is a search), then what
    # the tools draw. Outputs that every tool returns are not repeated on cards.
    n = len(tools)
    outs = [set(t["outputs"] + t["optional_outputs"]) for t in tools]
    filters = {
        "tags": [r for r in tags if 2 <= r["count"] < n],
        "outputs": [{"out": o, "count": c, "help": OUTPUT_HELP.get(o, o)}
                    for o in OUTPUT_FILTERS for c in [sum(o in s for s in outs)] if 0 < c < n],
    }
    common_outputs = sorted(set.intersection(*outs)) if outs else []

    # The tools' own artwork first, then the stand-ins, each A-Z.
    names = {t["id"]: t["name"].lower() for t in tools}
    gallery_order = sorted(arts_for_gallery, key=lambda p: (p[1], names[p[0]]))
    gbuf = io.BytesIO()
    social_gallery([im for _, _, im in gallery_order], len(tools)).save(gbuf, "JPEG", quality=86, optimize=True, progressive=True)
    changed += write_if_changed(os.path.join(social, "store.jpg"), gbuf.getvalue())

    # Remove artwork of tools that left the registry (a placeholder has none).
    for folder, pat in ((media, re.compile(r"^(.+?)(@2x)?\.webp$")), (social, re.compile(r"^(.+?)\.jpg$"))):
        for fn in os.listdir(folder) if os.path.isdir(folder) else []:
            m = pat.match(fn)
            if m and m.group(1) not in keep and m.group(1) != "store":
                os.remove(os.path.join(folder, fn))
                changed += 1

    data = {
        "schema": 2,
        "source": "the PointillViz tool registry's index.json, latest version of each tool",
        "count": len(tools),
        "gate_order": GATE_ORDER,
        "tags": tags,
        "filters": filters,
        "card_hidden_outputs": common_outputs,
        "tools": tools,
        "placeholders": placeholders,
    }
    raw = (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    changed += write_if_changed(os.path.join(out_root, "data", "tools.json"), raw)

    # The gallery needs only what a card shows and what search reads: no README,
    # parameters or gate messages.
    card_keys = ("id", "name", "version", "author", "description", "tags", "outputs", "optional_outputs",
                 "output_help", "published", "published_date", "language", "language_label", "gpu",
                 "gpu_label", "risks", "art", "url")
    index = dict(data, tools=[{k: t[k] for k in card_keys} for t in tools])
    del index["gate_order"]
    slim = (json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    changed += write_if_changed(os.path.join(out_root, "data", "tools-index.json"), slim)
    return {"tools": len(tools), "placeholders": len(placeholders), "files_changed": changed,
            "json_bytes": len(raw), "index_bytes": len(slim), "backdrops": backdrops}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", default=DEFAULT_INDEX,
                    help="the registry's index.json, a path or an http(s) URL "
                         "(default: the public registry's)")
    ap.add_argument("--registry", default="",
                    help="a registry checkout: README.md and preview.svg are read from its "
                         "tools/<id>/, else from the index's URLs (the default)")
    ap.add_argument("--out", default=STORE, help="the store site folder (default: this repository)")
    a = ap.parse_args()
    index = a.index if re.match(r"^https?://", a.index, re.I) else os.path.abspath(a.index)
    res = build(index, os.path.abspath(a.registry) if a.registry else "", os.path.abspath(a.out))
    print(f"{res['tools']} tools, {res['placeholders']} coming soon · tools.json {res['json_bytes'] / 1024:.1f} kB · "
          f"tools-index.json {res['index_bytes'] / 1024:.1f} kB · {res['files_changed']} files written")
    if res["backdrops"]:
        print("backdrop dropped from the artwork of: " + ", ".join(res["backdrops"]))


if __name__ == "__main__":
    main()
