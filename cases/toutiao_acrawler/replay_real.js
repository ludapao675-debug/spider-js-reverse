// replay_real.js — 路径 B：在 Node 直接运行真实 acrawler VM（活对象堆 + 原生 env）
// 用较完整的浏览器垫片提供 window/navigator/document/canvas/webgl/audio 等，
// 调用 byted_acrawler.sign({url}) 纯离线复现 _signature。
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const HERE = __dirname;
const RAW = path.join(HERE, 'raw', 'acrawler.js');

// P3.4 --env-override：接受 JSON 文件路径，覆盖 vm 沙箱中 navigator/window 等字段（如 {"navigator.webdriver":true}）
const _eoIdx = process.argv.indexOf('--env-override');
const ENV_OVERRIDE = _eoIdx >= 0 ? JSON.parse(fs.readFileSync(process.argv[_eoIdx + 1], 'utf-8')) : null;
// 从非标志参数中取 URL 和 TIMEOUT（排除 --env-override 及其值）
const _positional = process.argv.slice(2).filter((a, i, arr) => {
  if (a === '--env-override') return false;
  if (arr[i - 1] === '--env-override') return false;
  return true;
});
const TARGET_URL = _positional[0] || 'https://www.toutiao.com/?wid=1783780226601';
const TIMEOUT = parseInt(_positional[1] || '90000', 10);

