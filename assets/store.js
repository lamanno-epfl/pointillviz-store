/*! store.pointillviz.com · store.js · no dependencies (uses window.PV from pv.js and
 * window.STField from field.js when present)
 *
 * Gallery (index.html): search, filters and sort, all in the browser over
 * data/tools-index.json. The grid arrives pre-rendered by _build/build_store_pages.py,
 * so the page works and reads before this script runs; this script reconciles the grid
 * with the index (the source of truth) and then filters and orders it. The Coming soon
 * cards stay after the tools: search finds them, and a filter hides them. While the
 * pointer rests on a plate (or a plate has keyboard focus) the hero previews that tool.
 *
 * Tool pages: three views on one bar (Readme, Parameters, Outputs), the test summary
 * in a dialog, and the artwork developed by field.js. A formula wider than its column
 * becomes a focusable scroller that fades where it continues.
 *
 * Every string in the index was written by a tool's author: it reaches the page
 * through esc() or textContent, never as markup.
 */
(() => {
  'use strict';

  const doc = document;
  const root = doc.documentElement;
  const $ = (sel, ctx = doc) => ctx.querySelector(sel);
  const $$ = (sel, ctx = doc) => Array.from(ctx.querySelectorAll(sel));
  const reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => reduceMQ.matches;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // Typographer's apostrophes in names and search alike: "ripley's" finds Ripley’s.
  const fold = (s) => String(s || '').toLowerCase().replace(/[‘’]/g, "'");
  const cssNum = (name, fallback) => parseFloat(getComputedStyle(root).getPropertyValue(name)) || fallback;
  const scaleK = () => cssNum('--k', 1);
  const barBlock = () => cssNum('--pv-topbar-h', 64) * scaleK();

  function main() {
    if ($('#grid')) gallery();
    toolPage();
    notFound();
  }

  /* ======================================================= gallery */

  function gallery() {
    const grid = $('#grid');
    const hero = $('#hero');
    const input = $('#q');
    const form = input && input.form;
    const panel = $('#filters-panel');
    const toggle = $('#filters-toggle');
    const scrim = $('#filters-scrim');
    const tagList = $('#tag-list');
    const outList = $('#out-list');
    const sortBox = $('#sort');
    const countEl = $('#count');
    const live = $('#live');
    const empty = $('#empty');
    const emptyTitle = $('#empty-title');
    const emptyText = $('#empty-text');
    const emptyAction = $('#empty-action');
    const pill = $('#active-filter');
    const pillLabel = $('#active-filter-label');

    const SORTS = { newest: 'newest', name: 'name' };
    const state = { q: '', tag: '', out: '', sort: 'newest' };
    const toolCells = () => $$('.st-cell:not([data-soon]):not(.st-ghost)', grid);
    let tools = modelFromDom();
    let total = tools.length;
    let allTags = new Set(tools.flatMap((t) => t.tags.map(fold)));
    let firstApply = true;

    /* ---- the model -------------------------------------------------- */

    function searchText(t) {
      return fold([t.name, t.description, t.author, t.id, (t.tags || []).join(' ')].join(' '));
    }

    // Until the index arrives (or if it cannot), the pre-rendered cards carry
    // everything search, filters and sort need.
    function modelFromDom() {
      return toolCells().map((cell) => {
        const t = {
          id: cell.dataset.id,
          name: cell.dataset.name || ($('.st-card__name', cell) || {}).textContent || '',
          description: ($('.st-card__desc', cell) || {}).textContent || '',
          author: cell.dataset.author || '',
          tags: (cell.dataset.tags || '').split('|').filter(Boolean),
          outputs: (cell.dataset.outputs || '').split('|').filter(Boolean),
          optional_outputs: [],
          published: cell.dataset.published || '',
          version: cell.dataset.version || '',
        };
        t._hay = searchText(t);
        return t;
      });
    }

    // A Coming soon card: a name and one line, after the tools. Search reads it.
    const soonHay = (cell) => fold(`${cell.dataset.name || ''} ${($('.st-card__line', cell) || {}).textContent || ''} ${cell.dataset.id || ''}`);

    function matches(hay, q) {
      if (!q) return true;
      // Every word must match, as in the local store: "spatial entropy" should
      // not return a tool that is merely spatial.
      return fold(q).split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
    }

    const outsOf = (t) => (t.outputs || []).concat(t.optional_outputs || []);
    const hasTag = (t) => !state.tag || (t.tags || []).some((x) => fold(x) === state.tag);
    const hasOut = (t) => !state.out || outsOf(t).includes(state.out);

    // Newest: the day released, then name; tools released together stay A–Z
    // (as the pre-rendered grid). A–Z: name.
    function ordered(list) {
      const byName = (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
      const out = list.slice();
      if (state.sort === 'name') out.sort(byName);
      else {
        out.sort((a, b) => {
          const da = a.published.slice(0, 10), db = b.published.slice(0, 10);
          return da < db ? 1 : da > db ? -1 : byName(a, b);
        });
      }
      return out;
    }

    /* ---- rendering (mirrors card_html in _build/build_store_pages.py) --- */

    function cardHTML(t) {
      const a = t.art || {};
      const sizes = '(max-width: 559.98px) 92vw, (max-width: 819.98px) 46vw, (max-width: 1099.98px) 31vw, 23vw';
      return `<a class="st-card" href="${esc(t.url)}">
  <div class="st-card__art"><img src="${esc(a.src)}" srcset="${esc(a.src)} ${a.width}w, ${esc(a.src2x)} ${a.width * 2}w" sizes="${sizes}" width="${a.width}" height="${a.height}" alt="" loading="lazy" decoding="async"></div>
  <h3 class="st-card__name">${esc(t.name)}</h3>
  <p class="st-card__desc">${esc(t.description)}</p>
</a>`;
    }

    function setCellData(cell, t) {
      cell.dataset.id = t.id;
      cell.dataset.name = t.name;
      cell.dataset.author = t.author || '';
      cell.dataset.tags = (t.tags || []).join('|');
      cell.dataset.outputs = outsOf(t).join('|');
      cell.dataset.published = t.published || '';
      cell.dataset.version = t.version || '';
    }

    function optionHTML(attr, value, label, count, title) {
      const tip = title ? ` title="${esc(title)}"` : '';
      return `<button class="st-opt" type="button" aria-pressed="false" ${attr}="${esc(value)}"${tip}><span class="st-opt__label">${esc(label)}</span><span class="st-opt__n">${count}</span></button>`;
    }

    // The index is the source of truth: keep the cards that match it, re-render
    // the ones it changed, add the ones the static page did not have.
    function reconcile(data) {
      const byId = new Map(toolCells().map((c) => [c.dataset.id, c]));
      const keep = new Set();
      const next = (data.tools || []).map((t) => {
        let cell = byId.get(t.id);
        if (!cell || cell.dataset.version !== t.version) {
          const fresh = doc.createElement('li');
          fresh.className = 'st-cell';
          fresh.innerHTML = cardHTML(t);
          if (cell) cell.replaceWith(fresh); else grid.appendChild(fresh);
          cell = fresh;
        }
        setCellData(cell, t);
        keep.add(t.id);
        const m = { ...t };
        m._hay = searchText(m);
        return m;
      });
      byId.forEach((cell, id) => { if (!keep.has(id)) cell.remove(); });
      // A Coming soon card goes once its tool is published or no longer announced.
      const announced = new Set((data.placeholders || []).map((p) => p.id));
      $$('.st-cell[data-soon]', grid).forEach((cell) => {
        if (keep.has(cell.dataset.id) || !announced.has(cell.dataset.id)) cell.remove();
      });
      const f = data.filters || { tags: [], outputs: [] };
      const have = (list, key) => $$('.st-opt', list).map((o) => o.dataset[key]).join('|');
      if (tagList && have(tagList, 'tag') !== f.tags.map((r) => r.tag).join('|')) {
        tagList.innerHTML = f.tags.map((r) => optionHTML('data-tag', r.tag, r.tag, r.count)).join('');
      }
      if (outList && have(outList, 'out') !== f.outputs.map((r) => r.out).join('|')) {
        outList.innerHTML = f.outputs.map((r) => optionHTML('data-out', r.out, r.out, r.count, r.help.charAt(0).toUpperCase() + r.help.slice(1))).join('');
      }
      tools = next;
      total = tools.length;
      allTags = new Set(tools.flatMap((t) => (t.tags || []).map(fold)));
    }

    /* ---- state <-> URL ------------------------------------------------ */

    function readURL() {
      const p = new URLSearchParams(window.location.search);
      state.q = (p.get('q') || '').slice(0, 200);
      state.tag = fold(p.get('tag') || '');
      state.out = fold(p.get('out') || '');
      state.sort = SORTS[p.get('sort')] || 'newest';
    }

    function writeURL() {
      const p = new URLSearchParams();
      if (state.q.trim()) p.set('q', state.q.trim());
      if (state.tag) p.set('tag', state.tag);
      if (state.out) p.set('out', state.out);
      if (state.sort !== 'newest') p.set('sort', state.sort);
      const qs = p.toString();
      const url = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
      if (url !== window.location.pathname + window.location.search + window.location.hash) {
        try { window.history.replaceState(null, '', url); } catch (e) { /* file:// or sandboxed */ }
      }
    }

    // A filter the page does not offer (an old link to a tag that only one tool
    // has): that tag becomes a search, so the link still finds its tool.
    function settleFilters() {
      if (state.tag && !$$('.st-opt', tagList).some((o) => fold(o.dataset.tag) === state.tag)) {
        if (allTags.has(state.tag) && !state.q) {
          state.q = state.tag;
          if (input) input.value = state.q;
        }
        state.tag = '';
      }
      if (state.out && !$$('.st-opt', outList).some((o) => o.dataset.out === state.out)) state.out = '';
    }

    /* ---- apply -------------------------------------------------------- */

    let announceTimer = 0;
    function announce(text) {
      window.clearTimeout(announceTimer);
      announceTimer = window.setTimeout(() => { if (live) live.textContent = text; }, 650);
    }

    function apply({ animate = true } = {}) {
      settleFilters();
      const q = state.q.trim();
      const byQ = tools.filter((t) => matches(t._hay, q));
      const shown = ordered(byQ.filter((t) => hasTag(t) && hasOut(t)));
      const showIds = new Set(shown.map((t) => t.id));
      const cells = new Map(toolCells().map((c) => [c.dataset.id, c]));
      // Coming soon cards have no tags or outputs: a filter leaves them out.
      const soon = $$('.st-cell[data-soon]', grid);
      const soonShown = soon.filter((c) => !state.tag && !state.out && matches(soonHay(c), q));

      const mutate = () => {
        shown.forEach((t) => { const c = cells.get(t.id); if (c) { c.hidden = false; grid.appendChild(c); } });
        soon.forEach((c) => { c.hidden = !soonShown.includes(c); grid.appendChild(c); });
        cells.forEach((c, id) => { if (!showIds.has(id)) { c.hidden = true; grid.appendChild(c); } });
      };
      if (animate && !firstApply && !reduced() && 'animate' in Element.prototype) flip(mutate);
      else mutate();
      firstApply = false;

      // Which option is on, and how many tools it would leave given the rest.
      const byTag = byQ.filter(hasOut), byOut = byQ.filter(hasTag);
      const tagCount = new Map(), outCount = new Map();
      byTag.forEach((t) => (t.tags || []).forEach((x) => tagCount.set(fold(x), (tagCount.get(fold(x)) || 0) + 1)));
      byOut.forEach((t) => outsOf(t).forEach((o) => outCount.set(o, (outCount.get(o) || 0) + 1)));
      const paint = (opt, on, n) => {
        opt.setAttribute('aria-pressed', String(on));
        const count = $('.st-opt__n', opt);
        if (count) count.textContent = String(n);
        opt.toggleAttribute('data-empty', n === 0);
      };
      $$('.st-opt', tagList).forEach((o) => { const key = fold(o.dataset.tag); paint(o, key === state.tag, tagCount.get(key) || 0); });
      $$('.st-opt', outList).forEach((o) => { const key = o.dataset.out; paint(o, key === state.out, outCount.get(key) || 0); });
      $$('.st-opt', sortBox).forEach((o) => o.setAttribute('aria-pressed', String(o.value === state.sort)));

      const filtered = Boolean(q || state.tag || state.out);
      const n = shown.length + soonShown.length;
      if (countEl) {
        countEl.hidden = !filtered;
        countEl.textContent = filtered ? `${n} of ${total + soon.length}` : '';
      }
      // Said only in answer to the reader, not when the page loads.
      if (animate) announce(filtered ? `${n} of ${total + soon.length} tools` : `${total + soon.length} tools`);

      if (pill) {
        const label = [state.tag, state.out].filter(Boolean).join(' · ');
        pill.hidden = !label;
        if (pillLabel) pillLabel.textContent = label;
        pill.setAttribute('aria-label', label ? `Remove the filter ${label}` : '');
      }
      if (toggle) toggle.classList.toggle('is-on', Boolean(state.tag || state.out || state.sort !== 'newest'));
      shownCount = n;
      placeEnd();

      if (empty) {
        const none = n === 0 && total > 0;
        empty.hidden = !none;
        if (none) {
          emptyTitle.textContent = 'Nothing matches that';
          emptyText.textContent = 'Try a broader search, or clear the filter.';
          emptyAction.textContent = 'Clear search and filters';
          emptyAction.dataset.action = 'clear';
        }
      }
      writeURL();
    }

    /* ---- the closing block takes what the last row leaves free ---------- */

    const endBox = $('#end');
    let shownCount = 0;
    function placeEnd() {
      if (!endBox) return;
      const box = endBox.parentElement;
      const cols = getComputedStyle(box).gridTemplateColumns.split(' ').length;
      const free = shownCount ? (cols - (shownCount % cols)) % cols : 0;
      endBox.classList.toggle('st-end--beside', free > 0);
      endBox.style.setProperty('--st-end-col', free ? `span ${free}` : '1 / -1');
    }
    window.addEventListener('resize', placeEnd, { passive: true });

    /* ---- FLIP: cards travel to their new places ----------------------- */

    function flip(mutate) {
      $$('.st-ghost', grid).forEach((g) => g.remove());
      const cells = $$('.st-cell', grid);
      // Inside the zoomed page, lengths are in the zoomed unit.
      const k = scaleK();
      const gridBox = grid.parentElement.getBoundingClientRect();
      const before = new Map();
      cells.forEach((c) => { if (!c.hidden) before.set(c, c.getBoundingClientRect()); });
      cells.forEach((c) => c.getAnimations().forEach((a) => a.cancel()));
      mutate();
      const ease = 'cubic-bezier(0.22, 1, 0.36, 1)';
      let entering = 0;
      cells.forEach((c) => {
        const was = before.get(c);
        if (c.hidden) {
          if (!was) return;
          // A ghost fades where the card was, so leaving reads as leaving.
          const ghost = c.cloneNode(true);
          ghost.hidden = false;
          ghost.classList.add('st-ghost');
          ghost.setAttribute('aria-hidden', 'true');
          ghost.inert = true;
          Object.assign(ghost.style, {
            position: 'absolute', margin: '0', pointerEvents: 'none', zIndex: '0',
            left: `${(was.left - gridBox.left) / k}px`, top: `${(was.top - gridBox.top) / k}px`,
            width: `${was.width / k}px`, height: `${was.height / k}px`,
          });
          grid.appendChild(ghost);
          const anim = ghost.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.97)' }],
            { duration: 200, easing: 'cubic-bezier(0.64, 0, 0.78, 0)', fill: 'forwards' });
          anim.onfinish = () => ghost.remove();
          anim.oncancel = () => ghost.remove();
          return;
        }
        const now = c.getBoundingClientRect();
        if (was) {
          const dx = (was.left - now.left) / k, dy = (was.top - now.top) / k;
          if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
            c.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 420, easing: ease });
          }
        } else {
          c.animate([{ opacity: 0, transform: 'translateY(12px) scale(0.985)' }, { opacity: 1, transform: 'none' }],
            { duration: 360, easing: ease, delay: Math.min(entering++, 6) * 35, fill: 'backwards' });
        }
      });
    }

    /* ---- the filters panel --------------------------------------------- */

    // Beside the button, a press elsewhere closes the panel and does what it does. As
    // a sheet on a phone, the scrim takes the tap, so nothing under it is opened by it.
    function outsideDown(e) {
      if (!panel.contains(e.target) && !toggle.contains(e.target) && e.target !== scrim) closePanel(false);
    }

    function openPanel() {
      panel.hidden = false;
      if (scrim) scrim.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      doc.addEventListener('pointerdown', outsideDown, true);
      const first = $('.st-opt[aria-pressed="true"]:not([value])', panel) || $('.st-opt', panel);
      if (first) first.focus({ preventScroll: true });
    }

    function closePanel(refocus = true) {
      if (panel.hidden) return;
      panel.hidden = true;
      if (scrim) scrim.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      doc.removeEventListener('pointerdown', outsideDown, true);
      if (refocus) toggle.focus({ preventScroll: true });
    }

    if (toggle && panel) {
      toggle.addEventListener('click', () => { if (panel.hidden) openPanel(); else closePanel(); });
      panel.addEventListener('click', (e) => {
        const opt = e.target.closest('.st-opt');
        if (!opt) return;
        if (opt.dataset.tag !== undefined) {
          const v = fold(opt.dataset.tag);
          state.tag = state.tag === v ? '' : v;
        } else if (opt.dataset.out !== undefined) {
          state.out = state.out === opt.dataset.out ? '' : opt.dataset.out;
        } else if (opt.value) {
          state.sort = SORTS[opt.value] || 'newest';
        }
        apply();
      });
      // Arrows walk the options; Tab leaves, and leaving closes.
      panel.addEventListener('keydown', (e) => {
        const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
        if (!step) return;
        const opts = $$('.st-opt', panel);
        const i = opts.indexOf(doc.activeElement);
        if (i < 0) return;
        e.preventDefault();
        opts[(i + step + opts.length) % opts.length].focus();
      });
      panel.addEventListener('focusout', (e) => {
        const to = e.relatedTarget;
        if (to && !panel.contains(to) && !toggle.contains(to)) closePanel(false);
      });
      const closer = $('#filters-close');
      if (closer) closer.addEventListener('click', () => closePanel());
      if (scrim) scrim.addEventListener('click', () => closePanel());
      doc.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) closePanel(); });
    }

    /* ---- controls ------------------------------------------------------ */

    if (input) {
      input.addEventListener('input', () => { state.q = input.value; apply(); });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && input.value) {
          e.preventDefault();
          e.stopPropagation();
          input.value = '';
          state.q = '';
          apply();
        }
      });
    }
    if (form) form.addEventListener('submit', (e) => { e.preventDefault(); if (window.matchMedia('(pointer: coarse)').matches) input.blur(); });

    // "/" focuses the search, as in most catalogues; never while typing.
    doc.addEventListener('keydown', (e) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const el = doc.activeElement;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (!input) return;
      e.preventDefault();
      input.focus();
      input.select();
    });

    if (pill) pill.addEventListener('click', () => { state.tag = ''; state.out = ''; apply(); if (toggle) toggle.focus({ preventScroll: true }); });

    if (emptyAction) {
      emptyAction.addEventListener('click', () => {
        if (emptyAction.dataset.action === 'reload') { window.location.reload(); return; }
        state.q = '';
        state.tag = '';
        state.out = '';
        if (input) input.value = '';
        apply();
        if (input) input.focus();
      });
    }

    /* ---- the hero: the field, and the plate it is speaking of ---------- */

    const field = hero && window.STField ? window.STField.hero(hero) : null;
    if (hero && (!field || !field.drawn)) hero.classList.add('no-field');
    if (field) {
      const warm = (img) => field.warm(img.currentSrc || img.src);
      $$('img', grid).forEach((img) => {
        if (img.complete && img.naturalWidth) warm(img);
        else img.addEventListener('load', () => warm(img), { once: true });
      });
    }
    const nowName = $('#now-name');
    const nowDesc = $('#now-desc');
    const canHover = window.matchMedia('(hover: hover) and (pointer: fine)');
    let shownCell = null, restTimer = 0, leaveTimer = 0, lastScroll = -1e4;
    window.addEventListener('scroll', () => { lastScroll = performance.now(); }, { passive: true });

    // How much of the hero is on screen: whether its band has stuck under the top bar,
    // whether the hero's words still have their place, and how wide a picture is.
    function heroState() {
      if (!hero) return;
      const H = hero.offsetHeight;
      const k = scaleK();
      const band = 80 * k;
      const sticky = getComputedStyle(hero).position === 'sticky';
      const covered = sticky ? Math.max(0, Math.min(H - band, barBlock() - hero.getBoundingClientRect().top)) : 0;
      hero.classList.toggle('is-stuck', sticky && covered >= H - band - 1);
      hero.classList.toggle('is-compact', covered > 20 * k);
      const can = field && field.canShow();
      hero.style.setProperty('--st-pic-w', can ? `${((H - covered - 20 * k) * 12) / 7 / k}px` : '0px');
    }
    let stateFrame = 0;
    const queueState = () => { if (!stateFrame) stateFrame = requestAnimationFrame(() => { stateFrame = 0; heroState(); }); };
    window.addEventListener('scroll', queueState, { passive: true });
    window.addEventListener('resize', queueState, { passive: true });
    heroState();

    function preview(cell) {
      window.clearTimeout(leaveTimer);
      if (cell === shownCell) return;
      shownCell = cell;
      if (nowName) nowName.textContent = cell.dataset.name || '';
      const line = ($('.st-card__desc, .st-card__line', cell) || {}).textContent || '';
      if (nowDesc) nowDesc.textContent = line;
      // An unusually long description is set smaller rather than cut.
      if (hero) {
        hero.classList.toggle('is-long', line.length > 190);
        hero.classList.toggle('is-xlong', line.length > 420);
        hero.classList.toggle('is-long-name', (cell.dataset.name || '').length > 48);
      }
      if (hero) hero.classList.add('is-preview');
      const img = $('img', cell);
      if (!field) return;
      if (!img) { field.quiet(); return; }
      field.show(img.currentSrc || img.src).then((accent) => {
        // A number from the artwork's pixels, for the plate's edge.
        if (accent && cell.isConnected) cell.style.setProperty('--st-cell-art', accent);
      });
    }

    function release() {
      window.clearTimeout(restTimer);
      shownCell = null;
      if (hero) hero.classList.remove('is-preview');
      if (field) field.clear();
    }

    const previewing = () => canHover.matches && window.innerWidth >= 760;
    grid.addEventListener('pointerover', (e) => {
      if (e.pointerType !== 'mouse' || !previewing()) return;
      const cell = e.target.closest('.st-cell');
      if (!cell || cell.classList.contains('st-ghost')) return;
      // A plate reached by keyboard keeps the hero, whatever a parked pointer is over.
      const focused = $('.st-card:focus-visible', grid);
      if (focused && !cell.contains(focused)) return;
      window.clearTimeout(leaveTimer);
      window.clearTimeout(restTimer);
      // Resting, not crossing: a pointer on its way somewhere starts nothing, and
      // nor do plates passing under it while the page scrolls.
      const rest = () => {
        if (performance.now() - lastScroll < 120) restTimer = window.setTimeout(rest, 120);
        else preview(cell);
      };
      restTimer = window.setTimeout(rest, shownCell ? 60 : 110);
    });
    grid.addEventListener('pointerleave', (e) => {
      if (e.pointerType !== 'mouse') return;
      window.clearTimeout(restTimer);
      window.clearTimeout(leaveTimer);
      leaveTimer = window.setTimeout(release, 420);
    });
    grid.addEventListener('focusin', (e) => {
      if (!previewing() || !e.target.matches(':focus-visible')) return;
      const cell = e.target.closest('.st-cell');
      if (cell) preview(cell);
    });
    grid.addEventListener('focusout', (e) => {
      if (e.relatedTarget && grid.contains(e.relatedTarget)) return;
      window.clearTimeout(leaveTimer);
      leaveTimer = window.setTimeout(release, 200);
    });

    /* ---- boot ---------------------------------------------------------- */

    readURL();
    if (input) input.value = state.q;
    apply({ animate: false });

    fetch('data/tools-index.json', { cache: 'no-cache' })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((data) => {
        reconcile(data);
        apply({ animate: false });
      })
      .catch(() => {
        if (total > 0) return; // the pre-rendered cards keep working
        if (empty) {
          empty.hidden = false;
          emptyTitle.textContent = 'The tool list did not load';
          emptyText.textContent = 'Reload the page to try again.';
          emptyAction.textContent = 'Reload';
          emptyAction.dataset.action = 'reload';
        }
      });
  }

  /* ======================================================= tool page */

  function toolPage() {
    const host = $('.st-top');
    const plate = $('.st-artplate');
    const img = plate && $('img', plate);
    if (host && plate && img) {
      const reveal = () => plate.classList.add('is-shown');
      if (window.STField) window.STField.develop({ host, plate, img, onReveal: reveal });
      else reveal();
    }
    views();
    testSummary();
    formulas();
  }

  // The views: real links to real sections. Without JavaScript they are a list of
  // what is on the page; with it, a tab bar that shows one section at a time.
  function views() {
    const bar = $('#view-bar');
    const tabsBox = $('#view-tabs');
    if (!bar || !tabsBox) return;
    const tabs = $$('[data-view-link]', tabsBox);
    const ids = tabs.map((t) => t.dataset.viewLink);
    const panels = new Map(ids.map((id) => [id, doc.getElementById(id)]));
    const ind = doc.createElement('span');
    ind.className = 'st-tabs__ind';
    ind.setAttribute('aria-hidden', 'true');
    tabsBox.append(ind);
    tabsBox.setAttribute('role', 'tablist');
    tabs.forEach((t) => {
      const id = t.dataset.viewLink;
      t.id = `tab-${id}`;
      t.setAttribute('role', 'tab');
      t.setAttribute('aria-controls', id);
      const p = panels.get(id);
      if (p) { p.setAttribute('role', 'tabpanel'); p.setAttribute('aria-labelledby', t.id); }
    });

    function place() {
      const on = tabs.find((t) => t.getAttribute('aria-selected') === 'true');
      if (!on) return;
      ind.style.setProperty('--w', `${on.offsetWidth - 28}px`);
      ind.style.setProperty('--x', `${on.offsetLeft + 14}px`);
    }

    function show(view, { focus = false, scroll = false } = {}) {
      root.setAttribute('data-view', view);
      tabs.forEach((t) => {
        const on = t.dataset.viewLink === view;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        if (on && focus) t.focus();
      });
      place();
      // A view starts at its top, with the bar stuck above it: a press from the first
      // screen glides there, and from further down the view simply starts at its top.
      if (scroll) {
        const holder = bar.parentElement;
        const y = Math.max(0, holder.getBoundingClientRect().top + window.scrollY - barBlock());
        const glide = !bar.classList.contains('is-stuck') && !reduced();
        window.scrollTo({ top: y, behavior: glide ? 'smooth' : 'auto' });
      }
    }

    tabsBox.addEventListener('click', (e) => {
      const t = e.target.closest('[data-view-link]');
      if (!t) return;
      e.preventDefault();
      const view = t.dataset.viewLink;
      root.setAttribute('data-view-live', '');
      try { window.history.pushState(null, '', `#${view}`); } catch (err) { /* sandboxed */ }
      show(view, { scroll: true });
    });
    tabsBox.addEventListener('keydown', (e) => {
      const i = tabs.indexOf(doc.activeElement);
      if (i < 0) return;
      if (e.key === ' ') { e.preventDefault(); tabs[i].click(); return; }
      const last = tabs.length - 1;
      const next = { ArrowRight: i === last ? 0 : i + 1, ArrowLeft: i === 0 ? last : i - 1, Home: 0, End: last }[e.key];
      if (next === undefined) return;
      e.preventDefault();
      const view = ids[next];
      root.setAttribute('data-view-live', '');
      try { window.history.replaceState(null, '', `#${view}`); } catch (err) { /* sandboxed */ }
      show(view, { focus: true, scroll: true });
    });
    window.addEventListener('hashchange', () => {
      const h = window.location.hash.slice(1);
      if (ids.includes(h)) {
        show(h);
        const p = panels.get(h);
        if (p) p.scrollIntoView({ block: 'start' });
      }
    });
    window.addEventListener('popstate', () => {
      const h = window.location.hash.slice(1);
      show(ids.includes(h) ? h : ids[0], { scroll: true });
    });

    const first = root.getAttribute('data-view');
    show(ids.includes(first) ? first : ids[0]);
    if ('ResizeObserver' in window) new ResizeObserver(place).observe(tabsBox);
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(place);

    // Once the first screen has gone, the bar also says the name and offers Download.
    const top = $('.st-top');
    const nameEl = $('.st-bar__name', bar);
    const dl = $('.st-bar__dl', bar);
    const measure = () => {
      if (!nameEl) return;
      const k = scaleK();
      const w = nameEl.offsetParent ? nameEl.getBoundingClientRect().width / k + 24 : 0;
      bar.style.setProperty('--st-name-w', `${w}px`);
      if (dl) bar.style.setProperty('--st-dl-w', `${dl.getBoundingClientRect().width / k + 10}px`);
    };
    measure();
    window.addEventListener('resize', measure, { passive: true });
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(measure);
    if (top && 'IntersectionObserver' in window) {
      let io = null;
      const watch = () => {
        if (io) io.disconnect();
        const offset = Math.round(barBlock() + bar.offsetHeight);
        io = new IntersectionObserver(([entry]) => {
          const gone = !entry.isIntersecting && entry.boundingClientRect.top < offset;
          bar.classList.toggle('is-stuck', gone);
          bar.classList.toggle('is-gone', gone);
          if (dl) dl.tabIndex = gone ? 0 : -1;
        }, { rootMargin: `-${offset}px 0px 0px 0px`, threshold: 0 });
        io.observe(top);
      };
      watch();
      let settle = 0;
      window.addEventListener('resize', () => { window.clearTimeout(settle); settle = window.setTimeout(watch, 200); }, { passive: true });
    }
  }

  // Tool test summary: a modal dialog, so Escape closes it and focus comes back.
  function testSummary() {
    const dialog = $('#test-summary');
    const opener = $('#test-summary-open');
    if (!dialog || !opener || !dialog.showModal) return;
    // The address #tool-check belongs to this script now: left in place, the browser's
    // own jump to it would pull focus back out of the dialog.
    const anchor = $('#tool-check');
    if (anchor) anchor.removeAttribute('id');
    const open = () => { if (!dialog.open) dialog.showModal(); };
    opener.addEventListener('click', open);
    // On a phone the bar has room for the views only: the button stands with Download.
    const home = opener.parentElement, next = opener.nextSibling, spot = $('.st-get');
    const phone = window.matchMedia('(max-width: 759.98px)');
    const place = () => { if (phone.matches && spot) spot.append(opener); else home.insertBefore(opener, next); };
    phone.addEventListener('change', place);
    place();
    dialog.addEventListener('close', () => {
      opener.focus({ preventScroll: true });
      if (window.location.hash === '#tool-check') {
        try { window.history.replaceState(null, '', window.location.pathname + window.location.search); } catch (e) { /* sandboxed */ }
      }
    });
    dialog.addEventListener('click', (e) => {
      if (e.target === dialog || e.target.closest('[data-close-tests]')) dialog.close();
    });
    const fromAddress = () => { if (window.location.hash === '#tool-check') open(); };
    window.addEventListener('hashchange', fromAddress);
    fromAddress();
  }

  // A formula wider than its column scrolls: it takes focus (arrow keys scroll
  // it) and fades at the edge it continues past.
  function formulas() {
    const boxes = $$('.st-formula');
    if (!boxes.length) return;
    const check = (box) => {
      const scrolls = box.scrollWidth > box.clientWidth + 1;
      box.classList.toggle('is-scroll', scrolls);
      box.classList.toggle('is-end', scrolls && box.scrollLeft + box.clientWidth >= box.scrollWidth - 2);
      if (scrolls) box.tabIndex = 0; else box.removeAttribute('tabindex');
    };
    boxes.forEach((box) => {
      box.addEventListener('scroll', () => check(box), { passive: true });
      check(box);
    });
    if ('ResizeObserver' in window) {
      const ro = new ResizeObserver((entries) => entries.forEach((e) => check(e.target)));
      boxes.forEach((box) => ro.observe(box));
    }
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(() => boxes.forEach(check));
  }

  /* ======================================================= 404 */

  function notFound() {
    const lost = $('[data-st-404]');
    if (!lost) return;
    // GitHub Pages serves 404.html at the missing address. Under tools/, the
    // reader followed a link to a tool that is not (or no longer) listed.
    if (/\/tools\/[^/]+\/?$/.test(window.location.pathname)) {
      const t = $('[data-st-404-title]'), p = $('[data-st-404-text]');
      if (t) t.textContent = 'That tool is not here.';
      if (p) p.textContent = 'No published tool has this address.';
      doc.title = 'No tool here · The Tool Store · PointillViz';
    }
  }

  // On the 404 page this script is added by a script, so it may run before the
  // page is parsed.
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', main, { once: true });
  else main();
})();
