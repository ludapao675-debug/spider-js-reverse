// probe_mssdk_trigger.js — 看 Node bdms.init 后会不会打 mssdk，以及走 XHR 还是 fetch
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');

const HERE = __dirname;
const bdmsSrc = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');

(async () => {
  const g = makeBrowserShim('https://www.toutiao.com/');
  hardenAbogusShim(g);
  g.window = g; g.self = g; g.top = g; g.parent = g;

  const opens = [];
  const fetches = [];

  // 包装前记录：makeBrowserShim 已 enableRealXhr；再包一层日志
  const XHR = g.XMLHttpRequest;
  const _open = XHR.prototype.open;
  XHR.prototype.open = function (method, url) {
    opens.push({ method, url: String(url).slice(0, 200), t: Date.now() });
    return _open.apply(this, arguments);
  };

  const _fetch = g.fetch;
  g.fetch = function (input, init) {
    const u = typeof input === 'string' ? input : (input && input.url) || String(input);
    fetches.push({ url: String(u).slice(0, 200), t: Date.now() });
    if (typeof _fetch === 'function') return _fetch.apply(this, arguments);
    return Promise.resolve({ ok: false, status: 0, text: async () => '', headers: { get: () => null } });
  };

  vm.runInContext(bdmsSrc, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });

  await waitEnvReady(5000);
  await new Promise((r) => setTimeout(r, 8000));

  const me = g.bdms.init._v[2][24];
  const out = {
    xhr_real: g.__xhr_real,
    mssdk_last: g.__mssdk_last || null,
    me24_len: me && me.inner ? String(me.inner).length : 0,
    opens: opens.filter((x) => /mssdk|web\/common|bytedance|msToken/i.test(x.url)),
    opens_all_sample: opens.slice(0, 30),
    opens_count: opens.length,
    fetches: fetches.slice(0, 20),
    fetch_count: fetches.length,
  };
  fs.writeFileSync(path.join(HERE, 'probe_mssdk_trigger_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
