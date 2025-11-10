// docs/overview/build/render_playwright.mjs
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import playwright from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const svg  = process.env.SVG  || 'docs/overview/SmartMonitor_Lab_Sequence.svg';
const out  = process.env.OUT  || 'docs/overview/build';
const fps  = Number(process.env.FPS || 20);
const secs = Number(process.env.SECS || 20);

if (!fs.existsSync(svg)) {
  console.error('SVG not found:', svg);
  process.exit(2);
}
fs.mkdirSync(out, { recursive: true });

const html = `<!doctype html><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:#0e1420}
  .wrap{display:flex;align-items:center;justify-content:center;height:100%}
  img{max-width:100%;max-height:100%}
</style>
<div class="wrap"><img id="img" src="../${path.basename(svg)}"></div>`;
fs.writeFileSync(path.join(out, 'index.html'), html);
fs.copyFileSync(svg, path.join(out, path.basename(svg)));

const browser = await playwright.chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto('file://' + path.resolve(out, 'index.html'));

const frames = secs * fps;
for (let i = 0; i < frames; i++) {
  const f = path.join(out, `frame_${String(i).padStart(5, '0')}.png`);
  await page.screenshot({ path: f });
  await page.waitForTimeout(1000 / fps);
}
await browser.close();