// ---------- 浏览器垫片 ----------
function makeShim() {
  const g = {};
  // canvas 2d 上下文（确定性指纹）
  function fakeCtx2d() {
    return {
      fillStyle: '', strokeStyle: '', font: '', textBaseline: '',
      fillRect() {}, strokeRect() {}, beginPath() {}, moveTo() {}, lineTo() {},
      bezierCurveTo() {}, quadraticCurveTo() {}, arc() {}, closePath() {},
      fill() {}, stroke() {}, save() {}, restore() {}, translate() {}, rotate() {}, scale() {},
      drawImage() {}, putImageData() {}, setTransform() {}, resetTransform() {},
      clip() {}, arcTo() {}, rect() {},
      createLinearGradient() { return { addColorStop() {} }; },
      createRadialGradient() { return { addColorStop() {} }; },
      createPattern() { return {}; },
      getLineDash() { return []; }, setLineDash() {},
      measureText() { return { width: 10 }; },
      fillText() {}, strokeText() {},
      getImageData(x, y, w, h) {
        const W = w | 0, H = h | 0;
        const n = W * H * 4;
        const data = new Uint8ClampedArray(n);
        // 模拟真实 canvas 渲染读回：低频结构(图形/文字) + 高频噪声，打破周期性。
        // 旧实现 data[i]=(i*31+17)&0xff 是完美锯齿波，最易被 acrawler 环境
        // 完整性检测判为伪造 canvas → 降级分支(短签名)。
        for (let yy = 0; yy < H; yy++) {
          for (let xx = 0; xx < W; xx++) {
            const base = 128 + Math.sin(xx * 0.15 + yy * 0.07) * 60
                         + Math.cos((xx + yy) * 0.05) * 30;
            const noise = (((xx * 73856093) ^ (yy * 19349663)) & 0xff) * 0.3;
            const v = base + noise;
            const o = (yy * W + xx) * 4;
            data[o] = v & 0xff;
            data[o + 1] = (v * 1.1) & 0xff;
            data[o + 2] = (v * 0.9) & 0xff;
            data[o + 3] = 255;
          }
        }
        return { data, width: W, height: H };
      },
      toDataURL() { return 'data:image/png;base64,' + 'A'.repeat(6000); },
    };
  }
  // webgl 上下文
  function fakeGl() {
    const dbgExt = { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 };
    return new Proxy({}, {
      get(t, p) {
        if (p === 'readPixels') return (x, y, w, h, fmt, typ, buf) => {
          // 模拟 WebGL 渲染读回的真实像素：非零 + 伪随机，否则检测判为伪造 → 降级分支
          if (buf && buf.length) for (let i = 0; i < buf.length; i++) buf[i] = ((i * 2654435761) >>> 0) & 0xff;
          return buf;
        };
        if (p === 'getParameter') return (k) => {
          // 字符串型枚举必须返回字符串，否则 VM 后续 .indexOf 抛错进入异常分支
          // 以下值来自 MCP 真机采集（mcp_golden_evidence.json.real_env_fingerprint.webgl）
          if (k === 37445) return 'Google Inc. (Microsoft)';                    // UNMASKED_VENDOR_WEBGL
          if (k === 37446) return 'ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)'; // UNMASKED_RENDERER_WEBGL
          if (k === 7938) return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';          // GL_VERSION
          if (k === 7936) return 'WebKit';                                      // GL_VENDOR
          if (k === 7937) return 'WebKit WebGL';                                // GL_RENDERER
          if (k === 35724) return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)'; // GL_SHADING_LANGUAGE_VERSION
          if (k === 7939) return 'WebGL 1.0';
          return 16384; // 数值型枚举返回合理数值
        };
        if (p === 'getExtension') return (name) => (name === 'WEBGL_debug_renderer_info' ? dbgExt : {});
        if (p === 'getShaderPrecisionFormat') return () => ({ precision: 23, rangeMin: 127, rangeMax: 127 });
        if (p === 'getSupportedExtensions') return () => ['WEBGL_debug_renderer_info'];
        if (p === 'createBuffer' || p === 'createTexture' || p === 'createFramebuffer' || p === 'createRenderbuffer' || p === 'createProgram' || p === 'createShader') return () => ({});
        if (p === 'getAttribLocation') return () => 0;
        if (p === 'getUniformLocation') return () => ({});
        if (typeof p === 'string' && p.startsWith('create')) return () => ({});
        return () => 0;
      },
    });
  }
  function makeCanvas() {
    return {
      width: 300, height: 150, style: {},
      getContext(type) { return type === '2d' ? fakeCtx2d() : fakeGl(); },
      // toDataURL 返回真实长度的伪 PNG(base64)，避免长度异常被检测判为伪造
      toDataURL() { return 'data:image/png;base64,' + 'A'.repeat(6000); },
      addEventListener() {}, getBoundingClientRect() { return { width: 300, height: 150, top: 0, left: 0 }; },
    };
  }
  // 真实 Chrome(Windows)的典型插件/mimeTypes 列表，长度>0 是关键反爬判定点
  const mimeTypes = (() => {
    const list = [
      { type: 'application/pdf', description: '', suffixes: 'pdf', enabledPlugin: null },
      { type: 'application/x-google-chrome-pdf', description: 'Portable Document Format', suffixes: 'pdf', enabledPlugin: null },
      { type: 'application/x-nacl', description: '', suffixes: '', enabledPlugin: null },
      { type: 'application/x-pnacl', description: '', suffixes: '', enabledPlugin: null },
    ];
    const o = { length: list.length, item(i) { return list[i] || null; }, namedItem(n) { return list.find(m => m.type === n) || null; }, refresh() {} };
    list.forEach(m => { o[m.type] = m; });
    return o;
  })();
  const plugins = (() => {
    const pdf = { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1, item(i) { return mimeTypes[i]; }, namedItem(n) { return mimeTypes.namedItem(n); } };
    const pdfViewer = { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojklgdbeil7djg', description: '', length: 1, item() { return null; }, namedItem() { return null; } };
    const nacl = { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2, item(i) { return mimeTypes[i + 2]; }, namedItem(n) { return mimeTypes.namedItem(n); } };
    const list = [pdf, pdfViewer, nacl];
    const o = { length: list.length, item(i) { return list[i] || null; }, namedItem(n) { return list.find(p => p.name === n) || null; }, refresh() {} };
    list.forEach(p => { o[p.name] = p; });
    return o;
  })();
  // navigator 值来自 MCP 真机采集（mcp_golden_evidence.json.real_env_fingerprint）
  const nav = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    platform: 'Win32', language: 'zh-CN', languages: ['zh-CN', 'zh'],
    hardwareConcurrency: 16, deviceMemory: 16, vendor: 'Google Inc.', product: 'Gecko',
    appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', cookieEnabled: true, onLine: true,
    webdriver: false, maxTouchPoints: 0, productSub: '20030107', vendorSub: '',
    doNotTrack: null, pdfViewerEnabled: true,
    plugins, mimeTypes,
    // 真实 Chrome 特有但常被检测字段
    connection: { onchange: null, effectiveType: '4g', type: 'wifi', addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; } },
    mediaDevices: { ondevicechange: null, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; }, enumerateDevices() { return Promise.resolve([]); } },
    permissions: { query() { return Promise.resolve({ state: 'granted', onchange: null }); } },
    clipboard: { writeText() { return Promise.resolve(); }, readText() { return Promise.resolve(''); }, addEventListener() {}, removeEventListener() {} },
    credentials: { get() { return Promise.resolve(null); }, store() { return Promise.resolve(); }, preventSilentAccess() { return Promise.resolve(); }, create() { return Promise.resolve(null); } },
    storage: { estimate() { return Promise.resolve({ usage: 0, quota: 0 }); } },
    keyboard: { addEventListener() {}, removeEventListener() {}, lock() { return Promise.resolve(); }, unlock() {} },
    mediaSession: { metadata: null, playbackState: 'none', setActionHandler() {} },
    oscpu: 'Windows NT 10.0; Win64; x64',
    userActivation: { hasBeenActive: true, isActive: false },
    taintEnabled() { return false; },
    registerProtocolHandler() {}, unregisterProtocolHandler() {},
    requestMIDIAccess() { return Promise.resolve({ inputs: [], outputs: [], sysexEnabled: false }); },
    javaEnabled() { return false; }, sendBeacon() { return true; },
    getBattery() { return Promise.resolve({ charging: true, level: 1, chargingTime: 0, dischargingTime: Infinity, onchargingchange: null }); },
  };
  const loc = { href: TARGET_URL, origin: new URL(TARGET_URL).origin, hostname: new URL(TARGET_URL).hostname, protocol: 'https:', pathname: new URL(TARGET_URL).pathname, search: new URL(TARGET_URL).search, hash: '', assign() {}, replace() {}, reload() {} };
  const doc = {
    cookie: '', title: '今日头条', referrer: '', domain: 'toutiao.com',
    documentMode: undefined, hidden: false, visibilityState: 'visible',
    location: loc, plugins, mimeTypes,
    defaultView: g, readyState: 'complete', charset: 'UTF-8', characterSet: 'UTF-8',
    compatMode: 'CSS1Compat', contentType: 'text/html',
    createElement(tag) { return tag === 'canvas' ? makeCanvas() : { style: {}, appendChild() {}, addEventListener() {}, getContext: () => null, width: 0, height: 0, setAttribute() {}, getAttribute() { return null; }, remove() {} }; },
    createElementNS(ns, tag) { return this.createElement(tag); },
    getElementById() { return null; }, querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {}, getElementsByTagName() { return []; }, getElementsByClassName() { return []; },
    getElementsByName() { return []; },
    body: { appendChild() {}, style: {}, removeChild() {}, insertBefore() {}, scrollHeight: 1080, scrollWidth: 1920, clientHeight: 1080, clientWidth: 1920, ownerDocument: null },
    head: { appendChild() {}, style: {}, removeChild() {} },
    documentElement: { appendChild() {}, style: {}, contains() { return false; }, getAttribute() { return null; }, setAttribute() {}, removeAttribute() {}, scrollHeight: 1080, scrollWidth: 1920, clientHeight: 1080, clientWidth: 1920, ownerDocument: null, nodeType: 1 },
    createTextNode() { return { nodeType: 3, textContent: '' }; }, createComment() { return { nodeType: 8 }; },
    createDocumentFragment() { return { appendChild() {} }; },
    execCommand() { return false; }, hasFocus() { return false; },
    activeElement: null, styleSheets: [], forms: [], links: [], images: [], scripts: [], anchors: [],
    adoptNode() {}, importNode() { return {}; }, normalize() {}, open() {}, close() {}, write() {}, writeln() {},
    elementFromPoint() { return null; }, elementsFromPoint() { return []; },
    caretRangeFromPoint() { return null; }, caretPositionFromPoint() { return null; },
    getSelection() { return { type: 'None', toString() { return ''; } }; },
    currentScript: null, rootElement() { return doc.documentElement; },
    fullscreenElement: null, pointerLockElement: null,
  };
  // screen 值来自 MCP 真机采集（mcp_golden_evidence.json.real_env_fingerprint.screen）
  const screen = { width: 4000, height: 2500, availWidth: 3200, availHeight: 1910, colorDepth: 24, pixelDepth: 24, orientation: { type: 'landscape-primary' } };
  const history = { length: 1, pushState() {}, replaceState() {}, go() {}, back() {}, forward() {} };
  const storage = (() => { const m = {}; return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: (k) => { delete m[k]; }, clear() { for (const k in m) delete m[k]; }, key: (i) => Object.keys(m)[i] || null, get length() { return Object.keys(m).length; } }; })();

  g.window = g;
  g.self = g;
  g.globalThis = g;
  g.navigator = nav;
  g.document = doc;
  g.location = loc;
  g.history = history;
  g.screen = screen;
  g.localStorage = storage;
  g.sessionStorage = storage;
  g.devicePixelRatio = 0.800000011920929; // MCP 真机采集值
  g.innerWidth = 1920; g.innerHeight = 1080; g.outerWidth = 1920; g.outerHeight = 1040;
  g.pageXOffset = 0; g.pageYOffset = 0; g.scrollX = 0; g.scrollY = 0;
  g.clientWidth = 1920; g.clientHeight = 1080;
  // P3.4 环境覆盖（最小侵入：--env-override JSON 唯一副作用入口）
  if (ENV_OVERRIDE) {
    const apply = (obj, key, val) => { const parts = key.split('.'); const last = parts.pop(); let t = obj; for (const p of parts) { if (!t[p]) { if (parts.indexOf(p) === 0) { t[p] = {}; } else { t[p] = {}; } } t = t[p]; } t[last] = val; };
    for (const k of Object.keys(ENV_OVERRIDE)) {
      if (k.startsWith('navigator.')) apply(g.navigator, k.slice('navigator.'.length), ENV_OVERRIDE[k]);
      else if (k.startsWith('document.')) apply(g.document, k.slice('document.'.length), ENV_OVERRIDE[k]);
      else if (k.startsWith('screen.')) apply(g.screen, k.slice('screen.'.length), ENV_OVERRIDE[k]);
      else if (k.startsWith('location.')) apply(g.location, k.slice('location.'.length), ENV_OVERRIDE[k]);
      else g[k] = ENV_OVERRIDE[k];
    }
  }
  g.addEventListener = () => {}; g.removeEventListener = () => {};
  g.dispatchEvent = () => true; g.open = () => {}; g.close = () => {};
  g.HTMLElement = function () {}; g.Element = function () {}; g.Node = function () {};
  g.Image = function () { return makeCanvas(); };
  g.PluginArray = function () {}; g.MimeTypeArray = function () {};
  g.DOMException = DOMException;
  // ---- Chrome 专属全局（反爬判定是否为真实 Chrome 的关键）----
  nav.appName = 'Netscape';
  nav.appCodeName = 'Mozilla';
  // Chrome 新反爬核心：User-Agent Client Hints
  nav.userAgentData = {
    brands: [{ brand: 'Google Chrome', version: '131' }, { brand: 'Chromium', version: '131' }, { brand: 'Not_A Brand', version: '24' }],
    mobile: false, platform: 'Windows',
    getHighEntropyValues: () => Promise.resolve({ architecture: 'x86', bitness: '64', model: '', platformVersion: '10.0.0', uaFullVersion: '131.0.0.0', wow64: false }),
  };
  nav.gpu = { getPreferredCanvasFormat: () => 'rgba8unorm' };
  nav.locks = { request() {}, query() { return Promise.resolve([]); } };
  nav.wakeLock = { request() { return Promise.resolve({ type: 'screen', released: false }); } };
  g.clientInformation = nav;
  g.chrome = {
    app: { isInstalled: false, getDetails() { return {}; }, getIsInstalled() { return false; } },
    runtime: {
      id: undefined, lastError: undefined, OnInstalledReason: {}, OnRestartRequiredReason: {},
      PlatformArch: {}, PlatformNaclArch: {}, PlatformOs: { MAC: 'mac', WIN: 'win', LINUX: 'linux', CROS: 'cros', OPENBSD: 'openbsd' },
      RequestUpdateCheckStatus: {}, connect() { return { postMessage() {}, onMessage: {}, disconnect() {} }; },
      connectNative() { return { postMessage() {}, onMessage: {}, disconnect() {} }; },
      sendMessage() {}, getManifest() { return {}; }, getURL() { return ''; }, reload() {}, restart() {}, setUninstallURL() {},
    },
    loadTimes() {}, csi() {}, webstore: {},
  };
  g.external = { AddSearchProvider() {}, IsSearchProviderInstalled() { return 0; }, StartSearch() {} };
  g.crypto = {
    subtle: { digest: () => Promise.resolve(new Uint8Array(32)), importKey: () => Promise.resolve({}), sign: () => Promise.resolve(new Uint8Array(0)), verify: () => Promise.resolve(false), deriveKey: () => Promise.resolve({}), encrypt: () => Promise.resolve(new Uint8Array(0)), decrypt: () => Promise.resolve(new Uint8Array(0)) },
    getRandomValues(a) { return a; },
  };
  // performance.memory 见下方 g.performance 定义
  // 事件构造器（部分检测会 typeof 这些构造器）
  g.Event = (typeof Event !== 'undefined') ? Event : function () {};
  g.MouseEvent = (typeof MouseEvent !== 'undefined') ? MouseEvent : function () {};
  g.KeyboardEvent = (typeof KeyboardEvent !== 'undefined') ? KeyboardEvent : function () {};
  g.UIEvent = (typeof UIEvent !== 'undefined') ? UIEvent : function () {};
  g.CustomEvent = (typeof CustomEvent !== 'undefined') ? CustomEvent : function () {};
  g.PointerEvent = (typeof PointerEvent !== 'undefined') ? PointerEvent : function () {};
  g.SVGElement = function () {};
  g.trustedTypes = {
    createPolicy() { return { createHTML: (s) => s, createScript: (s) => s, createScriptURL: (s) => s }; },
    getAttributeType() { return null; }, getPropertyType() { return null; }, emptyScript: '',
  };
  g.featurePolicy = { allowedFeatures() { return []; }, allowsFeature() { return false; }, getAllowlistForFeature() { return []; } };
  g.speechSynthesis = { addEventListener() {}, removeEventListener() {}, getVoices() { return []; }, speak() {}, cancel() {}, pause() {}, resume() {} };
  g.visualViewport = { width: 1920, height: 980, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1 };
  g.indexedDB = { open: () => ({ onupgradeneeded: null, onsuccess: null, onerror: null }), deleteDatabase() {} };
  g.WebSocket = function () {}; g.Request = function () {}; g.Headers = function () {};
  g.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });
  g.XMLHttpRequest = function () { return { open() {}, send() {}, setRequestHeader() {}, getAllResponseHeaders() { return ''; }, status: 200, responseText: '' }; };
  // 真实音频频谱：模拟非零 getFloatFrequencyData / getByteFrequencyData，
  // 否则 acrawler 的环境完整性检测拿到全零频谱 → 走降级分支(段数少、bytelog 长)
  function makeAnalyser() {
    const N = 1024;
    const floatFreq = new Float32Array(N);
    const byteFreq = new Uint8Array(N);
    for (let i = 0; i < N; i++) {
      // 模拟真实频谱：低频能量高、带噪声，避免全零/纯常数被检测判为伪造
      const v = -90 + Math.sin(i * 0.07) * 35 + ((i * 2654435761) % 17);
      floatFreq[i] = v;
      byteFreq[i] = Math.max(0, Math.min(255, Math.floor(120 + v * 1.2)));
    }
    return {
      frequencyBinCount: N, fftSize: 2048, smoothingTimeConstant: 0.8,
      getFloatFrequencyData(a) { if (a) for (let i = 0; i < a.length; i++) a[i] = floatFreq[i % N]; },
      getByteFrequencyData(a) { if (a) for (let i = 0; i < a.length; i++) a[i] = byteFreq[i % N]; },
      getFloatTimeDomainData(a) { if (a) for (let i = 0; i < a.length; i++) a[i] = Math.sin(i * 0.1) * 0.5; },
      getByteTimeDomainData(a) { if (a) for (let i = 0; i < a.length; i++) a[i] = 128 + Math.floor(Math.sin(i * 0.1) * 60); },
      connect() {}, disconnect() {},
    };
  }
  g.AudioContext = function () { return { createOscillator: () => ({ connect() {}, start() {}, stop() {}, frequency: { setValueAtTime() {}, value: 440 }, type: 'sine' }), createAnalyser: () => makeAnalyser(), createGain: () => ({ connect() {}, gain: { value: 1 } }), createBiquadFilter: () => ({ connect() {}, type: '', frequency: { value: 0 }, Q: { value: 0 } }), destination: {}, currentTime: 0, sampleRate: 44100, state: 'running', close() {} }; };
  g.webkitAudioContext = g.AudioContext;
  g.performance = { now: () => Date.now(), timing: { navigationStart: Date.now() }, memory: { usedJSHeapSize: 12884902, totalJSHeapSize: 21740953, jsHeapSizeLimit: 219000000 } };
  g.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
  g.cancelAnimationFrame = (id) => clearTimeout(id);
  g.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  g.getComputedStyle = () => ({ getPropertyValue: () => '' });
  g.CSS = { supports: () => false };
  // 原生
  g.Date = Date; g.Math = Math; g.String = String; g.Array = Array; g.RegExp = RegExp;
  g.Object = Object; g.JSON = JSON; g.Number = Number; g.Boolean = Boolean;
  g.parseInt = parseInt; g.parseFloat = parseFloat; g.isNaN = isNaN; g.isFinite = isFinite;
  g.setTimeout = setTimeout; g.clearTimeout = clearTimeout; g.setInterval = setInterval; g.clearInterval = clearInterval;
  g.encodeURIComponent = encodeURIComponent; g.decodeURIComponent = decodeURIComponent;
  g.eval = eval; g.Function = Function; g.Error = Error; g.TypeError = TypeError;
  g.Promise = Promise; g.Map = Map; g.Set = Set; g.Symbol = Symbol; g.Proxy = Proxy;
  g.console = console; g.Uint8Array = Uint8Array; g.Uint8ClampedArray = Uint8ClampedArray;
  g.Float32Array = Float32Array; g.Int32Array = Int32Array; g.ArrayBuffer = ArrayBuffer;
  g.atob = (s) => Buffer.from(s, 'base64').toString('binary');
  g.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
  return g;
}

