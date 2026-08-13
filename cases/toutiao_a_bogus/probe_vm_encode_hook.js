// probe_vm_encode_hook.js — Node 侧同构钩 Function.prototype.call，对照活体 arr/ret 长度与 pc
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
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784618000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function installVmHook(g) {
  const hits = [];
  let lastAb = null;
  const MAX = 200;
  const ctx = vm.createContext(g);
  // 必须在加载 bdms 前改写；钩子体内禁止再用 .call/.apply（会递归爆栈）
  const FP = ctx.Function.prototype;
  const origCall = FP.call;
  FP.call = function patchedCall(thisArg) {
    const n = arguments.length;
    const callArgs = new Array(n);
    callArgs[0] = thisArg;
    for (let i = 1; i < n; i++) callArgs[i] = arguments[i];
    const ret = Reflect.apply(origCall, this, callArgs);
    try {
      if (this && this._u && this._v && hits.length < MAX) {
        const pc = this._v[0];
        const a0 = n > 1 ? arguments[1] : undefined;
        // 放宽：先看有没有 VM call
        if (hits.length < 5 || (hits.length % 50 === 0)) {
          hits.push({ k: 'vm_any', pc, argc: n - 1, a0t: typeof a0, rett: typeof ret, retlen: ret && ret.length, t: Date.now() });
        }
        if (typeof ret === 'string' && ret.length >= 100 && ret.length <= 220) {
          const head = ret.substring(0, 12);
          if (/^[A-Za-z0-9+/_=-]+$/.test(head)) {
            const hit = { k: 'ret', len: ret.length, pc, head: ret.substring(0, 32), t: Date.now() };
            hits.push(hit);
            lastAb = ret;
          }
        }
        if (a0 && typeof a0 === 'object') {
          const L = a0.length;
          if (typeof L === 'number' && L >= 50 && L <= 200) {
            const sample = [];
            const m = L < 16 ? L : 16;
            for (let j = 0; j < m; j++) sample.push(a0[j]);
            hits.push({ k: 'arr', len: L, pc, sample, t: Date.now() });
          }
        }
        if (typeof a0 === 'string' && a0.indexOf('/api/pc/list/feed') >= 0) {
          hits.push({ k: 'url_in', pc, url: a0.substring(0, 120), t: Date.now() });
        }
      }
    } catch (e) {
      /* ignore */
    }
    return ret;
  };
  return { ctx, hits, getLastAb: () => lastAb };
}

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

async function main() {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  hardenAbogusShim(g);
  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  const { ctx, hits, getLastAb } = installVmHook(g);
  vm.runInContext(BDMS, ctx, { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(4000);

  const before = hits.length;
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : getLastAb();
  const raw = decodeAb(ab);

  const arrLens = {};
  const retLens = {};
  const pcs = { arr: {}, ret: {}, url_in: {} };
  for (const h of hits) {
    if (h.k === 'arr') {
      arrLens[h.len] = (arrLens[h.len] || 0) + 1;
      pcs.arr[h.pc] = (pcs.arr[h.pc] || 0) + 1;
    } else if (h.k === 'ret') {
      retLens[h.len] = (retLens[h.len] || 0) + 1;
      pcs.ret[h.pc] = (pcs.ret[h.pc] || 0) + 1;
    } else if (h.k === 'url_in') {
      pcs.url_in[h.pc] = (pcs.url_in[h.pc] || 0) + 1;
    }
  }

  const out = {
    side: 'node',
    ab_len: ab ? ab.length : 0,
    raw_len: raw ? raw.length : 0,
    ab_head: ab ? ab.slice(0, 48) : null,
    me23: g.bdms.init._v[2][23],
    hits_total: hits.length,
    hits_during_sign: hits.length - before,
    arr_len_hist: arrLens,
    ret_len_hist: retLens,
    pc_hist: pcs,
    hits_sample: hits.slice(0, 60),
    hits_sign_phase: hits.slice(before, before + 80),
  };
  fs.writeFileSync(path.join(HERE, 'probe_vm_encode_hook_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify({
    ab_len: out.ab_len,
    raw_len: out.raw_len,
    arr_len_hist: arrLens,
    ret_len_hist: retLens,
    pc_ret: pcs.ret,
    pc_arr_top: Object.entries(pcs.arr).sort((a, b) => b[1] - a[1]).slice(0, 10),
  }, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
