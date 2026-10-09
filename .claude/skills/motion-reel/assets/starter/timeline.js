// The one timeline the picture and the sound both read. Work in beats:
// at 120 BPM a beat is 0.5 s and a bar is 2 s. Loaded by index.html
// (window.TL) and by audio.cjs (require).
//
// This is the starter's 6-second demo. Replace the shots and moments with
// your film's, keeping the shape: shot ranges, named moments, then cues.

(function (root) {
  const BPM = 120, BEAT = 60 / BPM;
  const b = (n) => +(n * BEAT).toFixed(3);      // beat n -> seconds

  const TL = {
    BPM, BEAT, DUR: b(12),
    W: 1080, H: 1920,                            // 9:16. 1080x1080 for 1:1, 1920x1080 for 16:9

    // Shots
    hook: [0, b(4)],
    product: [b(4), b(8)],
    end: [b(8), b(12)],

    // Moments
    hookIn: 0.08, hookSwap: b(2),
    cardIn: b(4), tap: b(6),
    endIn: b(8), endLine: b(9),
  };

  // Sound cues: { t, type, gain }. Types are the effects in audio.cjs.
  const C = [];
  const at = (t, type, gain = 1) => C.push({ t: +t.toFixed(3), type, gain });
  at(0, 'impact');
  at(TL.hookSwap, 'whoosh', 0.7);
  at(TL.cardIn, 'whoosh', 0.6);
  at(TL.tap, 'click');
  at(TL.tap + 0.05, 'chime', 0.6);
  at(TL.endIn, 'whoosh', 0.7);
  at(TL.endLine, 'impact', 0.7);
  TL.cues = C;

  // Chords, one per bar, for the synthesized score: [bass root midi, chord tones].
  TL.chords = [
    [48, [60, 64, 67]],  // C
    [55, [55, 59, 62]],  // G
    [57, [57, 60, 64]],  // Am
    [53, [53, 57, 60]],  // F
  ];

  if (typeof module !== 'undefined') module.exports = TL;
  else root.TL = TL;
})(typeof window !== 'undefined' ? window : globalThis);
