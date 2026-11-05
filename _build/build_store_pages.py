#!/usr/bin/env python3
"""Generate the Tool Store's static pages from store/data/tools.json.

    python3 -I _build/build_store_pages.py             (any Python 3.8+; no packages)
    python3 -I _build/build_store_pages.py --out DIR   (a test copy of the site)

Run _build/build_store_data.py first. This script writes:

  store/tools/<id>/index.html   one shareable page per tool, and a Coming soon
                                page (its name and one line) per placeholder;
                                it removes the folders of tools no longer listed
  store/index.html              only the regions between build markers:
                                  <!-- store:cards -->    the card grid, Newest first,
                                                          then the Coming soon cards
                                  <!-- store:filters -->  the filters panel's options:
                                                          shared tags, then outputs
                                and the tool count in its og:description
  store/404.html                only its logo regions (<!-- store:logo-* -->): the
                                logos as data URIs, since a 404 at any depth cannot
                                fetch them by a relative path before its <base> is set
  store/sitemap.xml, store/robots.txt

The rest of index.html, publish/index.html and 404.html are written by hand.
The pre-rendered grid is what a reader without JavaScript (and a crawler) sees;
assets/store.js rebuilds cards from data/tools-index.json for search, filters and
sorting, with the same markup (cardHTML there mirrors card_html here).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys

# realpath: a link to this file elsewhere still finds the site.
HERE = os.path.dirname(os.path.realpath(__file__))
STORE = os.path.dirname(HERE)                   # the store site: this repository
SITE_URL = "https://store.pointillviz.com/"
DOCS_TOOLS_URL = "https://docs.pointillviz.com/tool-store/"
# Until PointillViz is announced, search engines are asked not to list the store:
# every page carries noindex (the tool pages from ROBOTS, index.html and
# publish/index.html by hand) and robots.txt names no sitemap. Shared links and
# their previews work as usual. At the announcement: PRELAUNCH = False, rebuild,
# and take the tag out of those two hand-written pages.
PRELAUNCH = True
ROBOTS = '<meta name="robots" content="noindex">\n' if PRELAUNCH else ""

GATE_DONE = {"pass": "pass", "fail": "fail", "skip": "skipped", "warn": "flagged"}
GATE_STATE = {"pass": "pass", "fail": "fail", "skip": "pending", "warn": "advisory"}
# Badge and note texts, in the words of brief/CONTENT.md (B5, B7).
GATES_NOTE = "Passing the gates is a statement about the gates, not about whether the code is safe to run."
GPU_FACT = {"optional": "Optional: you choose when you run it",
            "required": "Meant for a GPU; also runs on the CPU"}
HOWTO_LABEL = "How to install and run a tool"
STORE_ART_ALT = "The Tool Store wordmark above the artwork of its community tools."
OUTPUT_GLYPHS = frozenset({"cells", "labels", "vectors", "matrix", "series", "chord", "images", "files", "table", "summary"})


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def icon(root: str, name: str, cls: str = "pv-icon") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} aria-hidden="true"><use href="{root}assets/pv/icons.svg#{name}"/></svg>'


def first_sentence(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    m = re.match(r"^(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text[:limit].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------- chrome
# The shared chrome of WEB/shared/CHROME.md, store variant.

# CHROME.md §1: above 1440 x 900 the chrome is drawn --k times larger (at most
# 1.6), set before the first paint so the bar never jumps (pv.js keeps it on resize).
SCALE_SCRIPT = ("<script>(function(d){try{var w=d.clientWidth||innerWidth;d.style.setProperty('--k',"
                "Math.min(Math.max(Math.min(w/1440,innerHeight/900),1),1.6).toFixed(4))}catch(e){}})"
                "(document.documentElement)</script>")
# CHROME.md §5: the publication line, the same on the three sites (brief/CONTENT.md A11).
PUB_LINE = ('<p class="pv-footer__pub">Preprint: Gargoori Motlagh&nbsp;A. <em>et&nbsp;al.</em>, bioRxiv · '
            '<a href="#" data-placeholder="paper">Coming soon</a></p>')

MENU_DOTS = ('<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><circle cx="4" cy="4" r="1.6"/>'
             '<circle cx="10" cy="4" r="1.6"/><circle cx="16" cy="4" r="1.6"/><circle cx="4" cy="10" r="1.6"/>'
             '<circle cx="10" cy="10" r="1.6"/><circle cx="16" cy="10" r="1.6"/><circle cx="4" cy="16" r="1.6"/>'
             '<circle cx="10" cy="16" r="1.6"/><circle cx="16" cy="16" r="1.6"/></svg>')


def head(root: str, title: str, desc: str, og_title: str, og_desc: str, url: str, image: str,
         image_alt: str, scripts: str = "", early: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{SCALE_SCRIPT}
<meta name="theme-color" content="#06070D">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{ROBOTS}<link rel="canonical" href="{esc(url)}">
<meta property="og:site_name" content="PointillViz">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(og_title)}">
<meta property="og:description" content="{esc(og_desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(image_alt)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}assets/pv/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,400&amp;family=JetBrains+Mono:wght@400..600&amp;display=swap">
<link rel="stylesheet" href="{root}assets/pv/pv.css">
<link rel="stylesheet" href="{root}assets/store.css">
<script src="{root}assets/pv/pv.js" defer></script>{scripts}
<script src="{root}assets/store.js" defer onerror="document.documentElement.classList.remove('st-js')"></script>
<script>document.documentElement.classList.add('st-js'){early}</script>
<noscript><style>.pv-topbar__menu {{ display: none !important; }}</style></noscript>
</head>"""


