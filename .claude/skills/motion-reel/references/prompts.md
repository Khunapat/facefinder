# Prompt patterns

When the user hands you a one-line request, expand it into the matching
pattern below yourself: these are the shapes that produced good films. Use them
to decide what to ask for, and as the brief you work from.

## Contents
1. One-liner showreel (a test of the engine, not an idea)
2. Brand reel (point it at a product)
3. Reference (borrow a look)
4. State-list spec (one shape that morphs through the product)
5. Director's brief (long films, overnight runs)
6. Variants that worked

## 1. One-liner showreel

```
make a dynamic 15-second motion graphics video that shows what an incredible
motion designer you are, like it's your showreel for a résumé. go all out.
```

Why it works: "showreel for a résumé" names a genre with known rules (fast
cuts, a new technique every shot, best work first); making the model the
subject means there is no product content to get wrong; 15 s fits 6 to 8 shots.
Its weakness: hundreds of people ran it and the reels rhyme with each other.
Use it to test the setup. For a product, use the brand reel.

## 2. Brand reel

```
Make a dynamic 20-second motion graphics video for [PRODUCT] ([URL]), with the
energy of a motion designer's showreel. Go all out.

Assets
- Use real screenshots (Playwright), the real logo, real colours and fonts.
  Save them to ./assets and list what you found before you animate.
- Never redraw the product UI from imagination. Crop and animate the real thing.

Story (one beat each, 2 to 4 seconds)
1. Hook: the problem in 5 words of huge kinetic type.
2. The product appears; the UI assembles itself piece by piece.
3. Three features, each a UI moment with a cursor or finger doing a real action.
4. One number that proves it works: [METRIC].
5. Logo lockup + [CTA].

Sound: original music, 120 BPM, synthesized in code. UI clicks and whooshes on the beat.
Format: 1080x1920 first, then 1:1 and 16:9 from the same timeline.
Before the full render, show a contact sheet of one frame per beat.
```

The three lines that matter most: the product URL, "use the real product
screenshots, logo and assets", and "it must have music". Keep one session per
brand: the second video in the same session is faster because the renderer,
synth and export already exist.

Voice or a mascot: if the user has a voice API key, it lives in `.env` and the
prompt only names the variable. Never paste a real key into a prompt or a file
you'll show.

## 3. Reference

Without a reference the model falls back to its defaults. Naming a style beats
describing one, and a frame or a video gives pacing, type and transitions.

```
Reference: ./refs/launch.mp4 (and ./refs/frames/*.png)
1. Extract one frame every 0.5 s with ffmpeg. Study them.
2. Write docs/style_guide.md: palette (hex), type (family, weight, tracking),
   shot lengths, transition types, camera moves, texture, how text enters and exits.
3. Write docs/shotlist.md for a [DURATION] s video about [SUBJECT] in THAT style.
   Take the grammar of the reference, never its content, logos or characters.
4. Show both files and wait for an OK before any code.
```

A folder of the user's own images or past work is a reference nobody else can
copy: write a style guide from it first. Specify the look and the constraints,
not the library.

## 4. State-list spec

One container never cuts: every state is the same element changing size,
radius and fill while its content swaps; a cursor drives every change; the last
frame equals the first so it loops.

```
<inputs>
Ask for: product + URL, 8 to 12 UI states that tell its story, the real data in each,
brand colours + fonts + one accent, a track near 120 BPM, formats.
</inputs>
<direction>
Product-film UI motion. One container never cuts. A cursor drives every change.
Neutral canvas, one accent. Springs with at most a tiny overshoot.
Banned: bouncy easing, glows, gradients on UI chrome, particle bursts, dead time.
</direction>
<structure>
120 BPM, 8 bars, something on every beat.
logo → CTA button → email field (typed) → loader → success check → dashboard card
→ chart draws itself → tooltip → command palette → toast → logo.
</structure>
<build>
One canvas, window.seek(t). Closed-form springs; a value with many targets sums one
spring per change. Text inside a morphing container enters after the morph starts and
leaves before the next one. Tab indicators: leading and trailing edges on different
springs so they stretch. 60 fps, 4 subframes blended for motion blur.
</build>
<gotchas>
The last frame must equal the first, cursor position and velocity included.
</gotchas>
```

## 5. Director's brief

For films over a minute, or an unattended run: don't describe a video, hire a
crew. The skeleton:

- **The film in one line**: the logline, so every decision can be checked against it.
- **References and inputs**: source video, song, image library; what to keep, what to push.
- **Tools and keys**: skills to load, APIs available (names of env vars only), budget.
- **Character bible**: proportions, palette, expressions, an identity that survives style changes.
- **Beat sheet**: acts with timestamps, a visual payoff every 3 to 5 s, a hook in the first 2.
- **Text on screen**: when captions go huge, when they sit like subtitles.
- **Workflow gates**: plan → stills → animatic (960x540, placeholder audio) → full pass →
  polish → audio → render. Don't skip gates.
- **Critique loop**: stills, scores, the three worst problems, fix; logged in docs/review_log.md.
- **Deliverables**: final MP4, poster, contact sheet, loop check, source with a README.

For long films split chapters across subagents, after writing docs/ANIMATION_GUIDE.md
so every chapter is coded in the same style.

## 6. Variants that worked

```
# Longer, with a real score
make a dynamic 16:9, 60-second motion graphics showreel. S-tier sound design, no generic
synth pads. Compose an original piano score and sync every cut to it.

# Anti-slop guardrail
... Avoid frames and text in the corners, the usual giveaways of AI-made video.

# Story instead of techniques
use your showreel energy, but tell a story: the history of [TOPIC] from [START] to today.
45 seconds, vertical 9:16.

# Agency persona
make a 30-second showreel as if you were a niche branding studio for [AUDIENCE].
Every graphic from scratch. One accent colour. Every shot a different technique.
```
