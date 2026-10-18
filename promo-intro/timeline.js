// The one timeline the picture and the sound both read. Seconds, 120 BPM
// (a beat is 0.5 s). Shared by index.html (window.TL) and audio.cjs.
(function (root) {
  const TL = {
    BPM: 120, BEAT: 0.5, DUR: 19, W: 1920, H: 1080,
    // 0-5 s: the Drive folder, then Ploy's message
    count: 0.1, word2: 0.9, wordOut: 1.75,
    phoneIn: 2.0, typing: 2.25, msg1: 2.75, msg2: 3.5, phoneOut: 4.75,
    // 5-8 s: scrolling and scrolling
    frantic: 5.0, cap3: 5.25, cap4: 6.5, capOut: 7.75,
    // 8-12.5 s: FaceFinder
    wipe: 8.0, faster: 8.25, appIn: 9.0, typeFrom: 9.25, typeTo: 9.9, open: 10.0,
    scanIn: 10.25, scanFrom: 10.5, scanTo: 12.0, stages: [10.75, 11.25, 11.75, 12.0],
    // 12.5-16.5 s: a folder for Ploy, sent
    everyIn: 12.5, ploy: 13.25, phone2In: 14.5, sent: 14.75, reply: 15.5,
    // 16.5-19 s: lockup
    endIn: 16.5, endLine: 17.0, endSub: 17.75,
  };
  const C = [], at = (t, type, gain = 1) => C.push({ t, type, gain });
  at(0, 'impact', 1); at(TL.word2, 'thump', 0.7);
  at(TL.phoneIn, 'whoosh', 0.6); at(TL.msg1, 'msg', 1); at(TL.msg2, 'msg', 0.9);
  at(TL.phoneOut, 'whoosh', 0.5);
  for (let i = 0; i < 10; i++) at(5.1 + i * 0.29, 'scroll', 0.5);
  at(TL.cap3, 'thump', 0.6); at(TL.cap4, 'thump', 0.6);
  at(7.25, 'riser', 0.8); at(TL.wipe, 'impact', 0.9); at(TL.faster, 'pop', 0.6);
  at(TL.appIn, 'whoosh', 0.6);
  for (let i = 0; i < 6; i++) at(TL.typeFrom + (TL.typeTo - TL.typeFrom) * (i + 0.5) / 6, 'key', 0.5);
  at(TL.open, 'click', 1);
  TL.stages.forEach((t) => at(t, 'tick', 0.8));
  at(TL.everyIn, 'whoosh', 0.6); at(TL.ploy, 'chime', 0.8);
  at(TL.phone2In, 'whoosh', 0.5); at(TL.sent, 'send', 1); at(TL.reply, 'msg', 1);
  at(TL.endIn, 'whoosh', 0.8); at(TL.endLine, 'impact', 0.7);
  TL.cues = C;
  if (typeof module !== 'undefined') module.exports = TL; else root.TL = TL;
})(typeof window !== 'undefined' ? window : globalThis);
