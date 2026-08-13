// env_snapshot_util.js — 浏览器环境快照：刷新、过期检测、live token 对比
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');

const HERE = __dirname;
const SNAP_PATH = path.join(HERE, 'browser_env_snapshot.json');
const BACKEND_HOST = process.env.CRYPTO_HUNTER_HOST || '127.0.0.1';
const BACKEND_PORT = Number(process.env.CRYPTO_HUNTER_PORT || 27183);
/** 默认快照有效期 10 分钟（msToken 会随页面活动轮换） */
const DEFAULT_MAX_AGE_MS = Number(process.env.SNAPSHOT_MAX_AGE_MS || 10 * 60 * 1000);

/** POST JSON 到 crypto-hunter 后端 */
function post(apiPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: apiPath,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

/** 读取快照 meta + me[24] */
function readSnapshotMeta() {
  if (!fs.existsSync(SNAP_PATH)) {
    return { exists: false, age_ms: null, me24: null, ts: null };
  }
  try {
    const snap = JSON.parse(fs.readFileSync(SNAP_PATH, 'utf8'));
    const ts = snap._meta?.ts ? Date.parse(snap._meta.ts) : NaN;
    const me24 = snap.init_me?.[24]?.inner || null;
    return {
      exists: true,
      ts: snap._meta?.ts || null,
      age_ms: Number.isFinite(ts) ? Date.now() - ts : null,
      me24,
      url: snap._meta?.url || null,
    };
  } catch (e) {
    return { exists: true, parse_error: String(e), age_ms: null, me24: null };
  }
}

/** 快照是否过期 */
function isSnapshotStale(maxAgeMs = DEFAULT_MAX_AGE_MS) {
  const meta = readSnapshotMeta();
  if (!meta.exists || meta.age_ms == null) return true;
  return meta.age_ms > maxAgeMs;
}

/** 从浏览器读取 live me[24].inner */
async function fetchLiveMe24() {
  const code = `(function(){
    var m = window.bdms && window.bdms.init && window.bdms.init._v && window.bdms.init._v[2];
    return { ok: !!(m && m[24]), inner: m && m[24] ? m[24].inner : null, url: location.href };
  })()`;
  const out = await post('/api/browser/page/run-js', {
    code,
    as_expr: true,
    return_mode: 'json',
    timeout_sec: 30,
  });
  const r = out.result || out.data?.result;
  return r || { ok: false, inner: null };
}

/** dump 并写入 browser_env_snapshot.json */
async function refreshSnapshot() {
  const code = fs.readFileSync(path.join(HERE, 'dump_ye_env.js'), 'utf8')
    .replace(/^\/\/[^\n]*\n/, '')
    .trim();

  const dump = await post('/api/browser/page/run-js', {
    code,
    as_expr: true,
    return_mode: 'json',
    timeout_sec: 30,
  });

  const r = dump.result || dump.data?.result;
  if (!r || !r.ok) {
    throw new Error(`dump 失败: ${JSON.stringify(dump).slice(0, 400)}`);
  }

  const snap = {
    _meta: {
      source: 'dump_ye_env',
      ts: new Date().toISOString(),
      url: r.url,
    },
    init_me: r.init_v,
    sign_fn_me: r.ye_me,
    sign_fn_pc: r.ye_pc,
    ye_test: r.ye_test,
  };

  fs.writeFileSync(SNAP_PATH, JSON.stringify(snap, null, 2));
  return {
    path: SNAP_PATH,
    me24: r.init_v?.[24]?.inner || null,
    ts: snap._meta.ts,
  };
}

/** 对比快照 vs 浏览器 live token */
async function compareSnapshotWithLive() {
  const meta = readSnapshotMeta();
  const live = await fetchLiveMe24();
  const match = !!(meta.me24 && live.inner && meta.me24 === live.inner);
  return {
    snapshot_me24_head: meta.me24 ? meta.me24.slice(0, 32) : null,
    live_me24_head: live.inner ? live.inner.slice(0, 32) : null,
    match,
    snapshot_age_ms: meta.age_ms,
    stale: isSnapshotStale(),
  };
}

module.exports = {
  SNAP_PATH,
  DEFAULT_MAX_AGE_MS,
  readSnapshotMeta,
  isSnapshotStale,
  fetchLiveMe24,
  refreshSnapshot,
  compareSnapshotWithLive,
};
