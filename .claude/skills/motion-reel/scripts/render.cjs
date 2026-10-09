#!/usr/bin/env node
// Render a seek(t) film frame by frame.
//
//   node render.cjs [--page index.html] [--fps 60] [--sub 4] [--from 0] [--dur <TL.DUR>] [--out out/silent.mp4]
//   node render.cjs --stills 0.5,2,4.25 [--out out/stills]        one PNG per time, for review
//
// The page must define window.seek(t) and window.ready (a promise that resolves
// once fonts and images are loaded), and draw into <canvas id="c">. Duration
// defaults to window.TL.DUR. Frames are piped to ffmpeg as PNG; with --sub N,
// N subframes per frame are averaged into motion blur.
const { spawn, execSync } = require('child_process');
const fs = require('fs'), path = require('path');

function playwright() {
  try { return require('playwright'); } catch (e) { /* fall through */ }
  try { return require(path.join(process.cwd(), 'node_modules', 'playwright')); } catch (e) { /* fall through */ }
  return require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
}
const { chromium } = playwright();

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const PAGE = path.resolve(arg('page', 'index.html'));
const FPS = +arg('fps', 60), SUB = +arg('sub', 4), FROM = +arg('from', 0);
const STILLS = arg('stills', null);
const OUT = arg('out', STILLS ? 'out/stills' : 'out/silent.mp4');

(async () => {
  const browser = await chromium.launch();
  const probe = await browser.newPage();
  await probe.goto('file://' + PAGE);
  const size = await probe.evaluate(() => { const c = document.getElementById('c'); return { w: c.width, h: c.height }; });
  await probe.close();

  const page = await browser.newPage({ viewport: { width: size.w, height: size.h }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => console.error('page error:', e.message));
  await page.goto('file://' + PAGE);
  await page.evaluate(() => { document.body.classList.add('render'); return window.ready; });
  const DUR = +arg('dur', await page.evaluate(() => (window.TL && window.TL.DUR) || 10));
  const shot = () => page.locator('#c').screenshot({ type: 'png' });

  if (STILLS) {
    fs.mkdirSync(OUT, { recursive: true });
    for (const t of STILLS.split(',').map(Number)) {
      await page.evaluate((t) => window.seek(t), t);
      fs.writeFileSync(path.join(OUT, `t${t.toFixed(2).padStart(6, '0')}.png`), await shot());
    }
    await browser.close();
    console.log('->', OUT);
    return;
  }

  fs.mkdirSync(path.dirname(path.resolve(OUT)), { recursive: true });
  const vf = SUB > 1 ? `tmix=frames=${SUB},select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/${FPS}/TB` : 'null';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS * SUB), '-i', '-',
    '-vf', vf, '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', OUT],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(DUR * FPS * SUB), t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate((t) => window.seek(t), FROM + i / (FPS * SUB));
    if (!ff.stdin.write(await shot())) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % (FPS * SUB) === 0) console.log(`${(i / (FPS * SUB)).toFixed(0)}s / ${DUR}s  (${((Date.now() - t0) / 1000).toFixed(0)}s elapsed)`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  await browser.close();
  console.log('->', OUT);
})();
