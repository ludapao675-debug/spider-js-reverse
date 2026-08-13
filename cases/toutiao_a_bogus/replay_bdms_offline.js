// replay_bdms_offline.js — 纯 Node 离线：bdms.init + XHR 链生成 a_bogus
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');
const { waitMsToken } = require('./xhr_real_network');
const {
  seedLocalStorage,
  writeCache,
  readCache,
  importFromSnapshot,
} = require('./mstoken_store');
const {
  refreshSnapshot,
  compareSnapshotWithLive,
  isSnapshotStale,
  readSnapshotMeta,
} = require('./env_snapshot_util');

const HERE = __dirname;
const RAW_BDMS = path.join(HERE, 'raw', 'bdms.js');
const TIMEOUT = parseInt(process.env.ABOGUS_TIMEOUT || '90000', 10);
const REFRESH_SNAPSHOT = process.argv.includes('--refresh-snapshot');
const SKIP_STALE_WARN = process.argv.includes('--skip-stale-warn');
const NO_HARDEN = process.argv.includes('--no-harden');
const NO_WAIT_ENV = process.argv.includes('--no-wait-env');
/** 强制只用 browser_env_snapshot（旧路径） */
const FORCE_SNAPSHOT = process.argv.includes('--force-snapshot');
/** 禁止 snapshot / 禁止 xmst 缓存（仅 mssdk，实验用） */
const NO_SNAPSHOT = process.argv.includes('--no-snapshot');
const MS_TOKEN_WAIT_MS = parseInt(process.env.MSTOKEN_WAIT_MS || '8000', 10);
const ENV_WAIT_MS = parseInt(process.env.ABOGUS_ENV_WAIT_MS || '3500', 10);
const positional = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const INPUT_URL = positional[0]
  || 'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web&msToken=test';

/** 加载 bdms.js */
function loadBdms(g) {
  const src = fs.readFileSync(RAW_BDMS, 'utf8');
  const ctx = vm.createContext(g);
  vm.runInContext(src, ctx, { timeout: TIMEOUT, filename: 'bdms.js' });
  if (typeof g.bdms !== 'object' || typeof g.bdms.init !== 'function') {
    throw new Error('bdms.init 未就绪');
  }
}

/** 从 browser_env_snapshot.json 补全 bdms.init._v[2] */
function patchInitEnv(g) {
  const snapPath = path.join(HERE, 'browser_env_snapshot.json');
  if (!fs.existsSync(snapPath)) return 0;

  const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;

  function rebuildQueue(qSnap) {
    if (!qSnap || !Array.isArray(qSnap.items)) return qSnap;
    return {
      items: qSnap.items.slice(),
      front: qSnap.front != null ? qSnap.front : 0,
      rear: qSnap.rear != null ? qSnap.rear : qSnap.items.length,
    };
  }

  let patched = 0;
  for (let i = 0; i < initMeSrc.length; i++) {
    const v = initMeSrc[i];
    if (v == null || (v && v.__fn)) continue;
    if (v && v.items && typeof v.front === 'number') {
      initMe[i] = rebuildQueue(v);
    } else if (typeof v === 'object' && !Array.isArray(v)) {
      initMe[i] = JSON.parse(JSON.stringify(v));
    } else if (typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') {
      initMe[i] = v;
    } else continue;
    patched++;
  }

  if (snap.mouse_queue_sample && initMe[2] && initMe[2]['0']) {
    const q = initMe[2]['0'];
    if (q && Array.isArray(q.items)) {
      snap.mouse_queue_sample.forEach((pt, idx) => { q.items[idx] = pt; });
      q.rear = snap.mouse_queue_sample.length;
      patched++;
    }
  }

  if (patched > 0) g.__init_env_patched = patched;
  return patched;
}

/** 读取 browser_fingerprint.json 的 ENV_OVERRIDE（可选） */
function loadEnvOverride() {
  const fpPath = path.join(HERE, 'browser_fingerprint.json');
  if (!fs.existsSync(fpPath)) return null;
  try {
    const fp = JSON.parse(fs.readFileSync(fpPath, 'utf8'));
    return fp.env_override || null;
  } catch (e) {
    console.warn('[replay_bdms_offline] 解析 browser_fingerprint.json 失败:', e.message);
    return null;
  }
}

/** 规范化待签 URL：去掉已有 a_bogus / 占位 msToken（由 bdms XHR hook 在 send 时写入） */
function resolveInputUrl() {
  try {
    const u = new URL(INPUT_URL);
    u.searchParams.delete('a_bogus');
    const ms = u.searchParams.get('msToken');
    if (!ms || ms === 'test' || ms === 'dump_test') u.searchParams.delete('msToken');
    return u.href;
  } catch (e) {
    return INPUT_URL;
  }
}

/** bdms.init（与首页 HTML `_SdkGlueInit` 一致：paths 为数组） */
function runInit(g) {
  g.bdms.init({
    aid: 24,
    pageId: 6457,
    paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'],
  });
}

