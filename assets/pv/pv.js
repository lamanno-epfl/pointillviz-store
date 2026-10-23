/*! PointillViz shared behaviour · pv.js · v1.1 (2026-10-23) · no dependencies
 *
 * Load once, deferred:  <script src="assets/pv/pv.js" defer></script>
 * Everything is opt-in through markup (see WEB/shared/DESIGN_SYSTEM.md):
 *
 *   [data-pv-drawer-open="id"]   opens <dialog class="pv-drawer" id="id">
 *   [data-pv-drawer-close]       closes the drawer it sits in
 *   [data-pv-reveal]             fades up once when scrolled into view
 *   [data-pv-reveal="stagger"]   the same, child by child
 *   [data-pv-copy]               copies the code of its .pv-code (or a selector)
 *   [data-pv-theme-toggle]       switches dark / light, remembered per browser
 *   [data-pv-tabs]               role=tablist tabs with a sliding indicator
 *   [data-pv-seg]                segmented control (buttons with aria-pressed)
 *   [data-placeholder="code|paper|trailer|install|…"]
 *                                not available yet: the click opens a toast
 *
 * Always on: the large-screen chrome scale (--k on <html>, CHROME.md §1),
 * the top bar's scrolled state, and one sweep of each skeleton in view.
 *
 * API (window.PV): toast(), setTheme(), theme(), reveal(root), tabs(root),
 * seg(root), copy(text), reducedMotion().
 * Events: "pv:themechange" on document; "pv:tabchange" and "pv:change"
 * bubble from the tabs or segmented control that changed.
 */
