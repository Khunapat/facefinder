# Reviewing your own frames

You can read images, so look at what you rendered before anyone else does.
Clips that went viral were iterated; ones posted with "it's a bit mid" were
first tries. Plan on at least two review rounds before the full render.

## Commands

```bash
# one still per beat (120 BPM: every 0.5 s, offset so you land mid-beat)
T=$(python3 -c "print(','.join(str(round(i*0.5+0.25,2)) for i in range(40)))")
node <skill>/scripts/render.cjs --stills $T --out out/stills
bash <skill>/scripts/review.sh out/stills                 # -> out/contact.png

# only the moments you changed, bigger
node <skill>/scripts/render.cjs --stills 3.3,3.6,3.8 --out out/fix

# after a full render: contact sheet at 2 fps, phone-size test, poster, strips
bash <skill>/scripts/review.sh out/final.mp4 3.0 11.0     # strips of 12 frames from 3.0 s and 11.0 s
```

Look at a strip around every fast move (zooms, swaps, wipes): a contact sheet
samples too sparsely to catch a pop or an overlap between two frames.

## Score it like a harsh motion director

Score 1 to 10 on each, then write the three biggest problems with timestamps:

- **Hook**: does the first 2 s stop a scroll? Big type, motion, no logo first.
- **Readability at phone size**: view the phone sheet at 360 px wide. Can you
  read every word? UI text under ~40 px in a 1080-wide frame usually fails.
- **Motion quality**: springs, not linear slides; no dead frames; nothing pops in.
- **Variety**: something new every 2 to 4 s.
- **Composition**: no empty half-frames, nothing crowding the edges, type and UI
  not fighting for the same space.
- **Brand accuracy**: real UI, real colours, one accent.
- **Sound sync**: cuts and taps on the beat. You can't hear it, but you can
  check cue times against the picture's moments in `timeline.js`, and measure
  loudness (`review.sh` prints it; aim for about -14 LUFS integrated).

## What to hunt for

Each of these happened in real builds:

- **Text that never leaves.** A caller set `globalAlpha` to fade a block, but a
  helper set its own alpha per word and overrode it. Pass alpha into the helper.
- **A white flash or empty frame** between shots: a transition finished early
  (or started late), leaving dead frames. Check the strip around every cut.
- **A reveal or zoom aimed at the wrong point**: compute the target's on-screen
  position through the same transforms the camera applies.
- **A top-heavy or bottom-empty composition**: lockups placed for a 16:9 eye
  in a 9:16 frame. Centre the mass of the shot, not its first element.
- **Clipped UI text**: a crop height that cuts a wrapped second line.
- **Ghosted double text** in stills during fast pans: that is 2-subframe
  motion blur. Use 4 subframes for the final render.
- Plus the usual: overlapping text during swaps, corner labels or frame
  borders, a centred title on a gradient, blurry upscaled text, a dead beat,
  a stutter at a loop seam.

Fix the worst three, re-render only the affected stills, look again. Stop when
every score is 8 or above, then do the full render and one last review of the
final file.
