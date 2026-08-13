// mstoken_store.js — msToken / localStorage.xmst 本地持久化（摆脱浏览器 dump）
'use strict';

const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const CACHE_PATH = path.join(HERE, 'mstoken_cache.json');
/** 默认认为 24h 内可复用；服务端真实 TTL 可能更长/更短，失败再刷新 */
const DEFAULT_MAX_AGE_MS = Number(process.env.MSTOKEN_MAX_AGE_MS || 24 * 60 * 60 * 1000);

function readCache() {
  try {
    if (!fs.existsSync(CACHE_PATH)) return null;
    const j = JSON.parse(fs.readFileSync(CACHE_PATH, 'utf8'));
    if (!j || !j.msToken || typeof j.msToken !== 'string' || j.msToken.length < 32) return null;
    return j;
  } catch (e) {
    return null;
  }
}

function writeCache(msToken, meta) {
  const out = {
    msToken: String(msToken),
    len: String(msToken).length,
    ts: new Date().toISOString(),
    source: (meta && meta.source) || 'unknown',
    ...(meta || {}),
  };
  fs.writeFileSync(CACHE_PATH, JSON.stringify(out, null, 2));
  return out;
}

function isCacheFresh(cache, maxAgeMs) {
  if (!cache || !cache.ts) return false;
  const t = Date.parse(cache.ts);
  if (!Number.isFinite(t)) return false;
  return Date.now() - t <= (maxAgeMs != null ? maxAgeMs : DEFAULT_MAX_AGE_MS);
}

/**
 * 在 bdms.init 之前写入 localStorage.xmst（bdms 会读入 me[24]）
 * @returns {{ok:boolean, msToken?:string, source?:string, age_ms?:number|null}}
 */
function seedLocalStorage(g, opts) {
  const opt = opts || {};
  const cache = readCache();
  let token = opt.msToken || null;
  let source = opt.source || null;

  if (!token && cache && (opt.allowStale || isCacheFresh(cache, opt.maxAgeMs))) {
    token = cache.msToken;
    source = cache.source || 'cache';
  }
  if (!token) {
    return { ok: false, reason: 'no_mstoken_cache', path: CACHE_PATH };
  }

  try {
    if (g.localStorage && typeof g.localStorage.setItem === 'function') {
      g.localStorage.setItem('xmst', token);
    }
  } catch (e) {
    return { ok: false, reason: 'localStorage_set_failed', error: String(e.message || e) };
  }

  const ageMs = cache && cache.ts ? Date.now() - Date.parse(cache.ts) : null;
  return { ok: true, msToken: token, source: source || 'seed', age_ms: ageMs, len: token.length };
}

/** 从 snapshot / 活体 me[24] 同步进缓存（一次性迁移） */
function importFromSnapshot() {
  const snapPath = path.join(HERE, 'browser_env_snapshot.json');
  if (!fs.existsSync(snapPath)) return null;
  try {
    const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
    const me = snap.init_me || snap.init_v;
    const inner = me && me[24] && me[24].inner;
    if (!inner || String(inner).length < 32) return null;
    return writeCache(String(inner), { source: 'snapshot_import' });
  } catch (e) {
    return null;
  }
}

module.exports = {
  CACHE_PATH,
  DEFAULT_MAX_AGE_MS,
  readCache,
  writeCache,
  isCacheFresh,
  seedLocalStorage,
  importFromSnapshot,
};