/** 走 XHR hook 签名（a_bogus 在 send 后写入 responseURL/_url） */
function signViaXhr(g, inputUrl) {
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', inputUrl);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || inputUrl;
  const m = signed.match(/[?&]a_bogus=([^&]+)/);
  return {
    signed_url: signed,
    a_bogus: m ? decodeURIComponent(m[1]) : null,
  };
}

async function main() {
  const pageUrl = (() => {
    try {
      const snap = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_env_snapshot.json'), 'utf8'));
      return snap._meta?.url || 'https://www.toutiao.com/';
    } catch (e) {
      return 'https://www.toutiao.com/';
    }
  })();
  // 默认不用 fingerprint 覆盖：点号键 performance.memory.* 会污染全局；harden 已对齐屏幕/UA
  const envOverride = NO_HARDEN ? loadEnvOverride() : null;
  const g = makeBrowserShim(pageUrl, envOverride);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  // 纯本地关键：init 前注入 localStorage.xmst（bdms 读入 me[24]），无需浏览器 dump
  let xmstSeed = { ok: false };
  if (!FORCE_SNAPSHOT && !NO_SNAPSHOT) {
    if (!readCache()) {
      const imported = importFromSnapshot();
      if (imported) {
        console.log('[replay_bdms_offline] 已从 snapshot 导入 mstoken_cache len=%d', imported.len);
      }
    }
    xmstSeed = seedLocalStorage(g, { allowStale: true });
    if (xmstSeed.ok) {
      console.log(
        '[replay_bdms_offline] 已注入 localStorage.xmst source=%s len=%d age=%ss',
        xmstSeed.source,
        xmstSeed.len,
        xmstSeed.age_ms != null ? Math.round(xmstSeed.age_ms / 1000) : '?',
      );
    } else {
      console.warn('[replay_bdms_offline] 无 mstoken_cache：将尝试 mssdk / snapshot。可先浏览器 refresh 一次');
    }
  }

  let hardenInfo = null;
  if (!NO_HARDEN) {
    hardenInfo = hardenAbogusShim(g);
    console.log(
      '[replay_bdms_offline] harden: canvas_png_len=%d flags=%j',
      hardenInfo.canvasDataUrlLen,
      hardenInfo.flags,
    );
  } else if (envOverride) {
    console.log('[replay_bdms_offline] 已加载 browser_fingerprint.json (--no-harden)');
  }

  console.log('[replay_bdms_offline] 加载 bdms.js ...');
  loadBdms(g);

  console.log('[replay_bdms_offline] bdms.init ...');
  runInit(g);

  let patched = 0;
  let msTokenSource = xmstSeed.ok ? 'xmst_cache' : 'none';

  if (FORCE_SNAPSHOT) {
    patched = patchInitEnv(g);
    if (patched) {
      msTokenSource = 'snapshot';
      console.log('[replay_bdms_offline] --force-snapshot：已注入 (%d 槽)', patched);
    }
  } else if (!xmstSeed.ok) {
    // 无缓存时：短等 mssdk，再回退 snapshot
    console.log('[replay_bdms_offline] 等待 mssdk (最多 %dms) ...', MS_TOKEN_WAIT_MS);
    const tok = await waitMsToken(g, MS_TOKEN_WAIT_MS);
    if (tok.ok) {
      msTokenSource = 'mssdk';
      writeCache(tok.msToken, { source: 'mssdk' });
      console.log('[replay_bdms_offline] msToken 来自 mssdk len=%d（已写入 cache）', tok.msToken.length);
    } else if (NO_SNAPSHOT) {
      console.error('[replay_bdms_offline] 无 xmst cache 且 mssdk 失败: %j', tok.last_mssdk);
      process.exit(2);
    } else {
      console.warn('[replay_bdms_offline] mssdk 未拿到，回退 snapshot。last=%j', tok.last_mssdk);
      patched = patchInitEnv(g);
      if (patched) {
        msTokenSource = 'snapshot';
        console.log('[replay_bdms_offline] 已注入 browser_env_snapshot (%d 槽)', patched);
        const me = g.bdms.init._v[2][24];
        if (me && me.inner) writeCache(String(me.inner), { source: 'snapshot' });
      }
    }
  } else {
    // 已有 xmst：确认 me[24] 已就绪；可选短等 mssdk 轮换（不阻塞）
    const tok = await waitMsToken(g, 500);
    if (tok.ok && tok.msToken !== xmstSeed.msToken) {
      msTokenSource = 'mssdk_refresh';
      writeCache(tok.msToken, { source: 'mssdk_refresh' });
      console.log('[replay_bdms_offline] msToken 已由 mssdk 轮换更新');
    }
  }

  // bdms 约 3s 后异步采集 canvas/plugins；等齐再签才能走长签(176)
  if (!NO_WAIT_ENV) {
    console.log('[replay_bdms_offline] 等待环境采集 %dms ...', ENV_WAIT_MS);
    await waitEnvReady(ENV_WAIT_MS);
  }

  // 行为指纹：派发 mousemove + 可选喂 me[2]（活体 168→176 靠行为）
  try {
    const { fireMouseMoves, feedMe2Behavior } = require('./shim_event_target');
    const mouse = fireMouseMoves(g, { rounds: 10, perRound: 40 });
    const me2 = feedMe2Behavior(g, 100);
    console.log('[replay_bdms_offline] behavior: mouse=%j me2=%j', mouse, me2);
    await new Promise((r) => setTimeout(r, 400));
  } catch (e) {
    console.warn('[replay_bdms_offline] behavior feed skipped: %s', e.message || e);
  }

  const inputUrl = resolveInputUrl();
  const t0 = Date.now();
  const { signed_url, a_bogus: abogus } = signViaXhr(g, inputUrl);
  const elapsed = Date.now() - t0;

  const msInUrl = ((signed_url.match(/[?&]msToken=([^&]+)/) || [])[1] || '');
  const msToken = msInUrl ? decodeURIComponent(msInUrl) : null;

  console.log('[replay_bdms_offline] 耗时 %d ms', elapsed);
  console.log('INPUT :', inputUrl.slice(0, 120) + (inputUrl.length > 120 ? '...' : ''));
  console.log('OUTPUT:', abogus ? `${abogus.slice(0, 72)}...` : abogus);
  console.log('TYPE  :', typeof abogus, ' LEN:', abogus ? abogus.length : 0);
  console.log('msToken source=%s len=%s', msTokenSource, msToken ? msToken.length : 0);

  if (typeof abogus === 'string' && abogus.length > 80) {
    const out = {
      input_url: inputUrl,
      a_bogus: abogus,
      signed_url,
      abogus_len: abogus.length,
      msToken,
      msToken_len: msToken ? msToken.length : 0,
      msToken_source: msTokenSource,
      elapsed_ms: elapsed,
      init_env_patched: patched,
      harden: !NO_HARDEN,
      env_wait_ms: NO_WAIT_ENV ? 0 : ENV_WAIT_MS,
      target_len_home: 176,
      len_ok: abogus.length === 176 || abogus.length === 172 || abogus.length === 168,
      mssdk_last: g.__mssdk_last || null,
    };
    fs.writeFileSync(path.join(HERE, 'replay_bdms_offline_out.json'), JSON.stringify(out, null, 2));
    console.log('[replay_bdms_offline] 已写入 replay_bdms_offline_out.json');
    if (abogus.length !== 176) {
      console.warn('[replay_bdms_offline] 警告: 期望首页长签 176，实际 %d（仍可用，但未完全对齐）', abogus.length);
    }
    if (!msToken) {
      console.warn('[replay_bdms_offline] 警告: URL 无 msToken，纯 HTTP 取数会空 body');
    } else {
      writeCache(msToken, { source: msTokenSource });
    }
    // bdms 会在 XHR load 定时回调里继续跑 VM，签名完成后立即退出避免误报崩溃
    process.exit(abogus.length >= 168 && msToken ? 0 : 2);
  }
  console.warn('[replay_bdms_offline] a_bogus 无效；需 browser_env_snapshot.json（含 me[24].inner）+ 正确 XHR 垫片');
  process.exit(2);
}

