// node audio.cjs out/mix.wav
// Score and sound effects, synthesized from the same timeline as the picture:
// kick, clap, hats, plucked bass and arpeggio over TL.chords (one per bar,
// cycling), and the effects in FX placed from TL.cues. Deterministic: seeded
// noise only. Optional TL.dropouts: [[from, to], ...] seconds with no drums,
// e.g. under a riser before a big reveal.

const fs = require('fs');
const TL = require('./timeline.js');

const SR = 48000, N = Math.ceil((TL.DUR + 0.05) * SR);
const L = new Float32Array(N), R = new Float32Array(N);
const BEAT = TL.BEAT, BAR = BEAT * 4;

let seed = 7;
const noise = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 2147483648) - 1;
const midi = (m) => 440 * Math.pow(2, (m - 69) / 12);

function add(t0, len, fn, gain = 1, pan = 0) {
  const s0 = Math.floor(t0 * SR), n = Math.floor(len * SR);
  const gl = gain * Math.cos((pan + 1) * Math.PI / 4), gr = gain * Math.sin((pan + 1) * Math.PI / 4);
  for (let i = 0; i < n; i++) {
    const k = s0 + i; if (k < 0 || k >= N) continue;
    const v = fn(i / SR, i);
    L[k] += v * gl * Math.SQRT2; R[k] += v * gr * Math.SQRT2;
  }
}

// ---------------------------------------------------------------- voices
// Plucked saw: additive harmonics, the high ones dying first, like a closing filter.
function pluck(f, len, bright = 1) {
  const H = Math.max(1, Math.min(14, Math.floor(9000 / f)));
  return (t) => {
    let v = 0;
    for (let h = 1; h <= H; h++) v += Math.sin(2 * Math.PI * f * h * t) / h * Math.exp(-t * (3 + h * 2.2 / bright));
    return v * 0.5 * Math.min(1, t / 0.003) * Math.min(1, (len - t) / 0.02);
  };
}
const kick = (t) => Math.sin(2 * Math.PI * (48 * t + 90 * (1 - Math.exp(-t * 28)) / 28 * 1)) * Math.exp(-t * 7)
  + Math.sin(2 * Math.PI * 150 * t) * Math.exp(-t * 60) * 0.3;
function clap() {
  let lp = 0;
  return (t) => {
    const env = (t < 0.03 ? (Math.exp(-((t % 0.01) * 300))) : Math.exp(-(t - 0.03) * 22)) * 0.9;
    const n = noise(); lp += 0.45 * (n - lp);
    return (n - lp) * env;
  };
}
function hat(open) {
  let prev = 0;
  return (t) => { const n = noise(); const hp = n - prev; prev = n; return hp * Math.exp(-t * (open ? 18 : 70)) * 0.5; };
}

// ---------------------------------------------------------------- score
const BARS = Math.ceil(TL.DUR / BAR);
const CHORDS = TL.chords || [[48, [60, 64, 67]], [55, [55, 59, 62]], [57, [57, 60, 64]], [53, [53, 57, 60]]];
const silentDrums = (t) => (TL.dropouts || []).some(([a, b]) => t >= a && t < b) || t >= TL.DUR - 0.5;

for (let bar = 0; bar < BARS; bar++) {
  const t0 = bar * BAR, last = bar === BARS - 1;
  const [root, tones] = last ? CHORDS[0] : CHORDS[bar % CHORDS.length];   // resolve home at the end
  for (let b = 0; b < 4; b++) {
    const tb = t0 + b * BEAT;
    if (!silentDrums(tb)) add(tb, 0.45, kick, 0.95);
    if (bar >= 1 && (b === 1 || b === 3) && !silentDrums(tb)) add(tb, 0.3, clap(), 0.35, 0.05);
    const dense = bar >= 2;
    for (let s = 0; s < (dense ? 4 : 2); s++) {
      const th = tb + (dense ? s * BEAT / 4 : BEAT / 2 * s + BEAT / 4);
      if (!silentDrums(th)) add(th, 0.12, hat(false), s % 2 ? 0.16 : 0.22, 0.35);
    }
    if (!silentDrums(tb + BEAT / 2)) add(tb + BEAT / 2, 0.25, hat(true), 0.12, -0.3);
    for (let e = 0; e < 2; e++) {                       // bass on eighths
      if (last && b > 0) continue;
      add(tb + e * BEAT / 2, BEAT / 2, pluck(midi(root - 24 + (root < 50 ? 12 : 0)), BEAT / 2, 0.6), e ? 0.35 : 0.5);
    }
  }
  if (bar >= 1 && !last) {                              // 16th arpeggio across the chord
    for (let s = 0; s < 16; s++) {
      const m = tones[s % 3] + 12 + (Math.floor(s / 4) % 2 ? 12 : 0);
      add(t0 + s * BEAT / 4, 0.3, pluck(midi(m), 0.3, 1.4), 0.11, s % 2 ? 0.4 : -0.4);
    }
  }
  tones.forEach((m, i) => add(t0, last ? 2 : 0.9, pluck(midi(m + 12), last ? 2 : 0.9, 0.9), last ? 0.2 : 0.12, (i - 1) * 0.5));
}

