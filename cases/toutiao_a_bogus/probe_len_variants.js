// probe_len_variants.js — 探测何种 init/环境配置能让离线 a_bogus 达到 176
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784599930&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function loadEnvOverride() {
  try {
    return JSON.parse(fs.readFileSync(path.join(HERE, 'browser_fingerprint.json'), 'utf8')).env_override || null;
  } catch (e) {
    return null;
  }
}

function patchInitEnv(g) {
  const snapPath = path.join(HERE, 'browser_env_snapshot.json');
  if (!fs.existsSync(snapPath)) return 0;
  const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;
  let patched = 0;
  for (let i = 0; i < initMeSrc.length; i++) {
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
    } else if (typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') {
      initMe[i] = v;
    } else continue;
    patched++;
  }
  return patched;
}

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

/** 单次干净签名（独立 shim + bdms） */
function signOnce(label, initCfg, opts = {}) {
  const g = makeBrowserShim('https://www.toutiao.com/', opts.env === false ? null : loadEnvOverride());
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  // 可选：补更多 navigator / canvas 桩，观察长度变化
  if (opts.enrichEnv) {
    try {
      Object.defineProperty(g.navigator, 'webdriver', { get: () => false, configurable: true });
      g.navigator.plugins = { length: 5, 0: {}, 1: {}, 2: {}, 3: {}, 4: {} };
      g.navigator.mimeTypes = { length: 2 };
      g.chrome = { runtime: {} };
      g.OfflineAudioContext = function OfflineAudioContext() {};
      g.webkitOfflineAudioContext = g.OfflineAudioContext;
      // 简易 canvas 指纹
      const proto = g.HTMLCanvasElement && g.HTMLCanvasElement.prototype;
      if (proto && !proto.__ab_patched) {
        const _getContext = proto.getContext;
        proto.getContext = function getContext(type) {
          const ctx = _getContext ? _getContext.call(this, type) : null;
          if (ctx && type === '2d' && !ctx.__ab) {
            ctx.__ab = true;
            const _getImageData = ctx.getImageData;
            ctx.getImageData = function () {
              if (_getImageData) return _getImageData.apply(this, arguments);
              return { data: new Uint8ClampedArray(16) };
            };
            ctx.fillText = function () {};
            ctx.fillRect = function () {};
            ctx.fillStyle = '#000';
          }
          return ctx || {
            fillText() {},
            fillRect() {},
            getImageData() {
              return { data: new Uint8ClampedArray(16) };
            },
            canvas: this,
          };
        };
        proto.toDataURL = function () {
          return 'data:image/png;base64,iVBORw0KGgo=';
        };
        proto.__ab_patched = true;
      }
    } catch (e) {
      /* ignore */
    }
  }

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 60000, filename: 'bdms.js' });
  g.bdms.init(initCfg);
  const patched = opts.skipPatch ? 0 : patchInitEnv(g);

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);
  const row = {
    label,
    len: ab ? ab.length : 0,
    raw: raw ? raw.length : 0,
    head: ab ? ab.slice(0, 40) : null,
    anchor5f5: !!(ab && ab.includes('5f5LfY3qV')),
    patched,
  };
  console.log(JSON.stringify(row));
  return row;
}

const variants = [
  [
    'current_full',
    {
      aid: 24,
      pageId: 6457,
      boe: false,
      ddrt: 3,
      paths: { include: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
      track: {},
      dump: true,
      rpU: '',
    },
  ],
  [
    'html_exact_paths_array',
    {
      aid: 24,
      pageId: 6457,
      paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'],
    },
  ],
  [
    'html_plus_ddrt',
    {
      aid: 24,
      pageId: 6457,
      ddrt: 3,
      paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'],
    },
  ],
  [
    'paths_include_obj',
    {
      aid: 24,
      pageId: 6457,
      paths: { include: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    },
  ],
  [
    'no_patch_html',
    { aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    { skipPatch: true },
  ],
  [
    'enrich_env_html',
    { aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    { enrichEnv: true },
  ],
  [
    'no_env_override',
    { aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    { env: false },
  ],
];

const results = [];
for (const [label, cfg, opts] of variants) {
  try {
    results.push(signOnce(label, cfg, opts || {}));
  } catch (e) {
    console.log(JSON.stringify({ label, err: String(e && e.message ? e.message : e) }));
  }
}

fs.writeFileSync(path.join(HERE, 'probe_len_variants_out.json'), JSON.stringify(results, null, 2));
console.log('[probe] wrote probe_len_variants_out.json');
process.exit(0);
