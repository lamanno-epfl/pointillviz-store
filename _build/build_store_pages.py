#!/usr/bin/env python3
"""Generate the Tool Store's static pages from store/data/tools.json.

    python3 -I _build/build_store_pages.py             (any Python 3.8+; no packages)
    python3 -I _build/build_store_pages.py --out DIR   (a test copy of the site)

Run _build/build_store_data.py first. This script writes:

  store/tools/<id>/index.html   one shareable page per tool, and a Coming soon
                                page (its name and one line) per placeholder;
                                it removes the folders of tools no longer listed
  store/index.html              only the regions between build markers:
                                  <!-- store:cards -->  the card grid, Newest first,
                                                        then the Coming soon cards
                                  <!-- store:tags -->   the filters: shared tags, then outputs
                                  <!-- store:count -->  "13 tools published"
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
LANG_TIP = "Written in {}"
GPU_TIP = {"optional": "Runs on the CPU or a GPU: you choose when you run it.",
           "required": ("Meant for a GPU. PointillViz selects the GPU when the computer has one; "
                        "the tool also runs on the CPU.")}
STORE_ART_ALT = "The Tool Store wordmark above the artwork of its community tools."
NBSP = "\xa0"


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


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


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
         image_alt: str, extra: str = "") -> str:
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,400&amp;family=Fraunces:opsz,wght@9..144,600&amp;family=JetBrains+Mono:wght@400..600&amp;display=swap">
<link rel="stylesheet" href="{root}assets/pv/pv.css">
<link rel="stylesheet" href="{root}assets/store.css">
<script src="{root}assets/pv/pv.js" defer></script>
<script src="{root}assets/store.js" defer></script>
<script>document.documentElement.classList.add('st-js')</script>
<noscript><style>.pv-topbar__menu {{ display: none !important; }}</style></noscript>{extra}
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


def badges(t: dict) -> str:
    """The language the tool is written in, and whether it can use a GPU."""
    out = f'<span class="pv-tag st-badge" title="{esc(LANG_TIP.format(t["language_label"]))}">{esc(t["language_label"])}</span>'
    if t.get("gpu"):
        out += (f'<span class="pv-tag st-badge" title="{esc(GPU_TIP.get(t["gpu"], ""))}">'
                f'{esc(t["gpu_label"])}</span>')
    return out


def risk_chips(t: dict) -> str:
    return "".join(
        f'<span class="st-risk" title="Disclosed by the advisory imports gate: this tool {esc(r["text"])}. '
        f'A tool can pass every gate and still do this.">{esc(r["label"])}</span>' for r in t["risks"])


CARD_SIZES = "(max-width: 519.98px) 112px, (min-width: 1280px) 340px, (min-width: 900px) 31vw, (min-width: 600px) 46vw, 92vw"


def card_html(t: dict, root: str = "", eager: bool = False, heading: str = "h3", hidden_outputs=()) -> str:
    """One card. Outputs that every tool returns (a summary) are left off the card;
    the tool's page lists them all. The tags are on the tool's page and in search."""
    all_outs = t["outputs"] + t["optional_outputs"]
    outs = "".join(f'<li class="pv-tag pv-tag--out" title="{esc(t["output_help"].get(o, o))}">{esc(o)}</li>'
                   for o in all_outs if o not in hidden_outputs)
    data = (f'data-id="{esc(t["id"])}" data-name="{esc(t["name"])}" data-tags="{esc("|".join(t["tags"]))}" '
            f'data-outputs="{esc("|".join(all_outs))}" data-published="{esc(t["published"])}" '
            f'data-version="{esc(t["version"])}"')
    return f"""<li class="st-cell" {data}>
