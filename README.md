# store.pointillviz.com

The public Tool Store of PointillViz, published by GitHub Pages at <https://store.pointillviz.com>.
It lists the community tools of the public registry
(<https://github.com/lamanno-epfl/pointillviz-registry>) and explains how to install them. It does not
install or run anything: a tool page offers the tool's `.pvtool` bundle for download, and tools are
installed inside PointillViz (Tools → Store → Install, or Install from file with the download).

Everything here is static. GitHub Pages serves the files as they are, with no build step.

## What is in this folder

| Path | What it is |
|---|---|
| `index.html` | The gallery: search, filters (shared tags, then outputs), sort and the cards, then a Coming soon card per announced tool. Written by hand, except the regions between `<!-- store:… -->` markers, which the page script fills. |
| `tools/<id>/index.html` | One page per tool, so every tool has its own address, and a Coming soon page (its name and one line) per announced tool. Generated. |
| `publish/index.html` | Build & publish: the author's loop, publishing by pull request to the public registry, and the gates. Written by hand. |
| `404.html` | The page GitHub Pages shows for a missing address. Written by hand, except its logos (`<!-- store:logo-* -->`), which the page script fills as data URIs. |
| `data/tools.json` | Every listed tool, latest version: manifest fields, README (as safe HTML, formulas as MathML), parameters, outputs, language and GPU, the bundle's address and size, the release date and the gate report; then the announced tools. Generated. |
| `data/tools-index.json` | The same tools with only what a card shows and search reads (14 kB instead of 145 kB). The gallery loads this. Generated. |
| `sitemap.xml`, `robots.txt` | For search engines. Generated. |
| `assets/store.css`, `assets/store.js` | The store's own styles and behaviour. Written by hand. |
| `assets/pv/` | The shared PointillViz design system. A copy: do not edit it here (see below). |
| `assets/vendor/noto-sans-math-3.000/` | A subset of the Noto Sans Math font (SIL OFL 1.1, with its licence), for the formulas on tool pages. |
| `assets/media/tools/` | Each tool's card artwork as WebP, 720 × 420 and 1440 × 840 (`@2x`). Generated. |
| `assets/media/social/` | 1200 × 630 link previews: one per tool, and `store.jpg` for the gallery. Generated. |
| `assets/media/*.webp` | The Tools tab at its real size and Fig. 2a's result (gallery), and Fig. 2a (Build & publish). Generated once. |
| `_build/` | The two scripts that generate the pages from the registry, the fonts of the link previews (DM Sans and JetBrains Mono, SIL OFL 1.1, with their licences) and the locked environment they run in (`pixi.toml`, `pixi.lock`). |
| `.github/workflows/rebuild.yml` | Rebuilds the store from the registry every hour, and commits what changed. |
| `CNAME` | The custom domain. GitHub Pages reads it, so leave it in place. |
| `.nojekyll` | Tells GitHub Pages to publish the files as they are. |

No tool's code is copied here. A tool page links to its bundle on the registry's releases and to its
folder in the public registry.

## Regenerate the pages

The store keeps itself up to date. Every hour, the `rebuild` workflow runs the two scripts in
`_build/` (`build_store_data.py`, then `build_store_pages.py`) against the public registry's
`index.json`, commits what changed, and asks GitHub Pages to publish it. It runs them in the
environment of `_build/pixi.toml`, whose lock pins Pillow and librsvg, so the same index always gives
the same bytes. Commit only what that environment builds: other versions encode the artwork
differently.

The scripts read the registry's
`index.json`, which its release workflow builds with `scripts/build_index.py`: each tool's latest
version, with its manifest, its bundle's address and size, its gate report and its release date,
and the tools announced as Coming soon. A tool's `README.md` and `preview.svg` come from a registry
checkout's `tools/<id>/` when there is one, or else from the addresses the index gives.

```bash
pixi run --manifest-path _build/pixi.toml build              # both steps, as the workflow runs them

# 1. Data and artwork (needs Pillow and rsvg-convert: run it in _build/pixi.toml's environment)
python -I _build/build_store_data.py --index PATH|URL        # any other index
python -I _build/build_store_data.py --index PATH --registry DIR --out DIR
                                                             # a registry checkout, into a copy of this site

# 2. Pages (any Python 3.8+, no packages)
python3 -I _build/build_store_pages.py                       # or --out DIR, as above
```

`build_store_data.py` writes `data/tools.json`, `data/tools-index.json`, the artwork and the link
previews. For each tool it strips e-mail addresses from the author and the gate messages, converts
the README with a small Markdown subset that escapes all text (its `$$` formulas and its
*emphasized* maths become MathML), and rasterizes the tool's `preview.svg` (its own artwork) to
WebP, after dropping a full-size backdrop the author drew first so that every artwork sits on the
store's plate. A tool without artwork gets a seeded field of points instead. Tools are listed
newest first, by release date, then by name.

`build_store_pages.py` writes one page per tool and one Coming soon page per announced tool,
removes the pages of tools that are no longer listed, fills the marked regions of `index.html` (the
cards, newest first, then the Coming soon cards; the filters and the count) and of `404.html` (its
logos), and writes `sitemap.xml` and `robots.txt`. The filters are
the tags that two or more tools share (a tag on every tool filters nothing, and a tag on one tool
is found by search), then what the tools draw. For the same reason a tool's page leaves out a tag
that every tool carries. Readers without JavaScript see the pre-rendered
cards; with JavaScript, `assets/store.js` loads `data/tools-index.json` and filters, sorts and
searches in the browser, and keeps the choice in the address (`?q=`, `?tag=`, `?out=`, `?sort=`).
Search also finds the Coming soon cards; a tag or output filter leaves them out.

`build_store_media.py` crops the page pictures from the PointillViz paper's figure sources. It lives
in the PointillViz web workspace, not here, because those sources are not public. Run it only if they
change.

Both scripts write a file only when its content changed, so a rerun leaves `git status` clean.

## Add a tool

1. The tool is published in the public registry: a pull request adds its folder, it is merged
   automatically once its checks pass, and the release workflow releases its bundle and adds it to
   `index.json` (the registry's CONTRIBUTING.md has the details).
2. Within the hour, the rebuild workflow adds its page and its card here. Nothing is done by hand.

A new version of a listed tool works the same way: the index lists only the latest version, and the
earlier ones stay available as the registry's GitHub releases.

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
- **Placeholders.** The tools of the registry's `placeholders.json` are shown as Coming soon: a
  card with a name and one line, and a page of the same at the tool's address. Nothing else about
  them is published.
