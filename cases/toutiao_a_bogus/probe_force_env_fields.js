// probe_force_env_fields.js — 向 shim 注入活体级 plugins/webgl/audio/fonts，观察签长是否从 168→180
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
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784617000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

/** 对齐活体 Chrome 插件表（MCP 实测 3 项） */
function installLivePlugins(g) {
  const mime0 = {
    type: 'application/pdf',
    suffixes: 'pdf',
    description: 'Portable Document Format',
    enabledPlugin: null,
  };
  const mime1 = {
    type: 'text/pdf',
    suffixes: 'pdf',
    description: 'Portable Document Format',
    enabledPlugin: null,
  };
  const plugins = [
    {
      name: 'Chrome PDF Plugin',
      filename: 'internal-pdf-viewer',
      description: 'Portable Document Format',
      length: 1,
      0: mime0,
      item(i) {
        return this[i] || null;
      },
      namedItem() {
        return null;
      },
    },
    {
      name: 'Chrome PDF Viewer',
      filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
      description: 'Portable Document Format',
      length: 1,
      0: mime0,
      item(i) {
        return this[i] || null;
      },
      namedItem() {
        return null;
      },
    },
    {
      name: 'Native Client',
      filename: 'internal-nacl-plugin',
      description: 'Native Client Executable',
      length: 2,
      0: mime0,
      1: mime1,
      item(i) {
        return this[i] || null;
      },
      namedItem() {
        return null;
      },
    },
  ];
  plugins.length = 3;
  plugins.item = function (i) {
    return this[i] || null;
  };
  plugins.namedItem = function (n) {
    return this[0] && this[0].name === n ? this[0] : null;
  };
  plugins.refresh = function () {};

  const mimeTypes = [mime0, mime1];
  mimeTypes.length = 2;
  mimeTypes.item = function (i) {
    return this[i] || null;
  };
  mimeTypes.namedItem = function (t) {
    return this.find((x) => x.type === t) || null;
  };
  mime0.enabledPlugin = plugins[0];
  mime1.enabledPlugin = plugins[0];

  try {
    Object.defineProperty(g.navigator, 'plugins', { configurable: true, get: () => plugins });
    Object.defineProperty(g.navigator, 'mimeTypes', { configurable: true, get: () => mimeTypes });
  } catch (e) {
    g.navigator.plugins = plugins;
    g.navigator.mimeTypes = mimeTypes;
  }
  return { plugins_n: plugins.length, mime_n: mimeTypes.length };
}

/** 补 fonts / chrome / speech 等常见指纹面 */
function installExtraSurfaces(g) {
  g.chrome = g.chrome || { runtime: {}, csi: () => ({}), loadTimes: () => ({}) };
  if (!g.navigator.languages || !g.navigator.languages.length) {
    g.navigator.languages = ['zh-CN', 'zh'];
  }
  try {
    Object.defineProperty(g.navigator, 'webdriver', { get: () => false, configurable: true });
  } catch (e) {
    /* ignore */
  }
  // document.fonts.check 常用
  if (!g.document.fonts) {
    g.document.fonts = {
      check: () => true,
      ready: Promise.resolve(),
      status: 'loaded',
      size: 0,
      forEach() {},
    };
  }
}

async function signOnce(label, opts = {}) {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  hardenAbogusShim(g);
  const plug = opts.livePlugins ? installLivePlugins(g) : null;
  if (opts.extra) installExtraSurfaces(g);

  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  await waitEnvReady(opts.waitMs != null ? opts.waitMs : 4500);

  // 签名前再确认 plugins 可读
  let pluginsLen = -1;
  try {
    pluginsLen = g.navigator.plugins.length;
  } catch (e) {
    pluginsLen = -2;
  }

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
    head: ab ? ab.slice(0, 48) : null,
    me23: g.bdms.init._v[2][23],
    pluginsLen,
    plug,
  };
}

async function main() {
  const cases = [
    { label: 'harden_only', opts: {} },
    { label: 'harden_live_plugins', opts: { livePlugins: true } },
    { label: 'harden_plugins_extra', opts: { livePlugins: true, extra: true } },
    { label: 'harden_plugins_wait8', opts: { livePlugins: true, extra: true, waitMs: 8000 } },
  ];
  const results = [];
  for (const c of cases) {
    console.error('[case]', c.label);
    // eslint-disable-next-line no-await-in-loop
    const r = await signOnce(c.label, c.opts);
    results.push(r);
    console.error('  ->', r.len, r.raw, 'plugins', r.pluginsLen);
  }
  const out = { ts: new Date().toISOString(), results };
  fs.writeFileSync(path.join(HERE, 'probe_force_env_fields_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
