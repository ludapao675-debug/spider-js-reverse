/**
 * 京东 JCAP Headless Blink 落地脚本（方案 B 延续）
 *
 * 已验证前提：
 * - 真实 Blink C++ 节点下 WASM 产出 AwPF（非 JSDOM 的 AAHE）
 * - /fp → code:0 + st
 *
 * 本脚本接力：
 * 1) querySid → /fp(AwPF ct)
 * 2) /check 拉拼图（tp=30）
 * 3) 页内算缺口 + 拟人拖 .move-img
 * 4) 二次 /check 提交 tk/ct/cs（页内 WASM getTK/getCTData/F）
 *
 * 运行：
 *   node repro_node_headless_blink.js
 *   或 D:\node_js22.0\node.exe repro_node_headless_blink.js
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { chromium } = require('playwright-core');

const LOG_FILE = path.join(__dirname, 'repro_node_output.log');
const OUT_JSON = path.join(__dirname, 'repro_check_result.json');
fs.writeFileSync(LOG_FILE, `[START HEADLESS BLINK + CHECK] ${new Date().toISOString()}\n`);

function log(msg) {
  const str = `[${new Date().toISOString().substring(11, 19)}] ${typeof msg === 'object' ? JSON.stringify(msg, null, 2) : msg}\n`;
  fs.appendFileSync(LOG_FILE, str);
  console.log(typeof msg === 'object' ? JSON.stringify(msg, null, 2) : msg);
}

function getSavedCookies() {
  try {
    const jsonPath = path.join(__dirname, 'jd_cookies.json');
    if (fs.existsSync(jsonPath)) {
      const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
      return data.cookie_header || '';
    }
  } catch (e) {}
  return '';
}

function parseCookieHeader(cookieStr) {
  const cookies = [];
  if (!cookieStr) return cookies;
  for (const part of cookieStr.split(';')) {
    const kv = part.trim().split('=');
    if (kv.length < 2) continue;
    const name = kv[0].trim();
    const value = kv.slice(1).join('=').trim();
    if (name) cookies.push({ name, value, domain: '.jd.com', path: '/' });
  }
  return cookies;
}

function parseForm(body) {
  const out = {};
  if (!body) return out;
  for (const part of String(body).split('&')) {
    const i = part.indexOf('=');
    if (i < 0) continue;
    out[decodeURIComponent(part.slice(0, i))] = decodeURIComponent(part.slice(i + 1));
  }
  return out;
}

function summarizeBody(body) {
  const f = parseForm(body);
  const sum = {};
  for (const [k, v] of Object.entries(f)) {
    sum[k] = { len: v.length, prefix: v.slice(0, 8) };
  }
  return sum;
}

/** OpenCV 多策略缺口（优先于页内启发式） */
function computeGapOpenCV(b1, b2) {
  const tmp = path.join(__dirname, 'debug', '_puzzle_tmp.json');
  fs.mkdirSync(path.dirname(tmp), { recursive: true });
  fs.writeFileSync(tmp, JSON.stringify({ b1, b2 }));
  const py = spawnSync('python', [path.join(__dirname, 'solve_gap_opencv.py'), '--json', tmp], {
    encoding: 'utf8',
    timeout: 20000,
  });
  if (py.status !== 0 && !py.stdout) {
    return { ok: false, error: 'opencv_spawn', stderr: (py.stderr || '').slice(0, 400) };
  }
  try {
    return JSON.parse((py.stdout || '').trim().split('\n').pop());
  } catch (e) {
    return { ok: false, error: 'opencv_parse', raw: (py.stdout || '').slice(0, 200) };
  }
}

