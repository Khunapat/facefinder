# FaceFinder promo

A 20-second vertical (1080x1920, 60 fps) promo video. Everything is code: the
picture is a canvas program with `window.seek(t)`, and the music and sound
effects are synthesized from the same timeline.

## Rebuild it

```bash
# 1. the app, on the offline stand-in for Drive (repo root)
python -m tests.devserver

# 2. screenshot the real UI pieces into assets/ui/
node promo/capture.cjs

# 3. sound: score + effects -> out/mix.wav
cd promo && node audio.cjs out/mix.wav

# 4. picture: frame by frame in headless Chromium -> out/silent.mp4
node render.cjs --fps 60 --sub 4            # --sub = subframes blended for motion blur

# 5. mux, loudness-normalised to -14 LUFS
ffmpeg -i out/silent.mp4 -i out/mix.wav -filter:a loudnorm=I=-14:TP=-1.5:LRA=11 \
  -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart out/facefinder-promo.mp4
```

Open `index.html` in a browser for a live, looping preview. For review stills,
`node render.cjs --stills 0.5,4.5,12 --out out/stills`.

Needs Node 22, ffmpeg and Playwright's Chromium. Playwright is loaded from the
global install (`lib/pw.cjs`), so there is no `npm install`.

## Files

| file | what it is |
|---|---|
| `timeline.js` | every shot and moment on a 120 BPM grid, plus the sound cues. Picture and sound both read it |
| `index.html` | the film. `window.seek(t)` paints frame `t`; closed-form springs, no timers |
| `lib/cast.js` | the illustrated graduates, drawn in code from a seed |
| `capture.cjs` | drives the real app and screenshots the pieces the film animates |
| `render.cjs` | walks time, screenshots the canvas, pipes frames to ffmpeg |
| `audio.cjs` | the score (C G Am F, 120 BPM) and effects, written as a WAV |

## What is real and what is staged

The UI is the real `app/static/index.html`, served by the real app. Three
things are staged for the video:

- **The accent.** `--accent` is overridden to `#2E4BE8` (hover `#2238C2`,
  disabled `#C7CFF8`), the proposed replacement for the Airbnb pink. White on
  `#2E4BE8` is 6.4:1. Copy those three values into `app/static/index.html` to
  ship the same look.
- **The people.** Face crops are swapped at the network layer for the
  illustrated cast, so no real person's face appears. The names (Mint, Tan,
  Ploy, Bank, Fah, Nont) are made up.
- **The numbers.** A 4,000-photo album, "3,912 photos with faces", 630 photos
  across six folders. They show the scale the app is built for; they are not
  measurements.
