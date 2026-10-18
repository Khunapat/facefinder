// Motion kit for seek(t) films. Every function is pure: same inputs, same
// pixels. Loaded as a classic script; exposes window.M.

(function (root) {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, u) => a + (b - a) * u;
  const inv = (a, b, x) => clamp((x - a) / (b - a));      // where x sits between a and b, 0..1
  const smooth = (u) => u * u * (3 - 2 * u);

  // Closed-form damped spring, 0 -> 1, as a function of time since it started.
  function spring(t, k = 170, d = 26) {
    if (t <= 0) return 0;
    const w0 = Math.sqrt(k), z = d / (2 * w0);
    if (z < 1) {
      const wd = w0 * Math.sqrt(1 - z * z);
      return 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + (z * w0 / wd) * Math.sin(wd * t));
    }
    return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
  }
  // A value that changes target several times: one spring per change, summed.
  // keys: [[time, value], ...] sorted by time.
  function track(t, keys, k = 170, d = 26) {
    let v = keys[0][1];
    for (let i = 1; i < keys.length; i++) v += (keys[i][1] - keys[i - 1][1]) * spring(t - keys[i][0], k, d);
    return v;
  }
  // Spring presets: [stiffness, damping]
  const SNAPPY = [320, 30];   // buttons, toggles, words
  const SOFT = [170, 26];     // cards, panels, camera
  const HEAVY = [120, 24];    // big type, logo lockups, zooms
  const PLAYFUL = [260, 14];  // mascots, stickers (visible overshoot)

  // Seeded noise (mulberry32). Never Math.random: renders must repeat exactly.
  function rng(seed) {
    return () => {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function rrect(g, x, y, w, h, r) {
    g.beginPath();
    g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }
  function shadow(g, blur, dy, a) { g.shadowColor = `rgba(0,0,0,${a})`; g.shadowBlur = blur; g.shadowOffsetY = dy; }
  function noShadow(g) { g.shadowColor = 'transparent'; g.shadowBlur = 0; g.shadowOffsetY = 0; }

  // Kinetic type: words rise in on a stagger (from tIn) and leave upward
  // (from tOut, or never if null). Each word is clipped to its own line box
  // so it slides out of an invisible slot rather than fading.
  // opt: { weight, font, lh, track (em), alpha, accentWord, accent }
  function words(g, lines, x, y, size, t, tIn, tOut, color, opt = {}) {
    const lh = size * (opt.lh || 1.02);
    g.font = `${opt.weight || 800} ${size}px ${opt.font || 'sans-serif'}`;
    g.textBaseline = 'alphabetic'; g.textAlign = 'left';
    if ('letterSpacing' in g) g.letterSpacing = (opt.track ?? -0.035) * size + 'px';
    const n = lines.join(' ').split(' ').length;
    let i = 0;
    lines.forEach((line, li) => {
      let cx = x;
      const parts = line.split(' ');
      parts.forEach((wd, wi) => {
        const ws = wd + (wi < parts.length - 1 ? ' ' : '');
        const w = g.measureText(ws).width;
        const s = spring(t - tIn - i * 0.06, ...SNAPPY);
        const out = tOut == null ? 0 : smooth(inv(tOut, tOut + 0.22, t + (n - i) * 0.012));
        // NB: set alpha here from opt.alpha; a globalAlpha set by the caller would be overwritten
        const a = clamp(s * 1.6) * (1 - out) * (opt.alpha ?? 1);
        if (a > 0.001) {
          const dy = (1 - s) * size * 0.55 - out * size * 0.5;
          g.save();
          g.beginPath(); g.rect(cx - 10, y + li * lh - size, w + 40, size * 1.32); g.clip();
          g.globalAlpha = a; g.fillStyle = opt.accentWord === wd ? opt.accent : color;
          g.fillText(ws, cx, y + li * lh + dy);
          g.restore();
        }
        cx += w; i++;
      });
    });
    if ('letterSpacing' in g) g.letterSpacing = '0px';
  }

  // A screenshot on a white rounded panel. s = screen px per image px.
  // opt: { h (image px to show), sy (image px to start at), clipH, shadow:false, fill }
  function panel(g, im, x, y, s, r, opt = {}) {
    const ih = opt.h ?? im.height, w = im.width * s, h = ih * s;
    g.save();
    if (opt.shadow !== false) { shadow(g, 60, 24, 0.14); rrect(g, x, y, w, h, r); g.fillStyle = opt.fill || '#fff'; g.fill(); noShadow(g); }
    rrect(g, x, y, w, h, r); g.clip();
    g.fillStyle = opt.fill || '#fff'; g.fillRect(x, y, w, h);
    if (opt.clipH != null) { g.beginPath(); g.rect(x, y, w, opt.clipH * s); g.clip(); }
    g.drawImage(im, 0, opt.sy || 0, im.width, ih, x, y, w, h);
    g.restore();
    return { x, y, w, h, s };
  }

  // A fingertip that presses at tTap, with a ripple. For phone-format films;
  // draw an arrow cursor instead for desktop UI.
  function finger(g, x, y, tTap, t, alpha = 1, ring = 'rgba(46,75,232,') {
    const p = t - tTap;
    const press = p > -0.08 && p < 0.16 ? Math.sin(clamp((p + 0.08) / 0.24) * Math.PI) : 0;
    g.save(); g.globalAlpha = alpha;
    if (p > 0 && p < 0.6) {
      const u = p / 0.6;
      g.strokeStyle = ring + (0.5 * (1 - u)) + ')'; g.lineWidth = 6;
      g.beginPath(); g.arc(x, y, 40 + u * 90, 0, Math.PI * 2); g.stroke();
    }
    shadow(g, 24, 8, 0.25);
    g.fillStyle = 'rgba(255,255,255,0.92)';
    g.beginPath(); g.arc(x, y, 44 * (1 - 0.18 * press), 0, Math.PI * 2); g.fill();
    noShadow(g);
    g.strokeStyle = 'rgba(18,19,24,0.35)'; g.lineWidth = 4; g.stroke();
    g.fillStyle = `rgba(18,19,24,${0.18 + 0.3 * press})`;
    g.beginPath(); g.arc(x, y, 16, 0, Math.PI * 2); g.fill();
    g.restore();
  }
  // Fingertip opacity: in over [tTap-0.6, tTap-0.3], out over [tTap+0.3, tTap+0.6]
  const fingerIn = (t, tTap) => smooth(inv(tTap - 0.6, tTap - 0.3, t)) * (1 - smooth(inv(tTap + 0.3, tTap + 0.6, t)));

  // Load images by name from a folder; resolves to { name: Image }.
  function loadImages(names, dir) {
    const out = {};
    return Promise.all(names.map((n) => new Promise((res, rej) => {
      const im = new Image(); im.onload = res; im.onerror = () => rej(new Error('missing image ' + n));
      im.src = dir + '/' + n + '.png'; out[n] = im;
    }))).then(() => out);
  }

  root.M = { clamp, lerp, inv, smooth, spring, track, SNAPPY, SOFT, HEAVY, PLAYFUL, rng,
    rrect, shadow, noShadow, words, panel, finger, fingerIn, loadImages };
})(typeof window !== 'undefined' ? window : globalThis);