/** 用 /check 返回的 b1(底图)/b2(滑块) dataURL 在页内算缺口偏移 */
async function computeGapFromDataUrls(page, b1, b2) {
  return page.evaluate(async ({ b1, b2 }) => {
    function load(src) {
      return new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = (e) => reject(e);
        im.src = src;
      });
    }

    const bgImg = await load(b1);
    const pieceImg = await load(b2);
    const bw = bgImg.naturalWidth;
    const bh = bgImg.naturalHeight;
    const pw = pieceImg.naturalWidth;
    const ph = pieceImg.naturalHeight;

    const bgC = document.createElement('canvas');
    bgC.width = bw;
    bgC.height = bh;
    const bgCtx = bgC.getContext('2d');
    bgCtx.drawImage(bgImg, 0, 0);
    const bgData = bgCtx.getImageData(0, 0, bw, bh).data;

    const pcC = document.createElement('canvas');
    pcC.width = pw;
    pcC.height = ph;
    const pcCtx = pcC.getContext('2d');
    pcCtx.drawImage(pieceImg, 0, 0);
    const pcData = pcCtx.getImageData(0, 0, pw, ph).data;

    // JPEG 无 alpha：用近白/近透明启发式；JPG 拼图块通常白底，取非近白为块
    const mask = new Uint8Array(pw * ph);
    let ymin = ph;
    let ymax = 0;
    let xmin = pw;
    let xmax = 0;
    for (let y = 0; y < ph; y++) {
      for (let x = 0; x < pw; x++) {
        const o = (y * pw + x) * 4;
        const r = pcData[o];
        const g = pcData[o + 1];
        const b = pcData[o + 2];
        const a = pcData[o + 3];
        const nearWhite = r > 245 && g > 245 && b > 245;
        const on = a > 128 && !nearWhite;
        if (on) {
          mask[y * pw + x] = 1;
          if (y < ymin) ymin = y;
          if (y > ymax) ymax = y;
          if (x < xmin) xmin = x;
          if (x > xmax) xmax = x;
        }
      }
    }
    if (ymax < ymin) return { ok: false, error: 'empty_piece', bg: [bw, bh], piece: [pw, ph] };

    const gray = new Float32Array(bw * bh);
    for (let i = 0; i < bw * bh; i++) {
      const o = i * 4;
      gray[i] = 0.299 * bgData[o] + 0.587 * bgData[o + 1] + 0.114 * bgData[o + 2];
    }
    const gx = new Float32Array(bw * bh);
    for (let y = 0; y < bh; y++) {
      for (let x = 1; x < bw; x++) {
        const i = y * bw + x;
        gx[i] = Math.abs(gray[i] - gray[i - 1]);
      }
    }

    // 缺口左缘常在强竖直边缘；结合块轮廓对齐
    let bestX = 0;
    let bestScore = -1e18;
    const maxX = Math.max(0, bw - pw);
    for (let x0 = Math.floor(pw * 0.2); x0 <= maxX; x0++) {
      let score = 0;
      for (let y = ymin; y <= ymax; y++) {
        for (let x = 1; x < pw; x++) {
          const mi = y * pw + x;
          if (mask[mi] !== mask[mi - 1]) {
            score += gx[y * bw + (x0 + x)];
          }
        }
      }
      // 惩罚贴边
      score -= Math.abs(x0 - bw * 0.45) * 0.01;
      if (score > bestScore) {
        bestScore = score;
        bestX = x0;
      }
    }

    // DOM 底图显示宽度（用于 CSS px）
    const domBg = document.querySelector('#captcha_modal #cpc_img, #captcha_modal .cpc-img-container img, #captcha_modal img');
    const dispW = (domBg && domBg.getBoundingClientRect().width) || bw;
    const scale = dispW / bw;

    return {
      ok: true,
      bestX,
      offsetCss: Math.round(bestX * scale),
      scale,
      bg: [bw, bh],
      piece: [pw, ph],
      pieceBox: [xmin, ymin, xmax, ymax],
      score: bestScore,
      source: 'check_img_b1_b2',
    };
  }, { b1, b2 });
}

function loadLiveTrackSample() {
  const p = path.join(__dirname, 'track_sample_live.json');
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch (e) {
    return null;
  }
}

/** 样本轨迹 + best_x 重采样（对齐活体 xyList: [x,y,dt]） */
function resampleTrack(sampleList, bestX) {
  const srcMax = Math.max(...sampleList.map((p) => p[0]), 1);
  const scale = bestX / srcMax;
  const out = [];
  let lastX = -1;
  for (const [x, y, dt] of sampleList) {
    let nx = Math.round(x * scale);
    if (nx < lastX) nx = lastX;
    if (out.length && nx === lastX && dt < 30) {
      out[out.length - 1][2] += dt;
      continue;
    }
    out.push([nx, y | 0, dt | 0]);
    lastX = nx;
  }
  if (!out.length || out[0][0] !== 0) out.unshift([0, 0, 0]);
  if (out[out.length - 1][0] !== bestX) {
    out.push([bestX, 0, 400]);
  } else {
    out[out.length - 1][0] = bestX;
  }
  return out;
}