// ---------------------------------------------------------------- effects
function whoosh(len) {
  let lp = 0;
  return (t) => {
    const u = t / len, cut = 0.02 + 0.5 * Math.sin(Math.PI * u) ** 2;
    lp += cut * (noise() - lp);
    return lp * Math.sin(Math.PI * Math.min(1, u)) ** 1.5 * 1.6;
  };
}
const FX = {
  impact: [0.9, () => { let lp = 0; return (t) => { lp += 0.1 * (noise() - lp);
    return Math.sin(2 * Math.PI * (40 * t + 60 * (1 - Math.exp(-t * 12)) / 12)) * Math.exp(-t * 4) + lp * Math.exp(-t * 9) * 1.5; }; }],
  thump: [0.4, () => (t) => Math.sin(2 * Math.PI * (60 * t + 50 * (1 - Math.exp(-t * 20)) / 20)) * Math.exp(-t * 10)],
  whoosh: [0.45, () => whoosh(0.45)],
  riser: [1, () => { const len = 1, w = whoosh(len * 2); let ph = 0;
    return (t) => { const u = t / len; ph += 2 * Math.PI * (200 + 900 * u * u) / SR;
      return (w(t * 0.5 + len * 0.5 * u) * 0.6 + Math.sin(ph) * 0.15) * u * u; }; }],
  lock: [0.25, () => (t) => (Math.sin(2 * Math.PI * 1320 * t) * (t < 0.07 ? 1 : 0) + Math.sin(2 * Math.PI * 1980 * t) * (t >= 0.07 ? 1 : 0)) * Math.exp(-((t % 0.07) * 30)) * 0.35],
  key: [0.04, () => (t) => noise() * Math.exp(-t * 180) * 0.6],
  click: [0.08, () => (t) => (Math.sin(2 * Math.PI * 2200 * t) * 0.5 + noise() * 0.5) * Math.exp(-t * 110)],
  pop: [0.15, () => (t) => Math.sin(2 * Math.PI * (500 * t + 2400 * t * t)) * Math.exp(-t * 28) * 0.6],
  tick: [0.18, () => (t) => (Math.sin(2 * Math.PI * 1568 * t) + 0.5 * Math.sin(2 * Math.PI * 2352 * t)) * Math.exp(-t * 26) * 0.45],
  chime: [1.6, () => (t) => [1047, 1319, 1568, 2093].reduce((v, f, i) => v + Math.sin(2 * Math.PI * f * t) * Math.exp(-t * (2.5 + i)) / (i + 1.5), 0) * 0.5],
};
for (const c of TL.cues) {
  const [len, mk] = FX[c.type];
  // a whoosh peaks on its cue; a riser ends on it (put the cue on the hit it leads into)
  const t0 = c.type === 'whoosh' ? c.t - 0.2 : c.type === 'riser' ? c.t - len : c.t - 0.005;
  add(t0, len, mk(), 0.55 * c.gain, 0);
}

// ---------------------------------------------------------------- write
let peak = 0;
for (let i = 0; i < N; i++) { L[i] = Math.tanh(L[i] * 0.7); R[i] = Math.tanh(R[i] * 0.7); peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i])); }
const fade = Math.floor(0.4 * SR);
for (let i = 0; i < fade; i++) { const k = N - 1 - i, g = i / fade; L[k] *= g; R[k] *= g; }
const out = process.argv[2] || 'out/mix.wav';
const b = Buffer.alloc(44 + N * 4);
b.write('RIFF', 0); b.writeUInt32LE(36 + N * 4, 4); b.write('WAVEfmt ', 8);
b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(2, 22);
b.writeUInt32LE(SR, 24); b.writeUInt32LE(SR * 4, 28); b.writeUInt16LE(4, 32); b.writeUInt16LE(16, 34);
b.write('data', 36); b.writeUInt32LE(N * 4, 40);
for (let i = 0; i < N; i++) {
  b.writeInt16LE(Math.round(L[i] / peak * 0.95 * 32767), 44 + i * 4);
  b.writeInt16LE(Math.round(R[i] / peak * 0.95 * 32767), 46 + i * 4);
}
fs.writeFileSync(out, b);
console.log('->', out);
