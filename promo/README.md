# FaceFinder promo

A 20-second vertical (1080x1920, 60 fps) promo video. Everything is code: the
picture is a canvas program with `window.seek(t)`, and the music and sound
effects are synthesized from the same timeline.

| time | shot |
|---|---|
| 0-3 s | a wall of camp photos: "800 camp photos. Now sort them." |
| 3-5 s | the camera mascot, the wordmark, "Sort your album any way you can describe it." |
| 5-7.5 s | the real scanning screen, its real stages, the mascot animated beside the progress |
| 7.5-10 s | Everyone: four faces ticked and named, "A folder for each person." |
| 10-13.5 s | Cull: the Review pile, a photo opened, "Why: ... eyes shut", Exclude |
| 13.5-16 s | Sort by description: a Thai rule typed, Blue team and Orange team folders |
| 16-18 s | Export to Drive: the copy, then "649 photos copied into 2 folders" |
| 18-20 s | lockup on the pink accent |

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
| `lib/cast.js` | illustrated people, drawn in code from a seed |
| `lib/photos.js` | the staged camp album: which photo shows whom, in which shirt, with which flaw |
| `capture.cjs` | drives the real app and screenshots the pieces the film animates |
| `render.cjs` | walks time, screenshots the canvas, pipes frames to ffmpeg |
| `audio.cjs` | the score (C G Am F, 120 BPM) and effects, written as a WAV |

## What is real and what is staged

The UI is the real `app/static/index.html`, served by the real app, in its own
pink brand with the camera mascot from `design-canvas/assets/`. Staged for the
video:

- **The people and photos.** Every photo and face is an illustration from
  `lib/photos.js`, swapped in at the network layer, so no real person appears.
  The names (Mint, Tan, Ploy, Bank) are made up.
- **The numbers.** An 800-photo camp album, 1,920 faces, Keep 612 / Review 143 /
  Rejected 45, 352 + 297 photos in the two team folders. They show the scale the
  app is built for; they are not measurements.
- **The results.** The cull reasons and the sorted folders are written into the
  app's own state for the shot; they are not a live Gemini run.
- **The scanning mascot** is hidden in the capture and drawn by the film with
  the app's own bob-and-beam motion, so it moves.
