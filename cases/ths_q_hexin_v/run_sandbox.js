// 在 Node vm 隔离沙箱中完整执行 chameleon 脚本，直接调用内部 qn.update() 生成 v
// 验证方向：若沙箱生成的 v 也被服务端 401，则 gate 校验时间窗/指纹细节；若 200，则手工布局有误
const fs = require('fs');
const vm = require('vm');

const src = fs.readFileSync(__dirname + '/chameleon.1.7.min.js', 'utf8');

// ---- DOM/BOM stub：只覆盖 chameleon Init 路径用到的对象 ----
function mkEl() {
  return {
    style: {}, setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    save() {}, addBehavior() {}, load() {}, appendChild() {}, removeChild() {},
    addEventListener() {}, attachEvent() {}, getContext() { return null; },
    set src(v) {}, set onload(f) {}, set onerror(f) {},
  };
}
const documentStub = {
  cookie: '',
  head: { appendChild() {} },
  body: { appendChild() {} },
  documentElement: { style: {} },
  defaultCharset: 'utf-8',
  createElement(tag) { return mkEl(); },
  getElementsByTagName() { return [mkEl()]; },
  addEventListener() {}, attachEvent() {},
};
const navigatorStub = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
  appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
  vendor: 'Google Inc.', language: 'zh-CN', languages: ['zh-CN', 'en'],
  platform: 'Win32', plugins: [], mimeTypes: [], javaEnabled: () => false,
  productSub: '20030107',
};
const windowStub = {
  document: documentStub, navigator: navigatorStub,
  addEventListener() {}, attachEvent() {}, setInterval() { return 1; }, setTimeout(f) { return 1; },
};
windowStub.window = windowStub;
windowStub.top = windowStub;
windowStub.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
windowStub.TOKEN_SERVER_TIME = Math.floor(Date.now() / 1000);

const ctx = vm.createContext({
  window: windowStub, document: documentStub, navigator: navigatorStub,
  location: { protocol: 'https:', hostname: 'q.10jqka.com.cn', href: 'https://q.10jqka.com.cn/' },
  localStorage: windowStub.localStorage, TOKEN_SERVER_TIME: windowStub.TOKEN_SERVER_TIME,
  Array, Map, Function, String, RegExp, Date, Object, Math, JSON, parseInt, encodeURIComponent,
  Element: function(){}, ActiveXObject: undefined, XMLHttpRequest: undefined, fetch: undefined,
  Headers: undefined, setTimeout: () => 1, setInterval: () => 1, navigator: navigatorStub,
  console: { log() {} },
});

try {
  // 追加桥接代码：脚本末尾 Zn.Init() 已执行，qn/zn 在闭包内；
  // 通过触发脚本自身的更新链路拿不到引用，改为注入探针：
  // 重写 document.cookie setter 不可行（脚本用赋值），直接在源尾注入代码调用内部 API。
  // qn/zn 是外层 IIFE 内局部变量，无法外部访问；因此把探针代码拼接到源码末尾（同一作用域）。
  const probe = `;try{ qn.Init(); window.__INIT_OK = true; }catch(ei){ window.__INIT_ERR = String(ei && ei.stack || ei); }
    try{ var __orig = null;
    for (var __k in Qn) { if (typeof Qn[__k] === 'function') { (function(k){ var o = Qn[k]; Qn[k] = function(x){ if (x && x.length && typeof x[0] === 'number') { window.__BUF_PROBE = {fn: k, bytes: Array.prototype.slice.call(x)}; } return o.apply(this, arguments); }; })(__k); } }
    try { window.__V_PROBE = qn.update(); } catch(e2) { window.__V_PROBE_ERR2 = String(e2); }
  }catch(e){ window.__V_PROBE_ERR = String(e); }`;
  // 内层 IIFE 结尾为 }()，探针插到它之前即处于 qn 同作用域（Zn.Init 之后）
  const idx = src.lastIndexOf('}()');
  const patched = src.slice(0, idx) + probe + src.slice(idx);
  vm.runInContext(patched, ctx, { timeout: 5000 });
  console.log('脚本执行完成, CHAMELEON_LOADED =', ctx.window.CHAMELEON_LOADED);
  if (ctx.window.__INIT_ERR) console.log('qn.Init 异常:', ctx.window.__INIT_ERR.split('\n')[0]);
  if (ctx.window.__V_PROBE_ERR) console.log('探针异常:', ctx.window.__V_PROBE_ERR);
} catch (e) {
  console.log('执行异常(可忽略若核心已初始化):', String(e).slice(0, 200));
}

// 优先用探针拿到的 v；否则回退解析 document.cookie
const bufProbe = ctx.window.__BUF_PROBE;
if (bufProbe) {
  console.log('buffer捕获 fn=' + bufProbe.fn + ' 长度=' + bufProbe.bytes.length);
  console.log('buffer(hex):', Buffer.from(bufProbe.bytes).toString('hex'));
}
if (ctx.window.__V_PROBE_ERR2) console.log('qn.update 异常:', ctx.window.__V_PROBE_ERR2);
const probeV = ctx.window.__V_PROBE;
if (probeV) {
  console.log('V_SANDBOX=' + probeV);
  console.log('长度:', probeV.length);
  fs.writeFileSync(__dirname + '/v_sandbox.txt', probeV);
}
const cookieRaw = documentStub.cookie;
console.log('document.cookie =', cookieRaw.slice(0, 120));
const m = cookieRaw.match(/(?:^|;\s*)v=([^;]+)/);
if (m) {
  const v = decodeURIComponent(m[1]);
  console.log('V_SANDBOX=' + v);
  console.log('长度:', v.length);
  fs.writeFileSync(__dirname + '/v_sandbox.txt', v);
} else {
  console.log('未能从 document.cookie 提取 v');
}
