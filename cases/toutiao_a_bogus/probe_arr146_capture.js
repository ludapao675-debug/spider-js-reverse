// probe_arr146_capture.js — 捕获 Function.call 中 length=146 的数组内容，对照最终 a_bogus
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
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784620000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

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

  const captured = [];
  const abRets = [];
  const ctx = vm.createContext(g);
  const FP = ctx.Function.prototype;
  const origCall = FP.call;
  FP.call = function (thisArg) {
    const n = arguments.length;
    const callArgs = new Array(n);
    callArgs[0] = thisArg;
    for (let i = 1; i < n; i++) callArgs[i] = arguments[i];
    const ret = Reflect.apply(origCall, this, callArgs);
    try {
      const a0 = n > 1 ? arguments[1] : null;
      if (a0 && typeof a0 === 'object' && a0.length === 146) {
        const bytes = [];
        for (let j = 0; j < 146; j++) bytes.push(a0[j] & 0xff);
        captured.push({
          t: Date.now(),
          bytes,
          hex_head: Buffer.from(bytes.slice(0, 32)).toString('hex'),
          hex_tail: Buffer.from(bytes.slice(-32)).toString('hex'),
        });
      }
      if (typeof ret === 'string' && ret.length >= 160 && ret.length <= 200) {
        if (/^[A-Za-z0-9+/_=-]+$/.test(ret.substring(0, 8))) {
          abRets.push({ len: ret.length, s: ret });
        }
      }
    } catch (e) {
      /* ignore */
    }
    return ret;
  };

  vm.runInContext(BDMS, ctx, { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(3500);

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);

  // 对比：146 数组是否等于 raw 的某种扩展，或能否 base64 出 abRets
  const comparisons = captured.map((c, idx) => {
    const buf = Buffer.from(c.bytes);
    let b64 = buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return {
      idx,
      arr146_b64_len: b64.length,
      arr146_b64_head: b64.slice(0, 40),
      equals_final_raw_prefix: raw ? buf.slice(0, raw.length).equals(raw) : false,
      raw_len: raw ? raw.length : 0,
      // LCS-ish：前缀重合
      prefix_match_n: raw
        ? (() => {
            let n = 0;
            while (n < raw.length && n < buf.length && raw[n] === buf[n]) n++;
            return n;
          })()
        : 0,
    };
  });

  const out = {
    ab_len: ab ? ab.length : 0,
    raw_len: raw ? raw.length : 0,
    ab,
    raw_hex: raw ? raw.toString('hex') : null,
    ab_rets: abRets,
    captured_n: captured.length,
    captured: captured.map((c) => ({
      hex_head: c.hex_head,
      hex_tail: c.hex_tail,
      bytes_len: c.bytes.length,
      // 全量 bytes 太大也落盘一份
      bytes: c.bytes,
    })),
    comparisons,
  };
  fs.writeFileSync(path.join(HERE, 'probe_arr146_capture_out.json'), JSON.stringify(out, null, 2));
  console.log(
    JSON.stringify(
      {
        ab_len: out.ab_len,
        raw_len: out.raw_len,
        ab_rets: abRets.map((x) => x.len),
        captured_n: captured.length,
        comparisons,
      },
      null,
      2,
    ),
  );
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