def nav_link(root: str, current: str) -> tuple[str, str]:
    """The Tool Store's own link in the top bar, the drawer and the footer. It is
    the current page on the gallery (aria-current="page"), and the current site
    on a page within it (aria-current="true")."""
    return root or "./", f' aria-current="{current}"'


def topbar(root: str, current: str = "true") -> str:
    href, cur = nav_link(root, current)
    return f"""<a class="pv-skip" href="#main">Skip to content</a>
<header class="pv-topbar">
  <div class="pv-topbar__inner">
    <a class="pv-topbar__brand" href="https://pointillviz.com/" translate="no">
      <img src="{root}assets/pv/logo.svg" width="169" height="20" alt="PointillViz">
    </a>
    <nav class="pv-topbar__nav" aria-label="Main">
      <ul>
        <li><a href="https://pointillviz.com/">Overview</a></li>
        <li><a href="https://docs.pointillviz.com/">Docs</a></li>
        <li><a href="{href}"{cur}>Tool Store</a></li>
        <li><a href="#" data-placeholder="paper">Paper</a></li>
      </ul>
    </nav>
    <div class="pv-topbar__end">
      <button class="pv-topbar__menu" type="button" aria-haspopup="dialog" aria-expanded="false" aria-controls="pv-drawer" data-pv-drawer-open="pv-drawer">
        {MENU_DOTS}
        <span class="pv-sr-only">Menu</span>
      </button>
    </div>
  </div>
  <noscript>
    <nav class="pv-nojs-nav" aria-label="Main">
      <a href="https://pointillviz.com/">Overview</a><a href="https://docs.pointillviz.com/">Docs</a><a href="{href}"{cur}>Tool Store</a>
    </nav>
  </noscript>
</header>
<dialog class="pv-drawer" id="pv-drawer" aria-label="Menu">
  <div class="pv-drawer__panel">
    <div class="pv-drawer__head">
      <img src="{root}assets/pv/logo.svg" width="152" height="18" alt="PointillViz" translate="no">
      <button class="pv-btn pv-btn--ghost pv-btn--icon" type="button" data-pv-drawer-close aria-label="Close menu" autofocus>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M5 5l10 10M15 5 5 15"/></svg>
      </button>
    </div>
    <nav aria-label="Main">
      <ul class="pv-drawer__nav">
        <li><a href="https://pointillviz.com/"><span class="pv-drawer__name">Overview</span><span class="pv-drawer__host">pointillviz.com</span></a></li>
        <li><a href="https://docs.pointillviz.com/"><span class="pv-drawer__name">Docs</span><span class="pv-drawer__host">docs.pointillviz.com</span></a></li>
        <li><a href="{href}"{cur}><span class="pv-drawer__name">Tool Store</span><span class="pv-drawer__host">store.pointillviz.com</span></a></li>
        <li><a href="#" data-placeholder="paper"><span class="pv-drawer__name">Paper</span><span class="pv-drawer__host">bioRxiv</span></a></li>
      </ul>
    </nav>
    <div class="pv-drawer__foot">
      <p>© 2026 PointillViz</p>
    </div>
  </div>
</dialog>"""


def footer(root: str, current: str = "true") -> str:
    href, cur = nav_link(root, current)
    return f"""<footer class="pv-footer">
  <div class="pv-footer__inner">
    <a class="pv-footer__brand" href="https://pointillviz.com/" translate="no"><img src="{root}assets/pv/logo-mark.svg" width="28" height="28" alt="">PointillViz</a>
    <nav class="pv-footer__sites" aria-label="PointillViz sites">
      <ul>
        <li><a href="https://pointillviz.com/"><span class="pv-footer__site">Overview</span><span class="pv-footer__host">pointillviz.com</span></a></li>
        <li><a href="https://docs.pointillviz.com/"><span class="pv-footer__site">Docs</span><span class="pv-footer__host">docs.pointillviz.com</span></a></li>
        <li><a href="{href}"{cur}><span class="pv-footer__site">Tool Store</span><span class="pv-footer__host">store.pointillviz.com</span></a></li>
      </ul>
    </nav>
    {PUB_LINE}
    <p class="pv-footer__copy">© 2026 PointillViz</p>
  </div>
</footer>"""


