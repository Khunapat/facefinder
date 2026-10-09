// The one timeline the picture and the sound both read. Seconds; 120 BPM, so a
// beat is 0.5 s and a bar is 2 s. Shared by index.html (window.TL) and the
// audio scripts (require).

(function (root) {
  const BPM = 120, BEAT = 60 / BPM, DUR = 20;
  const b = (n) => +(n * BEAT).toFixed(3);          // beat n -> seconds

  const TL = {
    BPM, BEAT, DUR, W: 1080, H: 1920,

    // Shot boundaries
    hook:     [0, b(8)],     // 0-4    the wall of 4,000 photos
    brand:    [b(8), b(12)], // 4-6    logo lockup
    paste:    [b(12), b(16)],// 6-8    paste the link
    scan:     [b(16), b(21)],// 8-10.5 every face scanned once
    everyone: [b(21), b(29)],// 10.5-14.5 tick and name
    folders:  [b(29), b(35)],// 14.5-17.5 one folder each
    end:      [b(35), DUR],  // 17.5-20 end card

    // Moments
    hookWord1: b(0) + 0.08, hookWord2: b(1),
    hookSwap: b(4),
    lockOn: b(5.5),          // face box snaps onto Mint
    zoom: b(6.25),
    reveal: b(7.25),
    logo: b(8),
    tagline: b(9),
    pasteIn: b(12),
    typeFrom: b(12.75), typeTo: b(14.5),
    orbTap: b(15),
    scanFrom: b(16), scanTo: b(20.25),
    detect: [b(16.5), b(17), b(17.5), b(18), b(18.5), b(19)],
    cardIn: b(21),
    ticks: [b(22.5), b(23), b(24.5), b(25), b(26.5), b(27)],
    barIn: b(29),
    exportTap: b(30),
    copy: [b(30.5), b(31), b(31.5), b(32)],
    done: b(32.5),
    doneRows: [b(33), b(33.25), b(33.5), b(33.75), b(34), b(34.25)],
    endIn: b(35),
    endLine: b(36),
    endSub: b(37),
  };

  // Sound cues, in the order they happen.
  const C = [];
  const at = (t, type, gain = 1) => C.push({ t: +t.toFixed(3), type, gain });
  at(0, 'impact', 1);
  at(TL.hookWord2, 'thump', 0.7);
  at(TL.hookSwap, 'whoosh', 0.8);
  at(TL.lockOn, 'lock', 0.9);
  at(TL.zoom, 'riser', 0.8);
  at(TL.logo, 'impact', 0.9);
  at(TL.pasteIn, 'whoosh', 0.6);
  for (let i = 0; i < 10; i++) at(TL.typeFrom + (TL.typeTo - TL.typeFrom) * (i + 0.5) / 10, 'key', 0.5);
  at(TL.orbTap, 'click', 1);
  TL.detect.forEach((t) => at(t, 'pop', 0.6));
  at(TL.cardIn, 'whoosh', 0.6);
  TL.ticks.forEach((t) => at(t, 'tick', 0.9));
  at(TL.barIn, 'whoosh', 0.5);
  at(TL.exportTap, 'click', 1);
  TL.copy.forEach((t) => at(t, 'pop', 0.4));
  at(TL.done, 'chime', 0.9);
  at(TL.endIn, 'whoosh', 0.8);
  at(TL.endLine, 'impact', 0.7);
  TL.cues = C;

  if (typeof module !== 'undefined') module.exports = TL;
  else root.TL = TL;
})(typeof window !== 'undefined' ? window : globalThis);
