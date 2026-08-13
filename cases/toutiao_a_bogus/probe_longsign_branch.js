// probe_longsign_branch.js — 深度探测：长签(176) vs 短签(168) 分支条件
// 目标：对照 me[23]、定时器采集、强制 patch、签长/raw 长度
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');
const { seedLocalStorage, readCache, importFromSnapshot } = require('./mstoken_store');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784615000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

function summarizeMe(me) {
  if (!me || !Array.isArray(me)) return null;
  const out = [];
  for (let i = 0; i < Math.min(me.length, 40); i++) {
    const v = me[i];
    if (v == null) {
      out.push({ i, t: 'null' });
      continue;
    }
    if (typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') {
      out.push({
        i,
        t: typeof v,
        v: typeof v === 'string' ? `str:${v.length}` : v,
      });
      continue;
    }
    if (typeof v === 'function') {
      out.push({ i, t: 'fn' });
      continue;
    }
    if (typeof v === 'object') {
      const keys = Object.keys(v).slice(0, 8);
      const row = { i, t: 'obj', keys };
      if (v.__fn) row.fn = true;
      if (typeof v.inner === 'string') row.inner_len = v.inner.length;
      if (Array.isArray(v.items)) row.items_n = v.items.length;
      if (typeof v.front === 'number') row.front = v.front;
      out.push(row);
      continue;
    }
    out.push({ i, t: typeof v });
  }
  return out;
}

function patchInitEnv(g, opts = {}) {
  const snap = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_env_snapshot.json'), 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;
  let n = 0;
  const only = opts.onlySlots || null;
  for (let i = 0; i < initMeSrc.length; i++) {
    if (only && !only.includes(i)) continue;
    const v = initMeSrc[i];
    if (v == null || (v && v.__fn)) continue;
    if (v && v.items && typeof v.front === 'number') {
      initMe[i] = {
        items: v.items.slice(),
        front: v.front || 0,
        rear: v.rear != null ? v.rear : v.items.length,
      };
    } else if (typeof v === 'object' && !Array.isArray(v)) {
      initMe[i] = JSON.parse(JSON.stringify(v));
    } else if (['boolean', 'number', 'string'].includes(typeof v)) {
      initMe[i] = v;
    } else {
      continue;
    }
    n++;
  }
  if (opts.forceMe23 != null) initMe[23] = !!opts.forceMe23;
  return n;
}

function hookTimers(g, bag) {
  const _st = g.setTimeout;
  const _si = g.setInterval;
  g.setTimeout = function (fn, ms) {
    bag.timeouts.push({ ms: Number(ms) || 0, t: Date.now() });
    return _st.apply(this, arguments);
  };
  g.setInterval = function (fn, ms) {
    bag.intervals.push({ ms: Number(ms) || 0, t: Date.now() });
    return _si.apply(this, arguments);
  };
}

function hookCanvas(g, stats) {
  const _create = g.document.createElement.bind(g.document);
  g.document.createElement = function (tag) {
    const el = _create(tag);
    if (String(tag).toLowerCase() === 'canvas') {
      stats.create_canvas++;
      const _gc = el.getContext.bind(el);
      el.getContext = function (type) {
        const t = String(type || '');
        if (t === '2d') stats.getContext_2d++;
        if (t.indexOf('webgl') >= 0) stats.getContext_webgl++;
        return _gc(t);
      };
      const _td = el.toDataURL.bind(el);
      el.toDataURL = function () {
        stats.toDataURL++;
        return _td.apply(this, arguments);
      };
    }
    return el;
  };
}

async function runCase(label, opts = {}) {
  const stats = {
    create_canvas: 0,
    toDataURL: 0,
    getContext_2d: 0,
    getContext_webgl: 0,
    offlineAudio: 0,
  };
  const timers = { timeouts: [], intervals: [] };

  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  hardenAbogusShim(g);
  hookTimers(g, timers);
  hookCanvas(g, stats);

  const _OAC = g.OfflineAudioContext;
  g.OfflineAudioContext = function (...args) {
    stats.offlineAudio++;
    return new _OAC(...args);
  };
  g.webkitOfflineAudioContext = g.OfflineAudioContext;

  if (opts.seedXmst !== false) {
    if (!readCache()) importFromSnapshot();
    seedLocalStorage(g, { allowStale: true });
  }

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });

  const meAfterInit = g.bdms.init._v[2];
  const me23_after_init = meAfterInit ? meAfterInit[23] : null;

  let patched = 0;
  if (opts.patchFull) patched = patchInitEnv(g, { forceMe23: opts.forceMe23 });
  else if (opts.forceMe23 != null) {
    if (meAfterInit) meAfterInit[23] = !!opts.forceMe23;
  } else if (opts.patchSlots) {
    patched = patchInitEnv(g, { onlySlots: opts.patchSlots, forceMe23: opts.forceMe23 });
  }

  const waitMs = opts.waitMs != null ? opts.waitMs : 4000;
  if (waitMs > 0) await waitEnvReady(waitMs);

  const me = g.bdms.init._v[2];
  const me23_before_sign = me ? me[23] : null;

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);

  return {
    label,
    len: ab ? ab.length : 0,
    raw: raw ? raw.length : 0,
    head: ab ? ab.slice(0, 40) : null,
    anchor: !!(ab && ab.includes('5f5LfY3qV')),
    me23_after_init,
    me23_before_sign,
    patched,
    stats,
    timeout_n: timers.timeouts.length,
    timeout_ms_sample: timers.timeouts.slice(0, 15).map((x) => x.ms),
    interval_n: timers.intervals.length,
    me_summary: summarizeMe(me),
  };
}

async function main() {
  const cases = [
    { label: 'xmst_only_wait4s', opts: { seedXmst: true, waitMs: 4000 } },
    { label: 'xmst_force_me23_true', opts: { seedXmst: true, forceMe23: true, waitMs: 4000 } },
    { label: 'xmst_force_me23_false', opts: { seedXmst: true, forceMe23: false, waitMs: 4000 } },
    { label: 'patch_full_snapshot', opts: { seedXmst: true, patchFull: true, waitMs: 4000 } },
    { label: 'patch_full_wait10s', opts: { seedXmst: true, patchFull: true, waitMs: 10000 } },
    { label: 'no_wait', opts: { seedXmst: true, forceMe23: true, waitMs: 0 } },
  ];

  const results = [];
  for (const c of cases) {
    console.error('[case]', c.label);
    // 每个 case 独立 VM，避免污染
    // eslint-disable-next-line no-await-in-loop
    const r = await runCase(c.label, c.opts);
    results.push(r);
    console.error('  -> len=%d raw=%d me23=%j canvas=%j', r.len, r.raw, r.me23_before_sign, r.stats);
  }

  const outPath = path.join(HERE, 'probe_longsign_branch_out.json');
  fs.writeFileSync(outPath, JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  console.log(JSON.stringify({ ok: true, out: outPath, lens: results.map((r) => [r.label, r.len, r.me23_before_sign]) }, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