# --------------------------------------------------------------------------- pieces

def art_img(t: dict, root: str, sizes: str, eager: bool = False, alt: str = "") -> str:
    a = t["art"]
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return (f'<img src="{root}{esc(a["src"])}" srcset="{root}{esc(a["src"])} {a["width"]}w, '
            f'{root}{esc(a["src2x"])} {a["width"] * 2}w" sizes="{sizes}" width="{a["width"]}" '
            f'height="{a["height"]}" alt="{esc(alt)}" {load} decoding="async">')


CARD_SIZES = "(max-width: 559.98px) 92vw, (max-width: 819.98px) 46vw, (max-width: 1099.98px) 31vw, 23vw"


def card_html(t: dict, root: str = "", eager: bool = False, heading: str = "h3") -> str:
    """One plate: the artwork and the name. The description is in the markup for
    search, for screen readers and for a reader without JavaScript; with JavaScript
    the hero says it while the plate is under the pointer (store.css §4, store.js).
    Everything else about a tool is on its page."""
    all_outs = t["outputs"] + t["optional_outputs"]
    data = (f'data-id="{esc(t["id"])}" data-name="{esc(t["name"])}" data-author="{esc(t["author"])}" '
            f'data-tags="{esc("|".join(t["tags"]))}" data-outputs="{esc("|".join(all_outs))}" '
            f'data-published="{esc(t["published"])}" data-version="{esc(t["version"])}"')
    return f"""<li class="st-cell" {data}>
<a class="st-card" href="{root}{esc(t['url'])}">
  <div class="st-card__art">{art_img(t, root, CARD_SIZES, eager)}</div>
  <{heading} class="st-card__name">{esc(t['name'])}</{heading}>
  <p class="st-card__desc">{esc(t['description'])}</p>
</a>
</li>"""


def soon_card_html(p: dict) -> str:
    """A tool that is announced, not published: its name and one line, on an empty
    plate. Listed after the tools; search finds it."""
    return f"""<li class="st-cell st-cell--soon" data-id="{esc(p['id'])}" data-name="{esc(p['name'])}" data-soon>
<div class="st-card st-card--soon">
  <div class="st-card__art st-card__art--soon"><span class="pv-soon">Coming soon</span></div>
  <h3 class="st-card__name">{esc(p['name'])}</h3>
  <p class="st-card__line">{esc(p['description'])}</p>
</div>
</li>"""


def filter_option(attr: str, value: str, label: str, count: int, title: str = "") -> str:
    tip = f' title="{esc(title)}"' if title else ""
    return (f'<button class="st-opt" type="button" aria-pressed="false" {attr}="{esc(value)}"{tip}>'
            f'<span class="st-opt__label">{esc(label)}</span><span class="st-opt__n">{count}</span></button>')


def filters_html(data: dict) -> str:
    """The panel's two legends: the tags two or more tools share, and what the tools
    draw. A tag only one tool has is found by search instead."""
    f = data.get("filters") or {"tags": [], "outputs": []}
    tags = "\n".join(filter_option("data-tag", r["tag"], r["tag"], r["count"]) for r in f["tags"])
    outs = "\n".join(filter_option("data-out", r["out"], r["out"], r["count"], r["help"].capitalize()) for r in f["outputs"])
    return (f'<div class="st-filters__group st-filters__group--tags" role="group" aria-labelledby="f-tags">\n'
            f'<p class="st-filters__h" id="f-tags">Tags</p>\n<div class="st-filters__opts" id="tag-list">\n{tags}\n</div>\n</div>\n'
            f'<div class="st-filters__group" role="group" aria-labelledby="f-outs">\n'
            f'<p class="st-filters__h" id="f-outs">Outputs</p>\n<div class="st-filters__opts" id="out-list">\n{outs}\n</div>\n</div>')


# --------------------------------------------------------------------------- the README, taken apart
# readme_html is sanitized by build_store_data.py. It is split here, never rewritten:
# its first sentence may be lifted out, and the sections that repeat a part of the
# page move next to that part, folded, so that nothing is shown twice by default
# and nothing is lost. A README that does not follow this shape is left as it is.

