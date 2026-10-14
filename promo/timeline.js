// The one timeline the picture and the sound both read. Seconds; 120 BPM, so a
// beat is 0.5 s and a bar is 2 s. Shared by index.html (window.TL) and the
// audio script (require).

(function (root) {
  const BPM = 120, BEAT = 60 / BPM, DUR = 20;
  const b = (n) => +(n * BEAT).toFixed(3);          // beat n -> seconds

  const TL = {
    BPM, BEAT, DUR, W: 1080, H: 1920,

    // Shot boundaries
    hook:     [0, b(6)],      // 0-3     a wall of 800 camp photos
    brand:    [b(6), b(10)],  // 3-5     mascot + wordmark + promise
    scan:     [b(10), b(15)], // 5-7.5   faces found, every photo checked
    everyone: [b(15), b(20)], // 7.5-10  a folder for each person
    cull:     [b(20), b(27)], // 10-13.5 keep the best, see why, one tap
    sort:     [b(27), b(32)], // 13.5-16 describe it (in Thai), Gemini sorts
    exp:      [b(32), b(36)], // 16-18   straight into Drive
    end:      [b(36), DUR],   // 18-20   lockup

    // Hook
    hookWord1: 0.08, hookWord2: b(1), hookSwap: b(3),
    zoom: b(4.5),             // riser starts (the name the audio script reads)
    reveal: b(5.25),          // page-pink circle opens from the middle
    // Brand
    logo: b(6), word: b(6.75), tagline: b(7.75),
    // Scan: the nine captured states, then the stage changes that get a tick
    scanIn: b(10), scanFrom: b(10.75), scanTo: b(14.25),
    stages: [b(11.5), b(13), b(14.25)],
    // Everyone
    cardIn: b(15), ticks: [b(16), b(17), b(18), b(19)],
    // Cull
    cullIn: b(20), tapTile: b(22), previewOpen: b(22.25), cap2: b(23),
    tapOut: b(24.5), previewClose: b(25.75),
    // Sort
    sortIn: b(27), typeFrom: b(27.75), typeTo: b(29.5), tapSort: b(30), sortRes: b(30.5),
    // Export
    barIn: b(32), exportTap: b(32.75), copy: [b(33.25), b(33.75), b(34.25), b(34.75)],
    done: b(35), doneRows: [b(35.5), b(35.75)],
    // End
    endIn: b(36), endLine: b(37), endSub: b(38),
  };

  // Sound cues, in the order they happen.
  const C = [];
  const at = (t, type, gain = 1) => C.push({ t: +t.toFixed(3), type, gain });
  at(0, 'impact', 1);
  at(TL.hookWord2, 'thump', 0.7);
  at(TL.hookSwap, 'whoosh', 0.8);
  at(TL.zoom, 'riser', 0.8);
  at(TL.logo, 'impact', 0.9);
  at(TL.word, 'pop', 0.6);
  at(TL.scanIn, 'whoosh', 0.6);
  TL.stages.forEach((t) => at(t, 'tick', 0.8));
  at(TL.cardIn, 'whoosh', 0.6);
  TL.ticks.forEach((t) => at(t, 'tick', 0.9));
  at(TL.cullIn, 'whoosh', 0.6);
  at(TL.tapTile, 'click', 1);
  at(TL.previewOpen, 'pop', 0.5);
  at(TL.tapOut, 'click', 1);
  at(TL.previewClose, 'whoosh', 0.4);
  at(TL.sortIn, 'whoosh', 0.6);
  for (let i = 0; i < 6; i++) at(TL.typeFrom + (TL.typeTo - TL.typeFrom) * (i + 0.5) / 6, 'key', 0.5);
  at(TL.tapSort, 'click', 1);
  at(TL.sortRes, 'pop', 0.6);
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
