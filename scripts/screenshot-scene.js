/**
 * Playwright screenshot script for RowingScene visual testing.
 * Usage: Run with `npm run test-scene` from the dashboard/ directory,
 *        or `nix develop --command bash -c "cd dashboard && npm run test-scene"`
 * Requires the Vite dev server to already be running on :5173.
 */
// Resolve playwright from dashboard/node_modules when run from scripts/ dir
const { createRequire } = require('module');
const dashboardRequire = createRequire(require('path').join(__dirname, '..', 'dashboard', 'package.json'));
const { chromium } = dashboardRequire('playwright');
const path = require('path');

async function screenshot(page, viewport, name) {
  await page.setViewportSize(viewport);

  // Log console messages from the page for debugging
  page.on('console', msg => {
    const type = msg.type();
    if (type === 'error' || type === 'warning') console.log(`  [PAGE ${type.toUpperCase()}] ${msg.text()}`);
  });
  page.on('pageerror', err => console.log(`  [PAGE EXCEPTION] ${err.message}`));
  page.on('response', resp => {
    if (resp.status() >= 400) {
      console.log(`  [HTTP ${resp.status()}] ${resp.url()}`);
    }
  });

  const port = process.env.VITE_PORT || '5173';
  // Use load to ensure scripts have started executing
  await page.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
  // Wait for React to mount and Pixi to initialize
  try {
    await page.waitForSelector('#root > div', { timeout: 10000 });
  } catch (e) {
    console.log(`  WARNING: root div not found after 10s`);
  }
  await page.waitForTimeout(4000);

  const outDir = path.join(__dirname, '..', 'docs', 'screenshots');
  require('fs').mkdirSync(outDir, { recursive: true });

  // Debug: log what elements exist
  const bodyHTML = await page.evaluate(() => document.body.innerHTML.substring(0, 500));
  console.log(`  Page body preview: ${bodyHTML.replace(/\n/g, ' ').substring(0, 200)}`);

  // Check if canvas is rendering
  const canvasInfo = await page.evaluate(() => {
    const canvas = document.querySelector('.rowing-scene canvas');
    if (!canvas) return 'no canvas found';
    const ctx2d = canvas.getContext('2d');
    // Try to read pixels from multiple positions
    if (ctx2d) {
      const topPx = ctx2d.getImageData(canvas.width/2, 10, 1, 1).data;
      const midPx = ctx2d.getImageData(canvas.width/2, canvas.height/2, 1, 1).data;
      const botPx = ctx2d.getImageData(canvas.width/2, canvas.height - 10, 1, 1).data;
      return `2d: top(y=10)=${Array.from(topPx).join(',')}, mid=${Array.from(midPx).join(',')}, bot=${Array.from(botPx).join(',')}`;
    }
    // For WebGL canvas, create a temp 2d canvas to read pixels
    const size = { w: canvas.width, h: canvas.height };
    return `canvas: ${size.w}x${size.h}, context=WebGL`;
  });
  console.log(`  Canvas info: ${canvasInfo}`);

  // Full page
  await page.screenshot({ path: path.join(outDir, `${name}-full.png`), fullPage: false });
  console.log(`  Saved ${name}-full.png`);

  // Just the scene
  const scene = await page.$('.rowing-scene');
  if (scene) {
    await scene.screenshot({ path: path.join(outDir, `${name}-scene.png`) });
    console.log(`  Saved ${name}-scene.png`);
  } else {
    console.log(`  WARNING: .rowing-scene not found`);
    // Try to find any canvas elements
    const canvases = await page.$$('canvas');
    console.log(`  Found ${canvases.length} canvas elements`);
  }
}

async function main() {
  // Use the nix-provided Chromium browser if PLAYWRIGHT_BROWSERS_PATH is set.
  // The nix flake pins chromium-1200 while the npm package may expect a newer version;
  // specifying executablePath directly bypasses the version check.
  const browsersPath = process.env.PLAYWRIGHT_BROWSERS_PATH;
  let executablePath;
  if (browsersPath) {
    const fs = require('fs');
    // Try full chromium first, then headless shell
    const candidates = [
      require('path').join(browsersPath, 'chromium-1200', 'chrome-linux64', 'chrome'),
      require('path').join(browsersPath, 'chromium_headless_shell-1200', 'chrome-headless-shell-linux64', 'chrome-headless-shell'),
    ];
    executablePath = candidates.find(p => fs.existsSync(p));
    if (executablePath) console.log(`Using Chromium: ${executablePath}`);
  }

  const browser = await chromium.launch({
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-web-security',
      '--allow-file-access-from-files',
      '--enable-webgl',
      '--use-gl=swiftshader',
      '--ignore-gpu-blocklist',
      '--enable-gpu-rasterization',
    ],
    ...(executablePath ? { executablePath } : {}),
  });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  console.log('Screenshotting mobile (430px)...');
  await screenshot(page, { width: 430, height: 932 }, 'mobile');

  console.log('Screenshotting tablet (820px)...');
  await screenshot(page, { width: 820, height: 1180 }, 'tablet');

  await browser.close();
  console.log('Done. Screenshots in docs/screenshots/');
}

main().catch(err => { console.error(err); process.exit(1); });