QUESTION = re.compile(
    r"^\s*<p>\s*(?:this tool\s+)?answers the question\s*:?\s*"
    r"(?:<(?:strong|b)>(?P<q1>.+?)</(?:strong|b)>|(?P<q2>[^<]+?))\s*</p>\s*", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
PARAMS_HEADS = {"parameters", "parameter", "options", "settings", "the parameters"}
OUTPUTS_HEADS = {"what you get", "outputs", "output", "results", "what it returns", "what it draws"}
CITE_HEADS = {"citation", "citations", "references", "reference", "how to cite", "cite", "citing"}


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", fragment))).strip()


def words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", plain(text).lower()))


def overlap(a: str, b: str) -> float:
    """How much of two texts is the same words (Jaccard)."""
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def split_readme(t: dict) -> dict:
    """The README in parts: the lifted question, the reading view, and the sections
    that belong with the parameters, the outputs and the references."""
    src = t["readme_html"] or ""
    question = ""
    m = QUESTION.match(src)
    if m:
        question = (m.group("q1") or m.group("q2") or "").strip()
        src = src[m.end():]
    # Its sections are its largest headings, at whichever level the author chose.
    level = "h3" if re.search(r"<h3\b", src, re.I) else "h4"
    parts = re.split(rf"<{level}\b[^>]*>(.*?)</{level}>", src, flags=re.I | re.S)
    body, params, outs, cite = [parts[0]], [], [], []
    for head, text in zip(parts[1::2], parts[2::2]):
        key = plain(head).lower().rstrip(":. ")
        if key in PARAMS_HEADS:
            params.append(text)
        elif key in OUTPUTS_HEADS:
            outs.append(text)
        elif key in CITE_HEADS:
            cite.append(text)
        else:
            body.append(f"<{level}>{head}</{level}>{text}")
    # The question opens the reading view, unless it says what the description
    # above it already says.
    if question and overlap(question, t["description"]) >= 0.8:
        question = ""
    return {"question": question, "body": "".join(body).strip(), "params": "".join(params).strip(),
            "outputs": "".join(outs).strip(), "cite": "".join(cite).strip()}


def linked(text: str) -> str:
    """Escaped text, its http(s) addresses made links (a citation's DOI)."""
    out, pos = [], 0
    for m in re.finditer(r"https?://[^\s<>\"']+[^\s<>\"'.,;)]", text):
        out.append(esc(text[pos:m.start()]))
        out.append(f'<a class="pv-link" href="{esc(m.group(0))}" rel="noopener noreferrer nofollow">{esc(m.group(0))}</a>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def references_html(t: dict, cite: str) -> str:
    """One block. The manifest's citation shows too only if it says something the
    README's own Citation section does not."""
    rows = []
    if cite:
        rows.append(cite)
    manifest = t.get("citation") or ""
    if manifest:
        mine = words(manifest)
        known = len(mine & words(cite)) / len(mine) if mine else 0
        if known < 0.7:
            rows.append(f"<p>{linked(manifest)}</p>")
    if not rows:
        return ""
    return f'<div class="st-refs"><h3 class="st-refs__h">References</h3><div class="st-md">{"".join(rows)}</div></div>'


def fold_html(label: str, inner: str) -> str:
    """A README section that repeats what stands above it: there, one click away."""
    if not inner:
        return ""
    return (f'<details class="st-fold"><summary class="st-fold__sum">{esc(label)}'
            f'<svg class="st-fold__chev" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg></summary>'
            f'<div class="st-md st-fold__body">{inner}</div></details>')


# --------------------------------------------------------------------------- tool page

PARAM_KIND = {"categorical_field": "a categorical column", "continuous_field": "a continuous column",
              "category_value": "one of its categories", "gene": "a gene", "genes": "genes", "bool": "on or off",
              "int": "whole number", "float": "number"}


def param_range(p: dict) -> str:
    """A numeric parameter's range, drawn: its ends, and a lit point at the default."""
    lo, hi, d = p.get("min"), p.get("max"), p.get("default")
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)) or hi <= lo:
        return ""
    m = re.match(r"^\w+,\s*(.+)–(.+)$", p.get("type_text") or "")
    lo_text, hi_text = (m.group(1), m.group(2)) if m else (f"{lo:g}", f"{hi:g}")
    point = ""
    if isinstance(d, (int, float)) and not isinstance(d, bool):
        x = max(0.0, min(1.0, (d - lo) / (hi - lo)))
        point = f'<i class="st-range__pt" style="--x:{x:.4f}"></i>'
    return (f'<span class="st-range" aria-hidden="true"><span class="st-range__end">{esc(lo_text)}</span>'
            f'<span class="st-range__track">{point}</span><span class="st-range__end">{esc(hi_text)}</span></span>'
            f'<span class="pv-sr-only">Range {esc(lo_text)} to {esc(hi_text)}. </span>')


