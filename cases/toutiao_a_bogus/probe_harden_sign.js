// probe_harden_sign.js — harden + 等待后签名，并统计 canvas/webgl 是否被 bdms 调用
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784601000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

function patchInitEnv(g) {
  const snap = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_env_snapshot.json'), 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;
  let n = 0;
  for (let i = 0; i < initMeSrc.length; i++) {
    const v = initMeSrc[i];
    if (v == null || (v && v.__fn)) continue;
    if (v && v.items && typeof v.front === 'number') {
      initMe[i] = { items: v.items.slice(), front: v.front || 0, rear: v.rear != null ? v.rear : v.items.length };
    } else if (typeof v === 'object' && !Array.isArray(v)) initMe[i] = JSON.parse(JSON.stringify(v));
    else if (['boolean', 'number', 'string'].includes(typeof v)) initMe[i] = v;
    else continue;
    n++;
  }
  return n;
}

async function main() {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  const stats = { create_canvas: 0, toDataURL: 0, getContext_2d: 0, getContext_webgl: 0, offlineAudio: 0, exts: 0 };
  const hard = hardenAbogusShim(g);

  // 再包一层统计
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
        const ctx = _gc(t);
        if (ctx && t.indexOf('webgl') >= 0 && typeof ctx.getSupportedExtensions === 'function') {
          const ex = ctx.getSupportedExtensions();
          stats.exts = Array.isArray(ex) ? ex.length : 0;
        }
        return ctx;
      };
      const _td = el.toDataURL.bind(el);
      el.toDataURL = function () {
        stats.toDataURL++;
        return _td();
      };
    }
    return el;
  };
  const _OAC = g.OfflineAudioContext;
  g.OfflineAudioContext = function (...args) {
    stats.offlineAudio++;
    return new _OAC(...args);
  };
  g.webkitOfflineAudioContext = g.OfflineAudioContext;

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  patchInitEnv(g);

  console.log('[1] after init stats', JSON.stringify(stats));
  await waitEnvReady(4000);
  console.log('[2] after wait stats', JSON.stringify(stats));

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);

  const out = {
    len: ab ? ab.length : 0,
    raw: raw ? raw.length : 0,
    head: ab ? ab.slice(0, 48) : null,
    anchor: !!(ab && ab.includes('5f5LfY3qV')),
    stats,
    canvasDataUrlLen: hard.canvasDataUrlLen,
    msToken_in_url: /msToken=/.test(signed),
  };
  console.log(JSON.stringify(out, null, 2));
  fs.writeFileSync(path.join(HERE, 'probe_harden_sign_out.json'), JSON.stringify(out, null, 2));
  process.exit(out.len === 176 ? 0 : 0); // 探测不失败退出
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