let killer;
killer = setTimeout(() => {
  console.error('[replay_bdms_offline] 超时 %dms', TIMEOUT);
  process.exit(2);
}, TIMEOUT + 5000);
killer.unref && killer.unref();

try {
  (async () => {
    if (REFRESH_SNAPSHOT) {
      console.log('[replay_bdms_offline] --refresh-snapshot: 刷新 browser_env_snapshot ...');
      const r = await refreshSnapshot();
      console.log('[replay_bdms_offline] 快照 me[24] =', r.me24 ? `${r.me24.slice(0, 40)}...` : '(空)');
    } else if (!SKIP_STALE_WARN && isSnapshotStale()) {
      const meta = readSnapshotMeta();
      console.warn(
        '[replay_bdms_offline] 警告: 快照已过期 (age=%ss)，msToken 可能已轮换；建议 node refresh_env_snapshot.js 或加 --refresh-snapshot',
        meta.age_ms != null ? Math.round(meta.age_ms / 1000) : '?',
      );
      try {
        const cmp = await compareSnapshotWithLive();
        if (!cmp.match && cmp.live_me24_head) {
          console.warn(
            '[replay_bdms_offline] live me[24]=%s... 与快照 %s... 不一致',
            cmp.live_me24_head,
            cmp.snapshot_me24_head || '(无)',
          );
        }
      } catch (e) {
        console.warn('[replay_bdms_offline] 无法对比 live token（后端未运行?）:', e.message || e);
      }
    }
    await main();
    clearTimeout(killer);
  })();
} catch (e) {
  console.error('[replay_bdms_offline] ERROR:', e && e.stack ? e.stack : e);
  process.exit(1);
}