def param_rows(t: dict) -> str:
    if not t["parameters"]:
        return '<p class="st-empty-line">This tool takes no parameters.</p>'
    rows = []
    for p in t["parameters"]:
        kind = PARAM_KIND.get(p["type"], p.get("type_text") or p["type"])
        default = p["default_text"]
        has_default = default != "—"
        if not has_default:
            default = "required"
        # On a phone there is no column head to say what this value is.
        said = '<span class="st-p__dl">Default: </span>' if default not in ("required", "optional") else ""
        sweep = (' <span class="st-p__sweep" title="This parameter can be swept: one run per value, '
                 'with a slider between the results.">can be swept</span>') if t.get("sweep") == p["name"] else ""
        opts = p.get("options") or []
        # The default stands on its own beside the name: here, the other choices.
        others = [o for o in opts if o.get("value") != p.get("default")]
        lead = "Or" if has_default else "One of"
        extra = f'<p class="st-p__opts">{lead}: {esc(", ".join(str(o.get("label")) for o in others))}</p>' if others else ""
        ranged = param_range(p)
        kind_html = "" if opts or ranged else f'<span class="st-p__kind">{esc(kind)}</span>'
        rows.append(f"""<tr role="row" class="st-p">
  <th scope="row" role="rowheader" class="st-p__head"><span class="st-p__label">{esc(p['label'])}</span> <code class="st-p__name" translate="no">{esc(p['name'])}</code>{sweep}</th>
  <td role="cell" class="st-p__val"><span class="st-p__default">{said}{esc(default)}</span>{ranged}{kind_html}</td>
  <td role="cell" class="st-p__help"><span class="st-p__text">{esc(p['help'])}</span>{extra}</td>
</tr>""")
    return f"""<table class="st-ptable" role="table" aria-labelledby="parameters-h">
<thead role="rowgroup"><tr role="row" class="st-p st-p--names"><th scope="col" role="columnheader" class="st-p__head">Parameter</th><th scope="col" role="columnheader" class="st-p__val">Default</th><th scope="col" role="columnheader" class="pv-sr-only">What it does</th></tr></thead>
<tbody role="rowgroup">
{chr(10).join(rows)}
</tbody>
</table>"""


def glyph(root: str, kind: str, cls: str = "st-glyph") -> str:
    """What an output is, drawn (assets/outputs.svg). A kind the sprite does not
    know gets a plain point: publishing is automatic, so a new kind may appear."""
    name = kind if kind in OUTPUT_GLYPHS else "any"
    return f'<svg class="{cls}" aria-hidden="true"><use href="{root}assets/outputs.svg#o-{name}"/></svg>'


def outputs_html(t: dict, root: str) -> str:
    items = []
    for o in t["outputs"] + t["optional_outputs"]:
        opt = '<span class="st-out__opt">optional</span>' if o in t["optional_outputs"] else ""
        what = t["output_help"].get(o, "")
        what = what[:1].upper() + what[1:] if what else ""
        items.append(f'<li class="st-out">{glyph(root, o)}<code class="st-out__name" translate="no">{esc(o)}</code>'
                     f'<span class="st-out__what">{esc(what)}{opt}</span></li>')
    if not items:
        return '<p class="st-empty-line">This tool lists no outputs.</p>'
    return f'<ul class="st-outs">{"".join(items)}</ul>'


def gates_html(t: dict) -> str:
    """The strip of points, then what each gate saw. The strip has no words of its
    own: the names are in the log right below it."""
    if not t["gates"]:
        return '<p class="st-empty-line">No gate report is on file for this version.</p>'
    strip, log = [], []
    for g in t["gates"]:
        state, word = GATE_STATE.get(g["status"], "pending"), GATE_DONE.get(g["status"], g["status"])
        # An advisory gate (imports) never blocks: drawn as a ring (store.css §7).
        adv, adv_attr = ('', '') if g["required"] else (' <span class="st-gate__adv">advisory</span>', ' data-adv')
        strip.append(f'<li class="st-strip__dot" data-state="{state}"{adv_attr} title="{esc(g["id"])}: {esc(word)}"></li>')
        log.append(f"""<li class="st-gate" data-state="{state}"{adv_attr}>
  <p class="st-gate__head"><code class="st-gate__name" translate="no">{esc(g['id'])}</code>{adv}<span class="st-gate__word">{esc(word)}</span></p>
  <p class="st-gate__msg">{esc(g['message'])}</p>
</li>""")
    passed = sum(1 for g in t["gates"] if g["status"] == "pass")
    return f"""<ol class="st-strip" aria-hidden="true">{''.join(strip)}</ol>
<p class="st-tests__lead">{passed} of {len(t['gates'])} gates passed when this version was released. They ran in this order:</p>
<ol class="st-gates">
{chr(10).join(log)}
</ol>
<p class="st-tests__note">{esc(GATES_NOTE)}</p>"""


def gates_state(t: dict) -> str:
    """The point on the button: all passed, something flagged, or a gate failed."""
    if not t["gates"]:
        return "none"
    states = {g["status"] for g in t["gates"]}
    return "fail" if "fail" in states else "advisory" if states - {"pass"} else "pass"