/**
 * 按活体样本重放拖拽（y≈0，含长停顿）。SDK 自行写入 runtimeState.xyList。
 */
async function humanDrag(page, selector, offsetX) {
  const handle = await page.waitForSelector(selector, { timeout: 10000, state: 'visible' });
  const box = await handle.boundingBox();
  if (!box) throw new Error('move handle has no box');

  const startX = box.x + Math.min(8, box.width / 2);
  const startY = box.y + box.height / 2;
  const sample = loadLiveTrackSample();
  const track = sample && sample.list && sample.list.length
    ? resampleTrack(sample.list, Math.round(offsetX))
    : null;

  // 进轨前轻微游移
  await page.mouse.move(startX - 30, startY + 20, { steps: 5 });
  await page.waitForTimeout(120 + Math.random() * 100);
  await page.mouse.move(startX, startY, { steps: 8 });
  await page.waitForTimeout(180 + Math.random() * 120);
  await page.mouse.down();

  if (track) {
    log(`[7a] sample track n=${track.length} totalDt=${track.reduce((s, p) => s + p[2], 0)} endX=${track[track.length - 1][0]}`);
    for (let i = 1; i < track.length; i++) {
      const [x, y, dt] = track[i];
      // 保留活体长停顿特征，仅把极端 >3s 压到 ~2s
      let wait = dt;
      if (wait > 3000) wait = 1800 + Math.floor(Math.random() * 400);
      if (wait > 0) await page.waitForTimeout(wait);
      // 微步插值，避免一次大跳导致 SDK 采样过稀
      const prevX = track[i - 1][0];
      const dx = x - prevX;
      if (Math.abs(dx) >= 4) {
        const mid = prevX + Math.round(dx / 2);
        await page.mouse.move(startX + mid, startY + y);
        await page.waitForTimeout(12 + Math.random() * 20);
      }
      await page.mouse.move(startX + x, startY + y);
    }
    await page.waitForTimeout(150 + Math.random() * 200);
    await page.mouse.up();
    return { mode: 'sample', n: track.length, endX: track[track.length - 1][0] };
  }

  // fallback：旧匀速曲线
  const endX = startX + offsetX;
  const steps = 24;
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    await page.mouse.move(startX + (endX - startX) * e, startY);
    await page.waitForTimeout(40 + Math.random() * 80);
  }
  await page.waitForTimeout(400);
  await page.mouse.up();
  return { mode: 'fallback', n: steps, endX: offsetX };
}

