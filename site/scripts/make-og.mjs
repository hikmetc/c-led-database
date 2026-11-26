// Generate static/og.png (1200x630): the name and a small matrix motif. Run once; the PNG is committed.
// PW_CHANNEL=chrome uses an installed Chrome instead of Playwright's own Chromium.
import { chromium } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'static', 'og.png');
const shades = ['#e8eef6', '#c5dbf5', '#93bef0', '#559be8', '#0071e3'];
// a fixed decorative pattern, not data
const pattern = [4, 1, 0, 3, 2, 0, 2, 4, 1, 0, 3, 1, 3, 0, 4, 2, 1, 4, 1, 2, 0, 4, 3, 0, 0, 3, 2, 1, 4, 2];
const cells = pattern.map((s) => `<i style="background:${shades[s]}"></i>`).join('');
const html = `<!doctype html><html><body style="margin:0"><div style="width:1200px;height:630px;box-sizing:border-box;padding:88px 96px;background:#fff;color:#1d1d1f;display:flex;justify-content:space-between;align-items:center;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','Segoe UI',Roboto,Arial,sans-serif">
<div style="max-width:600px"><div style="display:inline-block;padding:6px 18px;border:2px solid #86868b;border-radius:980px;font-size:22px;font-weight:600;color:#6e6e73;margin-bottom:28px">Beta version</div><div style="font-size:76px;font-weight:600;letter-spacing:-0.02em;line-height:1.05">EFLM Laboratory Error Database</div>
<div style="font-size:26px;line-height:1.4;color:#6e6e73;margin-top:28px">Source-cited evidence on analytical interference</div></div>
<div style="display:grid;grid-template-columns:repeat(5,56px);gap:10px">${cells}</div>
<style>i{display:block;width:56px;height:56px;border-radius:12px}</style></div></body></html>`;

const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.setContent(html);
await page.screenshot({ path: out, type: 'png' });
await browser.close();
console.log('wrote', out);