def facts_html(t: dict) -> str:
    def fact(k, v):
        return f'<div class="st-facts__row"><dt>{esc(k)}</dt><dd>{v}</dd></div>'
    gpu = GPU_FACT.get(t.get("gpu"), t["gpu_label"]) if t.get("gpu") else "Not used"
    rows = [
        fact("Author", esc(t["author"] or "Not stated")),
        fact("Version", f'<span class="st-facts__num" translate="no">{esc(t["version"])}</span>'),
        fact("Published", f'<time datetime="{esc(t["published"])}">{esc(t["published_date"])}</time>'),
        fact("Licence", esc(t["license"] or "Not stated")),
        fact("Language", esc(t["language_label"])),
        fact("GPU", esc(gpu)),
        fact("Needs", "<br>".join(esc(x) for x in t["needs"]) if t["needs"] else "Nothing in particular"),
    ]
    return f'<dl class="st-facts__list">{"".join(rows)}</dl>'


def risks_html(t: dict) -> str:
    """What the advisory imports gate disclosed: beside Download, in words."""
    if not t["risks"]:
        return ""
    items = "".join(f'<li>This tool {esc(r["text"])}.</li>' for r in t["risks"])
    return (f'<ul class="st-risks" aria-label="Disclosed by the advisory imports gate">{items}</ul>')


def related(t: dict, tools: list[dict], n: int = 4) -> list[dict]:
    mine = set(t["tags"])
    scored = []
    for o in tools:
        if o["id"] == t["id"]:
            continue
        shared = len(mine & set(o["tags"]))
        scored.append((-shared, o["name"].lower(), o))
    scored.sort(key=lambda s: s[:2])
    return [s[2] for s in scored[:n]]


VIEWS = [("readme", "Readme"), ("parameters", "Parameters"), ("outputs", "Outputs")]
# Before the first paint: the view the address asks for, so that a panel never flashes.
EARLY_VIEW = (";(function(d,m){d.setAttribute('data-view',m?m[1]:'readme')})"
              "(document.documentElement,/^#(readme|parameters|outputs)$/.exec(location.hash))")
CLOSE_X = ('<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
           'aria-hidden="true"><path d="M5 5l10 10M15 5 5 15"/></svg>')


def keep_together(name: str) -> str:
    """A hyphenated word in a title stays whole while it fits ("Cross-L"), without
    changing the title's text."""
    return re.sub(r"\S+-\S+", lambda m: f'<span class="st-keep">{m.group(0)}</span>', esc(name))


