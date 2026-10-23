/*! store.pointillviz.com · store.js · no dependencies (uses window.PV from pv.js when present)
 *
 * Gallery (index.html): search, filters (shared tags and outputs), sort and count,
 * all in the browser over data/tools-index.json. The grid arrives pre-rendered by
 * tools/build_store_pages.py, so the page works and reads before this script runs;
 * this script reconciles the grid with the index (the source of truth) and then
 * filters and orders it.
 *
 * Tool pages: the "Install into PointillViz" placeholder explains installing from
 * the app, the section list follows the section in view, and a formula wider than
 * its column becomes a focusable scroller that fades where it continues.
 *
 * Every string in the index was written by a tool's author: it reaches the page
 * through esc() or textContent, never as markup.
 */
(() => {
  'use strict';

  const doc = document;
  const $ = (sel, ctx = doc) => ctx.querySelector(sel);
  const $$ = (sel, ctx = doc) => Array.from(ctx.querySelectorAll(sel));
  const reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => reduceMQ.matches;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  // Typographer's apostrophes in names and search alike: "ripley's" finds Ripley’s.
  const fold = (s) => String(s || '').toLowerCase().replace(/[\u2018\u2019]/g, "'");

  // A radio group of buttons: one tab stop; arrows, Home and End move and select.
  function radioKeys(group, onPick) {
    group.addEventListener('keydown', (e) => {
      const list = $$('[role="radio"]', group).filter((b) => b.offsetParent !== null);
      const i = list.indexOf(doc.activeElement);
      if (i < 0) return;
      const next = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: list.length - 1 }[e.key];
      if (next === undefined) return;
      e.preventDefault();
      const target = list[(next + list.length) % list.length];
      target.focus();
      onPick(target);
    });
  }

  function checkOne(group, chosen) {
    $$('[role="radio"]', group).forEach((b) => {
      const on = b === chosen;
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    });
  }

  function main() {
    installBox();
    if ($('#grid')) gallery();
    toolPage();
    notFound();
  }

  /* ======================================================= how installing works */

  // Folded to its one-line summary on every width; the reader opens it.
  function installBox() {
    const install = $('#install');
    const btn = install && $('.st-install__toggle', install);
    if (!btn) return;
    btn.addEventListener('click', () => {
      const open = !install.classList.contains('is-open');
      install.classList.toggle('is-open', open);
      btn.setAttribute('aria-expanded', String(open));
    });
  }

  /* ======================================================= gallery */

  function gallery() {
    const grid = $('#grid');
    const input = $('#q');
    const form = input && input.form;
    const tagList = $('#tag-list');
    const sortSeg = $('#sort');
    const countEl = $('#count');
    const live = $('#live');
    const empty = $('#empty');
    const emptyTitle = $('#empty-title');
    const emptyText = $('#empty-text');
    const emptyAction = $('#empty-action');
    const activeBtn = $('#active-tag');
    const toolbar = $('#toolbar');
    const sentinel = $('.st-sentinel');

    const SORTS = { popular: 'popular', newest: 'newest', name: 'name' };
    const state = { q: '', tag: '', out: '', sort: 'popular' };
    let tools = modelFromDom();
    let total = tools.length;
    let allTags = new Set(tools.flatMap((t) => t.tags.map(fold)));
    let hiddenOutputs = [];
    let firstApply = true;

    /* ---- the model -------------------------------------------------- */

    function searchText(t) {
      return fold([t.name, t.description, t.author, t.id, (t.tags || []).join(' ')].join(' '));
    }

    // Until the index arrives (or if it cannot), the pre-rendered cards carry
    // everything search, filters and sort need.
    function modelFromDom() {
      return $$('.st-cell', grid).map((cell) => {
        const t = {
          id: cell.dataset.id,
          name: cell.dataset.name || ($('.pv-card__link', cell) || {}).textContent || '',
          description: ($('.st-card__desc', cell) || {}).textContent || '',
          author: ($('.st-card__author', cell) || {}).textContent || '',
          tags: (cell.dataset.tags || '').split('|').filter(Boolean),
          outputs: (cell.dataset.outputs || '').split('|').filter(Boolean),
          optional_outputs: [],
          downloads: +cell.dataset.downloads || 0,
          published: cell.dataset.published || '',
          version: cell.dataset.version || '',
        };
        t._hay = searchText(t);
        return t;
      });
    }

    function matches(t, q) {
      if (!q) return true;
      // Every word must match, as in the local store: "spatial entropy" should
      // not return a tool that is merely spatial.
      return fold(q).split(/\s+/).filter(Boolean).every((w) => t._hay.includes(w));
    }

    const outsOf = (t) => (t.outputs || []).concat(t.optional_outputs || []);
    const passes = (t) => (!state.tag || (t.tags || []).some((x) => fold(x) === state.tag))
      && (!state.out || outsOf(t).includes(state.out));

    // Popular: downloads, then the newest, then name (as the pre-rendered grid).
    // Newest: the day published, then name; tools published together stay A–Z.
    function ordered(list) {
      const byName = (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
      const out = list.slice();
      if (state.sort === 'name') out.sort(byName);
      else if (state.sort === 'newest') {
        out.sort((a, b) => {
          const da = a.published.slice(0, 10), db = b.published.slice(0, 10);
          return da < db ? 1 : da > db ? -1 : byName(a, b);
        });
      } else {
        out.sort((a, b) => (b.downloads - a.downloads)
          || (a.published < b.published ? 1 : a.published > b.published ? -1 : byName(a, b)));
      }
      return out;
    }

    /* ---- rendering (mirrors card_html in tools/build_store_pages.py) --- */

    const VERIFIED_TIP = 'Passed every required gate when this version was published. That is a statement about the gates, not about whether the code is safe to run.';
    const UNVERIFIED_TIP = 'This version has no passing gate report on file.';

    function dotState(status, required) {
      if (status === 'fail') return 'fail';
      if (status === 'skip') return 'skip';
      if (!required) return status === 'warn' ? 'flag' : 'adv';
      return 'pass';
    }

    function badgeHTML(t) {
      const dots = (t.strip || []).map(([, s, r]) => `<i data-s="${dotState(s, r)}"></i>`).join('');
      const totalGates = t.gates_total || 9;
      const sr = `<span class="pv-sr-only">: passed ${t.gates_passed || 0} of ${totalGates} gates</span>`;
      return t.verified
        ? `<span class="st-vbadge" title="${esc(VERIFIED_TIP)}"><span class="st-vbadge__dots" aria-hidden="true">${dots}</span>Verified${sr}</span>`
        : `<span class="st-vbadge st-vbadge--no" title="${esc(UNVERIFIED_TIP)}"><span class="st-vbadge__dots" aria-hidden="true">${dots}</span>Unverified${sr}</span>`;
    }

    function cardHTML(t) {
      const a = t.art || {};
      const outs = outsOf(t).filter((o) => !hiddenOutputs.includes(o)).map((o) =>
        `<li class="pv-tag pv-tag--out" title="${esc((t.output_help || {})[o] || o)}">${esc(o)}</li>`).join('');
      const risks = (t.risks || []).map((r) =>
        `<span class="st-risk" title="Disclosed by the advisory imports gate: this tool ${esc(r.text)}. A tool can pass every gate and still do this.">${esc(r.label)}</span>`).join('');
      const dl = t.downloads || 0;
      const sizes = '(max-width: 519.98px) 112px, (min-width: 1280px) 340px, (min-width: 900px) 31vw, (min-width: 600px) 46vw, 92vw';
      return `<article class="pv-card pv-card--link st-card">
  <div class="st-card__art"><img src="${esc(a.src)}" srcset="${esc(a.src)} ${a.width}w, ${esc(a.src2x)} ${a.width * 2}w" sizes="${sizes}" width="${a.width}" height="${a.height}" alt="" loading="lazy" decoding="async"></div>
  <h3 class="pv-card__title st-card__title"><a class="pv-card__link" href="${esc(t.url)}">${esc(t.name)}</a></h3>
  <p class="pv-card__meta st-card__by"><span class="st-card__author">${esc(t.author)}</span> <time class="st-card__date" datetime="${esc((t.published || '').slice(0, 10))}">${esc(t.published_date)}</time></p>
  <p class="pv-card__body st-card__desc">${esc(t.description)}</p>
  <ul class="pv-tags st-card__outs" aria-label="Outputs">${outs}</ul>
  <div class="pv-card__foot st-card__foot">
    ${badgeHTML(t)}${risks}
    <span class="st-card__ver" title="Version">v${esc(t.version)}</span>
    <span class="st-card__dl" title="${plural(dl, 'download')}"><svg class="st-card__dl-i" aria-hidden="true"><use href="assets/pv/icons.svg#i-download"/></svg><span aria-hidden="true">${dl}</span><span class="pv-sr-only">${plural(dl, 'download')}</span></span>
  </div>
</article>`;
    }

    function setCellData(cell, t) {
      cell.dataset.id = t.id;
      cell.dataset.name = t.name;
      cell.dataset.tags = (t.tags || []).join('|');
      cell.dataset.outputs = outsOf(t).join('|');
      cell.dataset.downloads = String(t.downloads || 0);
      cell.dataset.published = t.published || '';
      cell.dataset.version = t.version || '';
    }

    function filtersHTML(data) {
      const f = data.filters || { tags: [], outputs: [] };
      const chip = (attr, value, label, count, extra = '') =>
        `<button class="pv-chip st-chip${extra}" type="button" role="radio" aria-checked="false" tabindex="-1" ${attr}="${esc(value)}">${label} <span class="pv-chip__count">${count}</span></button>`;
      const tags = [chip('data-tag', '', 'All', data.count)].concat(f.tags.map((r) => chip('data-tag', r.tag, esc(r.tag), r.count)));
      const groups = [`<div class="st-tags__group">${tags.join('\n')}</div>`];
      if (f.outputs.length) {
        const outs = ['<span class="st-tags__sep" aria-hidden="true">Outputs</span>'].concat(f.outputs.map((r) =>
          chip('data-out', r.out, `<span class="pv-sr-only">Output: </span>${esc(r.out)}`, r.count, ' st-chip--out')
            .replace('type="button"', `type="button" title="${esc(r.help.charAt(0).toUpperCase() + r.help.slice(1))}"`)));
        groups.push(`<div class="st-tags__group st-tags__group--out">${outs.join('\n')}</div>`);
      }
      return groups.join('\n');
    }

    // The index is the source of truth: keep the cards that match it, re-render
    // the ones it changed, add the ones the static page did not have.
    function reconcile(data) {
      hiddenOutputs = data.card_hidden_outputs || [];
      const byId = new Map($$('.st-cell', grid).map((c) => [c.dataset.id, c]));
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
      const f = data.filters || { tags: [], outputs: [] };
      const have = $$('.st-chip', tagList).map((c) => (c.dataset.out ? `o:${c.dataset.out}` : `t:${c.dataset.tag}`)).join('|');
      const want = ['t:'].concat(f.tags.map((r) => `t:${r.tag}`), f.outputs.map((r) => `o:${r.out}`)).join('|');
      if (have !== want) tagList.innerHTML = filtersHTML(data);
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
      state.sort = SORTS[p.get('sort')] || 'popular';
    }

    function writeURL() {
      const p = new URLSearchParams();
      if (state.q.trim()) p.set('q', state.q.trim());
      if (state.tag) p.set('tag', state.tag);
      if (state.out) p.set('out', state.out);
      if (state.sort !== 'popular') p.set('sort', state.sort);
      const qs = p.toString();
      const url = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
      if (url !== window.location.pathname + window.location.search + window.location.hash) {
        try { window.history.replaceState(null, '', url); } catch (e) { /* file:// or sandboxed */ }
      }
    }

    // A filter the page does not offer (an old link to a tag that only one tool
    // has): that tag becomes a search, so the link still finds its tool.
    function settleFilters() {
      const chips = $$('.st-chip', tagList);
      if (state.tag && !chips.some((c) => c.dataset.tag && fold(c.dataset.tag) === state.tag)) {
        if (allTags.has(state.tag) && !state.q) {
          state.q = state.tag;
          if (input) input.value = state.q;
        }
        state.tag = '';
      }
      if (state.out && !chips.some((c) => c.dataset.out === state.out)) state.out = '';
      if (state.tag && state.out) state.out = '';
    }

    /* ---- apply -------------------------------------------------------- */

    let announceTimer = 0;
    function announce(text) {
      window.clearTimeout(announceTimer);
      announceTimer = window.setTimeout(() => { if (live) live.textContent = text; }, 650);
    }

    function countText(n, filtered) {
      if (!filtered) return `${plural(n, 'tool')} published`;
      return n === 1 ? '1 tool matching' : `${n} tools matching`;
    }

    function apply({ animate = true } = {}) {
      settleFilters();
      const q = state.q.trim();
      const byQ = tools.filter((t) => matches(t, q));
      const shown = ordered(byQ.filter(passes));
      const showIds = new Set(shown.map((t) => t.id));
      const cells = new Map($$('.st-cell', grid).map((c) => [c.dataset.id, c]));

      const mutate = () => {
        grid.dataset.sort = state.sort;
        shown.forEach((t) => { const c = cells.get(t.id); if (c) { c.hidden = false; grid.appendChild(c); } });
        cells.forEach((c, id) => { if (!showIds.has(id)) { c.hidden = true; grid.appendChild(c); } });
      };
      if (animate && !firstApply && !reduced() && 'animate' in Element.prototype) flip(mutate);
      else mutate();
      firstApply = false;

      // Filters: which one is checked, and how many tools each would leave given the search.
      const tagCount = new Map(), outCount = new Map();
      byQ.forEach((t) => {
        (t.tags || []).forEach((x) => tagCount.set(fold(x), (tagCount.get(fold(x)) || 0) + 1));
        outsOf(t).forEach((o) => outCount.set(o, (outCount.get(o) || 0) + 1));
      });
      let checked = null;
      $$('.st-chip', tagList).forEach((chip) => {
        const isOut = chip.dataset.out !== undefined;
        const key = isOut ? chip.dataset.out : fold(chip.dataset.tag || '');
        const on = isOut ? key === state.out : (key ? key === state.tag : !state.tag && !state.out);
        if (on) checked = chip;
        const n = isOut ? (outCount.get(key) || 0) : key ? (tagCount.get(key) || 0) : byQ.length;
        const count = $('.pv-chip__count', chip);
        if (count) count.textContent = String(n);
        chip.toggleAttribute('data-empty', n === 0);
      });
      checkOne(tagList, checked || $('.st-chip', tagList));

      const filtered = Boolean(q || state.tag || state.out);
      const text = countText(shown.length, filtered);
      if (countEl) countEl.textContent = text;
      announce(text);

      if (activeBtn) {
        const label = state.tag || state.out;
        activeBtn.hidden = !label;
        const lab = $('.st-active__label', activeBtn);
        if (lab) lab.textContent = label;
        activeBtn.setAttribute('aria-label', label ? `Remove the filter ${label}` : '');
      }

      if (empty) {
        const none = shown.length === 0 && total > 0;
        empty.hidden = !none;
        if (none) {
          emptyTitle.textContent = 'Nothing matches that';
          emptyText.textContent = 'Try a broader search, or clear the tag filter.';
          emptyAction.textContent = 'Clear search and filters';
          emptyAction.dataset.action = 'clear';
        }
      }
      writeURL();
    }

    /* ---- FLIP: cards travel to their new places ----------------------- */

    function flip(mutate) {
      $$('.st-ghost', grid).forEach((g) => g.remove());
      const cells = $$('.st-cell', grid);
      const gridBox = grid.getBoundingClientRect();
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
            left: `${was.left - gridBox.left}px`, top: `${was.top - gridBox.top}px`,
            width: `${was.width}px`, height: `${was.height}px`,
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
          const dx = was.left - now.left, dy = was.top - now.top;
          if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
            c.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 420, easing: ease });
          }
        } else {
          c.animate([{ opacity: 0, transform: 'translateY(12px) scale(0.985)' }, { opacity: 1, transform: 'none' }],
            { duration: 360, easing: ease, delay: Math.min(entering++, 6) * 35, fill: 'backwards' });
        }
      });
    }

    /* ---- controls ------------------------------------------------------ */

    function pickChip(chip) {
      if (chip.dataset.out !== undefined) { state.out = chip.dataset.out; state.tag = ''; }
      else { state.tag = fold(chip.dataset.tag || ''); state.out = ''; }
      apply();
    }

    if (tagList) {
      tagList.addEventListener('click', (e) => {
        const chip = e.target.closest('.st-chip');
        if (chip) pickChip(chip);
      });
      radioKeys(tagList, pickChip);
    }

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

    // Sort: a radio group, drawn as the system's segmented control with its thumb.
    let placeThumb = () => {};
    if (sortSeg) {
      const buttons = $$('[role="radio"]', sortSeg);
      const thumb = doc.createElement('span');
      thumb.className = 'pv-seg__thumb';
      thumb.setAttribute('aria-hidden', 'true');
      sortSeg.prepend(thumb);
      placeThumb = (instant) => {
        const on = buttons.find((b) => b.getAttribute('aria-checked') === 'true');
        if (!on) return;
        if (instant) thumb.style.transition = 'none';
        thumb.style.width = `${on.offsetWidth}px`;
        thumb.style.transform = `translateX(${on.offsetLeft}px)`;
        if (instant) { thumb.getBoundingClientRect(); thumb.style.transition = ''; }
      };
      const pickSort = (b) => {
        if (b.getAttribute('aria-checked') === 'true') return;
        checkOne(sortSeg, b);
        placeThumb(false);
        state.sort = SORTS[b.value] || 'popular';
        apply();
      };
      buttons.forEach((b) => b.addEventListener('click', () => pickSort(b)));
      radioKeys(sortSeg, pickSort);
      if ('ResizeObserver' in window) new ResizeObserver(() => placeThumb(true)).observe(sortSeg);
    }

    if (activeBtn) activeBtn.addEventListener('click', () => { state.tag = ''; state.out = ''; apply(); if (input) input.focus(); });

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

    // The bar takes its glass and dotted rule only once it is stuck, and only
    // where it sticks (not on phones, where it scrolls with the page).
    if (toolbar && sentinel && 'IntersectionObserver' in window) {
      const wide = window.matchMedia('(min-width: 760px)');
      let io = null;
      let barH = 0;
      // The room the top bar takes: its height times the large-screen chrome
      // scale --k (pv.css: --pv-topbar-block).
      const bar = () => {
        const css = getComputedStyle(doc.documentElement);
        return Math.round((parseFloat(css.getPropertyValue('--pv-topbar-h')) || 64) * (parseFloat(css.getPropertyValue('--k')) || 1));
      };
      const observe = () => {
        if (io) { io.disconnect(); io = null; }
        toolbar.classList.remove('is-stuck');
        if (!wide.matches) return;
        const h = barH = bar();
        io = new IntersectionObserver(([entry]) => {
          toolbar.classList.toggle('is-stuck', !entry.isIntersecting && entry.boundingClientRect.top < h + 2);
        }, { rootMargin: `-${h + 1}px 0px 0px 0px`, threshold: 0 });
        io.observe(sentinel);
      };
      observe();
      wide.addEventListener('change', observe);
      // A window resized across 1440 x 900 changes the bar's height (pv.js
      // updates --k on the next frame; check once the resizing settles).
      let settle = 0;
      window.addEventListener('resize', () => {
        window.clearTimeout(settle);
        settle = window.setTimeout(() => { if (wide.matches && bar() !== barH) observe(); }, 200);
      }, { passive: true });
    }

    /* ---- boot ---------------------------------------------------------- */

    readURL();
    if (input) input.value = state.q;
    if (sortSeg) {
      const b = $(`[role="radio"][value="${state.sort}"]`, sortSeg);
      if (b) checkOne(sortSeg, b);
      placeThumb(true);
      sortSeg.classList.add('is-ready');
    }
    apply({ animate: false });
    if (live) live.textContent = '';

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
        if (countEl) countEl.textContent = '';
      });
  }

  /* ======================================================= tool page */

  function toolPage() {
    const installBtn = $('[data-st-install]');
    if (installBtn) {
      const panel = doc.getElementById(installBtn.getAttribute('aria-controls'));
      installBtn.addEventListener('click', () => {
        const open = installBtn.getAttribute('aria-expanded') !== 'true';
        installBtn.setAttribute('aria-expanded', String(open));
        if (!panel) return;
        panel.hidden = !open;
        panel.classList.toggle('is-in', open);
      });
    }

    const onpage = $('.st-onpage');
    if (onpage && 'IntersectionObserver' in window) {
      const links = $$('a[href^="#"]', onpage);
      const rail = $('ul', onpage);
      const secs = links.map((a) => doc.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
      const visible = new Map();
      let current = null;
      const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => visible.set(e.target.id, e.isIntersecting));
        const first = secs.find((s) => visible.get(s.id));
        if (!first || first === current) return;
        current = first;
        links.forEach((a) => {
          const on = a.getAttribute('href') === `#${first.id}`;
          if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
          // In the row of pills, keep the current one in view.
          if (on && rail && rail.scrollWidth > rail.clientWidth + 1) {
            a.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
          }
        });
      }, { rootMargin: '-30% 0px -55% 0px' });
      secs.forEach((s) => io.observe(s));
    }

    // A formula wider than its column scrolls: it takes focus (arrow keys
    // scroll it) and fades at the edge it continues past.
    const formulas = $$('.st-formula');
    if (formulas.length) {
      const check = (box) => {
        const scrolls = box.scrollWidth > box.clientWidth + 1;
        box.classList.toggle('is-scroll', scrolls);
        box.classList.toggle('is-end', scrolls && box.scrollLeft + box.clientWidth >= box.scrollWidth - 2);
        if (scrolls) box.tabIndex = 0; else box.removeAttribute('tabindex');
      };
      formulas.forEach((box) => {
        box.addEventListener('scroll', () => check(box), { passive: true });
        check(box);
      });
      if ('ResizeObserver' in window) {
        const ro = new ResizeObserver((entries) => entries.forEach((e) => check(e.target)));
        formulas.forEach((box) => ro.observe(box));
      }
      if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(() => formulas.forEach(check));
    }
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
