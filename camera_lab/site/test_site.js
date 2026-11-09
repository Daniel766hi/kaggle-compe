// End-to-end check of the Vision Lab website: still photos, every mode, a live (fake) camera with the line
// counter, the content pages, ad slots off and on, and phone-width layout. Usage: node test_site.js SITE NPM OUT Y4M
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [site, npm, out, y4m] = process.argv.slice(2);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml' };
const srv = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
  p = path.join(site, p);
  fs.readFile(p, (err, data) => { if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' }); res.end(data); });
}).listen(8766);
const LOCAL = { 'tf.min.js': `${npm}/tensorflow-tfjs-4.22.0/package/dist/tf.min.js`,
                'coco-ssd.min.js': `${npm}/tensorflow-models-coco-ssd-2.2.3/package/dist/coco-ssd.min.js` };
const BASE = 'http://localhost:8766/';
let failures = 0;
const check = (ok, msg) => { console.log((ok ? 'PASS ' : 'FAIL ') + msg); if (!ok) failures++; };

async function newPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1280, height: 900 }, colorScheme: opts.scheme || 'light',
    permissions: ['camera'], deviceScaleFactor: opts.dpr || 1 });
  const page = await ctx.newPage();
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') page.errors.push(m.text()); });
  page.adRequests = [];
  await page.route('https://cdn.jsdelivr.net/**', (r) => r.fulfill({ path: LOCAL[r.request().url().split('/').pop()], contentType: 'application/javascript' }));
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ body: '', contentType: 'text/css' }));
  await page.route('https://pagead2.googlesyndication.com/**', (r) => { page.adRequests.push(r.request().url()); r.fulfill({ body: '', contentType: 'application/javascript' }); });
  if (opts.client) await page.route(BASE + 'config.js', (r) => r.fulfill({ contentType: 'application/javascript',
    body: `window.SITE={ADSENSE_CLIENT:"${opts.client}",SLOTS:{top:"1111111111",side:"",inline:"2222222222",footer:""}};` }));
  return page;
}
const canvasPng = (page) => page.evaluate(() => document.getElementById('view').toDataURL('image/png').split(',')[1]);
const waitDetected = (page) => page.waitForFunction(() => { const s = document.getElementById('detectStatus');
  return s.textContent.startsWith('Detected') || s.classList.contains('error'); }, null, { timeout: 180000 });