async function main() {
  const result = {
    ok: false,
    fp: null,
    checks: [],
    gap: null,
    finalCheck: null,
  };

  log('============================================================');
  log('[1] 加载 jd_cookies.json ...');
  const cookieHeader = getSavedCookies();
  log(`[✓] Cookie 长度: ${cookieHeader.length}`);

  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const executablePath = fs.existsSync(edgePath) ? edgePath : chromePath;
  const headed = process.env.JCAP_HEADED === '1' || process.env.JCAP_HEADED === 'true';
  const cdpUrl = process.env.JCAP_CDP || ''; // e.g. http://127.0.0.1:9222
  log(`[2] 启动 ${cdpUrl ? 'CDP-attach ' + cdpUrl : headed ? 'Headed' : 'Headless'} Blink: ${cdpUrl || executablePath}`);

  let browser;
  let context;
  let page;
  if (cdpUrl) {
    browser = await chromium.connectOverCDP(cdpUrl);
    const contexts = browser.contexts();
    context = contexts[0] || (await browser.newContext());
    const pages = context.pages();
    page =
      pages.find((p) => p.url().includes('mygiftcard') || p.url().includes('jd.com')) ||
      pages[0] ||
      (await context.newPage());
    log(`[✓] CDP attach pages=${pages.length} url=${page.url().slice(0, 80)}`);
  } else {
    browser = await chromium.launch({
      executablePath,
      headless: headed ? false : true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1920,1080',
      ],
    });

    context = await browser.newContext({
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0',
      viewport: { width: 1920, height: 1080 },
    });

    const parsedCookies = parseCookieHeader(cookieHeader);
    if (parsedCookies.length) {
      await context.addCookies(parsedCookies);
      log(`[✓] 注入 Cookie ${parsedCookies.length} 条`);
    }

    page = await context.newPage();
  }

  let fpReq = null;
  let fpResp = null;
  const checkEvents = [];
  const reportEvents = [];

  page.on('request', (request) => {
    const url = request.url();
    if (url.includes('web_jcap_report') || url.includes('jcapmonitor')) {
      reportEvents.push({ kind: 'jcap_report', method: request.method(), url: url.slice(0, 300) });
      log(`[NET] report ${request.method()} ${url.slice(0, 180)}`);
    }
    if (url.includes('sgm-w.jd.com')) {
      reportEvents.push({ kind: 'sgm', method: request.method(), url: url.slice(0, 120) });
      log(`[NET] sgm ${request.method()} (ignored telemetry)`);
    }
    if (request.method() !== 'POST') return;
    if (url.includes('/cgi-bin/api/fp')) {
      fpReq = request.postData();
    }
    if (url.includes('/cgi-bin/api/check')) {
      const body = request.postData() || '';
      checkEvents.push({
        phase: 'request',
        ts: Date.now(),
        body,
        fields: summarizeBody(body),
      });
      log(`[NET] /check POST fields=${JSON.stringify(summarizeBody(body))}`);
    }
  });

  page.on('response', async (response) => {
    const url = response.url();
    if (response.request().method() !== 'POST') return;
    try {
      if (url.includes('/cgi-bin/api/fp')) {
        fpResp = await response.json();
      }
      if (url.includes('/cgi-bin/api/check')) {
        const json = await response.json();
        checkEvents.push({ phase: 'response', ts: Date.now(), json });
        log(`[NET] /check RESP code=${json.code} tp=${json.tp} st=${json.st || ''}`);
      }
    } catch (e) {}
  });

  log('[3] 打开礼品卡页...');
  if (!page.url().includes('myGiftCardInit') && !page.url().includes('mygiftcard')) {
    await page.goto('https://mygiftcard.jd.com/giftcard/myGiftCardInit.action', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  } else {
    log(`[✓] 已在目标页: ${page.url().slice(0, 90)}`);
  }
  // 清残留验证码遮罩，避免拦截「立即绑定」
  await page.evaluate(() => {
    for (const sel of ['#captcha_modal', '#captcha_dom', '.captcha_drop', '.jcap_refresh']) {
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
  await page.waitForSelector('div.bind-form > div.fl > input', { timeout: 20000 });

  log('[4] 填卡号并点击立即绑定 → 触发 /fp WASM(AwPF)...');
  // 先在页面游走鼠标，喂饱 touche_message（活体 tk≈5170 远大于仅滑轨采样）
  const vp = page.viewportSize() || { width: 1200, height: 800 };
  for (let i = 0; i < 40; i++) {
    const x = 80 + Math.random() * (vp.width - 160);
    const y = 80 + Math.random() * (vp.height - 160);
    await page.mouse.move(x, y, { steps: 2 + Math.floor(Math.random() * 4) });
    await page.waitForTimeout(30 + Math.random() * 70);
  }
  await page.fill('div.bind-form > div.fl > input', 'ABCD 1234 EFGH 9678');
  await page.waitForTimeout(200 + Math.random() * 200);
  await page.click('div.e-btn.red');

  // 等 /fp
  const fpDeadline = Date.now() + 20000;
  while (!fpResp && Date.now() < fpDeadline) {
    await page.waitForTimeout(200);
  }

  if (!fpReq || !fpResp) {
    log('[!] /fp 未捕获，中止');
    result.error = 'fp_missing';
    fs.writeFileSync(OUT_JSON, JSON.stringify(result, null, 2));
    await browser.close();
    process.exit(1);
  }

  const ctPrefix = (parseForm(fpReq).ct || '').slice(0, 4);
  log(`[✓] /fp ct前缀=${ctPrefix} code=${fpResp.code} st=${fpResp.st}`);
  result.fp = { request_fields: summarizeBody(fpReq), response: fpResp, ct_prefix: ctPrefix };

  if (fpResp.code !== 0 || ctPrefix !== 'AwPF') {
    log('[!] /fp 未通关 AwPF/code0，不继续 /check');
    fs.writeFileSync(OUT_JSON, JSON.stringify(result, null, 2));
    await browser.close();
    process.exit(1);
  }

  log('[5] 等待 /check tp=30 拼图图包...');
  let puzzleImg = null;
  const puzzleDeadline = Date.now() + 20000;
  while (Date.now() < puzzleDeadline) {
    for (const e of checkEvents) {
      if (e.phase !== 'response' || !e.json) continue;
      if (e.json.tp === 30 && e.json.img) {
        try {
          puzzleImg = typeof e.json.img === 'string' ? JSON.parse(e.json.img) : e.json.img;
        } catch (err) {
          puzzleImg = null;
        }
      }
    }
    if (puzzleImg && puzzleImg.b1 && puzzleImg.b2) break;
    await page.waitForTimeout(200);
  }

  if (!puzzleImg || !puzzleImg.b1 || !puzzleImg.b2) {
    log('[!] 未拿到 b1/b2，尝试等 DOM...');
    try {
      await page.waitForSelector('#captcha_modal .move-img', { timeout: 8000, state: 'visible' });
    } catch (e) {}
    result.checks = checkEvents;
    result.error = 'no_puzzle_img';
    fs.writeFileSync(OUT_JSON, JSON.stringify(result, null, 2));
    await browser.close();
    process.exit(1);
  }

  await page.waitForSelector('#captcha_modal .move-img', { timeout: 15000, state: 'visible' });

  // 弹层出现后再游荡一阵，继续累积 touch 轨迹
  for (let i = 0; i < 25; i++) {
    const box = await page.locator('#captcha_modal').boundingBox().catch(() => null);
    if (!box) break;
    const x = box.x + 20 + Math.random() * Math.max(40, box.width - 40);
    const y = box.y + 20 + Math.random() * Math.max(40, box.height - 40);
    await page.mouse.move(x, y, { steps: 3 });
    await page.waitForTimeout(40 + Math.random() * 80);
  }

  // Headless 下弹层偶发未完成布局（宽仅十几 px），强制可用宽度后再拖
  await page.evaluate(() => {
    const modal = document.querySelector('#captcha_modal');
    if (!modal) return;
    modal.style.width = '360px';
    modal.style.maxWidth = '90vw';
    modal.style.transform = 'none';
    // 对齐活体 A.wt/sw≈290
    const box = modal.querySelector('.cpc-img-container, #cpc_img, .drag-box') || modal;
    if (box) {
      box.style.width = '290px';
      box.style.maxWidth = '290px';
    }
    document.documentElement.style.setProperty('--jcap-zoom', '1');
  });
  await page.waitForTimeout(500);

  const layout = await page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('#captcha_modal img')).map((im) => ({
      w: im.getBoundingClientRect().width,
      h: im.getBoundingClientRect().height,
      nw: im.naturalWidth,
      nh: im.naturalHeight,
      cls: im.className,
    }));
    // 底图：naturalWidth 最大的那张
    let bgEl = null;
    let bgArea = 0;
    document.querySelectorAll('#captcha_modal img').forEach((im) => {
      const a = (im.naturalWidth || 0) * (im.naturalHeight || 0);
      if (a > bgArea) {
        bgArea = a;
        bgEl = im;
      }
    });
    const handle = document.querySelector('#captcha_modal .move-img');
    const track =
      document.querySelector('#captcha_modal .drag-box') ||
      document.querySelector('#captcha_modal .slider') ||
      (handle && handle.parentElement);
    return {
      imgs,
      imgW: bgEl ? bgEl.getBoundingClientRect().width : 0,
      imgH: bgEl ? bgEl.getBoundingClientRect().height : 0,
      imgNatural: bgEl ? [bgEl.naturalWidth, bgEl.naturalHeight] : null,
      handle: handle ? handle.getBoundingClientRect() : null,
      trackW: track ? track.getBoundingClientRect().width : 0,
    };
  });
  log('[5b] captcha layout:');
  log(layout);

  const gapJs = await computeGapFromDataUrls(page, puzzleImg.b1, puzzleImg.b2);
  const gapCv = computeGapOpenCV(puzzleImg.b1, puzzleImg.b2);
  log('[6a] gap JS:');
  log(gapJs);
  log('[6b] gap OpenCV:');
  log(gapCv);

  // 优先 OpenCV；失败回退 JS
  let gap = gapCv && gapCv.ok ? { ...gapCv } : { ...gapJs };
  gap.js = gapJs;
  gap.opencv = gapCv;

  // 优先用滑轨宽度映射到显示坐标（与实测 A.wt/sw≈290 一致）
  // 关键：matchTemplate 的 bestX = 裁剪后「块内容」左缘应对齐的底图 x；
  // 而 DOM 拖的是整张 b2（左侧还有 cropOffsetX 黑边/透明）。
  // 位移 i 满足：i + cropOffsetX*scale ≈ bestX*scale
  // 即 offsetCss ≈ (bestX - cropOffsetX) * scale
  // 旧公式直接 bestX*scale → 系统偏大 ~cropOffsetX（常见 10~20px），与肉眼「多拖一截」一致。
  if (gap.ok && gap.bg && gap.bg[0]) {
    const trackW = layout.trackW > 200 ? layout.trackW : layout.imgW > 180 ? layout.imgW : gap.bg[0];
    const cropX = Number(gap.cropOffsetX != null ? gap.cropOffsetX : (gap.pieceBox && gap.pieceBox[0]) || 0);
    gap.scale = trackW / gap.bg[0];
    gap.cropOffsetX = cropX;
    gap.offsetCssRaw = Math.round(gap.bestX * gap.scale); // 旧算法（会多拖）
    gap.offsetCss = Math.round((gap.bestX - cropX) * gap.scale);
    gap.trackW = trackW;
  }
  result.gap = gap;
  result.layout = layout;
  // 落盘本轮 b1/b2 原图，便于离线精确核验缺口位置
  try {
    fs.mkdirSync(path.join(__dirname, 'debug'), { recursive: true });
    const m1 = (puzzleImg.b1 || '').match(/base64,(.*)$/);
    const m2 = (puzzleImg.b2 || '').match(/base64,(.*)$/);
    if (m1) fs.writeFileSync(path.join(__dirname, 'debug', 'b1_cur.png'), Buffer.from(m1[1], 'base64'));
    if (m2) fs.writeFileSync(path.join(__dirname, 'debug', 'b2_cur.png'), Buffer.from(m2[1], 'base64'));
    log('[6c] 已保存 b1/b2 到 debug/');
  } catch (e) {
    log(`[6c] 保存 b1/b2 失败: ${e.message}`);
  }
  result.reports = reportEvents;
  log('[6] 缺口选用:');
  log({
    source: gap.source,
    bestX: gap.bestX,
    cropOffsetX: gap.cropOffsetX,
    offsetCssRaw: gap.offsetCssRaw,
    offsetCss: gap.offsetCss,
    scale: gap.scale,
    trackW: gap.trackW,
  });

  if (!gap.ok) {
    result.error = 'gap_failed';
    fs.writeFileSync(OUT_JSON, JSON.stringify(result, null, 2));
    await browser.close();
    process.exit(1);
  }

  let offset = gap.offsetCss;
  // 可选微调；默认 0（旧默认 +2 会在已修正公式上继续多拖）
  const gapBias = Number.parseInt(process.env.JCAP_GAP_BIAS || '0', 10);
  if (Number.isFinite(gapBias) && gapBias !== 0) {
    offset = Math.round(offset + gapBias);
    gap.gapBias = gapBias;
    gap.offsetCss = offset;
    log(`[6d] 缺口校正 GAP_BIAS=${gapBias} → offsetCss=${offset}`);
  }
  if (!(gap.scale > 0.7 && gap.scale < 1.6) || !(offset >= 40)) {
    log(`[!] 换算异常 scale=${gap.scale} offset=${offset}，回退 bestX=${gap.bestX}`);
    offset = gap.bestX;
  }
  if (offset < 40 || offset > 250) {
    log(`[!] 测算偏移异常 ${offset}，回退 130`);
    offset = 130;
  }
  offset = Math.max(40, Math.round(offset));

  const checksBeforeDrag = checkEvents.filter((e) => e.phase === 'request').length;
  log(`[7] 拟人拖动 .move-img offsetX=${offset} (bestX=${gap.bestX}, scale=${gap.scale}, trackW=${gap.trackW}) ...`);

  const watchPause = Number.parseInt(process.env.JCAP_WATCH_PAUSE_MS || '0', 10);
  if (watchPause > 0) {
    log(`>>> 请看屏幕：即将拖到 offset=${offset}px（bestX=${gap.bestX} bias=${gap.gapBias || 0}），${watchPause}ms 后开始拖`);
    await page.waitForTimeout(watchPause);
  }

  // ---- P0 修复：注入真实结构的 touche_message ----
  // 静态还原结论（jcap_ujb96b.js）：
  //  - PC 端 touche_message 仅由 document 'click' 监听累积（mousemove 不写入，
  //    因 gesture 对象 c 仅由 touchstart 初始化），存储后端为 localStorage
  //    （getter N 优先读 localStorage.getItem，setter R 写 setItem）。
  //  - 复现的纯 page.mouse.move 游走不会录入 → tk 短 → 16807。
  // 覆写 Storage.prototype.getItem 使 SDK 读取到的 touche_message 始终为本合成结构
  // （不被滑块 mouseup 触发的 click 覆盖）；并 hook JSON.stringify 抓取实际提交的 f。
  const handleBox = layout.handle || null;
  const synthResult = await page.evaluate(({ offset, hb }) => {
    const vw = window.innerWidth || 1200;
    const vh = window.innerHeight || 800;
    const now = Date.now();
    const scrX = window.screenX || 0;
    const scrY = window.screenY || 0;
    const sx0 = hb ? Math.round(hb.x + hb.width / 2) : Math.round(vw / 2);
    const sy0 = hb ? Math.round(hb.y + hb.height / 2) : Math.round(vh / 2);
    const pts = [];
    // 环境点击点（PC 端 click 监听录入的元素形状 {did,cn,sx,sy,px,py,time,type:"click"}）
    for (let i = 0; i < 9; i++) {
      const sx = 80 + Math.floor(Math.random() * (vw - 160));
      const sy = 80 + Math.floor(Math.random() * (vh - 160));
      pts.push({ did: '', cn: '', sx, sy, px: sx, py: sy, time: now - (9 - i) * 400, type: 'click' });
    }
    // 滑块拖拽手势（与本次偏移一致）：{did,cn,time,pt:[[clientX,screenY,pageX,pageY,dt]...]}
    const g = { did: '', cn: 'move-img', time: now, pt: [] };
    let acc = 0;
    const N = 22;
    for (let i = 0; i <= N; i++) {
      const x = Math.round((offset * i) / N);
      const dt = i === 0 ? 0 : Math.floor(20 + Math.random() * 80);
      acc += dt;
      g.pt.push([sx0 + x, sy0 + scrY, sx0 + x, sy0, acc]);
    }
    pts.push(g);
    const SYNTH = JSON.stringify(pts);
    const origGet = Storage.prototype.getItem;
    Storage.prototype.getItem = function (k) {
      if (k === 'touche_message') return SYNTH;
      return origGet.apply(this, arguments);
    };
    const origStringify = JSON.stringify;
    window.__captured = null;
    JSON.stringify = function (v) {
      try {
        if (v && typeof v === 'object' && v.touchList !== undefined && window.__captured === null) {
          window.__captured = {
            touchListLen: Array.isArray(v.touchList) ? v.touchList.length : -1,
            touchList: v.touchList,
          };
        }
      } catch (e) {}
      return origStringify.apply(this, arguments);
    };
    return { synthLen: SYNTH.length, synthSample: pts.slice(0, 2) };
  }, { offset, hb: handleBox });
  log('[6.5] 注入合成 touche_message:');
  log(synthResult);
  result.injectedTouchList = synthResult;

  const dragInfo = await humanDrag(page, '#captcha_modal .move-img', offset);
  result.drag = dragInfo;
  if (watchPause > 0) {
    log(`>>> 拖完了，请看拼图块是否对准缺口（停 ${watchPause}ms 再读结果）`);
    await page.waitForTimeout(watchPause);
  }
  // 回读 SDK xyList，确认采样
  try {
    const xy = await page.evaluate(() => {
      const el = document.querySelector('#captcha_modal .move-img, #captcha_modal');
      let cur = el;
      for (let i = 0; i < 12 && cur; i++) {
        const v = cur.__vue__ || cur.__vueParentComponent;
        if (v) {
          const proxy = v.proxy || v;
          const rs = (proxy.runtimeState) || (proxy.$data && proxy.$data.runtimeState) ||
            (v.ctx && v.ctx.runtimeState);
          if (rs && rs.xyList) {
            return { n: rs.xyList.length, head: rs.xyList.slice(0, 3), tail: rs.xyList.slice(-3) };
          }
        }
        cur = cur.parentElement;
      }
      return { n: -1 };
    });
    result.xyList = xy;
    log('[7c] runtime xyList:');
    log(xy);
  } catch (e) {
    log(`[7c] xyList read fail: ${e.message}`);
  }
  log('[7b] drag done:');
  log(dragInfo);

  // 等拖拽后的 /check（含 tk/ct/cs）
  const dragDeadline = Date.now() + 15000;
  while (Date.now() < dragDeadline) {
    const submitReqs = checkEvents.filter(
      (e) => e.phase === 'request' && e.fields && e.fields.cs && e.fields.cs.len > 0
    );
    if (submitReqs.length > 0) break;
    const newReqs = checkEvents.filter((e) => e.phase === 'request').length;
    if (newReqs > checksBeforeDrag && checkEvents.some((e) => e.phase === 'response' && e.ts > Date.now() - 5000)) {
      // 可能已有响应
    }
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(1500);

  result.checks = checkEvents;
  const submitReq = [...checkEvents]
    .reverse()
    .find((e) => e.phase === 'request' && e.fields && (e.fields.cs || e.fields.tk));
  const submitResp = [...checkEvents]
    .reverse()
    .find((e) => e.phase === 'response');

  result.finalCheck = {
    request_fields: submitReq ? submitReq.fields : null,
    response: submitResp ? submitResp.json : null,
  };

  // 抓取实际提交给 WASM 的 f.touchList（hook JSON.stringify 所得）
  try {
    const cap = await page.evaluate(() => window.__captured);
    result.capturedTouchList = cap;
    log('[7d] 实际提交 f.touchList:');
    log(cap);
  } catch (e) {
    log(`[7d] 抓取 f.touchList 失败: ${e.message}`);
  }

  log('============================================================');
  log('[8] /check 提交摘要:');
  log(result.finalCheck);

  if (submitReq && submitReq.fields) {
    const f = submitReq.fields;
    const cryptoOk =
      f.tk && String(f.tk.prefix).startsWith('AwPF') &&
      f.ct && String(f.ct.prefix).startsWith('AwPF') &&
      (!f.cs || String(f.cs.prefix).startsWith('AwPF'));
    result.crypto_ok = !!cryptoOk;
    if (cryptoOk) {
      log('[✓] 页内 WASM 已生成 AwPF tk/ct(/cs) — k→getTK / x→getCTData（补环境沿用 /fp 结论）');
    }
  }

  if (submitResp && submitResp.json) {
    log(`[✓] /check 响应 code=${submitResp.json.code} tp=${submitResp.json.tp} msg=${submitResp.json.msg || ''}`);
    if (submitResp.json.code === 0) {
      log('[✓✓✓] /check 通关（验证码侧）');
      result.ok = true;
    } else {
      log('[!] 缺口/轨迹未过风控（加密链路已通，可调 offset 或重试）');
    }
  } else {
    log('[!] 未捕获到拖拽后 /check 响应');
  }

  // 页面业务提示
  try {
    const tip = await page.evaluate(() => (document.body && document.body.innerText) || '');
    const hit = tip.match(/该卡密[^\n]{0,20}|绑定成功[^\n]{0,20}|验证失败[^\n]{0,20}/);
    if (hit) log(`[UI] ${hit[0]}`);
  } catch (e) {}

  fs.writeFileSync(OUT_JSON, JSON.stringify(result, null, 2));
  log(`[✓] 结果已写入 ${OUT_JSON}`);

  if (cdpUrl) {
    // attach 模式只断开，不杀外部浏览器
    await browser.close();
    log('[✓] CDP 连接已断开（外部浏览器保留）');
  } else {
    await browser.close();
    log('[✓] Headless 节点释放');
  }
  // 0=验证码通关；3=加密 AwPF 已通但缺口未过；2=其它失败
  if (result.ok) process.exit(0);
  if (result.crypto_ok) process.exit(3);
  process.exit(2);
}

main().catch((err) => {
  log(`[CRITICAL] ${err.stack || err.message}`);
  process.exit(1);
});
