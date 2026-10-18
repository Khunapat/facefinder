// node render.cjs [--fps 30] [--sub 2] [--from 0] [--dur 20] [--out out/silent.mp4]
// node render.cjs --stills 0.5,1,2 --out out/stills    (PNG per time, for review)
const { chromium } = require('../promo/lib/pw.cjs');
const { spawn } = require('child_process');
const fs = require('fs'), path = require('path');
const TL = require('./timeline.js');

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const FPS = +arg('fps', 30), SUB = +arg('sub', 2), FROM = +arg('from', 0), DUR = +arg('dur', TL.DUR);
const OUT = arg('out', 'out/silent.mp4'), STILLS = arg('stills', null);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: TL.W, height: TL.H }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => console.error('page error:', e.message));
  await page.goto('file://' + path.join(__dirname, 'index.html'));
  await page.evaluate(() => { document.body.classList.add('render'); return window.ready; });
  const shot = () => page.locator('#c').screenshot({ type: 'png' });

  if (STILLS) {
    fs.mkdirSync(OUT, { recursive: true });
    for (const t of STILLS.split(',').map(Number)) {
      await page.evaluate((t) => window.seek(t), t);
      fs.writeFileSync(path.join(OUT, `t${t.toFixed(2).padStart(5, '0')}.png`), await shot());
    }
    await browser.close(); return;
  }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const vf = SUB > 1 ? `tmix=frames=${SUB},select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/${FPS}/TB` : 'null';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS * SUB), '-i', '-',
    '-vf', vf, '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', OUT],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(DUR * FPS * SUB), t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate((t) => window.seek(t), FROM + i / (FPS * SUB));
    if (!ff.stdin.write(await shot())) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % (FPS * SUB) === 0) process.stdout.write(`\r${(i / (FPS * SUB)).toFixed(0)}s / ${DUR}s  (${((Date.now() - t0) / 1000).toFixed(0)}s elapsed)`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  await browser.close();
  console.log('\n->', OUT);
})();
