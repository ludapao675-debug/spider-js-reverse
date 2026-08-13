/**
 * 只弹验证码并截图，不拖滑块。
 *   set JCAP_CDP=http://127.0.0.1:9222
 *   set JCAP_SHOTS=6
 *   node capture_captcha_shots.js
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const OUT = path.join(__dirname, 'debug', 'shots');
const N = Math.max(5, Math.min(8, Number(process.env.JCAP_SHOTS || 6)));
const cdpUrl = process.env.JCAP_CDP || 'http://127.0.0.1:9222';

function log(m) {
  console.log(typeof m === 'object' ? JSON.stringify(m, null, 2) : m);
}

async function clearCaptcha(page) {
  await page.evaluate(() => {
    for (const sel of ['#captcha_modal', '#captcha_dom', '.captcha_drop']) {
      document.querySelectorAll(sel).forEach((el) => {
        try {
          el.remove();
        } catch (e) {
          el.style.display = 'none';
          el.style.pointerEvents = 'none';
        }
      });
    }
  }).catch(() => {});
}

async function waitPuzzle(page, ms = 25000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const ok = await page.evaluate(() =>
      Array.from(document.querySelectorAll('img')).some(
        (im) => im.naturalWidth >= 200 && im.getBoundingClientRect().width > 180
      )
    );
    if (ok) return true;
    await page.waitForTimeout(200);
  }
  return false;
}

async function triggerCaptcha(page) {
  await clearCaptcha(page);
  await page.waitForTimeout(200);
  await page.waitForSelector('div.bind-form > div.fl > input', { timeout: 20000 });
  await page.fill('div.bind-form > div.fl > input', `ABCD 1234 EFGH ${1000 + Math.floor(Math.random() * 8000)}`);
  await page.locator('div.e-btn.red').click({ force: true, timeout: 10000 });
  if (!(await waitPuzzle(page))) throw new Error('captcha image not visible');
  await page.waitForTimeout(500);
}

async function refreshCaptcha(page) {
  const how = await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll('a, span, div, button, i, em'));
    const btn = nodes.find((el) => (el.innerText || el.textContent || '').trim() === '刷新');
    if (btn) {
      btn.click();
      return 'text';
    }
    return '';
  });
  if (how) {
    await page.waitForTimeout(1200);
    await waitPuzzle(page, 10000);
    return;
  }
  await clearCaptcha(page);
  await page.waitForTimeout(300);
  await triggerCaptcha(page);
}

async function locateBoxes(page) {
  return page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll('div, section'));
    let panel = null;
    let panelArea = Infinity;
    for (const el of nodes) {
      const t = (el.innerText || '').replace(/\s+/g, '');
      if (!t.includes('安全验证')) continue;
      if (!(t.includes('拖动') || t.includes('拼图') || t.includes('刷新'))) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 280 || r.height < 240 || r.width > 480 || r.height > 520) continue;
      const area = r.width * r.height;
      if (area < panelArea) {
        panelArea = area;
        panel = {
          x: Math.max(0, Math.floor(r.x)),
          y: Math.max(0, Math.floor(r.y)),
          width: Math.ceil(r.width),
          height: Math.ceil(r.height),
        };
      }
    }
    let puzzle = null;
    for (const im of document.querySelectorAll('img')) {
      if (im.naturalWidth < 200 || im.naturalHeight < 120) continue;
      const r = im.getBoundingClientRect();
      if (r.width < 180) continue;
      puzzle = {
        x: Math.max(0, Math.floor(r.x)),
        y: Math.max(0, Math.floor(r.y)),
        width: Math.ceil(r.width),
        height: Math.ceil(r.height),
      };
      break;
    }
    return { panel, puzzle };
  });
}

async function shotClip(page, file, clip) {
  if (!clip || clip.width < 10 || clip.height < 10) return false;
  const vp = page.viewportSize() || { width: 1920, height: 1080 };
  const x = Math.max(0, Math.floor(clip.x));
  const y = Math.max(0, Math.floor(clip.y));
  const width = Math.max(1, Math.min(Math.ceil(clip.width), vp.width - x));
  const height = Math.max(1, Math.min(Math.ceil(clip.height), vp.height - y));
  if (width < 10 || height < 10) return false;
  try {
    await page.screenshot({
      path: file,
      clip: { x, y, width, height },
      timeout: 15000,
      animations: 'disabled',
    });
    return true;
  } catch (e) {
    log(`[!] clip shot fail ${path.basename(file)}: ${e.message}`);
    return false;
  }
}

async function saveShot(page, idx) {
  fs.mkdirSync(OUT, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const base = path.join(OUT, `cap_${String(idx).padStart(2, '0')}_${stamp}`);

  await page.screenshot({
    path: `${base}_page.png`,
    fullPage: false,
    timeout: 15000,
    animations: 'disabled',
  });

  const box = await locateBoxes(page);
  if (box.panel) {
    await shotClip(page, `${base}_modal.png`, box.panel);
  } else if (box.puzzle) {
    await shotClip(page, `${base}_modal.png`, {
      x: Math.max(0, box.puzzle.x - 12),
      y: Math.max(0, box.puzzle.y - 48),
      width: Math.min(420, box.puzzle.width + 24),
      height: box.puzzle.height + 140,
    });
  }
  if (box.puzzle) await shotClip(page, `${base}_puzzle.png`, box.puzzle);

  const imgs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('img')).map((im) => {
      const src = im.currentSrc || im.src || '';
      const r = im.getBoundingClientRect();
      return {
        w: Math.round(r.width),
        h: Math.round(r.height),
        nw: im.naturalWidth,
        nh: im.naturalHeight,
        cls: im.className || '',
        dataUrl: src.startsWith('data:') ? src : '',
      };
    })
  );

  fs.writeFileSync(
    `${base}_meta.json`,
    JSON.stringify(
      {
        idx,
        panel: box.panel,
        puzzle: box.puzzle,
        imgs: imgs.map((x) => ({
          w: x.w,
          h: x.h,
          nw: x.nw,
          nh: x.nh,
          cls: x.cls,
          dataLen: x.dataUrl.length,
        })),
      },
      null,
      2
    )
  );

  const b1 = imgs.find((x) => x.nw >= 200 && x.nh >= 120 && x.dataUrl);
  const b2 = imgs.find((x) => x.nw >= 40 && x.nw <= 90 && x.nh >= 120 && x.dataUrl);
  if (b1) {
    fs.writeFileSync(
      `${base}_b1_${b1.nw}x${b1.nh}.${b1.dataUrl.includes('png') ? 'png' : 'jpg'}`,
      Buffer.from(b1.dataUrl.split('base64,')[1], 'base64')
    );
  }
  if (b2) {
    fs.writeFileSync(
      `${base}_b2_${b2.nw}x${b2.nh}.${b2.dataUrl.includes('png') ? 'png' : 'jpg'}`,
      Buffer.from(b2.dataUrl.split('base64,')[1], 'base64')
    );
  }

  log(`[✓] ${path.basename(base)} panel=${box.panel ? `${box.panel.width}x${box.panel.height}` : 'null'} b1=${!!b1} b2=${!!b2}`);
  return base;
}

async function main() {
  log(`shots=${N} cdp=${cdpUrl} out=${OUT}`);
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || (await browser.newContext());
  const pages = context.pages();
  const page =
    pages.find((p) => p.url().includes('mygiftcard') || p.url().includes('jd.com')) ||
    pages[0] ||
    (await context.newPage());

  if (!/mygiftcard|myGiftCard/i.test(page.url())) {
    await page.goto('https://mygiftcard.jd.com/giftcard/myGiftCardInit.action', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  }
  log(`page=${page.url().slice(0, 100)}`);

  if (!(await waitPuzzle(page, 2000))) await triggerCaptcha(page);

  const saved = [];
  for (let i = 1; i <= N; i++) {
    log(`\n==== 截图 ${i}/${N} ====`);
    if (!(await waitPuzzle(page, 1500))) await triggerCaptcha(page);
    saved.push(await saveShot(page, i));
    if (i < N) await refreshCaptcha(page);
  }

  await browser.close();
  log('\n完成:');
  for (const b of saved) log(`  ${b}_modal.png`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
