// Screenshot the real FaceFinder UI, piece by piece, for the promo.
//
//   python -m tests.devserver            (in the repo root, keep it running)
//   node promo/capture.cjs
//
// The app is the real app/static/index.html served by the real app, on the
// offline stand-in for Drive, in phone size at 3x. What is staged: the album
// (800 camp photos, the counts and names), and every photo and face, which are
// illustrated people drawn in code (lib/photos.js) and swapped in at the
// network layer, so no real face appears.

const { chromium } = require('./lib/pw.cjs');
const fs = require('fs');
const path = require('path');

const APP = process.env.APP || 'http://127.0.0.1:8077';
const OUT = path.join(__dirname, 'assets', 'ui');
const DPR = 3;
const TOTAL = 800;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: DPR });

  // A page that draws the staged photos on request.
  const factory = await ctx.newPage();
  await factory.setContent('<canvas id="c"></canvas>');
  await factory.addScriptTag({ path: path.join(__dirname, 'lib', 'cast.js') });
  await factory.addScriptTag({ path: path.join(__dirname, 'lib', 'photos.js') });
  const drawn = new Map();
  const render = async (key, fn) => {
    if (!drawn.has(key)) drawn.set(key, Buffer.from((await factory.evaluate(fn)).split(',')[1], 'base64'));
    return drawn.get(key);
  };
  const photoPng = (id, big) => render(id + (big ? '@big' : ''), `(() => {
    const c = document.getElementById('c'); c.width = ${big ? 1200 : 640}; c.height = ${big ? 900 : 480};
    Photos.draw(c.getContext('2d'), c.width, c.height, ${JSON.stringify(id)});
    return c.toDataURL('image/png'); })()`);
  const facePng = (i) => render('face' + i, `(() => {
    const c = document.getElementById('c'); c.width = c.height = 480;
    const g = c.getContext('2d'); g.clearRect(0, 0, 480, 480);
    const who = Photos.CREW[${i}] || Photos.kid(${600 + i}, ['green', 'white'][${i} % 2], { bg: ${i} % 5 });
    Cast.portrait(g, 480, who);
    return c.toDataURL('image/png'); })()`);

  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.error('page error:', e.message));
  await page.route('**/api/face/**', async (route) => {
    const m = /crew-(\d)/.exec(route.request().url());
    if (!m) return route.continue();
    route.fulfill({ status: 200, contentType: 'image/png', body: await facePng(+m[1]) });
  });
  await page.route('**/api/thumb/**', async (route) => {
    const url = new URL(route.request().url());
    const id = decodeURIComponent(url.pathname.split('/').pop());
    route.fulfill({ status: 200, contentType: 'image/png', body: await photoPng(id, +url.searchParams.get('s') > 600) });
  });
  await page.goto(APP + '/dev/login');
  await page.waitForFunction(() => typeof state !== 'undefined' && state.signedIn);
  await page.addStyleTag({ content: `.bar>i{transition:none!important} .nav{position:static}
    *{animation:none!important;transition:none!important;caret-color:transparent!important}
    body:not(.showbar) #actionbar{display:none!important}` });
  await page.evaluate(() => document.fonts.ready);

  const shots = {}, spots = {};
  const box = async (sel) => page.locator(sel).first().boundingBox();
  const spot = async (name, sel, within) => {
    const a = await box(sel), b = await box(within);
    spots[name] = { x: Math.round((a.x + a.width / 2 - b.x) * DPR), y: Math.round((a.y + a.height / 2 - b.y) * DPR),
                    w: Math.round(a.width * DPR), h: Math.round(a.height * DPR) };
  };
  const imagesLoaded = () => page.waitForFunction(() => [...document.images].filter((i) => i.offsetParent)
    .every((i) => i.complete && i.naturalWidth));
  const shot = async (name, sel) => {
    await imagesLoaded();
    const el = page.locator(sel).first();
    await el.screenshot({ path: path.join(OUT, name + '.png') });
    const b = await el.boundingBox();
    shots[name] = { w: Math.round(b.width * DPR), h: Math.round(b.height * DPR) };
  };

  // ---- scanning: the real card, with real stage names and counts ----
  await page.evaluate(() => {
    $('#hero').hidden = true; $('#scanCard').hidden = false;
    document.querySelector('.scanart').style.visibility = 'hidden';   // the film animates the mascot itself
  });
  const scanStates = [
    ['read', 0, 0], ['faces', 200, 0], ['faces', 400, 0], ['faces', 600, 0], ['faces', 800, 0],
    ['gemini', 800, 270], ['gemini', 800, 540], ['gemini', 800, 800], ['ready', 800, 800]];
  for (let k = 0; k < scanStates.length; k++) {
    await page.evaluate(([stage, done, judged, TOTAL]) => {
      const order = ['read', 'faces', 'gemini', 'ready'], at = order.indexOf(stage);
      document.querySelectorAll('#steps li').forEach((li) => {
        const i = order.indexOf(li.dataset.step); li.className = i < at || stage === 'ready' ? 'done' : i === at ? 'now' : '';
      });
      const n = stage === 'gemini' ? judged : done;
      $('#pbarBox').classList.remove('busy');
      $('#pbar').style.width = (stage === 'read' ? 0 : Math.round(100 * n / TOTAL)) + '%';
      $('#scanTitle').textContent = { read: 'Opening album…', faces: 'Finding faces…',
        gemini: 'Checking photo quality…', ready: 'Ready' }[stage];
      $('#pstat').textContent = stage === 'read' ? `${TOTAL} photos found`
        : `${n} of ${TOTAL} photos · ${Math.round(done * 2.4).toLocaleString('en')} faces found`;
    }, [...scanStates[k], TOTAL]);
    await shot('scan_' + k, '#scanCard');
  }
  await page.evaluate(() => { document.querySelector('.scanart').style.visibility = ''; });
  await spot('scanart', '.scanart', '#scanCard');

  // ---- the album is open ----
  await page.evaluate((TOTAL) => {
    $('#scanCard').hidden = true;
    state.folderId = 'camp-2026'; state.albumName = 'Camp 2026'; state.ready = true;
    $('#work').dataset.locked = '0';
    const info = $('#albumInfo'); info.hidden = false;
    info.innerHTML = `<b>Camp 2026</b> · ${TOTAL} photos <button class="linkbtn">Rescan</button>`;
  }, TOTAL);
  await shot('chip', '#albumInfo');
  for (const m of ['everyone', 'cull', 'sort']) {
    await page.evaluate((m) => setMode(m), m);
    await shot('tabs_' + m, '.tabs');
  }

  // ---- Everyone: tick and name four people ----
  await page.evaluate(() => {
    state.crowd = Array.from({ length: 6 }, (_, i) => ({
      kind: 'cluster', id: 'p' + i, cover: { file_id: 'crew-' + i, face_idx: 0 },
      all: Array.from({ length: [128, 96, 143, 87, 61, 54][i] }, (_, k) => ({ file_id: `f${i}-${k}`, score: 0.62, face_idx: 0 })),
      removed: new Set(), name: '', on: false,
    }));
    setMode('everyone');
    msg($('#everyMsg'), '38 people appear in more than one photo.', 'ok');
    renderCrowd();
  });
  for (let i = 0; i < 4; i++) await spot('tick_' + i, `#faces .fcard:nth-child(${i + 1}) .tick`, '#modeEveryone .panel');
  for (let k = 0; k <= 4; k++) {
    await page.evaluate(([k, names]) => {
      state.crowd.forEach((g, i) => { g.on = i < k; g.name = i < k ? names[i] : ''; });
      renderCrowd();
    }, [k, ['Mint', 'Tan', 'Ploy', 'Bank']]);
    await shot('everyone_' + k, '#modeEveryone .panel');
  }

  // ---- Cull: the Review pile, one photo previewed and excluded ----
  await page.evaluate((TOTAL) => {
    const row = (id, why, long, i) => ({ file_id: id, name: `IMG_${String(4120 + i).padStart(4, '0')}.jpg`, why, long });
    const R = [
      ['cull-0', 'Closed eyes', 'Posed group photo; the person in the middle has their eyes shut.'],
      ['cull-1', 'Out of focus', 'The main subjects are soft; the camera focused behind them.'],
      ['cull-2', 'Similar to another frame', 'Looks like IMG_4131.jpg; keep both if the moment differs.'],
      ['cull-3', 'Too dark or bright', 'Faces are lost in shadow.'],
      ['cull-4', 'Gemini was not sure', 'Gemini was not sure: the face is small and partly turned away.'],
      ['cull-5', 'Something in the way', 'A raised hand covers part of the second person.'],
    ];
    const review = Array.from({ length: 143 }, (_, i) => row(R[i % 6][0] + '~' + i, R[i % 6][1], R[i % 6][2], i));
    const set = (name, all, removed) => ({ kind: 'set', name, all, removed: new Set(removed), limit: 24 });
    state.culled = {
      keep: set('Keep', Array.from({ length: 612 }, (_, i) => row('blue-' + (i % 4) + '~' + i, '', '', 300 + i)), []),
      review: set('Review', review, []),
      reject: set('Rejected', Array.from({ length: 45 }, (_, i) => row('cull-1~r' + i, 'Out of focus', '', 900 + i)), []),
    };
    state.cullPile = 'review';
    setMode('cull');
    $('#cullMsg').innerHTML = '<p class="whyline">Rejected: 21 out of focus · 14 too dark or bright · 10 closed eyes</p>';
    renderCull();
  }, TOTAL);
  await shot('cull_0', '#modeCull');
  await spot('tile0', '#cullResults .photo-open', '#modeCull');
  await spot('pileReview', '.piles button:nth-child(2)', '#modeCull');
  // the preview, as the app opens it
  await page.evaluate(() => { const g = state.culled.review; previewPhoto(g.all[0], g, () => updateBar()); });
  await page.waitForSelector('#photoPreview[open]');
  await page.evaluate(() => document.activeElement?.blur());   // no focus ring in the film
  await shot('preview_0', '#photoPreview');
  await spot('pOut', '#previewOut', '#photoPreview');
  await spot('pImg', '#previewImg', '#photoPreview');
  await page.click('#previewOut');
  await page.evaluate(() => document.activeElement?.blur());
  await shot('preview_1', '#photoPreview');
  await page.evaluate(() => $('#photoPreview').close());
  await shot('cull_1', '#modeCull');

  // ---- Sort by description: a Thai rule, then the folders ----
  const THAI = 'people in blue camp shirts';
  const typed = [0, 3, 6, 9, 12, THAI.length].map((n) => THAI.slice(0, n));
  await page.evaluate(() => {
    state.sortDefs = [{ name: 'Blue team', description: '' }, { name: 'Orange team', description: 'people in orange camp shirts' }];
    setMode('sort'); renderGroupRows();
  });
  for (let k = 0; k < typed.length; k++) {
    await page.evaluate((v) => { state.sortDefs[0].description = v; renderGroupRows(); }, typed[k]);
    await shot('sortform_' + k, '#modeSort .panel');
  }
  await spot('runSort', '#runSort', '#modeSort .panel');
  await page.evaluate(() => {
    const rows = (ids) => ids.map((id, i) => ({ file_id: id, name: `IMG_${4200 + i * 7}.jpg` }));
    state.sorted = [
      { kind: 'set', name: 'Blue team', all: rows(['blue-0', 'blue-1', 'blue-2', 'blue-3']), removed: new Set(), limit: 24 },
      { kind: 'set', name: 'Orange team', all: rows(['orange-0', 'orange-1']), removed: new Set(), limit: 24 },
    ];
    msg($('#sortMsg'), '352 photos in Blue team, 297 in Orange team, 18 to check.', 'ok');
    renderSorted();
  });
  await shot('sortres', '#sortResults .card');
  await shot('sortmsg', '#sortMsg');

  // ---- Export: the bar, the copy, the done card ----
  await page.evaluate(() => document.body.classList.add('showbar'));
  const summary = '<b>2</b> folders · <b>649</b> photos';
  await page.evaluate((s) => { updateBar(); $('#summary').innerHTML = s; document.activeElement?.blur(); }, summary);
  await shot('bar_0', '#actionbar .inner');
  await spot('export', '#export', '#actionbar .inner');
  for (let k = 0; k <= 4; k++) {
    await page.evaluate(([k, s]) => {
      $('#xprog').hidden = false; $('#xbar').style.width = (k * 25) + '%';
      $('#xtext').textContent = `Filling the folders — ${Math.round(649 * k / 4)} of 649 photos`;
      $('#export').disabled = true; $('#summary').innerHTML = s;
    }, [k, summary]);
    await shot('copy_' + k, '#actionbar .inner');
  }
  await page.evaluate(() => {
    $('#xprog').hidden = true; $('#actionbar').hidden = true;
    showDone({ status: 'done', copied: 649, skipped: 0, failed: 0, note: '',
      root_url: '#', root_name: 'FaceFinder - Camp 2026',
      people: [{ name: 'Blue team', url: '#', copied: 352, skipped: 0 }, { name: 'Orange team', url: '#', copied: 297, skipped: 0 }] });
  });
  await shot('done', '#doneCard');

  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify({ shots, spots }, null, 1));
  fs.writeFileSync(path.join(OUT, 'manifest.js'), 'window.UI_MANIFEST = ' + JSON.stringify({ shots, spots }) + ';\n');
  console.log(Object.keys(shots).length, 'shots ->', OUT);
  await browser.close();
})();