def tool_page(t: dict, tools: list[dict]) -> str:
    root = "../../"
    url = f"{SITE_URL}tools/{t['id']}/"
    desc = f"{first_sentence(t['description'])} A PointillViz community tool, version {t['version']}."
    alt = t["art"]["alt"] or f"Card artwork of {t['name']}."
    plate_tip = f' title="{esc(t["art"]["alt"])}"' if t["art"]["alt"] else ""
    # The title keeps its size for every name of today (35 characters at most); a longer
    # one comes down a step, so that Download stays in the first screen.
    name_len = ' data-len="xlong"' if len(t["name"]) > 64 else ' data-len="long"' if len(t["name"]) > 40 else ""
    install_words = ("In PointillViz: <b>Tools → Store → Install</b>, or <b>Install from file</b> with the download."
                     if t["bundle_url"] else "In PointillViz: <b>Tools → Store → Install</b>.")
    parts = split_readme(t)
    question = f'<p class="st-question">{parts["question"]}</p>' if parts["question"] else ""
    readme = parts["body"] or ('<p class="st-empty-line">This tool shipped no README.</p>' if not question else "")
    more = "\n".join(card_html(o, root, heading="h3") for o in related(t, tools))
    views = "\n".join(f'          <a class="st-tab" href="#{sid}" data-view-link="{sid}">{label}</a>' for sid, label in VIEWS)
    # The bundle is the release's own file; the source is the tool's folder in
    # the public registry (both from the index).
    download = (f'<a class="pv-btn pv-btn--primary pv-btn--lg st-get__btn" href="{esc(t["bundle_url"])}" download>'
                f'{icon(root, "i-download", "")}<span class="pv-btn__stack"><span>Download</span> '
                f'<span class="pv-btn__sub">.pvtool · {esc(t["bundle_size"])}</span></span></a>') if t["bundle_url"] else ""
    bar_download = (f'<a class="pv-btn pv-btn--primary st-bar__dl" href="{esc(t["bundle_url"])}" download tabindex="-1">'
                    f'{icon(root, "i-download", "")}<span>Download</span></a>') if t["bundle_url"] else ""
    source = (f'<p class="st-facts__src"><a class="pv-link" href="{esc(t["source_url"])}">Source in the public registry'
              f'{icon(root, "i-external")}</a></p>') if t["source_url"] else ""
    # <Tool> · The Tool Store · PointillViz, as the store's own pages.
    title = f"{t['name']} · The Tool Store · PointillViz"
    field_script = f'\n<script src="{root}assets/field.js" defer></script>'
    return f"""{head(root, title, desc, title, t['description'], url,
                     f"{SITE_URL}{t['social']}", alt, field_script, EARLY_VIEW)}
<body class="st-page st-page--tool">
{topbar(root)}
<main id="main" class="st-tool">
  <header class="st-top">
    <div class="st-wrap st-top__in">
      <div class="st-top__words">
        <a class="st-back" href="{root}">{icon(root, "i-arrow-left")}All tools</a>
        <h1 class="st-title st-top__name"{name_len}>{keep_together(t['name'])}</h1>
        <p class="st-top__desc">{esc(t['description'])}</p>
        <div class="st-get">
          {download}
          <p class="st-get__how"><span class="st-get__steps">{install_words} </span><a class="pv-link" href="{DOCS_TOOLS_URL}">{HOWTO_LABEL}</a></p>
          {risks_html(t)}
          <p class="st-get__note">This runs as you: a tool is arbitrary code, with your privileges. <a class="pv-link" href="{root}#safety">Safety note</a></p>
        </div>
      </div>
      <figure class="st-top__art">
        <div class="st-artplate"{plate_tip}>{art_img(t, root, "(max-width: 1023.98px) 92vw, 58vw", True, alt)}</div>
      </figure>
    </div>
  </header>
  <div class="st-views">
    <div class="st-bar" id="view-bar">
      <div class="st-wrap st-bar__in">
        <p class="st-bar__name" aria-hidden="true"><img class="st-bar__thumb" src="{root}{esc(t['art']['src'])}" width="{t['art']['width']}" height="{t['art']['height']}" alt="" loading="lazy" decoding="async"><span>{esc(t['name'])}</span></p>
        <nav class="st-tabs" aria-label="About this tool" id="view-tabs">
{views}
        </nav>
        <button class="st-testbtn" id="test-summary-open" type="button" aria-haspopup="dialog" aria-controls="test-summary" data-state="{gates_state(t)}">Tool test summary</button>
        {bar_download}
      </div>
    </div>
    <div class="st-wrap st-views__grid">
      <div class="st-panels">
        <section class="st-panel" id="readme" aria-labelledby="readme-h">
          <h2 class="st-panel__h" id="readme-h">Readme</h2>
          {question}
          <div class="st-md">
{readme}
          </div>
          {references_html(t, parts["cite"])}
        </section>
        <section class="st-panel" id="parameters" aria-labelledby="parameters-h">
          <h2 class="st-panel__h" id="parameters-h">Parameters</h2>
          {param_rows(t)}
          {fold_html("More on these parameters, from the readme", parts["params"])}
        </section>
        <section class="st-panel" id="outputs" aria-labelledby="outputs-h">
          <h2 class="st-panel__h" id="outputs-h">Outputs</h2>
          {outputs_html(t, root)}
          {fold_html("More on what you get, from the readme", parts["outputs"])}
        </section>
      </div>
      <aside class="st-facts" aria-labelledby="facts-h">
        <h2 class="pv-sr-only" id="facts-h">Details</h2>
        {facts_html(t)}
        {source}
      </aside>
    </div>
  </div>
  <dialog class="st-tests" id="test-summary" aria-labelledby="test-summary-h">
    <div class="st-tests__head" id="tool-check">
      <h2 class="st-tests__title" id="test-summary-h">Tool test summary</h2>
      <button class="st-tests__close" type="button" data-close-tests aria-label="Close the test summary">{CLOSE_X}</button>
    </div>
    <div class="st-tests__body">
      {gates_html(t)}
      <p class="st-tests__more"><a class="pv-link" href="{root}publish/#gates-h">What each gate checks</a></p>
    </div>
  </dialog>
  <section class="st-more" aria-labelledby="more-h">
    <div class="st-wrap">
      <h2 class="st-more__h" id="more-h">More tools</h2>
      <ul class="st-grid">
{more}
      </ul>
    </div>
  </section>
</main>
{footer(root)}
</body>
</html>
"""


def soon_page(p: dict) -> str:
    """A placeholder keeps its address: its name and one line, marked Coming soon."""
    root = "../../"
    url = f"{SITE_URL}tools/{p['id']}/"
    title = f"{p['name']} · The Tool Store · PointillViz"
    return f"""{head(root, title, f"{p['description']} A PointillViz community tool, coming soon.", title,
                     p['description'], url, f"{SITE_URL}assets/media/social/store.jpg", STORE_ART_ALT)}
<body class="st-page st-page--soon">
{topbar(root)}
<main id="main" class="st-tool st-soon">
  <div class="st-wrap">
    <a class="st-back" href="{root}">{icon(root, "i-arrow-left")}All tools</a>
    <header class="st-soon__head">
      <span class="pv-soon">Coming soon</span>
      <h1 class="st-title st-soon__name">{esc(p['name'])}</h1>
      <p class="st-top__desc">{esc(p['description'])}</p>
    </header>
  </div>
</main>
{footer(root)}
</body>
</html>
"""


