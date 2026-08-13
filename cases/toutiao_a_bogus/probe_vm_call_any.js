// probe_vm_call_any.js — 不依赖 _u/_v：统计 Function.prototype.call，找 a_bogus 字符串回流
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
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784619000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

async function main() {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  hardenAbogusShim(g);
  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  const stats = { call_n: 0, ret_str: 0, ab_like: [], arr_lens: {}, u8_lens: {}, url_in: 0 };
  const ctx = vm.createContext(g);
  const FP = ctx.Function.prototype;
  const origCall = FP.call;
  FP.call = function (thisArg) {
    const n = arguments.length;
    const callArgs = new Array(n);
    callArgs[0] = thisArg;
    for (let i = 1; i < n; i++) callArgs[i] = arguments[i];
    const ret = Reflect.apply(origCall, this, callArgs);
    stats.call_n++;
    try {
      if (typeof ret === 'string') {
        stats.ret_str++;
        if (ret.length >= 150 && ret.length <= 200 && /^[A-Za-z0-9+/_=-]+$/.test(ret.substring(0, 8))) {
          const keys = this && typeof this === 'object' ? Object.keys(this).slice(0, 8) : [];
          stats.ab_like.push({
            len: ret.length,
            head: ret.substring(0, 40),
            thisKeys: keys,
            has_u: !!(this && this._u),
            has_v: !!(this && this._v),
            pc: this && this._v ? this._v[0] : null,
          });
        }
      }
      const a0 = n > 1 ? arguments[1] : null;
      if (a0 && typeof a0 === 'object' && typeof a0.length === 'number' && a0.length >= 50 && a0.length <= 200) {
        stats.arr_lens[a0.length] = (stats.arr_lens[a0.length] || 0) + 1;
      }
      if (typeof a0 === 'string' && a0.indexOf('/api/pc/list/feed') >= 0) stats.url_in++;
    } catch (e) {
      /* ignore */
    }
    return ret;
  };

  // Uint8Array 构造（编码缓冲）
  const OrigU8 = ctx.Uint8Array;
  ctx.Uint8Array = function (...args) {
    const a = args.length === 1 ? new OrigU8(args[0]) : new OrigU8(...args);
    if (a && a.length >= 50 && a.length <= 200) {
      stats.u8_lens[a.length] = (stats.u8_lens[a.length] || 0) + 1;
    }
    return a;
  };
  ctx.Uint8Array.prototype = OrigU8.prototype;
  Object.setPrototypeOf(ctx.Uint8Array, OrigU8);

  vm.runInContext(BDMS, ctx, { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(3500);

  const before = { ...stats, ab_like: stats.ab_like.length, arr_lens: { ...stats.arr_lens }, u8_lens: { ...stats.u8_lens } };
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;

  const out = {
    ab_len: ab ? ab.length : 0,
    ab_head: ab ? ab.slice(0, 48) : null,
    call_n: stats.call_n,
    ret_str: stats.ret_str,
    url_in: stats.url_in,
    ab_like: stats.ab_like.slice(0, 20),
    arr_lens: stats.arr_lens,
    u8_lens: stats.u8_lens,
    before_sign_call_n: before.call_n,
  };
  fs.writeFileSync(path.join(HERE, 'probe_vm_call_any_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
