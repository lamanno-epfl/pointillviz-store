/*! store.pointillviz.com · field.js · no dependencies
 *
 * The store's signature, drawn in points.
 *
 * Gallery: STField.hero(el) lays a field of points in the homepage's case colours
 * behind the masthead. show(url) gathers those points into a tool's artwork,
 * sampled from its image into a grid of coloured cells; clear() lets them go home.
 *
 * Tool page: STField.develop(...) brings the artwork out of scattered points once,
 * on arrival, in under a second, and leaves a still halo of points in the
 * artwork's own colours around its plate.
 *
 * WebGL2 draws the points. Without it the resting field is painted once on a 2D
 * canvas; without that nothing is drawn and the page is unchanged. With
 * prefers-reduced-motion nothing travels: a picture simply replaces the field.
 * The loop stops off screen and when the tab is hidden.
 *
 * Only pixels of the store's own artwork images are read here, never a string from
 * the registry.
 */
(() => {
  'use strict';

  const doc = document;
  const root = doc.documentElement;
  const reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  const TAU = Math.PI * 2;
  const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
  const smooth = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
  const cssNum = (name, fallback) => parseFloat(getComputedStyle(root).getPropertyValue(name)) || fallback;
  const chromeScale = () => cssNum('--k', 1);
  // The room the top bar takes on screen (--pv-topbar-block in pv.css).
  const barBlock = () => cssNum('--pv-topbar-h', 64) * chromeScale();
  // A seeded random, so the field is the same at every visit.
  const seeded = (seed) => { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; };

  /* ---------------------------------------------------------------- colour */

  // The case colours in hue order, read from the design system, so that a mix
  // never passes through grey: they are blended in OKLab.
  const CASE_TOKENS = ['--pv-gold', '--pv-orange', '--pv-pink', '--pv-violet', '--pv-cyan', '--pv-mint'];
  const CASE_FALLBACK = ['#E2B25A', '#FF8A3D', '#FF5FA2', '#A77BFF', '#43C7F0', '#6FE0BD'];
  const toLin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  const toGam = (c) => { const v = clamp(c, 0, 1); return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055; };
  function oklab(hex) {
    const n = parseInt(hex.trim().slice(1), 16);
    const r = toLin((n >> 16 & 255) / 255), g = toLin((n >> 8 & 255) / 255), b = toLin((n & 255) / 255);
    const l = Math.cbrt(0.4122 * r + 0.5363 * g + 0.0514 * b);
    const m = Math.cbrt(0.2119 * r + 0.6807 * g + 0.1074 * b);
    const s = Math.cbrt(0.0883 * r + 0.2817 * g + 0.6300 * b);
    return [0.2105 * l + 0.7936 * m - 0.0041 * s, 1.9780 * l - 2.4286 * m + 0.4506 * s, 0.0259 * l + 0.7828 * m - 0.8087 * s];
  }
  function fromLab(L, a, b) {
    const l = (L + 0.3963 * a + 0.2158 * b) ** 3, m = (L - 0.1056 * a - 0.0639 * b) ** 3, s = (L - 0.0895 * a - 1.2915 * b) ** 3;
    return [toGam(4.0767 * l - 3.3077 * m + 0.2310 * s), toGam(-1.2684 * l + 2.6098 * m - 0.3414 * s), toGam(-0.0042 * l - 0.7034 * m + 1.7076 * s)];
  }
  function caseRamp(size = 512) {
    const css = getComputedStyle(root);
    const stops = CASE_TOKENS.map((t, i) => oklab(css.getPropertyValue(t).trim() || CASE_FALLBACK[i]));
    const out = new Float32Array(size * 3);
    for (let i = 0; i < size; i++) {
      const p = (i / size) * stops.length;
      const a = stops[Math.floor(p) % stops.length], b = stops[(Math.floor(p) + 1) % stops.length];
      const f = smooth(0.12, 0.88, p - Math.floor(p));
      const rgb = fromLab(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f);
      out[i * 3] = rgb[0]; out[i * 3 + 1] = rgb[1]; out[i * 3 + 2] = rgb[2];
    }
    return out;
  }

  /* ---------------------------------------------------------------- drawing */

  const STRIDE = 7; // x, y, radius, r, g, b, a

  const VS = `#version 300 es
layout(location=0) in vec2 aPos;
layout(location=1) in float aRad;
layout(location=2) in vec4 aCol;
uniform vec2 uRes;
uniform float uDpr;
out vec4 vCol;
out float vRad;
out float vSize;
void main() {
  vec2 c = aPos / uRes * 2.0 - 1.0;
  gl_Position = vec4(c.x, -c.y, 0.0, 1.0);
  vRad = aRad * uDpr;
  vSize = vRad * 2.0 + 2.0;
  gl_PointSize = aRad > 0.0 ? vSize : 0.0;
  vCol = aCol;
}`;
  const FS = `#version 300 es
precision mediump float;
in vec4 vCol;
in float vRad;
in float vSize;
out vec4 o;
void main() {
  float d = length(gl_PointCoord - 0.5) * vSize;
  float a = clamp(vRad - d + 0.5, 0.0, 1.0) * vCol.a;
  if (a < 0.004) discard;
  o = vec4(vCol.rgb * a, a);
}`;

  function glRenderer(canvas) {
    let gl = null;
    try {
      gl = canvas.getContext('webgl2', { alpha: true, antialias: false, depth: false, stencil: false, premultipliedAlpha: true, powerPreference: 'low-power' });
    } catch (e) { gl = null; }
    if (!gl) return null;
    let uRes = null, uDpr = null, capacity = 0, sized = null;
    const setup = () => {
      const shader = (type, src) => { const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh); return sh; };
      const prog = gl.createProgram();
      gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
      gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;
      gl.useProgram(prog);
      uRes = gl.getUniformLocation(prog, 'uRes');
      uDpr = gl.getUniformLocation(prog, 'uDpr');
      gl.bindVertexArray(gl.createVertexArray());
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      const bytes = STRIDE * 4;
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, bytes, 0);
      gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 1, gl.FLOAT, false, bytes, 8);
      gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 4, gl.FLOAT, false, bytes, 12);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.clearColor(0, 0, 0, 0);
      capacity = 0;
      return true;
    };
    if (!setup()) return null;
    const api = {
      moving: true,
      onRestore: null,
      size(w, h, dpr) {
        sized = [w, h, dpr];
        canvas.width = Math.max(1, Math.round(w * dpr));
        canvas.height = Math.max(1, Math.round(h * dpr));
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(uRes, w, h);
        gl.uniform1f(uDpr, dpr);
      },
      draw(buf, n) {
        if (buf.byteLength > capacity) { gl.bufferData(gl.ARRAY_BUFFER, buf.byteLength, gl.DYNAMIC_DRAW); capacity = buf.byteLength; }
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, buf, 0, n * STRIDE);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.drawArrays(gl.POINTS, 0, n);
      },
    };
    // A browser may take a context back (too many open, a GPU restart) and return it later.
    canvas.addEventListener('webglcontextlost', (e) => e.preventDefault());
    canvas.addEventListener('webglcontextrestored', () => {
      if (!setup()) return;
      if (sized) api.size(...sized);
      if (api.onRestore) api.onRestore();
    });
    return api;
  }

  // Without WebGL2: one still frame, drawn on a 2D canvas.
  function stillRenderer(canvas) {
    const ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) return null;
    let dpr = 1;
    return {
      moving: false,
      size(w, h, d) {
        dpr = d;
        canvas.width = Math.max(1, Math.round(w * d));
        canvas.height = Math.max(1, Math.round(h * d));
      },
      draw(buf, n) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < n; i++) {
          const o = i * STRIDE;
          if (buf[o + 6] < 0.01 || buf[o + 2] <= 0) continue;
          ctx.fillStyle = `rgba(${buf[o + 3] * 255 | 0},${buf[o + 4] * 255 | 0},${buf[o + 5] * 255 | 0},${buf[o + 6]})`;
          ctx.beginPath();
          ctx.arc(buf[o], buf[o + 1], buf[o + 2], 0, TAU);
          ctx.fill();
        }
      },
    };
  }

  function newCanvas(host, cls) {
    const canvas = doc.createElement('canvas');
    canvas.className = cls;
    canvas.setAttribute('aria-hidden', 'true');
    host.prepend(canvas);
    return canvas;
  }

  /* ---------------------------------------------------------------- artwork → points */

  const LIT = 44;             // the brightest channel a pixel needs to count as drawn, not as ground
  const READ_W = 360;         // the width artwork is read at for the hero (12:7, as every artwork)
  const artCache = new Map();

  function loadArt(url, width = READ_W) {
    const key = `${width}|${url}`;
    if (artCache.has(key)) return artCache.get(key);
    const im = new Image();
    im.src = url;
    // decode() does the work off the main thread, so reading it below takes no time.
    const p = im.decode().then(() => {
      const w = width, h = Math.round((width * 7) / 12);
      const c = doc.createElement('canvas');
      c.width = w;
      c.height = h;
      const g = c.getContext('2d', { willReadFrequently: true });
      g.imageSmoothingQuality = 'high';
      g.drawImage(im, 0, 0, w, h);
      const data = g.getImageData(0, 0, w, h).data;
      // How bright each pixel is, once, so that sampling skips the ground at a glance.
      const bright = new Uint8Array(w * h);
      for (let j = 0, i = 0; j < bright.length; j++, i += 4) {
        const m = data[i] > data[i + 1] ? (data[i] > data[i + 2] ? data[i] : data[i + 2]) : (data[i + 1] > data[i + 2] ? data[i + 1] : data[i + 2]);
        bright[j] = (m * data[i + 3]) / 255;
      }
      const art = { data, bright, w, h, samples: new Map(), coarse: null };
      art.coarse = cellsFor(art, 30);
      return art;
    });
    artCache.set(key, p);
    return p;
  }

  function cellsFor(art, rows) {
    let c = art.samples.get(rows);
    if (!c) { c = sampleCells(art, rows); art.samples.set(rows, c); }
    return c;
  }

  // One cell per point on a hexagonal lattice over the picture. A cell takes the
  // colour of what is drawn in it (lifted towards its brightest pixel, so that a
  // thin line stays bright), its size from how much of it is drawn, and it is left
  // out if nothing is. Cells come sorted left to right.
  function sampleCells(art, rows) {
    const { data, bright, w: SW, h: SH } = art;
    const cols = Math.max(2, Math.round((rows * 12) / 7));
    const cap = rows * cols;
    const cu = new Float32Array(cap), cv = new Float32Array(cap);
    const cr = new Float32Array(cap), cg = new Float32Array(cap), cb = new Float32Array(cap);
    const cw = new Float32Array(cap), ca = new Float32Array(cap);
    const slot = new Int32Array(cap), count = new Int32Array(cols * 2 + 2);
    const pw = SW / cols, ph = SH / rows;
    let n = 0;
    for (let row = 0; row < rows; row++) {
      const odd = row & 1;
      const y0 = Math.floor(row * ph), y1 = Math.min(SH, Math.ceil((row + 1) * ph));
      for (let col = 0; col < cols; col++) {
        const fx = col + odd * 0.5;
        if (fx + 0.5 > cols) continue;
        const x0 = Math.floor(fx * pw), x1 = Math.min(SW, Math.ceil((fx + 1) * pw));
        let lit = 0, sr = 0, sg = 0, sb = 0, peak = 0;
        for (let y = y0; y < y1; y++) {
          for (let x = x0, j = y * SW + x0; x < x1; x++, j++) {
            const m = bright[j];
            if (m < LIT) continue;
            const i = j * 4, al = data[i + 3] / 255;
            lit++;
            sr += data[i] * al; sg += data[i + 1] * al; sb += data[i + 2] * al;
            if (m > peak) peak = m;
          }
        }
        const cover = lit / ((y1 - y0) * (x1 - x0));
        if (cover < 0.08) continue;
        const mr = sr / lit, mg = sg / lit, mb = sb / lit;
        const mm = Math.max(mr, mg, mb);
        const lift = (mm + (peak - mm) * 0.6) / mm;
        cu[n] = (fx + 0.5) / cols;
        cv[n] = (row + 0.5) / rows;
        cr[n] = Math.min(1, (mr * lift) / 255);
        cg[n] = Math.min(1, (mg * lift) / 255);
        cb[n] = Math.min(1, (mb * lift) / 255);
        cw[n] = Math.sqrt(Math.min(1, cover * 1.35));
        ca[n] = 0.42 + 0.58 * smooth(LIT, 150, peak);
        // Grey and thin is a label or an axis: it stays in the picture, and quiet.
        if (cover < 0.55 && mm - Math.min(mr, mg, mb) < mm * 0.3) { ca[n] *= 0.62; cw[n] *= 0.86; }
        slot[n] = col * 2 + odd;
        count[slot[n] + 1]++;
        n++;
      }
    }
    // Left to right, by counting: the columns are known, and a comparison sort of this
    // many cells would be felt under the pointer.
    for (let i = 1; i < count.length; i++) count[i] += count[i - 1];
    const order = new Int32Array(n);
    for (let i = 0; i < n; i++) order[count[slot[i]]++] = i;
    const pick = (a) => { const out = new Float32Array(n); for (let i = 0; i < n; i++) out[i] = a[order[i]]; return out; };
    return { n, rows, cols, u: pick(cu), v: pick(cv), r: pick(cr), g: pick(cg), b: pick(cb), w: pick(cw), a: pick(ca) };
  }

  // How many rows a picture can have: the points must reach the budget at most,
  // and must not be finer than the pitch that still reads as points.
  function rowsFor(art, budget, maxRows) {
    const fill = Math.max(0.02, art.coarse.n / (art.coarse.rows * art.coarse.cols));
    const rows = Math.sqrt((budget / fill) * 7 / 12);
    return Math.round(clamp(rows, 10, Math.max(10, maxRows)) / 4) * 4;
  }

  // The artwork's own accent: the most common strong hue among its points,
  // lifted until it reads on ink. Plain numbers from pixels.
  function accentOf(art) {
    if (art.accent) return art.accent;
    const c = art.coarse;
    const bins = new Float32Array(12), sums = new Float32Array(36);
    let grey = 0, gr = 0, gg = 0, gb = 0;
    for (let i = 0; i < c.n; i++) {
      const r = c.r[i], g = c.g[i], b = c.b[i];
      const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
      const w = c.w[i] * c.a[i];
      if (d < 0.18) { grey += w; gr += r * w; gg += g * w; gb += b * w; continue; }
      let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      if (h < 0) h += 6;
      const bin = Math.floor(h * 2) % 12;
      const s = w * (d / max) * max;
      bins[bin] += s;
      sums[bin * 3] += r * s; sums[bin * 3 + 1] += g * s; sums[bin * 3 + 2] += b * s;
    }
    let best = -1, bw = 0;
    for (let i = 0; i < 12; i++) if (bins[i] > bw) { bw = bins[i]; best = i; }
    let rgb = best >= 0 && bw > grey * 0.12
      ? [sums[best * 3] / bw, sums[best * 3 + 1] / bw, sums[best * 3 + 2] / bw]
      : (grey ? [gr / grey, gg / grey, gb / grey] : [0.44, 0.88, 0.74]);
    // Luminance up to about 0.32, which is 6.5:1 and more on the store's ink.
    const lum = (v) => 0.2126 * toLin(v[0]) + 0.7152 * toLin(v[1]) + 0.0722 * toLin(v[2]);
    for (let i = 0; i < 12 && lum(rgb) < 0.32; i++) rgb = rgb.map((v) => v + (1 - v) * 0.14);
    art.accent = rgb.map((v) => Math.round(v * 255)).join(' ');
    return art.accent;
  }

  // The artwork's colours on a small blurred grid, for its halo: for every place on
  // the picture's edge, the colour nearby, lifted to read on ink, and how much is drawn.
  function paletteOf(art) {
    if (art.palette) return art.palette;
    const { data, w: SW, h: SH } = art;
    const gw = 18, gh = 11, size = gw * gh;
    let wt = new Float32Array(size), rr = new Float32Array(size), gg = new Float32Array(size), bb = new Float32Array(size);
    let tr = 0, tg = 0, tb = 0, tw = 0;
    for (let y = 0; y < SH; y += 2) {
      const gy = Math.min(gh - 1, Math.floor((y / SH) * gh));
      for (let x = 0; x < SW; x += 2) {
        const i = (y * SW + x) * 4;
        const al = data[i + 3] / 255;
        const r = (data[i] * al) / 255, g = (data[i + 1] * al) / 255, b = (data[i + 2] * al) / 255;
        const m = Math.max(r, g, b);
        if (m * 255 < LIT) continue;
        const sat = 0.25 + (m - Math.min(r, g, b));   // colour counts for more than grey
        const k = Math.floor((x / SW) * gw) + gy * gw;
        wt[k] += sat; rr[k] += r * sat; gg[k] += g * sat; bb[k] += b * sat;
        tr += r * sat; tg += g * sat; tb += b * sat; tw += sat;
      }
    }
    const blur = (a) => {
      const o = new Float32Array(size);
      for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) {
        let sum = 0, c = 0;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
          sum += a[nx + ny * gw]; c++;
        }
        o[x + y * gw] = sum / c;
      }
      return o;
    };
    for (let pass = 0; pass < 3; pass++) { wt = blur(wt); rr = blur(rr); gg = blur(gg); bb = blur(bb); }
    let peak = 1e-6;
    for (let i = 0; i < size; i++) if (wt[i] > peak) peak = wt[i];
    const avg = tw ? [tr / tw, tg / tw, tb / tw] : [0.44, 0.88, 0.74];
    const cr = new Float32Array(size), cg = new Float32Array(size), cb = new Float32Array(size), amt = new Float32Array(size);
    for (let i = 0; i < size; i++) {
      const w = wt[i] || 1e-6;
      const has = wt[i] / peak;
      const mix = 0.25 + 0.75 * Math.min(1, has * 2.2);
      const r = (rr[i] / w) * mix + avg[0] * (1 - mix), g = (gg[i] / w) * mix + avg[1] * (1 - mix), b = (bb[i] / w) * mix + avg[2] * (1 - mix);
      const lift = Math.min(1.5, 0.95 / (Math.max(r, g, b) || 1));
      cr[i] = Math.min(1, r * lift); cg[i] = Math.min(1, g * lift); cb[i] = Math.min(1, b * lift);
      amt[i] = 0.4 + 0.6 * Math.min(1, has * 1.9);
    }
    art.palette = { gw, gh, cr, cg, cb, amt };
    return art.palette;
  }

  /* ---------------------------------------------------------------- the gallery's field */

  const PICTURE_MIN = 1000;   // a window narrower than this has no room for a picture beside the words
  const SWARM = 9000;         // the points a picture is drawn with, at most; they rest unseen in the field
  // How a halo falls off with distance from the picture, in steps of a sixteenth of its reach.
  const HALO_STEPS = 16, HALO_N = 64;
  const HALO_A = Float32Array.from({ length: HALO_N }, (_, i) => Math.exp((-1.35 * i) / HALO_STEPS));
  const HALO_R = Float32Array.from({ length: HALO_N }, (_, i) => Math.exp((-1.6 * i) / HALO_STEPS));

  function hero(host) {
    const canvas = newCanvas(host, 'st-field');
    const R = glRenderer(canvas) || stillRenderer(canvas);
    if (!R) { canvas.remove(); return { drawn: false, show: () => Promise.resolve(null), clear() {}, quiet() {}, warm() {}, canShow: () => false }; }

    const ramp = caseRamp();
    const LUT = ramp.length / 3;
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)');

    let W = 0, H = 0, D = 1, k = 1, pitch = 8, L = 0, N = 0, rightEdge = 0, barPx = 0, tickNo = 0;
    let x, y, vx, vy, rad, cr, cg, cb, ca, om, restX, restY, side, swell, hue, cellOf, order, bucket, buf;
    let art = null, cells = null, sampledH = 0;
    let picK = 0, token = 0, hushed = false, swarmUntil = 0;
    let t0 = performance.now(), last = t0, raf = 0, frame = 0, busyUntil = 0, built = false;
    let inView = true;
    const rect = { x: 0, y: 0, w: 0, h: 0 };
    const ptr = { x: -1e5, y: -1e5, on: false, k: 0 };

    function build() {
      const box = host.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) return;
      barPx = barBlock();
      const dpr = Math.min(2, window.devicePixelRatio || 1), scale = chromeScale();
      if (built && box.width === W && box.height === H && dpr === D && scale === k) return;
      W = box.width; H = box.height; D = dpr; k = scale;
      R.size(W, H, D);
      const narrow = W < 760;
      pitch = (narrow ? 8 : 9) * k;
      const rowH = pitch * 0.866;
      const rnd = seeded(7);
      const lx = [], ly = [];
      for (let row = 0, py = rowH * 0.25; py < H + rowH; row++, py += rowH) {
        for (let px = (row % 2) * pitch * 0.5; px < W + pitch; px += pitch) { lx.push(px); ly.push(py); }
      }
      L = lx.length;
      N = R.moving && W >= PICTURE_MIN && fine.matches ? L + SWARM : L;
      x = new Float32Array(N); y = new Float32Array(N); vx = new Float32Array(N); vy = new Float32Array(N);
      rad = new Float32Array(N); cr = new Float32Array(N); cg = new Float32Array(N); cb = new Float32Array(N); ca = new Float32Array(N);
      om = new Float32Array(N); restX = new Float32Array(N); restY = new Float32Array(N);
      side = new Float32Array(N); swell = new Float32Array(N); hue = new Float32Array(N); cellOf = new Int32Array(N).fill(-1);
      order = new Int32Array(N); bucket = new Int32Array(N);
      buf = new Float32Array((N + 40) * STRIDE);
      for (let i = 0; i < N; i++) {
        // The lattice stays where it is. The swarm rests in the field too, unseen and away
        // from the words, so that a picture gathers out of it.
        const j = i < L ? i : Math.floor(rnd() * L);
        restX[i] = i < L ? lx[j] : W * (0.34 + 0.66 * rnd());
        restY[i] = ly[j];
        x[i] = restX[i]; y[i] = restY[i];
        const u = restX[i] / W, v0 = 1 - restY[i] / H;
        // The words sit at the left: the field is faint behind them on a wide
        // screen, and evenly quiet behind them on a narrow one.
        side[i] = i >= L ? 0 : narrow ? 0.16 + 0.34 * smooth(0.2, 1, u) * smooth(0, 0.9, v0) : W < PICTURE_MIN ? 0.14 + 0.5 * smooth(0.5, 0.95, u) : 0.07 + 0.93 * smooth(0.3, 0.62, u);
        om[i] = 6.2 + rnd() * 3.8;
      }
      const inner = host.querySelector('.st-hero__in');
      if (inner) {
        const b = inner.getBoundingClientRect();
        const pad = parseFloat(getComputedStyle(inner).paddingRight) || 0;
        rightEdge = b.right - box.left - pad * (b.width / inner.offsetWidth || 1);
      } else rightEdge = W;
      built = true;
      if (art) { sampledH = 0; place(); }
    }

    /* The picture sits in what is on screen of the hero: all of it wherever the hero
       stays in place, what is left of it in a short window, where it scrolls away. */
    function layout(visTop) {
      const visH = H - visTop;
      const pad = 10 * k;
      const h = clamp(visH - 2 * pad, 8, H - 2 * pad);
      rect.h = h;
      rect.w = (h * 12) / 7;
      rect.x = rightEdge - rect.w;
      rect.y = visTop + (visH - h) / 2;
    }

    function place() {
      if (!art) return;
      const bigger = Math.max(rect.h, 1) / Math.max(sampledH, 1);
      if (sampledH && bigger < 1.25 && bigger > 0.8) return;
      sampledH = rect.h;
      cells = cellsFor(art, rowsAt(art, rect.h));
      assign();
    }

    // How finely a picture of this height is drawn: fine enough to read, never finer
    // than points can be told apart, and never more of them than the swarm has.
    function rowsAt(a, h) {
      const pitchMin = (h > 120 * k ? 3.1 : 2.3) * k;
      return rowsFor(a, (N - L) * 0.98, Math.floor(h / pitchMin));
    }

    // Which point goes where: the swarm in order from left to right, so that a picture
    // pours in instead of crossing itself. By counting, as sampleCells does.
    function assign() {
      const E = N - L;
      const B = 2048, count = new Int32Array(B + 1);
      for (let i = L; i < N; i++) { const b = bucket[i - L] = clamp((x[i] / W) * B, 0, B - 1) | 0; count[b + 1]++; }
      for (let b = 1; b <= B; b++) count[b] += count[b - 1];
      for (let i = L; i < N; i++) order[count[bucket[i - L]]++] = i;
      cellOf.fill(-1);
      const M = Math.min(cells.n, E);
      for (let j = 0; j < M; j++) {
        const cell = M === cells.n ? j : Math.floor((j * cells.n) / M);
        cellOf[order[Math.floor((j * E) / M)]] = cell;
      }
      swarmUntil = Infinity;
    }

    function step(now, instant) {
      const dt = instant ? 1 : Math.min(0.034, (now - last) / 1000);
      last = now;
      const t = reduceMQ.matches ? 8 : (now - t0) / 1000;
      const visTop = clamp(barPx - host.getBoundingClientRect().top, 0, H);
      const visH = Math.max(1, H - visTop);
      if (art) { layout(visTop); place(); }
      const wanted = cells || hushed ? 1 : 0;
      picK = instant ? wanted : picK + (wanted - picK) * (1 - Math.exp(-dt * 7));
      ptr.k = instant ? 0 : ptr.k + ((ptr.on ? 1 : 0) - ptr.k) * (1 - Math.exp(-dt * 8));
      const lens = 130 * k, lens2 = lens * lens, lensK = ptr.k;
      const settled = instant || t > 2;
      const band = 1 - 0.5 * clamp(visTop / Math.max(1, H - 80 * k), 0, 1);
      const ease = instant ? 1 : 1 - Math.exp(-dt * 9);
      const dx0 = rect.x - 14 * k, dx1 = rect.x + rect.w + 14 * k, dy0 = rect.y - 10 * k, dy1 = rect.y + rect.h + 10 * k;
      const picR = cells ? (rect.h / cells.rows) * 0.46 : 0;
      const halo = art && rect.w > 0 ? paletteOf(art) : null;
      const reach = rect.h * 0.42;
      // Home again and unseen, the swarm costs nothing.
      const active = now < swarmUntil || instant ? N : L;
      // The swell and the hue move slowly: once the field is up, half of it each frame.
      const half = ++tickNo & 1;
      let rowY = -1, rowFoot = 0, rowEdge = 1, rowV = 0, rowHue = 0;
      for (let i = 0; i < active; i++) {
        const p = cellOf[i];
        let tx = restX[i], ty = restY[i], tr, tcr, tcg, tcb, ta;
        if (p >= 0) {
          tx = rect.x + cells.u[p] * rect.w;
          ty = rect.y + cells.v[p] * rect.h;
          tr = cells.w[p] * picR;
          tcr = cells.r[p]; tcg = cells.g[p]; tcb = cells.b[p];
          ta = cells.a[p];
        } else if (i < L) {
          if (ty !== rowY) {
            rowY = ty;
            rowV = ty / H;
            // Nothing under the top bar.
            rowFoot = ty < visTop ? 0 : 1 - smooth(0.66, 1, (ty - visTop) / visH);
            rowEdge = H - ty >= 16 * k ? 1 : smooth(0, 16 * k, H - ty);
            rowHue = 0.03 * Math.sin(rowV * 6 + t * 0.07);
          }
          const u = tx / W, v = rowV;
          if (!settled || instant || (i & 1) === half) {
            // Two slow warps make soft domains, as on a map of cell types; the points
            // swell over them like a halftone.
            const w1 = Math.sin(v * 3.1 + 1.7 * u + t * 0.13);
            const w2 = Math.sin(u * 7.3 + 1.2 * v - t * 0.1);
            const n = 0.5 + 0.5 * Math.sin(u * 7 + 1.25 * w1 + t * 0.17) * Math.cos(v * 4.6 + 0.9 * w2 - t * 0.12);
            swell[i] = n * n * (3 - 2 * n);
            hue[i] = ((u - 0.2) / 0.8) * 0.87 + 0.055 * w1 + 0.045 * w2;
          }
          const sw = swell[i];
          const intro = settled ? 1 : smooth(0, 1, t * 1.5 - (1 - u) * 0.9);
          const mask = side[i] * rowFoot * intro * band;
          tr = pitch * (0.04 + 0.44 * sw) * (0.32 + 0.68 * mask);
          ta = mask * (0.2 + 0.8 * sw);
          const li = (clamp(hue[i] + rowHue, 0, 0.999) * LUT | 0) * 3;
          tcr = ramp[li]; tcg = ramp[li + 1]; tcb = ramp[li + 2];
          if (picK > 0.001) {
            // The field steps back, and around a picture it takes the picture's colours.
            ta *= 1 - 0.8 * picK;
            tr *= 1 - 0.35 * picK;
            if (rect.w > 0 && tx > dx0 && tx < dx1 && ty > dy0 && ty < dy1) ta *= 1 - picK;
            else if (halo) {
              const qx = tx < rect.x ? rect.x : tx > rect.x + rect.w ? rect.x + rect.w : tx;
              const qy = ty < rect.y ? rect.y : ty > rect.y + rect.h ? rect.y + rect.h : ty;
              const ex = tx - qx, ey = ty - qy;
              const f = Math.sqrt(ex * ex + ey * ey) / reach * HALO_STEPS | 0;
              const fA = f < HALO_N ? HALO_A[f] : 0, fR = f < HALO_N ? HALO_R[f] : 0;
              const g = Math.min(halo.gw - 1, ((qx - rect.x) / rect.w) * halo.gw | 0) + Math.min(halo.gh - 1, ((qy - rect.y) / rect.h) * halo.gh | 0) * halo.gw;
              const near = picK * rowEdge * side[i];
              const ha = 0.62 * fA * halo.amt[g] * near, hr = pitch * (0.05 + 0.26 * fR) * near;
              if (ha > ta) ta = ha;
              if (hr > tr) tr = hr;
              tcr += (halo.cr[g] - tcr) * picK;
              tcg += (halo.cg[g] - tcg) * picK;
              tcb += (halo.cb[g] - tcb) * picK;
            }
          }
        } else {
          tr = 0; ta = 0; tcr = cr[i]; tcg = cg[i]; tcb = cb[i];
        }
        let rr = tr, aa = ta;
        if (lensK > 0.01) {
          const ex = x[i] - ptr.x, ey = y[i] - ptr.y;
          const d2 = ex * ex + ey * ey;
          if (d2 < lens2) {
            const g = (1 - Math.sqrt(d2) / lens) ** 2 * lensK;
            // Field points swell until they touch, never over each other; a picture's
            // points only a little, so that it stays a picture.
            rr = p >= 0 ? tr * (1 + 0.8 * g) : (ta > 0 ? tr + (pitch * 0.47 - tr) * g * 0.92 : tr);
            aa = ta > 0 ? Math.min(1, ta + 0.8 * g) : ta;
          }
        }
        if (instant) {
          x[i] = tx; y[i] = ty; vx[i] = 0; vy[i] = 0;
        } else {
          const w = om[i];
          const dx = tx - x[i], dy = ty - y[i];
          // A spring a little under critical, with a slight turn while in flight,
          // so the points pour rather than slide.
          const swirl = p >= 0 ? 0.9 : 0.25;
          vx[i] += (w * w * dx - 2 * 0.86 * w * vx[i] - swirl * w * dy) * dt;
          vy[i] += (w * w * dy - 2 * 0.86 * w * vy[i] + swirl * w * dx) * dt;
          x[i] += vx[i] * dt;
          y[i] += vy[i] * dt;
        }
        rad[i] += (rr - rad[i]) * ease;
        cr[i] += (tcr - cr[i]) * ease;
        cg[i] += (tcg - cg[i]) * ease;
        cb[i] += (tcb - cb[i]) * ease;
        ca[i] += (aa - ca[i]) * ease;
        const o = i * STRIDE;
        buf[o] = x[i]; buf[o + 1] = y[i]; buf[o + 2] = rad[i];
        buf[o + 3] = cr[i]; buf[o + 4] = cg[i]; buf[o + 5] = cb[i]; buf[o + 6] = ca[i];
      }
      // The picture's registration marks, in points, as on the plate it comes from.
      let total = active;
      if (picK > 0.02 && rect.w > 0 && rect.h > 110 * k) {
        const arm = 5, gap = 3.4 * k, off = 9 * k, a = 0.62 * picK, r = 0.8 * k;
        const x0 = rect.x - off, x1 = rect.x + rect.w + off, y0 = rect.y - off * 0.5, y1 = rect.y + rect.h + off * 0.5;
        for (let c = 0; c < 4; c++) {
          const cx = c & 1 ? x1 : x0, cy = c & 2 ? y1 : y0, sx = c & 1 ? -1 : 1, sy = c & 2 ? -1 : 1;
          for (let j = 0; j < arm * 2 - 1; j++) {
            const o = total * STRIDE;
            buf[o] = cx + sx * (j < arm ? j : 0) * gap; buf[o + 1] = cy + sy * (j < arm ? 0 : j - arm + 1) * gap; buf[o + 2] = r;
            buf[o + 3] = 0.94; buf[o + 4] = 0.9; buf[o + 5] = 0.82; buf[o + 6] = a;
            total++;
          }
        }
      }
      R.draw(buf, total);
    }

    function tick(now) {
      raf = requestAnimationFrame(tick);
      if (now > busyUntil && now - t0 > 2500) {
        // The resting drift is slow: every second frame is enough for it, and none at
        // all once the hero has mostly scrolled away (a short window).
        if (frame++ & 1) return;
        if (host.getBoundingClientRect().top < barPx - H * 0.5) return;
      }
      step(now, false);
    }

    function sync() {
      const run = R.moving && inView && doc.visibilityState === 'visible' && !reduceMQ.matches;
      if (run && !raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
      if (!run && raf) { cancelAnimationFrame(raf); raf = 0; }
      if (!run && built) step(performance.now(), true);
    }

    build();
    sync();

    if ('ResizeObserver' in window) {
      let pending = 0;
      new ResizeObserver(() => {
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(() => { build(); sync(); });
      }).observe(host);
    }
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(([e]) => { inView = e.isIntersecting; sync(); }).observe(host);
    }
    doc.addEventListener('visibilitychange', sync);
    reduceMQ.addEventListener('change', sync);
    // Where the hero scrolls away, the field follows the part of it on screen. Where it
    // stays in place, a scroll of the tools under it asks nothing of the field.
    let lastTop = host.getBoundingClientRect().top;
    window.addEventListener('scroll', () => {
      const top = host.getBoundingClientRect().top;
      if (top === lastTop) return;
      lastTop = top;
      busyUntil = Math.max(busyUntil, performance.now() + 240);
      if (!raf && inView && built) step(performance.now(), true);
    }, { passive: true });
    R.onRestore = () => { if (!raf && built) step(performance.now(), true); };

    // The Lens: points swell under the pointer, as under the viewer's Lens.
    window.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse') return;
      const box = host.getBoundingClientRect();
      ptr.x = e.clientX - box.left;
      ptr.y = e.clientY - box.top;
      const on = e.clientY >= box.top && e.clientY <= box.bottom && e.clientY >= barPx;
      if (on) busyUntil = performance.now() + 900;
      ptr.on = on;
    }, { passive: true });

    // Pictures of plates that have loaded are read while nothing else is going on, so
    // that the first rest on a plate has nothing left to compute.
    const waiting = [];
    let warming = false;
    const idle = window.requestIdleCallback || ((f) => window.setTimeout(f, 120));
    function warmNext() {
      const url = waiting.shift();
      if (!url) { warming = false; return; }
      loadArt(url).then((a) => {
        cellsFor(a, rowsAt(a, H - 20 * k));
        paletteOf(a);
        accentOf(a);
      }).catch(() => {}).then(() => idle(warmNext, { timeout: 900 }));
    }

    function release(hush) {
      token++;
      hushed = hush;
      art = null;
      cells = null;
      sampledH = 0;
      rect.w = 0;
      if (cellOf) cellOf.fill(-1);
      busyUntil = performance.now() + 2200;
      swarmUntil = busyUntil;
      if (!raf && built) step(performance.now(), true);
    }

    return {
      drawn: true,
      // Whether this window can show a picture at all.
      canShow: () => R.moving && W >= PICTURE_MIN,
      warm(url) {
        if (!(R.moving && W >= PICTURE_MIN && fine.matches)) return;
        waiting.push(url);
        if (!warming) { warming = true; idle(warmNext, { timeout: 900 }); }
      },
      show(url) {
        const mine = ++token;
        busyUntil = performance.now() + 2200;
        return loadArt(url).then((a) => {
          if (mine !== token) return null;
          if (R.moving && W >= PICTURE_MIN) {
            hushed = false;
            art = a;
            sampledH = 0;
            const box = host.getBoundingClientRect();
            layout(clamp(barPx - box.top, 0, H));
            place();
            if (!raf) step(performance.now(), true);
          } else release(true);
          return accentOf(a);
        }).catch(() => null);
      },
      clear() { release(false); },
      // A plate with no artwork: no picture, and the field steps back behind the words.
      quiet() { release(true); },
    };
  }

  /* ---------------------------------------------------------------- the tool page's artwork */

  const DEVELOP_W = 480;      // the plate on a tool page is large, and the picture is read finer for it

  function develop({ host, plate, img, onReveal }) {
    const canvas = newCanvas(host, 'st-halo');
    const R = glRenderer(canvas) || stillRenderer(canvas);
    let revealed = false;
    const reveal = () => { if (!revealed) { revealed = true; onReveal(); } };
    if (!R) { canvas.remove(); reveal(); return; }

    let haloBuf = null, haloN = 0, grid = null, D = 1;

    function buildHalo() {
      const box = host.getBoundingClientRect();
      const W = box.width, H = box.height;
      if (W < 1 || H < 1 || !grid) return;
      D = Math.min(2, window.devicePixelRatio || 1);
      R.size(W, H, D);
      const pb = plate.getBoundingClientRect();
      const px = pb.left - box.left, py = pb.top - box.top, pw = pb.width, ph = pb.height;
      const k = chromeScale();
      const narrow = W < 1024;
      const pitch = (narrow ? 8 : 9) * k;
      const rowH = pitch * 0.866;
      const reach = (narrow ? 34 : 92) * k;
      const rnd = seeded(11);
      const out = [];
      // Under the words the halo thins out, so that they stay on calm ink.
      const words = host.querySelector('.st-top__words');
      const wr = words && !narrow ? words.getBoundingClientRect().right - box.left : 0;
      for (let row = 0, y = rowH / 2; y < H; row++, y += rowH) {
        for (let x = (row % 2) * pitch * 0.5; x < W; x += pitch) {
          const inside = x > px && x < px + pw && y > py && y < py + ph;
          const jit = 0.75 + rnd() * 0.5;
          if (inside) continue;
          const qx = clamp(x, px, px + pw), qy = clamp(y, py, py + ph);
          const d = Math.hypot(x - qx, y - qy);
          if (d > reach * 3.2) continue;
          const g = Math.min(grid.gw - 1, Math.floor(((qx - px) / pw) * grid.gw)) + Math.min(grid.gh - 1, Math.floor(((qy - py) / ph) * grid.gh)) * grid.gw;
          const fall = Math.exp(-d / reach);
          const foot = smooth(0, 40 * k, H - y) * smooth(0, 14 * k, y);
          const calm = wr ? 0.1 + 0.9 * smooth(wr - 6 * k, wr + 44 * k, x) : 1;
          const a = 0.62 * Math.pow(fall, 1.35) * grid.amt[g] * foot * calm;
          if (a < 0.012) continue;
          const r = pitch * (0.05 + 0.26 * Math.pow(fall, 1.6)) * jit;
          out.push(x, y, r, grid.cr[g], grid.cg[g], grid.cb[g], a);
        }
      }
      haloN = out.length / STRIDE;
      haloBuf = new Float32Array(out);
    }

    const drawHalo = () => { if (haloBuf) R.draw(haloBuf, haloN); };
    R.onRestore = drawHalo;

    const settle = () => {
      canvas.classList.remove('is-over');
      reveal();
      drawHalo();
      if ('ResizeObserver' in window) {
        let pending = 0;
        new ResizeObserver(() => {
          cancelAnimationFrame(pending);
          pending = requestAnimationFrame(() => { buildHalo(); drawHalo(); });
        }).observe(host);
      }
    };

    function run(art) {
      const box = host.getBoundingClientRect();
      const pb = plate.getBoundingClientRect();
      const W = box.width, H = box.height;
      const k = chromeScale();
      const px = pb.left - box.left, py = pb.top - box.top, pw = pb.width, ph = pb.height;
      const budget = W < 700 ? 5000 : 15000;
      const rows = rowsFor(art, budget, Math.floor(ph / (3.2 * k)));
      const c = cellsFor(art, rows);
      const M = c.n;
      const rnd = seeded(23);
      const sx = new Float32Array(M), sy = new Float32Array(M), del = new Float32Array(M);
      const reach = Math.max(pw, ph) * 0.62;
      // The scatter keeps off the words beside the plate.
      const words = W >= 1024 ? host.querySelector('.st-top__words') : null;
      const minX = words ? words.getBoundingClientRect().right - box.left + 8 * k : 0;
      for (let i = 0; i < M; i++) {
        const ang = rnd() * TAU, far = reach * Math.sqrt(rnd());
        const tx = px + c.u[i] * pw, ty = py + c.v[i] * ph;
        // Mirrored at the edges rather than stopped, so that no points line up along them.
        const fx = tx + Math.cos(ang) * far, fy = ty + Math.sin(ang) * far * 0.8;
        sx[i] = clamp(fx < minX ? 2 * minX - fx : fx > W ? 2 * W - fx : fx, minX, W);
        sy[i] = clamp(fy < 0 ? -fy : fy > H ? 2 * H - fy : fy, 0, H);
        del[i] = rnd() * 0.24;
      }
      const picR = (ph / rows) * 0.46;
      const total = haloN + M;
      const all = new Float32Array(total * STRIDE);
      if (haloBuf) all.set(haloBuf);
      canvas.classList.add('is-over');
      const DUR = 640, FADE = 240;
      let start = 0, fadeFrom = 0, holding = false;
      const tick = (now) => {
        if (!start) start = now;
        const tt = Math.min(1, (now - start) / DUR);
        const haloA = smooth(0.3, 1, tt);
        for (let i = 0; i < haloN; i++) all[i * STRIDE + 6] = haloBuf[i * STRIDE + 6] * haloA;
        // The points hand over to the real picture as soon as it is there; until then
        // they are the picture.
        if (!fadeFrom && tt >= 1 && img.complete) { fadeFrom = now; reveal(); }
        const fade = fadeFrom ? 1 - smooth(0, FADE, now - fadeFrom) : 1;
        const appear = smooth(0, 0.16, tt);
        for (let i = 0; i < M; i++) {
          const ti = clamp((tt - del[i]) / 0.76, 0, 1);
          const e = 1 - (1 - ti) ** 4;
          const o = (haloN + i) * STRIDE;
          all[o] = sx[i] + (px + c.u[i] * pw - sx[i]) * e;
          all[o + 1] = sy[i] + (py + c.v[i] * ph - sy[i]) * e;
          all[o + 2] = c.w[i] * picR * (0.55 + 0.45 * e);
          all[o + 3] = c.r[i]; all[o + 4] = c.g[i]; all[o + 5] = c.b[i];
          all[o + 6] = c.a[i] * appear * fade;
        }
        R.draw(all, total);
        if (fade <= 0) { settle(); return; }
        // Drawn, and the large picture still on its way: nothing moves until it is here.
        if (tt >= 1 && !fadeFrom && !holding) {
          holding = true;
          const go = () => requestAnimationFrame(tick);
          img.addEventListener('load', go, { once: true });
          img.addEventListener('error', go, { once: true });
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }

    // The small file is enough to read the points from, and the gallery has just fetched
    // it: the page does not wait for the large one.
    loadArt(img.getAttribute('src'), DEVELOP_W).then((art) => {
      grid = paletteOf(art);
      accent(art);
      buildHalo();
      const box = host.getBoundingClientRect();
      // Arrival is the moment for it. On a slow connection the picture is already up by
      // itself (store.css), and it is left alone.
      const late = performance.now() > 2200;
      const still = late || !R.moving || reduceMQ.matches || doc.visibilityState !== 'visible' || box.bottom < 0 || box.top > window.innerHeight;
      if (still) settle(); else run(art);
    }).catch(reveal);

    // The page takes the artwork's accent (a number from its pixels) for its small marks.
    function accent(art) { root.style.setProperty('--st-art', accentOf(art)); }
  }

  window.STField = { hero, develop };
})();
