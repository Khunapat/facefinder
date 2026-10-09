// Illustrated graduates, drawn in code. Stand-ins for real people's photos so
// the promo never shows a real face. Pure functions of a seed: same seed, same
// drawing, every render.

(function (root) {
  function rng(seed) {
    return () => {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  const pick = (r, a) => a[Math.floor(r() * a.length)];

  const SKIN = ['#F2D3BC', '#E8BE9C', '#D9A47E', '#C68B62', '#A86E4A', '#8A5638', '#F5DCC8', '#DDB08C'];
  const HAIR = ['#1E1714', '#2B1D16', '#3B2619', '#121212', '#5A3A24', '#6E4A2E'];
  const GOWN = ['#1B2140', '#1E1E24', '#2A1F3D', '#14283A'];
  const BG = [
    ['#BFD7EA', '#E7EEF3'],   // sky
    ['#CFE3C5', '#EEF3E6'],   // lawn
    ['#EADBC8', '#F6EFE6'],   // stone
    ['#D9D4EC', '#EFEDF7'],   // lilac
    ['#F3D9C7', '#FAEDE3'],   // late sun
  ];
  const TASSEL = '#E9B23C';

  // One person, head centred at (x, y), head height h.
  function person(g, x, y, h, r, opt = {}) {
    const skin = opt.skin || pick(r, SKIN);
    const hair = opt.hair || pick(r, HAIR);
    const gown = opt.gown || pick(r, GOWN);
    const style = opt.style ?? Math.floor(r() * 5);
    const cap = opt.cap ?? (r() < 0.8);
    const w = h * 0.78;

    // shoulders + gown
    g.fillStyle = gown;
    g.beginPath();
    g.moveTo(x - w * 1.25, y + h * 3.6);
    g.bezierCurveTo(x - w * 1.25, y + h * 0.95, x - w * 0.8, y + h * 0.72, x, y + h * 0.7);
    g.bezierCurveTo(x + w * 0.8, y + h * 0.72, x + w * 1.25, y + h * 0.95, x + w * 1.25, y + h * 3.6);
    g.closePath(); g.fill();
    // collar V
    g.fillStyle = '#F4F2EE';
    g.beginPath();
    g.moveTo(x - w * 0.32, y + h * 0.66); g.lineTo(x, y + h * 1.1); g.lineTo(x + w * 0.32, y + h * 0.66);
    g.closePath(); g.fill();
    // hair behind
    g.fillStyle = hair;
    if (style === 1) { // long
      g.beginPath(); g.ellipse(x, y + h * 0.15, w * 0.62, h * 0.72, 0, 0, Math.PI * 2); g.fill();
      g.fillRect(x - w * 0.62, y + h * 0.1, w * 1.24, h * 0.62);
    } else if (style === 3) { // bob
      g.beginPath(); g.ellipse(x, y + h * 0.02, w * 0.64, h * 0.6, 0, 0, Math.PI * 2); g.fill();
    }

    // neck
    g.fillStyle = skin;
    g.beginPath();
    g.moveTo(x - w * 0.2, y + h * 0.3); g.lineTo(x + w * 0.2, y + h * 0.3);
    g.lineTo(x + w * 0.2, y + h * 0.72); g.lineTo(x, y + h * 0.9); g.lineTo(x - w * 0.2, y + h * 0.72);
    g.closePath(); g.fill();
    // stole
    if (opt.stole !== false) {
      g.fillStyle = opt.stoleColor || TASSEL;
      g.beginPath();
      g.moveTo(x - w * 0.42, y + h * 0.7); g.lineTo(x - w * 0.12, y + h * 1.05);
      g.lineTo(x - w * 0.2, y + h * 3.6); g.lineTo(x - w * 0.55, y + h * 3.6); g.closePath(); g.fill();
      g.beginPath();
      g.moveTo(x + w * 0.42, y + h * 0.7); g.lineTo(x + w * 0.12, y + h * 1.05);
      g.lineTo(x + w * 0.2, y + h * 3.6); g.lineTo(x + w * 0.55, y + h * 3.6); g.closePath(); g.fill();
    }

    // ears
    g.fillStyle = skin;
    g.beginPath(); g.ellipse(x - w * 0.5, y + h * 0.04, w * 0.09, h * 0.11, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(x + w * 0.5, y + h * 0.04, w * 0.09, h * 0.11, 0, 0, Math.PI * 2); g.fill();
    // face
    g.beginPath(); g.ellipse(x, y, w * 0.5, h * 0.5, 0, 0, Math.PI * 2); g.fill();

    // hair front
    g.fillStyle = hair;
    g.beginPath();
    if (style === 0) {        // short crop
      g.ellipse(x, y - h * 0.22, w * 0.53, h * 0.32, 0, Math.PI, 0); g.fill();
    } else if (style === 2) { // side part
      g.moveTo(x - w * 0.53, y - h * 0.02);
      g.quadraticCurveTo(x - w * 0.55, y - h * 0.56, x, y - h * 0.55);
      g.quadraticCurveTo(x + w * 0.58, y - h * 0.52, x + w * 0.52, y + h * 0.02);
      g.quadraticCurveTo(x + w * 0.25, y - h * 0.32, x - w * 0.18, y - h * 0.26);
      g.quadraticCurveTo(x - w * 0.4, y - h * 0.2, x - w * 0.53, y - h * 0.02); g.fill();
    } else if (style === 4) { // curls
      for (let i = 0; i < 9; i++) {
        const a = Math.PI * (1.05 + i * 0.1);
        g.beginPath();
        g.arc(x + Math.cos(a) * w * 0.48, y - h * 0.08 + Math.sin(a) * h * 0.46, w * 0.17, 0, Math.PI * 2); g.fill();
      }
    } else {                  // fringe (long, bob)
      g.moveTo(x - w * 0.54, y + h * 0.05);
      g.quadraticCurveTo(x - w * 0.56, y - h * 0.56, x, y - h * 0.56);
      g.quadraticCurveTo(x + w * 0.56, y - h * 0.56, x + w * 0.54, y + h * 0.05);
      g.quadraticCurveTo(x + w * 0.44, y - h * 0.22, x, y - h * 0.24);
      g.quadraticCurveTo(x - w * 0.44, y - h * 0.22, x - w * 0.54, y + h * 0.05); g.fill();
    }

    // features
    const eyeY = y + h * 0.04, eyeDX = w * 0.19;
    g.fillStyle = '#1A1412';
    g.beginPath(); g.ellipse(x - eyeDX, eyeY, w * 0.045, h * 0.05, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(x + eyeDX, eyeY, w * 0.045, h * 0.05, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = '#1A1412'; g.lineCap = 'round';
    g.lineWidth = Math.max(1, h * 0.03);
    const smile = opt.smile ?? (0.6 + r() * 0.6);
    g.beginPath(); g.arc(x, y + h * 0.16, w * 0.15 * smile, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke();
    g.fillStyle = 'rgba(220,110,100,0.22)';
    g.beginPath(); g.ellipse(x - w * 0.3, y + h * 0.17, w * 0.09, h * 0.05, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(x + w * 0.3, y + h * 0.17, w * 0.09, h * 0.05, 0, 0, Math.PI * 2); g.fill();

    // mortarboard
    if (cap) {
      const cy = y - h * 0.46, tilt = opt.tilt ?? (r() - 0.5) * 0.25;
      g.save(); g.translate(x, cy); g.rotate(tilt);
      g.fillStyle = '#16161A';
      g.beginPath(); g.ellipse(0, h * 0.05, w * 0.42, h * 0.15, 0, 0, Math.PI); g.fill();
      g.fillRect(-w * 0.42, -h * 0.04, w * 0.84, h * 0.1);
      g.beginPath();
      g.moveTo(-w * 0.95, -h * 0.06); g.lineTo(0, -h * 0.3); g.lineTo(w * 0.95, -h * 0.06); g.lineTo(0, h * 0.16);
      g.closePath(); g.fill();
      g.strokeStyle = TASSEL; g.lineWidth = Math.max(1, h * 0.03);
      g.beginPath(); g.moveTo(0, -h * 0.07); g.lineTo(w * 0.6, -h * 0.02); g.lineTo(w * 0.62, h * 0.32); g.stroke();
      g.fillStyle = TASSEL; g.fillRect(w * 0.58, h * 0.28, w * 0.09, h * 0.16);
      g.restore();
    }
    return { x, y, w: w, h };
  }

  function background(g, W, H, r, kind) {
    const [a, b] = BG[kind ?? Math.floor(r() * BG.length)];
    g.fillStyle = b; g.fillRect(0, 0, W, H);
    g.fillStyle = a; g.fillRect(0, 0, W, H * 0.62);
    // a few architectural shapes for depth
    g.fillStyle = 'rgba(255,255,255,0.35)';
    const n = 2 + Math.floor(r() * 3);
    for (let i = 0; i < n; i++) {
      const cw = W * (0.06 + r() * 0.05), cx = r() * W;
      g.fillRect(cx, H * 0.12, cw, H * 0.5);
    }
  }

  // A whole "photo": 1 to 4 graduates. Returns face boxes in pixel space.
  function photo(g, W, H, seed, opt = {}) {
    const r = rng(seed * 9973 + 17);
    background(g, W, H, r, opt.bg);
    const n = opt.n ?? (1 + Math.floor(r() * 4));
    const faces = [];
    const hh = H * (n === 1 ? 0.3 : n === 2 ? 0.22 : 0.17);
    for (let i = 0; i < n; i++) {
      const fx = W * ((i + 0.5) / n) + (r() - 0.5) * W * 0.04;
      const fy = H * (n === 1 ? 0.5 : 0.52) + (r() - 0.5) * H * 0.06;
      const who = opt.cast?.[i];
      const p = person(g, fx, fy, hh * (0.92 + r() * 0.16), who ? rng(who.seed) : r, who || {});
      faces.push({ x: p.x - p.w * 0.6, y: p.y - p.h * 0.62, w: p.w * 1.2, h: p.h * 1.22 });
    }
    return faces;
  }

  // A head-and-shoulders crop of one cast member.
  function portrait(g, S, who) {
    const r = rng(who.seed);
    background(g, S, S, rng(who.seed + 1), who.bg ?? 0);
    person(g, S / 2, S * 0.5, S * 0.42, r, { ...who, cap: who.cap ?? false });
  }


  // The six people the promo follows. Names are illustrative.
  const CREW = [
    { name: 'Mint', seed: 11, style: 1, skin: '#F2D3BC', hair: '#2B1D16', gown: '#1B2140', bg: 3, smile: 1.1 },
    { name: 'Tan',  seed: 23, style: 0, skin: '#C68B62', hair: '#121212', gown: '#1E1E24', bg: 0, smile: 0.9 },
    { name: 'Ploy', seed: 37, style: 3, skin: '#E8BE9C', hair: '#3B2619', gown: '#2A1F3D', bg: 4, smile: 1.2 },
    { name: 'Bank', seed: 41, style: 2, skin: '#D9A47E', hair: '#1E1714', gown: '#14283A', bg: 1, smile: 0.8 },
    { name: 'Fah',  seed: 53, style: 4, skin: '#8A5638', hair: '#121212', gown: '#1B2140', bg: 2, smile: 1.0 },
    { name: 'Nont', seed: 67, style: 0, skin: '#F5DCC8', hair: '#5A3A24', gown: '#2A1F3D', bg: 3, smile: 1.3 },
  ];

  root.Cast = { CREW, rng, person, photo, portrait, SKIN, HAIR };
})(typeof window !== 'undefined' ? window : globalThis);