# --------------------------------------------------------------------------- index regions, 404, sitemap

def fill(src: str, name: str, content: str, page: str = "index.html") -> str:
    pat = re.compile(rf"(<!-- store:{name} -->)([\s\S]*?)(<!-- /store:{name} -->)")
    if not pat.search(src):
        sys.exit(f"{page} has no <!-- store:{name} --> region")
    return pat.sub(lambda m: m.group(1) + content + m.group(3), src, count=1)


def svg_data_uri(path: str) -> str:
    """An SVG as a data: URI for an <img>, escaped only where a URI or an HTML
    attribute needs it (double quotes become single quotes)."""
    with open(path, encoding="utf-8") as fh:
        svg = re.sub(r"\s+", " ", fh.read()).strip().replace('"', "'")
    for ch, code in (("%", "%25"), ("#", "%23"), ("<", "%3C"), (">", "%3E"), ("&", "%26")):
        svg = svg.replace(ch, code)
    return "data:image/svg+xml," + svg


def sitemap(tools: list[dict]) -> str:
    rows = [f"  <url><loc>{SITE_URL}</loc></url>", f"  <url><loc>{SITE_URL}publish/</loc></url>"]
    for t in tools:
        rows.append(f"  <url><loc>{SITE_URL}{esc(t['url'])}</loc><lastmod>{esc(t['published'][:10])}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n")


def write(path: str, text: str) -> bool:
    data = text.encode("utf-8")
    try:
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as fh:
        fh.write(data)
    os.replace(path + ".tmp", path)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=STORE, help="the store site folder (default: this repository)")
    store = os.path.abspath(ap.parse_args().out)
    data_path = os.path.join(store, "data", "tools.json")
    try:
        with open(data_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        sys.exit(f"No {data_path}: run _build/build_store_data.py first.")
    tools = data["tools"]
    soon = data.get("placeholders") or []
    written = 0
    for t in tools:
        written += write(os.path.join(store, "tools", t["id"], "index.html"), tool_page(t, tools))
    for p in soon:
        written += write(os.path.join(store, "tools", p["id"], "index.html"), soon_page(p))
    keep = {t["id"] for t in tools} | {p["id"] for p in soon}
    tdir = os.path.join(store, "tools")
    for name in os.listdir(tdir):
        if name not in keep and os.path.isdir(os.path.join(tdir, name)):
            shutil.rmtree(os.path.join(tdir, name))
            written += 1

    index_path = os.path.join(store, "index.html")
    with open(index_path, encoding="utf-8") as fh:
        src = fh.read()
    # The first screen's plates (eight on a laptop) are fetched first.
    cards = "\n".join([card_html(t, "", eager=k < 8) for k, t in enumerate(tools)]
                      + [soon_card_html(p) for p in soon])
    src = fill(src, "cards", "\n" + cards + "\n")
    src = fill(src, "filters", "\n" + filters_html(data) + "\n")
    src = re.sub(r'(<meta property="og:description" content=")\d+( community tools)', rf"\g<1>{len(tools)}\g<2>", src)
    written += write(index_path, src)

    # The 404 page's logos, inline: see the module docstring.
    nf_path = os.path.join(store, "404.html")
    with open(nf_path, encoding="utf-8") as fh:
        nf = fh.read()
    logo = svg_data_uri(os.path.join(store, "assets", "pv", "logo.svg"))
    mark = svg_data_uri(os.path.join(store, "assets", "pv", "logo-mark.svg"))
    nf = fill(nf, "logo-topbar", f'<img src="{logo}" width="169" height="20" alt="PointillViz">', "404.html")
    nf = fill(nf, "logo-drawer", f'<img src="{logo}" width="152" height="18" alt="PointillViz" translate="no">', "404.html")
    nf = fill(nf, "logo-mark", f'<img src="{mark}" width="28" height="28" alt="">', "404.html")
    written += write(nf_path, nf)

    written += write(os.path.join(store, "sitemap.xml"), sitemap(tools))
    written += write(os.path.join(store, "robots.txt"),
                     "User-agent: *\nAllow: /\n" + ("" if PRELAUNCH else f"\nSitemap: {SITE_URL}sitemap.xml\n"))
    print(f"{len(tools)} tool pages, {len(soon)} coming soon · index regions filled · 404 logos · sitemap · {written} files written")


if __name__ == "__main__":
    main()
