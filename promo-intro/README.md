# FaceFinder intro (19 s, 16:9)

The opening of the demo video, before the real screen recording.

| Time | Shot |
|---|---|
| 0–2 s | A shared Drive folder, "Camp 2026", counts up to 800 photos |
| 2–5 s | Ploy messages: "Can you send me all the photos of us? Just the ones with me!" |
| 5–8 s | Scrolling faster and faster. "Scroll. Zoom. Squint." "Still 762 photos to go." |
| 8–12.5 s | "There's a faster way." Paste the Drive link; the scan card runs to Ready |
| 12.5–16.5 s | A folder for each person; Ploy's 143 photos are sent back to her |
| 16.5–19 s | FaceFinder lockup with the mascot |

**Staged:** everything. The people are drawn in code (`../promo/lib/cast.js`,
`../promo/lib/photos.js`); nobody is real. The album, the 800 photos, the
counts (762, 143) and the chat are made up. The Drive folder view and the chat
phone are generic drawings, not Google's or LINE's UI. The scan and people
cards are screenshots of the real app (`../promo/assets/ui/`, captured with the
staged album). The end card says "Illustrative animation".

## Rebuild

Needs Node 22+, ffmpeg and Playwright Chromium.

```bash
cd promo-intro
node render.cjs --stills 1,3,6,9,11,14,18 --out out/stills   # check frames
node render.cjs --fps 30 --sub 2 --out out/silent.mp4        # about 4 minutes
node audio.cjs out/mix.wav
ffmpeg -y -i out/silent.mp4 -i out/mix.wav -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:a aac -b:a 192k -shortest out/facefinder-intro.mp4
```

Open `index.html` in a browser to preview it live.