<article class="pv-card pv-card--link st-card">
  <div class="st-card__art">{art_img(t, root, CARD_SIZES, eager)}</div>
  <{heading} class="pv-card__title st-card__title"><a class="pv-card__link" href="{root}{esc(t['url'])}">{esc(t['name'])}</a></{heading}>
  <p class="pv-card__meta st-card__by"><span class="st-card__author">{esc(t['author'])}</span> <time class="st-card__date" datetime="{esc(t['published'])}">{esc(t['published_date'])}</time></p>
  <p class="pv-card__body st-card__desc">{esc(t['description'])}</p>
  <ul class="pv-tags st-card__outs" aria-label="Outputs">{outs}</ul>
  <div class="pv-card__foot st-card__foot">
    {badges(t)}{risk_chips(t)}
    <span class="st-card__ver" title="Version">v{esc(t['version'])}</span>
  </div>
</article>
</li>"""


def soon_card_html(p: dict) -> str:
    """A tool that is announced, not published: its name and one line, with no
    artwork and no page to open. Listed after the tools; search finds it."""
    return f"""<li class="st-cell st-cell--soon" data-id="{esc(p['id'])}" data-name="{esc(p['name'])}" data-soon>
<article class="pv-card st-card st-card--soon">
  <div class="st-card__art st-card__art--soon"></div>
  <h3 class="pv-card__title st-card__title">{esc(p['name'])}</h3>
  <p class="pv-card__body st-card__desc">{esc(p['description'])}</p>
  <div class="pv-card__foot st-card__foot"><span class="pv-soon">Coming soon</span></div>
</article>
</li>"""


def filters_html(data: dict) -> str:
    """One radio group in two parts that wrap as wholes: All and the tags two or
    more tools share, then what the tools draw. Single-tool tags are found by
    search instead."""
    f = data.get("filters") or {"tags": [], "outputs": []}
    chips = ['<button class="pv-chip st-chip" type="button" role="radio" aria-checked="true" tabindex="0" data-tag="">'
             f'All <span class="pv-chip__count">{data["count"]}</span></button>']
    for row in f["tags"]:
        chips.append(f'<button class="pv-chip st-chip" type="button" role="radio" aria-checked="false" tabindex="-1" '
                     f'data-tag="{esc(row["tag"])}">{esc(row["tag"])} <span class="pv-chip__count">{row["count"]}</span></button>')
    groups = ['<div class="st-tags__group">\n' + "\n".join(chips) + "\n</div>"]
    if f["outputs"]:
        outs = ['<span class="st-tags__sep" aria-hidden="true">Outputs</span>']
        for row in f["outputs"]:
            outs.append(f'<button class="pv-chip st-chip st-chip--out" type="button" role="radio" aria-checked="false" '
                        f'tabindex="-1" data-out="{esc(row["out"])}" title="{esc(row["help"].capitalize())}">'
                        f'<span class="pv-sr-only">Output: </span>{esc(row["out"])} '
                        f'<span class="pv-chip__count">{row["count"]}</span></button>')
        groups.append('<div class="st-tags__group st-tags__group--out">\n' + "\n".join(outs) + "\n</div>")
    return "\n".join(groups)


def count_text(n: int) -> str:
    return f"{plural(n, 'tool')} published"


# --------------------------------------------------------------------------- tool page

def param_rows(t: dict) -> str:
    if not t["parameters"]:
        return '<p class="st-empty-line">This tool takes no parameters.</p>'
    rows = []
    for p in t["parameters"]:
        sweep = (' <span class="pv-tag st-sweep" title="This parameter can be swept: one run per value, '
                 'with a slider between the results.">sweep</span>') if t.get("sweep") == p["name"] else ""
        rows.append(f"""<tr role="row">
  <th scope="row" role="rowheader" data-label="Parameter"><span class="st-param__label">{esc(p['label'])}</span><code class="st-param__name" translate="no">{esc(p['name'])}</code>{sweep}</th>
  <td role="cell" data-label="Type"><span class="st-param__type">{esc(p['type_text'])}</span></td>
  <td role="cell" data-label="Default"><span class="st-param__default">{esc(p['default_text'])}</span></td>
  <td role="cell" data-label="What it does">{esc(p['help'])}</td>
