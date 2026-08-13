// 抖音 webmssdk (byted_acrawler) 离线加载 + frontierSign 调用验证
// 目标：在 Node vm 中加载 webmssdk.es5.js（原始混淆样本），补最小浏览器垫片，
//       调用 window.byted_acrawler.frontierSign，验证 X-Bogus 可本地生成。
// 注意：X-Bogus 含 Math.random() 与 bogusIndex 状态，离线产出与 live 不逐字节一致（随机盐），
//       目标是「格式合法 + 算法结构一致」。

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const SAMPLE = path.join(__dirname, 'webmssdk.es5.js');
const src = fs.readFileSync(SAMPLE, 'utf8');

// ---- 最小浏览器垫片 ----
function makeWindowStub() {
  const store = {};
  const win = {
    navigator: {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      platform: 'Win32',
      language: 'zh-CN',
      languages: ['zh-CN', 'zh'],
      cookieEnabled: true,
      appVersion: '5.0 (Windows NT 10.0; Win64; x64)',
      vendor: 'Google Inc.',
      hardwareConcurrency: 8,
      deviceMemory: 8,
    },
    location: { href: 'https://www.douyin.com/', host: 'www.douyin.com', protocol: 'https:' },
    document: {
      referrer: '',
      cookie: '',
      createElement: () => ({ getContext: () => null, style: {} }),
      getElementById: () => null,
      addEventListener: () => {},
      documentElement: { style: {} },
    },
    screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040, colorDepth: 24, pixelDepth: 24 },
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    setTimeout: (fn) => { /* 不执行异步上报 */ return 0; },
    clearTimeout: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    __ac_referer: '',
  };
  win.window = win;
  win.self = win;
  win.top = win;
  win.locationbar = win.menubar = win.toolbar = { visible: true };
  win.history = { length: 1, pushState: () => {}, replaceState: () => {} };
  // crypto
  const cryptoObj = {
    getRandomValues: (arr) => { for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256); return arr; },
    subtle: {},
  };
  win.crypto = cryptoObj;
  win.WebSocket = function () {};
  win.XMLHttpRequest = function () { return { open() {}, send() {}, setRequestHeader() {}, addEventListener() {} }; };
  win.fetch = () => Promise.resolve({ ok: true, json: () => ({}) });
  win.PerformanceObserver = function () {};
  win.matchMedia = () => ({ matches: false, addListener() {}, addEventListener() {} });
  return win;
}

const win = makeWindowStub();
const ctx = {
  window: win,
  document: win.document,
  navigator: win.navigator,
  location: win.location,
  localStorage: win.localStorage,
  sessionStorage: win.sessionStorage,
  setTimeout: win.setTimeout,
  clearTimeout: win.clearTimeout,
  crypto: win.crypto,
  XMLHttpRequest: win.XMLHttpRequest,
  fetch: win.fetch,
  WebSocket: win.WebSocket,
  Math: Math,
  Date: Date,
  JSON: JSON,
  Object: Object,
  Array: Array,
  String: String,
  Number: Number,
  Boolean: Boolean,
  Uint8Array: Uint8Array,
  ArrayBuffer: ArrayBuffer,
  RegExp: RegExp,
  Error: Error,
  parseInt: parseInt,
  parseFloat: parseFloat,
  isNaN: isNaN,
  encodeURIComponent: encodeURIComponent,
  decodeURIComponent: decodeURIComponent,
  console: console,
  performance: { now: () => Date.now() },
};
ctx.self = ctx.window;
ctx.globalThis = ctx;

vm.createContext(ctx);

let ok = false, errMsg = null;
try {
  vm.runInContext(src, ctx, { filename: 'webmssdk.es5.js' });
  ok = true;
} catch (e) {
  errMsg = String(e && e.stack || e);
}

console.log('load_ok:', ok);
if (!ok) { console.log('load_err:\n' + errMsg); process.exit(1); }

// webmssdk 在 vm 沙箱里把 byted_acrawler 挂到了全局（ctx 顶层），而非 ctx.window
const ac = ctx.byted_acrawler || ctx.window.byted_acrawler;
if (!ac) { console.log('no byted_acrawler found'); process.exit(1); }

console.log('frontierSign_type:', typeof ac.frontierSign);
console.log('frontierSign_length(args):', ac.frontierSign ? ac.frontierSign.length : null);

// 调用 frontierSign（与 live 同形态：query, ua）
const ua = win.navigator.userAgent;
const q1 = 'aid=6383&device_platform=webapp&count=1';
const q2 = 'aid=6383&channel=channel_pc_web&count=10&device_id=123';

try {
  const r1 = ac.frontierSign(q1, ua);
  const r2 = ac.frontierSign(q2, ua);
  const r3 = ac.frontierSign(q1, 'FakeUA/1.0');
  console.log('q1_XBogus:', r1 && r1['X-Bogus']);
  console.log('q2_XBogus:', r2 && r2['X-Bogus']);
  console.log('q1_fakeUA_XBogus:', r3 && r3['X-Bogus']);
  const distinct = new Set([r1 && r1['X-Bogus'], r2 && r2['X-Bogus'], r3 && r3['X-Bogus']]).size;
  console.log('distinct:', distinct);
  console.log('len_q1:', r1 && r1['X-Bogus'] ? r1['X-Bogus'].length : null);
  console.log('OFFLINE_XBOGUS_OK:', !!r1 && !!r1['X-Bogus'] && r1['X-Bogus'].length === 16 && distinct >= 2);
} catch (e) {
  console.log('call_err:', String(e && e.stack || e));
  process.exit(1);
}
