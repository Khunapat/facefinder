# Motion reel studio

A film rendered from code. `index.html` paints any frame on demand through
`window.seek(t)`; the renderer walks time and pipes frames to ffmpeg; the
score and effects are synthesized from the same `timeline.js`.

```bash
open index.html                                          # live, looping preview
node render.cjs --stills 0.5,2,4 --out out/stills        # review stills
node render.cjs --fps 60 --sub 4 --out out/silent.mp4    # the film (sub = motion-blur subframes)
node audio.cjs out/mix.wav                               # the score
bash mux.sh out/silent.mp4 out/mix.wav out/final.mp4     # mixed to -14 LUFS
```

(`render.cjs`, `review.sh` and `mux.sh` live in the motion-reel skill's
`scripts/`; copy them in or call them by path.)

| file | what it is |
|---|---|
| `timeline.js` | shots, moments and sound cues on a 120 BPM grid; read by picture and sound |
| `index.html` | the film; one draw function per shot |
| `lib/motion.js` | springs, `track`, seeded noise, kinetic type, screenshot panels, fingertip |
| `audio.cjs` | drums, bass, arpeggio over `TL.chords`, and effects from `TL.cues` |
| `assets/ui/` | real UI screenshots, if the film uses them |

Rules: every frame is a pure function of `t` (no timers, transitions or carried
state), randomness only from the seeded `rng`, one display face, one UI face,
one accent.