</tr>""")
    return f"""<div class="pv-table-wrap st-params">
<table class="pv-table" role="table" aria-labelledby="parameters-h">
<thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Parameter</th><th scope="col" role="columnheader">Type</th><th scope="col" role="columnheader">Default</th><th scope="col" role="columnheader">What it does</th></tr></thead>
<tbody role="rowgroup">
{chr(10).join(rows)}
</tbody>
</table>
</div>"""


def outputs_html(t: dict) -> str:
    items = []
    for o in t["outputs"] + t["optional_outputs"]:
        opt = ' <span class="st-opt">optional</span>' if o in t["optional_outputs"] else ""
        items.append(f'<li><span class="pv-tag pv-tag--out">{esc(o)}</span><span class="st-outputs__what">'
                     f'{esc(t["output_help"].get(o, o))}{opt}</span></li>')
    return f'<ul class="st-outputs">{"".join(items)}</ul>'


def gates_html(t: dict) -> str:
    if not t["gates"]:
        return '<p class="st-empty-line">No gate report is on file for this version.</p>'
    strip, log = [], []
    for g in t["gates"]:
        state, word = GATE_STATE.get(g["status"], "pending"), GATE_DONE.get(g["status"], g["status"])
        # An advisory gate (imports) never blocks: drawn as a ring (store.css §7).
        adv, adv_attr = ('', '') if g["required"] else (' <span class="st-adv">advisory</span>', ' data-adv')
        strip.append(f'<li class="pv-gate" data-state="{state}"{adv_attr}><span class="pv-gate__name" translate="no">{esc(g["id"])}</span>'
                     f'<span class="pv-sr-only"> {esc(word)}{"" if g["required"] else ", advisory"}</span></li>')
        log.append(f"""<li class="st-gatelog__row" data-state="{state}"{adv_attr}>
  <span class="st-gatelog__name"><code translate="no">{esc(g['id'])}</code>{adv}</span>
  <span class="st-gatelog__status">{esc(word)}</span>
  <p class="st-gatelog__msg">{esc(g['message'])}</p>
</li>""")
    return f"""<div class="st-check">
  <ol class="pv-gates st-check__strip" aria-label="The gates, in the order they ran">{''.join(strip)}</ol>
  <ol class="st-gatelog" aria-label="What each gate saw">
{chr(10).join(log)}
  </ol>