(async () => {
  const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    `--use-file-for-fake-video-capture=${y4m}`] });

  // 1. Still photos and every mode.
  let page = await newPage(browser);
  await page.goto(BASE);
  await waitDetected(page);
  const table = async () => (await page.innerText('#objTable')).replace(/\n/g, ' / ');
  console.log('astronaut:', await table());
  check((await table()).includes('person'), 'astronaut sample: a person is detected');
  await page.click("[data-sample='samples/coffee.jpg']"); await waitDetected(page); await page.waitForTimeout(300);
  console.log('coffee:', await table());
  check((await table()).includes('cup'), 'coffee sample: a cup is detected');
  fs.writeFileSync(path.join(site, 'guide/detect.png'), Buffer.from(await canvasPng(page), 'base64'));
  await page.click("[data-sample='samples/chelsea.jpg']"); await waitDetected(page); await page.waitForTimeout(300);
  console.log('cat:', await table());
  check((await table()).includes('cat'), 'cat sample: a cat is detected');
  check(await page.evaluate(() => [...document.querySelectorAll('.ad')].every((a) => a.hidden)), 'no publisher ID: every ad slot is hidden');
  check(page.adRequests.length === 0, 'no publisher ID: no AdSense script requested');

  await page.click("[data-sample='samples/astronaut.jpg']"); await waitDetected(page);
  for (const m of ['edges', 'colour', 'cartoon', 'hist']) {
    await page.click(`.tab[data-mode='${m}']`);
    if (m === 'colour') { const box = await page.locator('#view').boundingBox(); await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.3); }
    await page.waitForTimeout(400);
    if (m === 'edges') fs.writeFileSync(path.join(site, 'guide/edges.png'), Buffer.from(await canvasPng(page), 'base64'));
    await page.locator('.grid').screenshot({ path: `${out}/mode_${m}.png` });
  }
  console.log('edges', await page.textContent('#edgeShare'), '| colour', await page.textContent('#colourShare'),
    '| hist', await page.textContent('#meanB'), await page.textContent('#sdB'));
  check((await page.textContent('#colourShare')).endsWith('%'), 'colour measure reports a share');
  const dl = page.waitForEvent('download');
  await page.click('#saveBtn');
  check((await dl).suggestedFilename() === 'vision-lab-hist.png', 'save offers a PNG download');
  check(page.errors.length === 0, 'still photos: no page errors ' + page.errors.join(' | '));
  await page.close();

  // 2. Live camera (fake device: the astronaut photo sliding down across the frame, looping every 6 s).
  page = await newPage(browser);
  await page.goto(BASE);
  await waitDetected(page);
  await page.selectOption('#countClass', 'person');
  await page.click('#camBtn');
  await page.waitForFunction(() => window.visionLab.live, null, { timeout: 20000 });
  check(await page.isVisible('#liveDot'), 'live: camera started and LIVE badge shown');
  await page.waitForTimeout(20000);
  const c = await page.evaluate(() => ({ a: window.visionLab.counter.a, b: window.visionLab.counter.b }));
  console.log('live hud:', await page.textContent('#hud'), '| counted down', c.a, 'up', c.b);
  check(c.a >= 2 && c.b === 0, `live counter: the person sliding down is counted down each pass (down ${c.a}, up ${c.b}; ~3 passes in 20 s)`);
  await page.locator('.grid').screenshot({ path: `${out}/live_counter.png` });
  await page.click('.tab[data-mode="edges"]'); await page.waitForTimeout(800);
  await page.click('.tab[data-mode="hist"]'); await page.waitForTimeout(800);
  await page.click('.tab[data-mode="detect"]');
  await page.click('#freezeBtn'); await page.waitForTimeout(300);
  check(!(await page.evaluate(() => window.visionLab.live)), 'freeze stops the camera');
  check((await page.textContent('#hud')).startsWith('Frozen'), 'freeze keeps the frame');
  check(page.errors.length === 0, 'live: no page errors ' + page.errors.join(' | '));
  await page.close();

  // 3. Ads switched on: slots appear and the AdSense script is requested once.
  page = await newPage(browser, { client: 'ca-pub-1234567890123456' });
  await page.goto(BASE); await page.waitForTimeout(1500);
  const slots = await page.evaluate(() => [...document.querySelectorAll('.ad')].map((a) => [a.dataset.slot, !a.hidden, a.querySelectorAll('ins.adsbygoogle').length]));
  console.log('slots with ID:', JSON.stringify(slots));
  check(slots.length === 4 && slots.every((s) => s[1]), 'with publisher ID: all 4 ad slots shown on the lab page');
  check(page.adRequests.length === 1 && page.adRequests[0].includes('client=ca-pub-1234567890123456'), 'with publisher ID: AdSense script requested with the ID');
  await page.close();

  // 4. Content pages and phone layout.
  for (const [w, h, scheme] of [[1280, 900, 'light'], [390, 844, 'dark']]) {
    for (const p of ['', 'guide.html', 'about.html', 'privacy.html']) {
      page = await newPage(browser, { viewport: { width: w, height: h }, scheme });
      const resp = await page.goto(BASE + p);
      await page.waitForTimeout(p ? 500 : 2500);
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      const broken = await page.evaluate(() => [...document.images].filter((i) => i.complete && !i.naturalWidth).map((i) => i.src));
      check(resp.status() === 200 && sw <= w && broken.length === 0 && page.errors.length === 0,
        `${p || 'index'} @${w}px ${scheme}: loads, no horizontal scroll (${sw}), no broken images ${broken}, no errors ${page.errors.join(' | ')}`);
      if (w === 390) await page.screenshot({ path: `${out}/phone_${p || 'index'}.png`, fullPage: true });
      await page.close();
    }
  }
  // Social preview image: the lab at 1200x630.
  page = await newPage(browser, { viewport: { width: 1200, height: 630 } });
  await page.goto(BASE); await waitDetected(page); await page.waitForTimeout(500);
  await page.evaluate(() => { document.querySelector('nav.site').style.display = 'none'; document.querySelector('.lede').style.display = 'none'; });
  await page.screenshot({ path: path.join(site, 'og.png') });
  await page.close();

  await browser.close(); srv.close();
  console.log(failures ? `${failures} FAILED` : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})();
