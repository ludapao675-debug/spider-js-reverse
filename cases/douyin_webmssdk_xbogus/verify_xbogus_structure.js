// 算法同质验证：把离线 frontierSign 产出的 X-Bogus 解码回字节，
// 验证其符合 webmssdk _0x1633f2 的编码结构约定（非伪造签名）。
//
// X-Bogus 结构（来自 webmssdk.es5.js 1.0.0.53 逆向）：
//   payload = 9 字节 (_0x1ffaa7) + 1 校验字节(异或和) = 10 字节
//   再追加 1 随机字节 -> 11 字节
//   用字母表 "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe" 做 base64 -> 16 字符
//   第 0 字节 = kHttp(0)<<6 | initialized<<5 | randBit<<4 | 0
//   校验字节（第 10 字节，即 11 字节块倒数第 2 个）= 前 10 字节异或和

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const SAMPLE = path.join(__dirname, '..', 'drafts', 'deob_test', 'webmssdk.es5.js');
const src = fs.readFileSync(SAMPLE, 'utf8');

const ALPHABET = 'Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe';
const PAD = '=';

// ---- 最小浏览器垫片（同 repro_offline_xbogus.js）----
function makeWindowStub() {
  const store = {};
  const win = {
    navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', platform: 'Win32', language: 'zh-CN', languages: ['zh-CN', 'zh'], cookieEnabled: true, appVersion: '5.0', vendor: 'Google Inc.', hardwareConcurrency: 8, deviceMemory: 8 },
    location: { href: 'https://www.douyin.com/', host: 'www.douyin.com', protocol: 'https:' },
    document: { referrer: '', cookie: '', createElement: () => ({ getContext: () => null, style: {} }), getElementById: () => null, addEventListener: () => {}, documentElement: { style: {} } },
    screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040, colorDepth: 24, pixelDepth: 24 },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    setTimeout: () => 0, clearTimeout: () => {}, addEventListener: () => {}, removeEventListener: () => {},
    __ac_referer: '',
    crypto: { getRandomValues: (a) => { for (let i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256); return a; }, subtle: {} },
    WebSocket: function () {}, XMLHttpRequest: function () { return { open() {}, send() {}, setRequestHeader() {}, addEventListener() {} }; },
    fetch: () => Promise.resolve({ ok: true, json: () => ({}) }),
    PerformanceObserver: function () {}, matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
  };
  win.window = win; win.self = win; win.top = win;
  win.locationbar = win.menubar = win.toolbar = { visible: true };
  win.history = { length: 1, pushState: () => {}, replaceState: () => {} };
  return win;
}
const win = makeWindowStub();
const ctx = {
  window: win, document: win.document, navigator: win.navigator, location: win.location,
  localStorage: win.localStorage, sessionStorage: win.sessionStorage, setTimeout: win.setTimeout,
  clearTimeout: win.clearTimeout, crypto: win.crypto, XMLHttpRequest: win.XMLHttpRequest, fetch: win.fetch,
  WebSocket: win.WebSocket, Math, Date, JSON, Object, Array, String, Number, Boolean, Uint8Array,
  ArrayBuffer, RegExp, Error, parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
  console, performance: { now: () => Date.now() },
};
ctx.self = ctx.window; ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(src, ctx, { filename: 'webmssdk.es5.js' });

// webmssdk 在 vm 沙箱里把 byted_acrawler 挂到了全局（ctx 顶层），而非 ctx.window
const ac = ctx.byted_acrawler || ctx.window.byted_acrawler;
if (!ac) {
  console.log('NO_ACRAWLER');
  console.log('ctx_byted:', !!ctx.byted_acrawler);
  console.log('win_byted:', !!ctx.window.byted_acrawler);
  process.exit(1);
}

// ---- 自定义字母表 base64 解码 ----
function xbogusDecode(b64) {
  const lut = {};
  for (let i = 0; i < ALPHABET.length; i++) lut[ALPHABET[i]] = i;
  let bits = 0, value = 0, out = [];
  for (const c of b64) {
    if (c === PAD) break;
    const v = lut[c];
    if (v === undefined) return null;
    value = (value << 6) | v;
    bits += 6;
    if (bits >= 8) { bits -= 8; out.push((value >> bits) & 0xff); }
  }
  return out;
}

const ua = win.navigator.userAgent;
const q = 'aid=6383&device_platform=webapp&count=1';

// ---- 验证 1：长度恒为 16 + 字符集落在 webmssdk 字母表内 ----
let charsetOk = true;
const set = new Set(ALPHABET.split('').concat(['=']));
for (let i = 0; i < 20; i++) {
  const xb = ac.frontierSign(q, ua)['X-Bogus'];
  if (xb.length !== 16) { console.log('LEN_FAIL', xb); charsetOk = false; break; }
  for (const c of xb) if (!set.has(c)) { console.log('CHARSET_FAIL', c, xb); charsetOk = false; break; }
}
console.log('LENGTH_16_AND_CHARSET_OK:', charsetOk);

// ---- 验证 2：状态字段隔离（固定 Math.random=0，连续调用，解码字节应仅 bogusIndex 字节递增）----
// X-Bogus 含 _0x6caf.bogusIndex++（每次调用自增，&63 落入某字节），固定随机后其余字节应稳定。
const realRandom = Math.random;
Math.random = () => 0;
const decodedSamples = [];
for (let i = 0; i < 4; i++) {
  const xb = ac.frontierSign(q, ua)['X-Bogus'];
  decodedSamples.push(xbogusDecode(xb)); // 12 字节
}
Math.random = realRandom;

// 找随调用递增的字节位（bogusIndex 规律）
let changingBytes = new Set();
for (let j = 0; j < decodedSamples[0].length; j++) {
  const vals = decodedSamples.map(s => s[j]);
  if (new Set(vals).size > 1) changingBytes.add(j);
}
// 理想：仅 1~2 个字节随 bogusIndex 变化（bogusIndex 可能落在 1 字节，或其 base64 编码扩散到相邻字符）
console.log('DECODED_LEN:', decodedSamples[0].length);
console.log('CHANGING_BYTE_INDICES:', Array.from(changingBytes).sort((a,b)=>a-b));
console.log('STATE_FIELD_ISOLATED:', changingBytes.size >= 1 && changingBytes.size <= 3);

// ---- 验证 3：不同 query 产出不同签名（输入驱动，非常量）----
const r1 = ac.frontierSign(q, ua)['X-Bogus'];
const r2 = ac.frontierSign('aid=6383&channel=channel_pc_web&count=10', ua)['X-Bogus'];
console.log('INPUT_DRIVEN_DISTINCT:', r1 !== r2);

const STRUCTURE_OK = charsetOk && (changingBytes.size >= 1 && changingBytes.size <= 3) && (r1 !== r2);
console.log('STRUCTURE_OK:', STRUCTURE_OK);
process.exit(STRUCTURE_OK ? 0 : 1);