</div>"""


def facts_html(t: dict) -> str:
    def fact(k, v):
        return f'<div class="st-facts__row"><dt>{esc(k)}</dt><dd>{v}</dd></div>'
    rows = [
        fact("Version", f'<span class="st-facts__ver">{esc(t["version"])}</span>'),
        fact("Published", f'<time datetime="{esc(t["published"])}">{esc(t["published_date"])}</time>'),
        fact("Licence", esc(t["license"] or "not stated")),
        fact("Needs", " · ".join(f'<span class="st-nowrap">{esc(x)}</span>' for x in t["needs"])
             if t["needs"] else "nothing in particular"),
    ]
    return f'<dl class="st-facts">{"".join(rows)}</dl>'


def related(t: dict, tools: list[dict], n: int = 3) -> list[dict]:
    mine = set(t["tags"])
    scored = []
    for o in tools:
        if o["id"] == t["id"]:
            continue
        shared = len(mine & set(o["tags"]))
        scored.append((-shared, o["name"].lower(), o))
    scored.sort(key=lambda s: s[:2])
    return [s[2] for s in scored[:n]]


ONPAGE = [("readme", "Readme"), ("parameters", "Parameters"), ("outputs", "Outputs"),
          ("tool-check", "Tool check")]


def hero_chips(t: dict, common_tags=frozenset()) -> str:
    """The tool's tags, then the gallery's dotted "Outputs" divider and what it
    draws. A tag that every tool carries says nothing here and is left out (search
    still finds it), and so is one that repeats the language badge ("R")."""
    tags = [x for x in t["tags"] if x not in common_tags and x.lower() != t["language_label"].lower()]
    outs = t["outputs"] + t["optional_outputs"]
    tag_items = "".join(f'<li class="pv-tag">{esc(x)}</li>' for x in tags)
    out_items = "".join(f'<li class="pv-tag pv-tag--out" title="{esc(t["output_help"].get(o, o))}">{esc(o)}</li>'
                        for o in outs)
    parts = []
    if tags:
        parts.append(f'<ul class="pv-tags" aria-label="Tags">{tag_items}</ul>')
    if outs:
        sep = "st-tags__sep" if tags else "st-tags__sep st-tags__sep--lead"
        parts.append(f'<div class="st-hero__outs"><span class="{sep}" aria-hidden="true">Outputs</span>'
                     f'<ul class="pv-tags" aria-label="Outputs">{out_items}</ul></div>')
    return f'<div class="st-hero__chips">{"".join(parts)}</div>' if parts else ""


def tool_page(t: dict, tools: list[dict], hidden_outputs=(), common_tags=frozenset()) -> str:
    root = "../../"
    url = f"{SITE_URL}tools/{t['id']}/"
    desc = f"{first_sentence(t['description'])} A PointillViz community tool, version {t['version']}."
    alt = t["art"]["alt"] or f"Card artwork of {t['name']}."
    caption = (f'<figcaption class="pv-figure__caption"><span>{esc(t["art"]["alt"])}</span>'
               f'<span class="pv-figure__meta">Artwork from the tool’s bundle</span></figcaption>') if t["art"]["alt"] else ""
    readme = t["readme_html"] or '<p class="st-empty-line">This tool shipped no README.</p>'
    refs = (f'<div class="st-refs"><h3 class="st-refs__h">References</h3><p>{esc(t["citation"])}</p></div>'
            if t.get("citation") else "")
    more = "\n".join(card_html(o, root, heading="h3", hidden_outputs=hidden_outputs) for o in related(t, tools))
    onpage = "\n".join(f'            <li><a href="#{sid}">{label}</a></li>' for sid, label in ONPAGE)
    # The bundle is the release's own file; the source is the tool's folder in
    # the public registry (both from the index).
    download = (f'<a class="pv-btn pv-btn--primary pv-btn--lg st-get__btn" href="{esc(t["bundle_url"])}" download>'
                f'{icon(root, "i-download", "")}<span class="pv-btn__stack"><span>Download</span> '
                f'<span class="pv-btn__sub">.pvtool · {esc(t["bundle_size"])}</span></span></a>') if t["bundle_url"] else ""
    source = (f'<p class="st-get__src"><a class="pv-link" href="{esc(t["source_url"])}">Source in the public registry'
              f'{icon(root, "i-external")}</a></p>') if t["source_url"] else ""
    check = (f'<p class="st-sec__intro">The gates this version passed when it was released, in the order they ran.</p>\n'
             f'          {gates_html(t)}\n          <p class="st-sec__note">{esc(GATES_NOTE)}</p>'
             if t["gates"] else gates_html(t))
    # <Tool> · The Tool Store · PointillViz, as the store's own pages.
    title = f"{t['name']} · The Tool Store · PointillViz"
    return f"""{head(root, title, desc, title, t['description'], url,
                     f"{SITE_URL}{t['social']}", alt)}
