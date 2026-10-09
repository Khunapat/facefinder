---
name: motion-reel
description: Make a promo, launch video, product reel, showreel, animated explainer or motion ad that is rendered entirely from code (a canvas film with window.seek(t), frame-by-frame in headless Chromium, ffmpeg, sound synthesized on the same beat grid) and reviewed frame by frame before delivery. Use this whenever the user wants a video to promote or launch their app, product, platform, startup or event, asks for "motion graphics", "a reel", "a TikTok/Reels/Shorts video", "a launch film", "an ad", "a video like the Opus motion design ones", or wants to turn a product's UI into an animated video, even if they never say "motion design" or "code". Not for editing existing footage or generating video with a video model.
---

# Motion reel

A video here is a program, not a file you can emit. You write one page whose
`window.seek(t)` paints the exact frame for any moment `t`; a headless browser
calls it for every frame, screenshots the canvas, and ffmpeg encodes it. Sound
is synthesized in code from the same timeline, so every hit lands on its cut.

The prompt is a small part of the result. What makes a reel good is the
harness: a real reference, real product assets, a beat grid, and a review loop
where you look at your own frames and fix them before anyone else sees them.
Skipping the loop is how you get the generic first try: centred title on a
gradient, everything fading in, a logo at the end.

## 1. Collect the inputs first

Ask in one short round (use a multiple-choice question tool if you have one),
and default sensibly for anything the user doesn't care about:

- **Product** and where its real UI lives: a URL, a repo you can run, or screenshots.
- **Format and length**: 9:16 1080x1920 for Reels/TikTok/Shorts is the usual
  default; 20 s is a good first length. 1:1 and 16:9 come later from the same timeline.
- **Language** of on-screen text.
- **Brand**: colours, fonts, logo. If the product borrows another company's
  brand colour, propose a replacement rather than shipping it.
- **What to show**: the real UI (preferred) or an abstract story.
- **Music**: a supplied track (measure its beats) or synthesize one.
- **Reference** (optional): a frame, a video or a folder of images whose look to borrow.

## 2. Set up the studio

Check for Node 22+, ffmpeg and Playwright Chromium. Then copy the starter:

```bash
cp -r <skill>/assets/starter ./promo && cd promo
node <skill>/scripts/render.cjs --stills 0.5,2,4 --out out/stills   # proves the toolchain works
```

The starter is a small, working three-shot film. Read `index.html`,
`timeline.js` and `lib/motion.js` once before writing anything; you will
replace the shots but keep the machinery. `scripts/render.cjs` loads Playwright
from a local or global install, so the studio needs no `npm install` when
Playwright is installed globally.

If the network is restricted, check before you plan around it: Google Fonts,
the product's site and package registries may or may not be reachable.

## 3. Gather real assets

Never redraw the product's UI from imagination. Screenshot the real thing and
animate the screenshots. `references/capture.md` covers driving a real app with
Playwright: element screenshots at deviceScaleFactor 3, staging app state
through its own functions, swapping images at the network layer, recording the
positions of buttons for the fingertip, and the traps that cost time.

**People in the video.** Don't put real people's faces into a promo unless the
user owns the rights and the people agreed: sample photos of public figures in
a repo are not a cast. Draw illustrated stand-ins in code instead (seeded, so
every render matches) and swap them in for the real images.

**Staged data.** Demo numbers and names are fine for showing scale, but tell
the user exactly which ones are staged, in your reply and in the README.

## 4. Write the timeline on a beat grid

Put every shot boundary and every moment in `timeline.js` in beats (120 BPM:
a beat is 0.5 s, a bar 2 s), plus the list of sound cues. Picture and sound
both read it, so they cannot drift. Shape:

1. **Hook, 0 to 2 s**: the problem in about five words of huge type over
   something that moves. No logo first.
2. **The product appears** and does its thing: one feature per 2 to 4 s, each
   as a real UI moment with a fingertip or cursor doing the real action.
3. **The payoff**: the result, or one number that proves it.
4. **Lockup and call to action.**

Something new must happen every 2 to 4 seconds. For prompt patterns (one-liner,
brand reel, reference, state-list spec, overnight director's brief) see
`references/prompts.md`.

## 5. Build the film

Rules that keep `seek(t)` deterministic, and why:

- Every value is a function of `t` alone. No timers, no CSS transitions, no
  `requestAnimationFrame` in render mode, no state carried between frames, so
  frame 812 renders without frames 0 to 811 and re-renders are identical.
- Motion uses closed-form springs (`spring`, `track` in `lib/motion.js`). A
  value with several targets sums one spring per change, so it stays continuous.
- Randomness only from the seeded `rng`, never `Math.random`.
- Wait for fonts and images in `window.ready`; canvas text silently falls back
  to a default face if the font has not loaded.

Look: one display face and one UI face, one accent colour. Banned defaults:
centred title on a gradient, everything fading in, text or labels in the
corners, frame borders, glows on UI chrome, generic particle bursts. Keep
on-screen text readable on a phone: in a 1080-wide frame, body UI text should
be about 40 px or larger, so show UI screenshots big and crop or pan rather
than shrinking a whole screen.

## 6. Sound

Start from `assets/starter/audio.cjs`: a small synth (kick, clap, hats, plucked
bass and arpeggio over a chord per bar) plus effects (impact, whoosh, riser,
click, pop, tick, chime) placed from the timeline's cues. If the user supplies
a track, measure its beats first (`scripts/beats.py`, needs librosa) and put
the cuts on the measured beats instead. You cannot hear the result, so say so:
measure loudness and tell the user to listen.

## 7. Review your own frames before showing anything

This is the step that separates a good reel from a mediocre one.
`references/critique.md` has the commands and the rubric. In short:

1. Render one still per beat (`render.cjs --stills ...`), tile them into a
   contact sheet (`scripts/review.sh`), and look at it.
2. Score 1 to 10: hook, readability at phone size, motion, variety,
   composition, brand accuracy, sound sync. List the three worst problems with
   timestamps.
3. Fix them, re-render only the affected stills, look again. At least two
   rounds; stop when everything is 8 or above.
4. Only then render the whole film.

## 8. Render, mix, deliver

```bash
node <skill>/scripts/render.cjs --fps 60 --sub 4 --out out/silent.mp4   # --sub: subframes blended as motion blur
node audio.cjs out/mix.wav
bash <skill>/scripts/mux.sh out/silent.mp4 out/mix.wav out/final.mp4    # -14 LUFS
bash <skill>/scripts/review.sh out/final.mp4                             # final contact sheet + strips
```

A full 20 s render at 60 fps with 4 subframes takes roughly 10 minutes, so run
it in the background. Use 2 subframes for drafts; with 2, fast pans show as a
double image in stills.

Deliver the MP4 itself (send the file if you have a tool for it), a poster
frame, and a short note: what each shot shows, what is real and what is
staged, the proposed brand colour if you changed it, and what you would
improve next. Keep the source with a README that says how to rebuild it.

## Reference files

- `references/capture.md`: screenshotting a real app for the film, and its traps.
- `references/critique.md`: review commands, scoring rubric, what to hunt for.
- `references/prompts.md`: prompt patterns from one-liner to overnight brief.
- `assets/starter/`: the working starter studio (film, kit, timeline, audio).
- `scripts/render.cjs`, `scripts/review.sh`, `scripts/mux.sh`, `scripts/beats.py`.
