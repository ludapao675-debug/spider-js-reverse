// probe_xmst_seed_sign.js — localStorage.xmst 种子 → 签名 → 是否带 msToken
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const https = require('https');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');

const HERE = __dirname;
const CACHE = path.join(HERE, 'mstoken_cache.json');

function httpGet(url) {
  return new Promise((resolve) => {
    https.get(url, {
      headers: {
        accept: 'application/json, text/plain, */*',
        referer: 'https://www.toutiao.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
      },
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        let j = {};
        try { j = JSON.parse(body || '{}'); } catch (e) { /* ignore */ }
        resolve({
          status: res.statusCode,
          body_len: body.length,
          message: j.message,
          n: Array.isArray(j.data) ? j.data.length : 0,
        });
      });
    }).on('error', (e) => resolve({ err: String(e.message || e) }));
  });
}

(async () => {
  // 优先用缓存；否则用活体 dump 的 xmst 样例（仅探针）
  let seed = null;
  if (fs.existsSync(CACHE)) {
    seed = JSON.parse(fs.readFileSync(CACHE, 'utf8')).msToken;
  }
  if (!seed) {
    seed = 'mnUc8u4wIzJYjIxg0UNqZHPtdTc8e-XehQrcV3BELmftLbD2AfQt9MkK1Y3g3CfBQEHwCc9IDxYt22BM';
  }

  const g = makeBrowserShim('https://www.toutiao.com/');
  hardenAbogusShim(g);
  g.window = g; g.self = g; g.top = g; g.parent = g;
  g.localStorage.setItem('xmst', seed);

  const ctx = vm.createContext(g);
  vm.runInContext(fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8'), ctx, {
    timeout: 90000,
    filename: 'bdms.js',
  });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(500);

  const me = g.bdms.init._v[2][24];
  const meInner = me && me.inner ? String(me.inner) : null;

  const url = `https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=${Math.floor(Date.now() / 1000)}&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web`;
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', url);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || url;
  const ab = ((signed.match(/[?&]a_bogus=([^&]+)/) || [])[1] || '');
  const ms = ((signed.match(/[?&]msToken=([^&]+)/) || [])[1] || '');
  const abDec = ab ? decodeURIComponent(ab) : null;
  const msDec = ms ? decodeURIComponent(ms) : null;

  const http = msDec && abDec ? await httpGet(signed) : { skipped: true };

  const out = {
    seed_len: seed.length,
    me24_len: meInner ? meInner.length : 0,
    me_eq_seed: meInner === seed,
    ab_len: abDec ? abDec.length : 0,
    ms_len: msDec ? msDec.length : 0,
    ms_eq_seed: msDec === seed,
    http,
    signed_head: signed.slice(0, 160),
  };
  fs.writeFileSync(path.join(HERE, 'probe_xmst_seed_sign_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
  process.exit(out.http && out.http.message === 'success' && out.http.n > 0 ? 0 : 2);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