(() => {
  'use strict';

  const doc = document;
  const root = doc.documentElement;
  const $$ = (sel, ctx = doc) => Array.from(ctx.querySelectorAll(sel));
  const reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reducedMotion = () => reduceMQ.matches;

  // Storage can throw (private windows, blocked site data): never let it.
  const store = {
    get(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* not remembered */ } },
  };

  const ICON = {
    close: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  };

  /* ---------------------------------------------------------------- live */

  let live;
  function announce(message) {
    if (!live) {
      live = doc.createElement('div');
      live.className = 'pv-live';
      live.setAttribute('aria-live', 'polite');
      doc.body.appendChild(live);
    }
    live.textContent = '';
    window.setTimeout(() => { live.textContent = message; }, 60);
  }

  /* --------------------------------------------------------------- theme */

  const THEME_KEY = 'pv-theme';
  const theme = () => (root.getAttribute('data-theme') === 'light' ? 'light' : 'dark');

  // The toggle's name says what a press does ("Switch to dark theme"), so it
  // carries no aria-pressed: a name that flips and a pressed state would
  // contradict each other. The browser's own chrome keeps the colour of the
  // top bar, which is ink in both themes (the frame is ink, the column paper).
  function syncTheme() {
    const light = theme() === 'light';
    $$('[data-pv-theme-toggle]').forEach((btn) => {
      const label = light ? 'Switch to dark theme' : 'Switch to light theme';
      btn.removeAttribute('aria-pressed');
      btn.setAttribute('aria-label', label);
      btn.title = label;
    });
    const meta = doc.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', light ? '#0A0C18' : '#06070D');
  }

  function setTheme(next, { persist = true } = {}) {
    const value = next === 'light' ? 'light' : 'dark';
    const apply = () => {
      root.setAttribute('data-theme', value);
      syncTheme();
      doc.dispatchEvent(new CustomEvent('pv:themechange', { detail: { theme: value } }));
    };
    if (persist) store.set(THEME_KEY, value);
    // A cross-fade where the browser can do it for free; instant otherwise.
    if (doc.startViewTransition && !reducedMotion() && value !== theme()) doc.startViewTransition(apply);
    else apply();
  }

  function initTheme() {
    const toggles = $$('[data-pv-theme-toggle]');
    if (!toggles.length) return; // only pages that offer a choice follow a stored one
    const saved = store.get(THEME_KEY);
    if ((saved === 'light' || saved === 'dark') && saved !== theme()) root.setAttribute('data-theme', saved);
    toggles.forEach((btn) => btn.addEventListener('click', () => setTheme(theme() === 'light' ? 'dark' : 'light')));
    syncTheme();
  }

  /* -------------------------------------------------------------- drawer */

  const openers = new WeakMap();

  function openDrawer(dlg, opener) {
    if (!dlg || dlg.open || typeof dlg.showModal !== 'function') return;
    dlg.classList.remove('is-closing');
    openers.set(dlg, opener || null);
    dlg.showModal();
    root.classList.add('pv-scroll-lock');
    if (opener) opener.setAttribute('aria-expanded', 'true');
  }

  function closeDrawer(dlg) {
    if (!dlg || !dlg.open || dlg.classList.contains('is-closing')) return;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      dlg.classList.remove('is-closing');
      dlg.close();
    };
    dlg.classList.add('is-closing');
    const panel = dlg.querySelector('.pv-drawer__panel');
    if (panel) panel.addEventListener('transitionend', (e) => { if (e.target === panel) finish(); });
    window.setTimeout(finish, 320);
  }

  function initDrawers() {
    $$('dialog.pv-drawer').forEach((dlg) => {
      dlg.addEventListener('cancel', (e) => { e.preventDefault(); closeDrawer(dlg); }); // Esc
      dlg.addEventListener('click', (e) => {
        if (e.target === dlg) { closeDrawer(dlg); return; } // the backdrop
        if (e.target.closest('[data-pv-drawer-close]')) { closeDrawer(dlg); return; }
        // Any link closes it; a placeholder's toast then shows above the page.
        if (e.target.closest('a[href]')) closeDrawer(dlg);
      });
      dlg.addEventListener('close', () => {
        root.classList.remove('pv-scroll-lock');
        const opener = openers.get(dlg);
        if (opener) {
          opener.setAttribute('aria-expanded', 'false');
          // Openers sit in sticky bars: focusing one must not scroll the page
          // away from the place the reader just chose.
          const a = doc.activeElement;
          if (!a || a === doc.body || dlg.contains(a)) opener.focus({ preventScroll: true });
        }
      });
    });
    $$('[data-pv-drawer-open]').forEach((btn) => {
      const id = btn.getAttribute('data-pv-drawer-open') || btn.getAttribute('aria-controls');
      const dlg = id && doc.getElementById(id);
      if (dlg) btn.addEventListener('click', () => openDrawer(dlg, btn));
    });
    // Widening past the breakpoint retires the drawer.
    window.matchMedia('(min-width: 760px)').addEventListener('change', (e) => {
      if (e.matches) $$('dialog.pv-drawer[open]').forEach(closeDrawer);
    });
  }

  /* -------------------------------------------------------------- reveal */

  let revealIO = null;

  function reveal(scope = doc) {
    const els = $$('[data-pv-reveal]', scope).filter((el) => !el.classList.contains('is-in'));
    els.forEach((el) => {
      if (el.getAttribute('data-pv-reveal') === 'stagger') {
        Array.from(el.children).forEach((child, i) => child.style.setProperty('--pv-i', String(Math.min(i, 6))));
      }
    });
    if (!('IntersectionObserver' in window) || reducedMotion()) {
      els.forEach((el) => el.classList.add('is-in'));
      return;
    }
    // Whatever is already on screen stays as it is: no flash, no wait.
    const vh = window.innerHeight || root.clientHeight;
    const pending = [];
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.top < vh * 0.92 && r.bottom > 0) el.classList.add('is-in');
      else pending.push(el);
    });
    if (!revealIO) {
      revealIO = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-in');
            revealIO.unobserve(entry.target);
          }
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    }
    pending.forEach((el) => revealIO.observe(el));
  }

  /* ---------------------------------------------------------------- copy */

  async function copy(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) { /* fall through */ }
    const ta = doc.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:-1000px;left:0;opacity:0';
    doc.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = doc.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  function initCopy() {
    doc.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-pv-copy]');
      if (!btn) return;
      const sel = btn.getAttribute('data-pv-copy');
      const box = btn.closest('.pv-code');
      const src = sel ? doc.querySelector(sel) : box && box.querySelector('pre code, pre');
      if (!src) return;
      const ok = await copy(src.innerText.replace(/\n$/, ''));
      const label = btn.querySelector('.pv-code__copy-label');
      if (label && !label.dataset.text) label.dataset.text = label.textContent;
      btn.setAttribute('data-copied', String(ok));
      if (label) label.textContent = ok ? 'Copied' : 'Select and copy';
      announce(ok ? 'Copied to the clipboard.' : 'Copy failed. Select the code and copy it.');
      window.clearTimeout(btn._pvTimer);
      btn._pvTimer = window.setTimeout(() => {
        btn.removeAttribute('data-copied');
        if (label) label.textContent = label.dataset.text;
      }, 1800);
    });
  }

  /* ---------------------------------------------------------------- tabs */

  function setupTabs(box) {
    if (box._pvTabs) return;
    box._pvTabs = true;
    const list = box.querySelector('[role="tablist"]');
    if (!list) return;
    const tabs = $$('[role="tab"]', list);
    if (!tabs.length) return;
    let ind = list.querySelector('.pv-tabs__ind');
    if (!ind) {
      ind = doc.createElement('span');
      ind.className = 'pv-tabs__ind';
      ind.setAttribute('aria-hidden', 'true');
      list.appendChild(ind);
    }
    const place = (tab) => {
      ind.style.transform = `translateX(${tab.offsetLeft}px) scaleX(${tab.offsetWidth})`;
    };
    const select = (i, focus) => {
      tabs.forEach((tab, j) => {
        const on = j === i;
        tab.setAttribute('aria-selected', String(on));
        tab.tabIndex = on ? 0 : -1;
        const panel = doc.getElementById(tab.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
      place(tabs[i]);
      if (focus) {
        tabs[i].focus();
        tabs[i].scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
      box.dispatchEvent(new CustomEvent('pv:tabchange', { bubbles: true, detail: { index: i, tab: tabs[i] } }));
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => select(i, false));
      tab.addEventListener('keydown', (e) => {
        const last = tabs.length - 1;
        const next = { ArrowRight: i === last ? 0 : i + 1, ArrowLeft: i === 0 ? last : i - 1, Home: 0, End: last }[e.key];
        if (next === undefined) return;
        e.preventDefault();
        select(next, true);
      });
    });
    const current = Math.max(0, tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true'));
    tabs.forEach((tab, j) => { tab.tabIndex = j === current ? 0 : -1; });
    place(tabs[current]);
    list.classList.add('is-ready');
    if ('ResizeObserver' in window) {
      new ResizeObserver(() => place(tabs[Math.max(0, tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true'))])).observe(list);
    }
  }
  const initTabs = (scope = doc) => $$('[data-pv-tabs]', scope).forEach(setupTabs);

  /* ----------------------------------------------------------- segmented */

  function setupSeg(seg) {
    if (seg._pvSeg) return;
    seg._pvSeg = true;
    const buttons = $$(':scope > button', seg);
    if (!buttons.length) return;
    const thumb = doc.createElement('span');
    thumb.className = 'pv-seg__thumb';
    thumb.setAttribute('aria-hidden', 'true');
    seg.prepend(thumb);
    const place = () => {
      const on = buttons.find((b) => b.getAttribute('aria-pressed') === 'true');
      thumb.style.opacity = on ? '1' : '0';
      if (!on) return;
      thumb.style.width = `${on.offsetWidth}px`;
      thumb.style.transform = `translateX(${on.offsetLeft}px)`;
    };
    buttons.forEach((btn) => btn.addEventListener('click', () => {
      if (btn.getAttribute('aria-pressed') === 'true') return;
      buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
      place();
      seg.dispatchEvent(new CustomEvent('pv:change', {
        bubbles: true,
        detail: { value: btn.value || btn.getAttribute('data-value') || btn.textContent.trim(), button: btn },
      }));
    }));
    // First placement without travel.
    thumb.style.transition = 'none';
    place();
    thumb.getBoundingClientRect();
    thumb.style.transition = '';
    seg.classList.add('is-ready');
    if ('ResizeObserver' in window) new ResizeObserver(place).observe(seg);
  }
  const initSeg = (scope = doc) => $$('[data-pv-seg]', scope).forEach(setupSeg);

  /* -------------------------------------------------------------- toasts */

  let toaster;
  function getToaster() {
    if (!toaster) {
      toaster = doc.createElement('div');
      toaster.className = 'pv-toaster';
      toaster.setAttribute('role', 'status');
      toaster.setAttribute('aria-live', 'polite');
      doc.body.appendChild(toaster);
    }
    return toaster;
  }

  function dismiss(t) {
    if (!t || t._pvGone) return;
    t._pvGone = true;
    window.clearTimeout(t._pvTimer);
    t.classList.remove('is-in');
    t.classList.add('is-out');
    window.setTimeout(() => t.remove(), 200);
  }

  function arm(t, ms) {
    window.clearTimeout(t._pvTimer);
    t._pvTimer = window.setTimeout(() => dismiss(t), ms);
  }

  function toast({ title = 'Coming soon', message = '', tone = 'soon', key = '', duration = 4500 } = {}) {
    const box = getToaster();
    const same = key && Array.from(box.children).find((el) => el.dataset.key === key && !el._pvGone);
    if (same) { arm(same, duration); return same; }

    const t = doc.createElement('div');
    t.className = 'pv-toast';
    t.dataset.tone = tone;
    if (key) t.dataset.key = key;
    const dot = doc.createElement('span');
    dot.className = 'pv-toast__dot';
    dot.setAttribute('aria-hidden', 'true');
    const body = doc.createElement('div');
    const h = doc.createElement('p');
    h.className = 'pv-toast__title';
    h.textContent = title;
    body.appendChild(h);
    if (message) {
      const p = doc.createElement('p');
      p.className = 'pv-toast__msg';
      p.textContent = message;
      body.appendChild(p);
    }
    const close = doc.createElement('button');
    close.type = 'button';
    close.className = 'pv-toast__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.innerHTML = ICON.close;
    close.addEventListener('click', () => dismiss(t));
    t.append(dot, body, close);

    // Hovering or focusing a toast holds it.
    t.addEventListener('pointerenter', () => window.clearTimeout(t._pvTimer));
    t.addEventListener('pointerleave', () => arm(t, 2000));
    t.addEventListener('focusin', () => window.clearTimeout(t._pvTimer));
    t.addEventListener('focusout', () => arm(t, 2000));

    box.appendChild(t);
    const live = Array.from(box.children).filter((el) => !el._pvGone);
    if (live.length > 3) dismiss(live[0]);
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => t.classList.add('is-in')));
    arm(t, duration);
    return t;
  }

  /* -------------------------------------------------------- placeholders */

  // What is not available yet, said plainly. No dates, no promises.
  const SOON = {
    code: 'The PointillViz source code is not public yet.',
    paper: 'The preprint is not available yet.',
    trailer: 'The trailer is not ready yet.',
    install: 'Tools are installed from the Tools tab inside PointillViz.',
    download: 'Downloads are not available yet.',
  };

  function initPlaceholders() {
    doc.addEventListener('click', (e) => {
      const el = e.target.closest('[data-placeholder]');
      if (!el) return;
      e.preventDefault();
      const kind = el.getAttribute('data-placeholder');
      toast({
        title: el.getAttribute('data-placeholder-title') || 'Coming soon',
        message: el.getAttribute('data-placeholder-msg') || SOON[kind] || 'This is not available yet.',
        key: `soon:${kind}`,
      });
    });
  }

  /* ------------------------------------------------------------- top bar */

  function initTopbar() {
    const bars = $$('.pv-topbar');
    if (!bars.length) return;
    let ticking = false;
    const update = () => {
      ticking = false;
      const scrolled = window.scrollY > 8;
      bars.forEach((bar) => bar.classList.toggle('is-scrolled', scrolled));
    };
    window.addEventListener('scroll', () => {
      if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* ------------------------------------------ skeletons: one sweep each */

  // A skeleton is swept once, when it is well in view (pv.css runs the sweep
  // on .is-in); nothing loops. Without an observer they rest unswept.
  function initSkeletons() {
    const skels = $$('.pv-skeleton');
    if (!skels.length || !('IntersectionObserver' in window)) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        io.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.5 });
    skels.forEach((el) => io.observe(el));
  }

  /* ------------------------------------------------- large-screen scale */

  // Above 1440 x 900 the chrome is drawn k times larger (at most 1.6), the same
  // formula as the head script of CHROME.md §1, which sets it before the first
  // paint; here it follows the window.
  function scale() {
    const w = root.clientWidth || window.innerWidth;
    const k = Math.min(Math.max(Math.min(w / 1440, window.innerHeight / 900), 1), 1.6);
    const v = k.toFixed(4);
    if (root.style.getPropertyValue('--k') !== v) root.style.setProperty('--k', v);
  }

  function initScale() {
    scale();
    let ticking = false;
    window.addEventListener('resize', () => {
      if (!ticking) { ticking = true; window.requestAnimationFrame(() => { ticking = false; scale(); }); }
    }, { passive: true });
  }

  /* ---------------------------------------------------------------- boot */

  function boot() {
    initScale();
    initTheme();
    initDrawers();
    initCopy();
    initTabs();
    initSeg();
    initPlaceholders();
    initTopbar();
    initSkeletons();
    getToaster();
    reveal();
    root.classList.add('pv-js'); // from here, below-the-fold reveals may hide
  }

  window.PV = Object.freeze({
    toast,
    setTheme,
    theme,
    reveal,
    tabs: initTabs,
    seg: initSeg,
    copy,
    reducedMotion,
  });

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
