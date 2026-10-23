# store.pointillviz.com

The public Tool Store of PointillViz, published by GitHub Pages at <https://store.pointillviz.com>.
It lists the community tools and explains how to install them. It does not install or run anything:
tools are installed from the Tools tab inside PointillViz.

Everything here is static. GitHub Pages serves the files as they are, with no build step.

## What is in this folder

| Path | What it is |
|---|---|
| `index.html` | The gallery: search, filters (shared tags, then outputs), sort and the cards. Written by hand, except the regions between `<!-- store:… -->` markers, which the page script fills. |
| `tools/<id>/index.html` | One page per tool, so every tool has its own address. Generated. |
| `publish/index.html` | Build & publish: the author's loop and the nine gates, in outline. Written by hand. |
| `404.html` | The page GitHub Pages shows for a missing address. Written by hand, except its logos (`<!-- store:logo-* -->`), which the page script fills as data URIs. |
| `data/tools.json` | Every listed tool, latest version: manifest fields, README (as safe HTML, formulas as MathML), parameters, outputs, downloads, dates, versions and the nine-gate report. Generated. |
| `data/tools-index.json` | The same tools with only what a card shows and search reads (15 kB instead of 140 kB). The gallery loads this. Generated. |
| `sitemap.xml`, `robots.txt` | For search engines. Generated. |
| `assets/store.css`, `assets/store.js` | The store's own styles and behaviour. Written by hand. |
| `assets/pv/` | The shared PointillViz design system. A copy: do not edit it here (see below). |
| `assets/vendor/noto-sans-math-3.000/` | A subset of the Noto Sans Math font (SIL OFL 1.1, with its licence), for the formulas on tool pages. |
| `assets/media/tools/` | Each tool's card artwork as WebP, 720 × 420 and 1440 × 840 (`@2x`). Generated. |
| `assets/media/social/` | 1200 × 630 link previews: one per tool, and `store.jpg` for the gallery. Generated. |
| `assets/media/*.webp` | The Tools tab at its real size and Fig. 2a's result (gallery), and Fig. 2a (Build & publish). Generated once. |
| `CNAME` | The custom domain. GitHub Pages reads it, so leave it in place. |
| `.nojekyll` | Tells GitHub Pages to publish the files as they are. |

No source code of any tool is published here. The bundles are opened only for their README and
their card artwork.

## Regenerate the pages

The scripts live in the `tools/` folder of the PointillViz web workspace, next to this site
(`build_store_data.py`, `build_store_pages.py`, `build_store_media.py`). They read a PointillViz
store registry: the folder a running store publishes into, with one
`<tool>/<version>/{manifest.json, meta.json, report.json, bundle.pvtool}` per published version.

```bash
# 1. Data and artwork (needs Pillow and rsvg-convert, both in the penv environment)
python -I tools/build_store_data.py                  # the registry beside the workspace
python -I tools/build_store_data.py --registry DIR   # or any other registry

# 2. Pages (any Python 3.8+, no packages)
python3 -I tools/build_store_pages.py
```

`build_store_data.py` writes `data/tools.json`, `data/tools-index.json`, the artwork and the link
previews. For each tool it takes the latest version, sums the downloads of every version, strips
e-mail addresses from the author and the gate messages, converts the README with a small Markdown
subset that escapes all text (its `$$` formulas and its *emphasized* maths become MathML), and
rasterizes the bundle's `preview.svg` (the tool's own artwork) to WebP, after dropping a full-size
backdrop the author drew first so that every artwork sits on the store's plate. A bundle without
artwork gets a seeded field of points instead. Tools are listed in Popular order: downloads, then
the newest, then name.

`build_store_pages.py` writes one page per tool, removes the pages of tools that are no longer
listed, fills the marked regions of `index.html` (the cards in Popular order, the filters and the
count) and of `404.html` (its logos), and writes `sitemap.xml` and `robots.txt`. The filters are
the tags that two or more tools share (a tag on every tool filters nothing, and a tag on one tool
is found by search), then what the tools draw. For the same reason a tool's page leaves out a tag
that every tool carries. Readers without JavaScript see the pre-rendered
cards; with JavaScript, `assets/store.js` loads `data/tools-index.json` and filters, sorts and
searches in the browser, and keeps the choice in the address (`?q=`, `?tag=`, `?out=`, `?sort=`).

`build_store_media.py` crops the page pictures from the PointillViz paper's figure sources. Run it
only if those change.

Both scripts write a file only when its content changed, so a rerun leaves `git status` clean.

## Add a tool

1. Publish the tool to a PointillViz store (its Publish panel, or `plugin_pack` and an upload).
   The store runs the nine gates and lists the tool only if every required gate passes.
2. Run the two scripts above, in order.
3. Check the new page at `tools/<id>/` and the gallery, then commit and push.

A new version of a listed tool works the same way: the page shows the latest version, and the
older ones under Versions.

## Preview before pushing

```bash
python3 -m http.server 8000   # from this folder, then open http://localhost:8000
```

The search, filters and sort work there too; `data/tools.json` is fetched from the same folder.

## Notes

- **Links.** Every link inside the store is relative, so the pages work at the domain root and in
  a subfolder. Links to the other sites use their full addresses: `https://pointillviz.com/` and
  `https://docs.pointillviz.com/`.
- **404.** GitHub Pages shows `404.html` at the missing address itself, at any depth. Its first
  script sets a `<base>` at the store's root and adds the style sheets and scripts after it, so
  that its relative links still resolve from the root; it then points the page's own `#` links
  (Skip to content) back at the missing address. Its logos are data URIs, so nothing is fetched
  from the wrong place before the `<base>` exists.
- **Design system.** `assets/pv/` is copied from the shared design system by the workspace's
  `tools/sync.sh`. Change the shared copy and run the sync; never edit `assets/pv/` here.
- **Placeholders.** "Install into PointillViz" on a tool page, "From this website" in the gallery,
  Publish and the guide for coding agents are not available yet. They say so on the page.
