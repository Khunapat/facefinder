// The staged camp album: illustrated photos drawn in code from a seed, used by
// capture.cjs (served to the real app in place of Drive thumbnails) and by the
// film itself (the wall of photos in the hook). Nobody in them is real.

(function (root) {
  const C = root.Cast;
  const SHIRT = { blue: '#2F6FD6', orange: '#F08A24', green: '#2E9E6A', white: '#F1F1EE', red: '#D9463B' };

  // A camper: a cast member in a camp shirt instead of a gown.
  const kid = (seed, shirt, more = {}) => ({ seed, gown: SHIRT[shirt], stole: false, cap: false, ...more });

  // The four people the film names. Names are illustrative.
  const CREW = [
    { name: 'Mint', ...kid(11, 'blue', { style: 1, skin: '#F2D3BC', hair: '#2B1D16', bg: 3, smile: 1.1 }) },
    { name: 'Tan',  ...kid(23, 'orange', { style: 0, skin: '#C68B62', hair: '#121212', bg: 0, smile: 0.9 }) },
    { name: 'Ploy', ...kid(37, 'blue', { style: 3, skin: '#E8BE9C', hair: '#3B2619', bg: 4, smile: 1.2 }) },
    { name: 'Bank', ...kid(41, 'orange', { style: 2, skin: '#D9A47E', hair: '#1E1714', bg: 1, smile: 0.8 }) },
  ];

  // Photos by id. fx: 'blur' | 'dark' | null.
  const SPEC = {
    // Cull: the Review pile, each with its flaw
    'cull-0': { seed: 301, bg: 1, cast: [kid(71, 'blue'), kid(72, 'blue', { eyesClosed: true }), kid(73, 'orange')] },
    'cull-1': { seed: 302, bg: 0, cast: [kid(74, 'orange'), kid(75, 'blue')], fx: 'blur' },
    'cull-2': { seed: 303, bg: 4, cast: [CREW[0], CREW[2]] },
    'cull-3': { seed: 304, bg: 2, cast: [kid(76, 'green'), kid(77, 'orange'), kid(78, 'blue')], fx: 'dark' },
    'cull-4': { seed: 305, bg: 3, cast: [kid(79, 'blue')] },
    'cull-5': { seed: 306, bg: 0, cast: [kid(80, 'orange'), kid(81, 'orange')] },
    // Sort: blue team and orange team
    'blue-0': { seed: 401, bg: 0, cast: [kid(82, 'blue'), CREW[0], kid(83, 'blue')] },
    'blue-1': { seed: 402, bg: 1, cast: [CREW[2], kid(84, 'blue')] },
    'blue-2': { seed: 403, bg: 4, cast: [kid(85, 'blue'), kid(86, 'blue'), kid(87, 'blue'), kid(88, 'blue')] },
    'blue-3': { seed: 404, bg: 2, cast: [kid(89, 'blue')] },
    'orange-0': { seed: 501, bg: 3, cast: [CREW[1], kid(90, 'orange'), CREW[3]] },
    'orange-1': { seed: 502, bg: 0, cast: [kid(91, 'orange'), kid(92, 'orange')] },
  };
  const MIX = ['blue', 'orange', 'green', 'white', 'red'];
  const wallSpec = (i) => {
    const r = C.rng(1000 + i * 7);
    const n = 1 + Math.floor(r() * 4);
    return { seed: 1000 + i, bg: i % 5, cast: Array.from({ length: n }, (_, k) => kid(2000 + i * 5 + k, MIX[Math.floor(r() * MIX.length)])) };
  };
  // 'cull-0~12' is the 12th copy of cull-0: a separate file id, the same picture.
  const spec = (id) => { id = id.split('~')[0]; return SPEC[id] || wallSpec(+(/\d+/.exec(id) || [0])[0]); };

  // Draw photo `id` into a canvas context of size W x H.
  function draw(g, W, H, id) {
    const s = spec(id);
    const tmp = g.canvas.ownerDocument.createElement('canvas'); tmp.width = W; tmp.height = H;
    const faces = C.photo(tmp.getContext('2d'), W, H, s.seed, { n: s.cast.length, bg: s.bg, cast: s.cast });
    g.save();
    if (s.fx === 'blur') g.filter = `blur(${Math.round(W / 90)}px)`;
    g.drawImage(tmp, 0, 0);
    g.filter = 'none';
    if (s.fx === 'dark') { g.fillStyle = 'rgba(10,8,20,0.66)'; g.fillRect(0, 0, W, H); }
    g.restore();
    return faces;
  }

  root.Photos = { SHIRT, CREW, SPEC, spec, draw, kid };
})(typeof window !== 'undefined' ? window : globalThis);
