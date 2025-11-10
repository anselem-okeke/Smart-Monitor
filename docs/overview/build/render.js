// docs/overview/build/render.js
const fs = require('fs');
const path = require('path');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const [,, SVG, OUT, FPS_STR, SECS_STR] = process.argv;
  if (!SVG) throw new Error('SVG arg missing');
  if (!OUT) throw new Error('OUT arg missing');
  const FPS = Number(FPS_STR || 20);
  const SECS = Number(SECS_STR || 20);

  if (!fs.existsSync(SVG)) throw new Error(`SVG not found: ${SVG}`);
  fs.mkdirSync(OUT, { recursive: true });

  const html = `<!doctype html>
<meta charset="utf-8">
<style>
  html,body{margin:0;background:#0e1420;height:100%}
  #wrap{display:flex;height:100%;align-items:center;justify-content:center}
  img{max-width:100%;max-height:100%}
</style>
<div id="wrap"><img id="img" src="${path.basename(SVG)}"></div>`;
  fs.writeFileSync(path.join(OUT, 'index.html'), html);
  fs.copyFileSync(SVG, path.join(OUT, path.basename(SVG)));

  const puppeteer = require('puppeteer');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--hide-scrollbars',
    ],
    defaultViewport: { width: 1280, height: 720 },
  });

  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(OUT, 'index.html'));

  const totalFrames = SECS * FPS;
  const frameDelayMs = Math.max(1, Math.round(1000 / FPS));

  for (let i = 0; i < totalFrames; i++) {
    const framePath = path.join(OUT, `frame_${String(i).padStart(5, '0')}.png`);
    await page.screenshot({ path: framePath });
    await sleep(frameDelayMs);
  }

  await browser.close();
})().catch(err => {
  console.error(err);
  process.exit(1);
});

