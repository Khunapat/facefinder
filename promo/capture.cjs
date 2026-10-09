// Screenshot the real FaceFinder UI, piece by piece, for the promo.
//
//   python -m tests.devserver            (in the repo root, keep it running)
//   node promo/capture.cjs
//
// The app is the real index.html served by the real app, on the offline
// stand-in for Drive. Two things are staged: the accent token is overridden
// with the new brand colour, and the album's people are the illustrated cast
// (face crops are swapped at the network layer), so no real face appears.

const { chromium } = require('./lib/pw.cjs');
const fs = require('fs');
const path = require('path');

const APP = process.env.APP || 'http://127.0.0.1:8077';
const OUT = path.join(__dirname, 'assets', 'ui');
const ACCENT = { accent: '#2E4BE8', active: '#2238C2', disabled: '#C7CFF8' };
const LINK = 'drive.google.com/drive/folders/1Grad26';
const COUNTS = [128, 96, 143, 87, 112, 64];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });

  // Illustrated face crops, keyed by the fake file id the staged crowd uses.
  const factory = await ctx.newPage();
  await factory.setContent('<canvas id="c" width="480" height="480"></canvas>');
  await factory.addScriptTag({ path: path.join(__dirname, 'lib', 'cast.js') });
  const crops = [];
  for (let i = 0; i < 6; i++) {
    const url = await factory.evaluate((i) => {
      const c = document.getElementById('c'), g = c.getContext('2d');
      g.clearRect(0, 0, 480, 480);
      Cast.portrait(g, 480, Cast.CREW[i]);
      return c.toDataURL('image/png');
    }, i);
    crops.push(Buffer.from(url.split(',')[1], 'base64'));
  }
  await factory.close();

  const page = await ctx.newPage();
  await page.route('**/api/face/**', (route) => {
    const m = /crew-(\d)/.exec(route.request().url());
    if (!m) return route.continue();
    route.fulfill({ status: 200, contentType: 'image/png', body: crops[+m[1]] });
  });
  await page.goto(APP + '/dev/login');
  await page.waitForFunction(() => typeof state !== 'undefined' && state.signedIn);
  await page.addStyleTag({ content:
    `:root{--accent:${ACCENT.accent};--accent-active:${ACCENT.active};--accent-disabled:${ACCENT.disabled}}
     
     .bar>i{transition:none!important} .nav{position:static}` });
  await page.evaluate(() => document.fonts.ready);

  const shots = {};
  const spots = {};
  const spot = async (name, sel, within) => {
    const a = await page.locator(sel).first().boundingBox();
    const b = await page.locator(within).first().boundingBox();
    spots[name] = { x: Math.round((a.x + a.width / 2 - b.x) * 3), y: Math.round((a.y + a.height / 2 - b.y) * 3) };
  };
  const shot = async (name, sel) => {
    const el = page.locator(sel).first();
    await el.screenshot({ path: path.join(OUT, name + '.png') });
    const b = await el.boundingBox();
    shots[name] = { w: Math.round(b.width * 3), h: Math.round(b.height * 3) };
  };

  await shot('nav', '.nav');
  await shot('hero', '.hero');

  // The album link, typed a few characters at a time.
  const steps = 10;
  for (let k = 0; k <= steps; k++) {
    await page.fill('#album', LINK.slice(0, Math.round(LINK.length * k / steps)));
    await shot('pill_' + k, '.pill');
  }
  await spot('orb', '#openAlbum', '.pill');

  // Scanning. Same elements and status text the app writes while it indexes.
  const TOTAL = 4000;
  for (let k = 0; k <= 10; k++) {
    await page.evaluate(([k, TOTAL]) => {
      msg($('#albumMsg'), 'Album <b>Grad Day 2026</b> is open.', 'ok');
      $('#indexBox').hidden = false;
      const done = Math.round(TOTAL * k / 10);
      $('#pbar').style.width = (k * 10) + '%';
      $('#pstat').textContent = k < 10
        ? `Scanning faces — ${done.toLocaleString('en')} of ${TOTAL.toLocaleString('en')} photos, ${Math.round(done * 2.3).toLocaleString('en')} faces found`
        : `Ready — ${TOTAL.toLocaleString('en')} photos, ${Math.round(TOTAL * 2.3).toLocaleString('en')} faces.`;
    }, [k, TOTAL]);
    await shot('scan_' + k, '.narrow');
  }

  // Everyone in the album: six people, ticked and named one at a time.
  await page.evaluate((COUNTS) => {
    state.folderId = 'grad-day-2026'; state.ready = true;
    $('#work').dataset.locked = '0';
    state.crowd = COUNTS.map((n, i) => ({
      kind: 'cluster', id: 'p' + i, cover: { file_id: 'crew-' + i, face_idx: 0 },
      all: Array.from({ length: n }, (_, k) => ({ file_id: `f${i}-${k}`, score: 0.62, face_idx: 0 })),
      removed: new Set(), name: '', on: false,
    }));
    setMode('everyone');
    msg($('#everyMsg'), 'Found <b>6</b> people who appear more than once, across 3,912 photos with faces.', 'ok');
    renderCrowd();
  }, COUNTS);
  await page.waitForFunction(() => [...document.querySelectorAll('.fpic img')].every((i) => i.complete && i.naturalWidth));
  await shot('modes', '.modes');
  for (let i = 0; i < 6; i++) await spot('tick_' + i, `#faces .fcard:nth-child(${i + 1}) .tick`, '#modeEveryone .card');
  for (let i = 0; i < 6; i++) await spot('face_' + i, `#faces .fcard:nth-child(${i + 1}) .fpic`, '#modeEveryone .card');
  for (let k = 0; k <= 6; k++) {
    await page.evaluate((k) => {
      const N = ['Mint', 'Tan', 'Ploy', 'Bank', 'Fah', 'Nont'];
      state.crowd.forEach((g, i) => { g.on = i < k; g.name = i < k ? N[i] : ''; });
      renderCrowd();
    }, k);
    await page.waitForFunction(() => [...document.querySelectorAll('.fpic img')].every((i) => i.complete && i.naturalWidth));
    await shot('everyone_' + k, '#modeEveryone .card');
    await shot('bar_' + k, '#actionbar');
  }
  await spot('export', '#export', '#actionbar');

  // Copying, then the result card.
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  for (let k = 0; k <= 4; k++) {
    await page.evaluate((k) => {
      $('#xprog').hidden = false;
      $('#xbar').style.width = (k * 25) + '%';
      $('#xtext').textContent = `Copying — ${Math.round(630 * k / 4)} of 630 photos`;
      $('#export').disabled = true;
    }, k);
    await shot('copy_' + k, '#actionbar');
  }
  await page.evaluate((COUNTS) => {
    $('#xprog').hidden = true;
    const N = ['Mint', 'Tan', 'Ploy', 'Bank', 'Fah', 'Nont'];
    showDone({ status: 'done', copied: 630, skipped: 0, failed: 0, note: '',
      root_url: '#', root_name: 'FaceFinder - Grad Day 2026',
      people: N.map((name, i) => ({ name, url: '#', copied: COUNTS[i], skipped: 0 })) });
  }, COUNTS);
  await shot('done', '#doneCard');
  const rows = await page.locator('#doneCard li').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().bottom));
  const top = (await page.locator('#doneCard').boundingBox()).y;
  spots.doneRows = rows.map((b) => Math.round((b - top) * 3));

  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify({ shots, spots }, null, 1));
  fs.writeFileSync(path.join(OUT, 'manifest.js'), 'window.UI_MANIFEST = ' + JSON.stringify({ shots, spots }) + ';\n');
  console.log(Object.keys(shots).length, 'shots ->', OUT);
  await browser.close();
})();