function main() {
  const g = makeShim();
  const src = fs.readFileSync(RAW, 'utf8');
  // 插桩：包裹 b 以捕获 bytelog（验证用），暴露常量池 i/r
  const ENTRY = '(glb="undefined"==typeof window?global:window)._$jsvmprt=function(b,e,f){';
  let patched = src;
  if (src.includes(ENTRY)) {
    patched = src.replace(ENTRY, '(glb="undefined"==typeof window?global:window)._$jsvmprt=function(b,e,f){ b=__wrapBytecode(b);');
    patched = patched.replace('return K(b,E,O/2,[],e,f);',
      'window.__entryO=O;window.__entryInfo={o:O,blen:(b?b.length:0),btype:typeof b,bhead:(b?String(b).slice(0,30):"")};window.__i=i;window.__r=r;return K(b,E,O/2,[],e,f);');
    const HEAD = `
window.__bytelog=[];
window.__wrapBytecode=function(b){var log=window.__bytelog;var isStr=typeof b==="string";var target=isStr?new String(b):b;return new Proxy(target,{get:function(t,p){
  // Symbol.toPrimitive：让 String(proxy)/模板字符串/拼接正确得到原始字符串 b
  if(p===Symbol.toPrimitive)return function(hint){return String(t);};
  var v=t[p];
  // 数字索引即取指字节：记录 pc 与字符
  if(p!=="length"&&typeof p==="string"&&/^\\d+$/.test(p)){
    var ch=isStr?String(v):String.fromCharCode(v&0xff);
    log.push({pc:+p,ch:ch});
  }
  // 关键：方法属性必须 bind 回 target，否则 String/toString 调用时 this=Proxy 触发 TypeError
  if(typeof v==="function")return v.bind(t);
  return v;
}});};
`;
    patched = HEAD + patched;
  }

  const ctx = vm.createContext(g);
  // 不设置 module/exports，强制 UMD 走全局(window)分支，使 byted_acrawler 挂到 g
  vm.runInContext(patched, ctx, { filename: 'acrawler.js', timeout: TIMEOUT });

  const ba = g.byted_acrawler || (g.module && g.module.exports && g.module.exports.byted_acrawler)
    || (g.exports && g.exports.byted_acrawler);
  if (!ba || typeof ba.sign !== 'function') {
    throw new Error('byted_acrawler.sign 未就绪 (g.byted_acrawler=' + typeof g.byted_acrawler
      + ', module.exports=' + (g.module && typeof (g.module.exports && g.module.exports.byted_acrawler)));
  }
  console.log('[replay_real] byted_acrawler.sign 就绪');

  const t0 = Date.now();
  const ret = ba.sign({ url: TARGET_URL });
  const handle = (sig) => {
    const bytelog = g.__bytelog || [];
    const segs = sig.split('.').length;
    console.log('[replay_real] 耗时 %d ms', Date.now() - t0);
    console.log('ENTRY O =', g.__entryO, ' entryInfo =', JSON.stringify(g.__entryInfo));
    console.log('URL :', TARGET_URL);
    console.log('SIG :', sig);
    console.log('段数 :', segs, ' 签名长度:', sig.length);
    // 导出 bytelog 长度用于核对
    console.log('bytelog 长度:', bytelog.length);
    fs.writeFileSync(path.join(HERE, 'replay_real_out.json'),
      JSON.stringify({ url: TARGET_URL, signature: sig, segs, sig_len: sig.length, bytelog_len: bytelog.length }));
    fs.writeFileSync(path.join(HERE, 'node_bytelog.json'),
      JSON.stringify({ url: TARGET_URL, bytelog }));
  };
  if (ret && typeof ret.then === 'function') ret.then(handle).catch((e) => { throw new Error('sign reject: ' + e); });
  else handle(ret);
}

const killer = setTimeout(() => { console.error('[replay_real] 超时 %dms，强制退出', TIMEOUT); process.exit(2); }, TIMEOUT + 5000);
killer.unref && killer.unref();
try {
  main();
} catch (e) {
  console.error('[replay_real] ERROR:', e && e.stack ? e.stack : e);
  process.exit(1);
}
