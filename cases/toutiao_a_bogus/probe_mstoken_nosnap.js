// probe_mstoken_nosnap.js — 验证 Node 无 snapshot 时 me[24]/msToken 是否自产
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');

const HERE = __dirname;
const bdmsSrc = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');

function run(label, { patchSnap, waitMs }) {
  const g = makeBrowserShim('https://www.toutiao.com/');
  hardenAbogusShim(g);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  vm.runInContext(bdmsSrc, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({
    aid: 24,
    pageId: 6457,
    paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'],
  });

  let patched = 0;
  if (patchSnap) {
    const snap = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_env_snapshot.json'), 'utf8'));
    const src = snap.init_me || snap.init_v;
    const me = g.bdms.init._v[2];
    for (let i = 0; i < (src || []).length; i++) {
      const v = src[i];
      if (v == null || (v && v.__fn)) continue;
      if (v && v.items && typeof v.front === 'number') {
        me[i] = { items: v.items.slice(), front: v.front || 0, rear: v.rear != null ? v.rear : v.items.length };
      } else if (typeof v === 'object' && !Array.isArray(v)) {
        me[i] = JSON.parse(JSON.stringify(v));
      } else if (['boolean', 'number', 'string'].includes(typeof v)) {
        me[i] = v;
      } else continue;
      patched++;
    }
  }

  const before = g.bdms.init._v[2][24];
  const beforeInner = before && before.inner ? String(before.inner) : null;
  // 同步忙等（探针用）
  const end = Date.now() + waitMs;
  while (Date.now() < end) { /* wait */ }

  const after = g.bdms.init._v[2][24];
  const afterInner = after && after.inner ? String(after.inner) : null;

  const url = `https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=${Math.floor(Date.now() / 1000)}&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web`;
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', url);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || url;
  const ab = ((signed.match(/[?&]a_bogus=([^&]+)/) || [])[1] || '');
  const ms = ((signed.match(/[?&]msToken=([^&]+)/) || [])[1] || '');
  const abDec = ab ? decodeURIComponent(ab) : null;
  const msDec = ms ? decodeURIComponent(ms) : null;

  return {
    label,
    patched,
    before_len: beforeInner ? beforeInner.length : 0,
    after_len: afterInner ? afterInner.length : 0,
    after_head: afterInner ? afterInner.slice(0, 32) : null,
    ab_len: abDec ? abDec.length : 0,
    ms_len: msDec ? msDec.length : 0,
    ms_head: msDec ? msDec.slice(0, 32) : null,
    ms_eq_after: !!(msDec && afterInner && msDec === afterInner),
    signed_head: signed.slice(0, 140),
  };
}

(async () => {
  // waitEnvReady 用真实 timer
  async function runAsync(label, opts) {
    const g = makeBrowserShim('https://www.toutiao.com/');
    hardenAbogusShim(g);
    g.window = g; g.self = g; g.top = g; g.parent = g;
    vm.runInContext(bdmsSrc, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
    g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
    if (opts.waitMs) await waitEnvReady(opts.waitMs);
    // 观察 init 后网络：shim 里 XHR 是否被 mssdk 调用
    const me24 = g.bdms.init._v[2][24];
    const url = `https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=${Math.floor(Date.now() / 1000)}&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web`;
    const xhr = new g.XMLHttpRequest();
    xhr.open('GET', url);
    xhr.send();
    const signed = xhr.responseURL || xhr._url || url;
    const ab = ((signed.match(/[?&]a_bogus=([^&]+)/) || [])[1] || '');
    const ms = ((signed.match(/[?&]msToken=([^&]+)/) || [])[1] || '');
    return {
      label,
      me24_type: me24 == null ? 'null' : typeof me24,
      me24_keys: me24 && typeof me24 === 'object' ? Object.keys(me24).slice(0, 8) : null,
      me24_inner_len: me24 && me24.inner ? String(me24.inner).length : 0,
      me24_head: me24 && me24.inner ? String(me24.inner).slice(0, 32) : null,
      ab_len: ab ? decodeURIComponent(ab).length : 0,
      ms_len: ms ? decodeURIComponent(ms).length : 0,
      ms_head: ms ? decodeURIComponent(ms).slice(0, 32) : null,
    };
  }

  const rows = [
    run('busy_no_snap_0', { patchSnap: false, waitMs: 0 }),
    run('busy_no_snap_3500', { patchSnap: false, waitMs: 3500 }),
    run('busy_with_snap_0', { patchSnap: true, waitMs: 0 }),
    await runAsync('async_no_snap_3500', { waitMs: 3500 }),
  ];
  const out = path.join(HERE, 'probe_mstoken_nosnap_out.json');
  fs.writeFileSync(out, JSON.stringify(rows, null, 2));
  console.log(JSON.stringify(rows, null, 2));
  console.log('wrote', out);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
