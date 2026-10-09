# Capturing a real product UI for the film

The film animates screenshots of the real product, so a viewer sees the actual
app and not an imagined one. Capture pieces (a search bar, a card, a bottom
bar) rather than whole screens: pieces can be placed, panned and swapped
independently, and shown big enough to read on a phone.

## Where the UI comes from

- **A running app you can start** (a repo with a dev server, ideally one with a
  fake backend or demo mode): best, because you can put it into any state.
- **A public website**: visit it with Playwright and screenshot elements. Check
  the network allows the host first.
- **Screenshots the user supplies**: crop them with ffmpeg or PIL; you cannot
  change their state, so plan the shots around what exists.

## The capture script pattern

```js
// node capture.cjs        (app running at APP)
const { chromium } = require(/* local or global */ 'playwright');
const browser = await chromium.launch();
// A phone viewport at 3x gives 1170 px wide pieces: sharp in a 1080-wide film.
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
const page = await ctx.newPage();
await page.goto(APP);
await page.addStyleTag({ content: `
  :root { --accent: #2E4BE8 }            /* restyle tokens if the brand changes */
  * { transition: none !important }      /* no half-finished transitions in shots */
  .nav { position: static }              /* sticky headers bleed into element shots */
` });
await page.evaluate(() => document.fonts.ready);

const shots = {}, spots = {};
async function shot(name, sel) {
  const el = page.locator(sel).first();
  await el.screenshot({ path: `assets/ui/${name}.png` });
  const b = await el.boundingBox();
  shots[name] = { w: Math.round(b.width * 3), h: Math.round(b.height * 3) };
}
// Where something tappable is, in image px of the piece it sits in, so the
// film's fingertip lands exactly on it.
async function spot(name, sel, within) {
  const a = await page.locator(sel).first().boundingBox();
  const b = await page.locator(within).first().boundingBox();
  spots[name] = { x: Math.round((a.x + a.width / 2 - b.x) * 3), y: Math.round((a.y + a.height / 2 - b.y) * 3) };
}

// Typing: one shot per few characters, then the film steps through them.
for (let k = 0; k <= 10; k++) {
  await page.fill('#search', TEXT.slice(0, Math.round(TEXT.length * k / 10)));
  await shot('search_' + k, '.search');
}
await spot('submit', '#submit', '.search');

// The manifest as a script, because a file:// page cannot fetch JSON.
fs.writeFileSync('assets/ui/manifest.js', 'window.UI_MANIFEST = ' + JSON.stringify({ shots, spots }) + ';\n');
```

In the film, load the PNGs in `window.ready` with `M.loadImages`, include
`assets/ui/manifest.js` with a script tag, and draw pieces with `M.panel`,
clipped to the element's own corner radius (times 3) so the white page corners
outside a rounded element don't show on a coloured background.

## Putting the app into the state you need

Drive the real UI where you can (click, fill). For states that are slow or need
data you don't have (a 4,000-photo album, a finished export), call the app's
own functions from `page.evaluate` with staged data: the app renders its real
markup and copy, only the data is staged. Tell the user which numbers and names
are staged.

Gotchas that cost time:

- **Top-level `const`/`let` are not on `window`.** A classic script's
  `const state = {...}` is reachable by name inside `page.evaluate`
  (`typeof state !== 'undefined' && state.ready`) but `window.state` is undefined.
- **Focus rings.** `page.fill` leaves the field focused; blur it
  (`document.activeElement.blur()`) before shooting a different piece.
- **Lazy images.** Wait until every `<img>` in the piece is complete before shooting:
  `page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth))`.
- **Sticky or fixed elements** appear inside other elements' screenshots.
  Make them static, or shoot them separately.
- **Text that wraps** at the phone width: shorten demo strings (a URL, a name)
  so they fit the field rather than scroll.

## Swapping images at the network layer

To replace photos, avatars or user content (for privacy, or because the demo
data has none), intercept the image requests and answer with your own PNGs:

```js
await page.route('**/api/avatar/**', (route) => {
  const m = /user-(\d+)/.exec(route.request().url());
  if (!m) return route.continue();
  route.fulfill({ status: 200, contentType: 'image/png', body: pngs[+m[1]] });
});
```

To make those PNGs in code, open a blank page, add your drawing script, draw
into a canvas and return `canvas.toDataURL('image/png')`; decode the base64
into a Buffer. Seed every drawing so it is identical on every run.

## Fonts and network

Canvas text needs its font loaded first; with `display=block` and
`document.fonts.load(...)` in `window.ready` the first frame is correct. If
Google Fonts is unreachable, fall back to a system face rather than hanging,
and tell the user the type is not final.
