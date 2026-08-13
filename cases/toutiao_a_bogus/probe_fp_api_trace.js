// probe_fp_api_trace.js — 签名瞬间追踪指纹 API 访问，对照长/短签原料差
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
  process.argv[2] ||
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784616000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

function installApiTrace(g, log) {
  const push = (tag, detail) => {
    log.push({ t: Date.now(), tag, detail: detail == null ? null : String(detail).slice(0, 200) });
  };

  // navigator 关键属性
  const navKeys = [
    'userAgent',
    'platform',
    'language',
    'languages',
    'hardwareConcurrency',
    'deviceMemory',
    'maxTouchPoints',
    'vendor',
    'webdriver',
    'plugins',
    'mimeTypes',
    'connection',
  ];
  if (g.navigator) {
    for (const k of navKeys) {
      try {
        let cur = g.navigator[k];
        Object.defineProperty(g.navigator, k, {
          configurable: true,
          enumerable: true,
          get() {
            push('nav.' + k, typeof cur === 'object' && cur && cur.length != null ? 'len=' + cur.length : cur);
            return cur;
          },
          set(v) {
            cur = v;
          },
        });
      } catch (e) {
        /* ignore */
      }
    }
  }

  // screen
  if (g.screen) {
    for (const k of ['width', 'height', 'availWidth', 'availHeight', 'colorDepth', 'pixelDepth']) {
      try {
        let cur = g.screen[k];
        Object.defineProperty(g.screen, k, {
          configurable: true,
          enumerable: true,
          get() {
            push('screen.' + k, cur);
            return cur;
          },
          set(v) {
            cur = v;
          },
        });
      } catch (e) {
        /* ignore */
      }
    }
  }

  // canvas / webgl
  const _create = g.document.createElement.bind(g.document);
  g.document.createElement = function (tag) {
    const el = _create(tag);
    if (String(tag).toLowerCase() !== 'canvas') return el;
    push('createElement', 'canvas');
    const _gc = el.getContext.bind(el);
    el.getContext = function (type) {
      push('canvas.getContext', type);
      const ctx = _gc(type);
      if (!ctx) return ctx;
      if (String(type).indexOf('webgl') >= 0) {
        const wrap = (name) => {
          if (typeof ctx[name] !== 'function') return;
          const orig = ctx[name].bind(ctx);
          ctx[name] = function () {
            const args = Array.prototype.slice.call(arguments, 0, 3);
            push('webgl.' + name, JSON.stringify(args).slice(0, 120));
            return orig.apply(this, arguments);
          };
        };
        [
          'getParameter',
          'getExtension',
          'getSupportedExtensions',
          'getShaderPrecisionFormat',
          'readPixels',
          'getContextAttributes',
        ].forEach(wrap);
      }
      if (String(type) === '2d') {
        ['getImageData', 'fillText', 'fillRect', 'measureText'].forEach((name) => {
          if (typeof ctx[name] !== 'function') return;
          const orig = ctx[name].bind(ctx);
          ctx[name] = function () {
            push('2d.' + name, '');
            return orig.apply(this, arguments);
          };
        });
      }
      return ctx;
    };
    const _td = el.toDataURL.bind(el);
    el.toDataURL = function () {
      push('canvas.toDataURL', '');
      return _td.apply(this, arguments);
    };
    return el;
  };

  // audio
  const _OAC = g.OfflineAudioContext;
  g.OfflineAudioContext = function (...args) {
    push('OfflineAudioContext', JSON.stringify(args));
    return new _OAC(...args);
  };
  g.webkitOfflineAudioContext = g.OfflineAudioContext;

  // plugins enumeration via length
  try {
    if (g.navigator && g.navigator.plugins) {
      const p = g.navigator.plugins;
      const desc = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(p), 'length') || {};
      // 已在 nav.plugins getter 记录
    }
  } catch (e) {
    /* ignore */
  }
}

async function main() {
  const log = [];
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  hardenAbogusShim(g);
  installApiTrace(g, log);

  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(4000);

  const before = log.length;
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);

  // 聚合
  const counts = {};
  for (const row of log) {
    counts[row.tag] = (counts[row.tag] || 0) + 1;
  }

  const out = {
    ab_len: ab ? ab.length : 0,
    raw_len: raw ? raw.length : 0,
    ab_head: ab ? ab.slice(0, 64) : null,
    me23: g.bdms.init._v[2][23],
    log_total: log.length,
    log_during_sign: log.length - before,
    counts,
    log_sample: log.slice(0, 80),
    log_sign_phase: log.slice(before, before + 100),
    raw_hex_head: raw ? raw.slice(0, 48).toString('hex') : null,
  };
  fs.writeFileSync(path.join(HERE, 'probe_fp_api_trace_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify({ ab_len: out.ab_len, raw_len: out.raw_len, me23: out.me23, counts: out.counts }, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