<body class="st-page st-page--tool">
{topbar(root)}
<main id="main" class="st-tool">
  <div class="pv-container">
    <nav class="st-back" aria-label="Back">
      <a class="st-back__link" href="{root}">{icon(root, "i-arrow-left")}All tools</a>
    </nav>
    <div class="st-tool__layout">
      <header class="st-hero">
        <h1 class="pv-title st-hero__title">{esc(t['name'])}</h1>
        <p class="st-hero__by">by {esc(t['author'])}</p>
        <p class="pv-lede st-hero__desc">{esc(t['description'])}</p>
        <div class="st-hero__badges">{badges(t)}<span class="pv-tag pv-tag--ver">v{esc(t['version'])}</span>{risk_chips(t)}</div>
        {hero_chips(t, common_tags)}
      </header>
      <figure class="pv-figure st-hero__art">
        <div class="pv-figure__stage st-artstage">{art_img(t, root, "(min-width: 1320px) 820px, (min-width: 1100px) 62vw, 94vw", True, alt)}</div>
        {caption}
      </figure>
      <div class="st-side">
        <aside class="st-get" aria-labelledby="get-h">
          <h2 class="st-get__title" id="get-h">Get this tool</h2>
          {download}
          <div class="st-get__how">
            <p>Install in PointillViz: <b>Tools → Store → Install</b>, or use <b>Install from file</b> with the download.</p>
            <p class="st-get__docs"><a class="pv-link" href="{DOCS_TOOLS_URL}">How tools work · Docs</a></p>
          </div>
          {source}
          <p class="st-get__note"><b>This runs as you.</b> A tool is arbitrary code, run with the privileges of whoever started PointillViz. <a class="pv-link" href="{root}#safety">Read the safety note</a></p>
          <h3 class="pv-label st-get__facts-h">Facts</h3>
          {facts_html(t)}
        </aside>
        <nav class="st-onpage" aria-labelledby="onpage-h">
          <p class="pv-label st-onpage__h" id="onpage-h">On this page</p>
          <ul>
{onpage}
          </ul>
        </nav>
      </div>
      <div class="st-tool__main">
        <section class="st-sec" id="readme" aria-labelledby="readme-h">
          <h2 class="st-sec__h" id="readme-h">Readme</h2>
          <div class="st-md">
{readme}
          </div>
          {refs}
        </section>
        <section class="st-sec" id="parameters" aria-labelledby="parameters-h">
          <h2 class="st-sec__h" id="parameters-h">Parameters</h2>
          {param_rows(t)}
        </section>
        <section class="st-sec" id="outputs" aria-labelledby="outputs-h">
          <h2 class="st-sec__h" id="outputs-h">Outputs</h2>
          {outputs_html(t)}
        </section>
        <section class="st-sec" id="tool-check" aria-labelledby="check-h">
          <h2 class="st-sec__h" id="check-h">Tool check</h2>
          {check}
        </section>
      </div>
    </div>
    <section class="st-more" aria-labelledby="more-h">
      <h2 class="st-more__h" id="more-h">More tools</h2>
      <ul class="st-grid st-grid--more">
{more}
      </ul>
    </section>
  </div>
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
  <div class="pv-container">
    <nav class="st-back" aria-label="Back">
      <a class="st-back__link" href="{root}">{icon(root, "i-arrow-left")}All tools</a>
    </nav>
    <header class="st-soon__head">
      <span class="pv-soon">Coming soon</span>
      <h1 class="pv-title st-hero__title">{esc(p['name'])}</h1>
      <p class="pv-lede st-hero__desc">{esc(p['description'])}</p>
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
    hidden = tuple(data.get("card_hidden_outputs") or ())
    # A tag on every tool (spatial) tells one tool from no other.
    common = frozenset.intersection(*(frozenset(t["tags"]) for t in tools)) if len(tools) > 1 else frozenset()
    written = 0
    for t in tools:
        written += write(os.path.join(store, "tools", t["id"], "index.html"), tool_page(t, tools, hidden, common))
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
    # The first row (four cards on a wide screen) is fetched first.
    cards = "\n".join([card_html(t, "", eager=k < 4, hidden_outputs=hidden) for k, t in enumerate(tools)]
                      + [soon_card_html(p) for p in soon])
    src = fill(src, "cards", "\n" + cards + "\n")
    src = fill(src, "tags", "\n" + filters_html(data) + "\n")
    src = fill(src, "count", count_text(len(tools)))
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
