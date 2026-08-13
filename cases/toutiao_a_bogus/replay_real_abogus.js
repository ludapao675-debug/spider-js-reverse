// replay_real_abogus.js
// 运行真实 a_bogus JSVMP（bdms.js 内嵌 IIFE @222136..254918）的 Node 垫片 harness。
// 思路：抽取 IIFE 源码 -> vm 带垫片执行 -> 插桩常量池记录 env 访问 -> 捕获 VM 返回值 / ye setter。
// 本步验证抽取正确、VM 能跑通（即便 env 占位也至少执行到底），并暴露真实 env 需求。

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const HERE = __dirname;
const RAW = path.join(HERE, "raw", "bdms.js");
const src = fs.readFileSync(RAW, "utf8");

// ---- 抽取 a_bogus IIFE ----
const II_START = src.indexOf("!function(e,r,t){", 221500);          // 222136
const II_END = src.indexOf("void 0)", 253860) + "void 0)".length;   // 254918
if (II_START < 0 || II_END <= "void 0)".length) throw new Error("IIFE 边界抽取失败");
let iife = src.slice(II_START, II_END);
if (iife.startsWith("!function")) iife = iife.slice(1); // 去 '!' 以便捕获返回值

// ---- 闭包变量清单（常量池 getter 29..51 引用） ----
const CLOSURE_VARS = ["M","W","T","q","B","F","U","D","L","N","H","V","Q","J","Z","X","K","$","te","ge","Ie","ye"];
const CAPTURE = {}; // 浏览器抓取的真实值填入此处即可复现

// ---- 垫片环境 ----
const accessLog = [];
function logAccess(kind, name, val) {
  if (accessLog.length < 8000) accessLog.push({ kind, name, t: typeof val, preview: String(val).slice(0, 80) });
}

// ★ 闭包变量真实初始化（非 stub）：VM 通过字节码在 IIFE 执行时填充它们
// 队列对象 ({items,front,rear}) 是真正的类型，非 stub 函数
function makeQueue() { return { items: [], front: 0, rear: 0 }; }

// 闭包变量所属类型（从浏览器 g.p[29..51] 读取）：
// VM函数(14个): M,q,D,H,V,Q,J,Z,X,K,$,te,ge,ye
// 队列(7个): W,T,B,F,U,L,N
// 原生: Ie(sessionStorage读取), me(环境数据对象)
const QUEUE_NAMES = new Set(["W","T","B","F","U","L","N"]);
const VM_NAMES = new Set(["M","q","D","H","V","Q","J","Z","X","K","$","te","ge"]);

const sandbox = {};
for (const name of CLOSURE_VARS) {
  let captured;
  if (QUEUE_NAMES.has(name)) {
    captured = makeQueue(); // 真实队列，VM 会 push/pop
  } else if (VM_NAMES.has(name)) {
    // VM 函数：IIFE 执行时通过 bytecode 创建，不能提前填充
    captured = undefined;
  } else if (name === "Ie") {
    // sessionStorage 读取器：不在 IIFE 中创建，需要从浏览器捕获
    captured = function() {
      // 浏览器中：读取 window.sessionStorage.__ac_nonce
      // Node 中：返回空串
      return { _s: (typeof process !== 'undefined' ? '' : ''), _d: '' };
    };
  } else if (name === "me") {
    // 环境数据对象：IIFE 执行时通过 bytecode 填充
    captured = {};
  } else {
    captured = undefined;
  }
  Object.defineProperty(sandbox, name, {
    configurable: true,
    get() { logAccess("closure", name, captured); return captured; },
    set(v) { captured = v; logAccess("closure-set", name, v); },
  });
}

function makeLS() {
  const m = {};
  return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
           removeItem: (k) => { delete m[k]; }, clear() {} };
}
const win = {
  location: { href: "https://www.toutiao.com/", search: "", pathname: "/", host: "www.toutiao.com",
              hostname: "www.toutiao.com", protocol: "https:", origin: "https://www.toutiao.com" },
  addEventListener() {}, removeEventListener() {},
  setTimeout, clearTimeout, setInterval, clearInterval,
  requestAnimationFrame(cb) { return setTimeout(cb, 0); }, localStorage: makeLS(),
};
const nav = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
  platform: "Win32", language: "zh-CN", languages: ["zh-CN","zh"], cookieEnabled: true, hardwareConcurrency: 8,
  deviceMemory: 8, maxTouchPoints: 0, vendor: "Google Inc.", product: "Gecko", appVersion: "5.0 (Windows NT 10.0; Win64; x64)", onLine: true };
win.navigator = nav;
const doc = { location: win.location, URL: "https://www.toutiao.com/", cookie: "", referrer: "", title: "今日头条",
  getElementById() { return null; }, createElement() { return { style: {}, getContext() { return null; } }; },
  addEventListener() {}, removeEventListener() {} };
win.document = doc;

sandbox.window = win; sandbox.navigator = nav; sandbox.document = doc; sandbox.location = win.location;
sandbox.localStorage = win.localStorage; sandbox.XMLHttpRequest = function () {};
sandbox.URL = URL; sandbox.Request = typeof Request !== "undefined" ? Request : function () {};
sandbox.performance = { now: () => Date.now() }; sandbox.requestAnimationFrame = win.requestAnimationFrame;
sandbox.setTimeout = setTimeout; sandbox.setInterval = setInterval;
Object.assign(sandbox, { Symbol, TypeError, Object, Array, String, Number, Reflect, ReferenceError, Proxy,
  Boolean, Error, isNaN, isFinite, Promise, JSON, Date, RegExp, Math, Function, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, encodeURI, decodeURI, escape, unescape, Infinity, NaN, undefined });

sandbox.globalThis = sandbox; sandbox.console = console; sandbox.__ABOGUS_RESULT = undefined;

const wrappedCode = "globalThis.__ABOGUS_RESULT = (" + iife + ");";
try {
  vm.runInNewContext(wrappedCode, sandbox, { timeout: 12000, filename: "abogus_iife.js" });
} catch (e) {
  console.log("[VM 执行异常]", e && e.stack ? e.stack.split("\n").slice(0, 8).join("\n") : e);
}

console.log("\n=== a_bogus VM 运行结果 ===");
console.log("IIFE 返回值:", JSON.stringify(sandbox.__ABOGUS_RESULT));
const yeSets = accessLog.filter(r => r.kind === "closure-set" && r.name === "ye");
if (yeSets.length) console.log("ye(set 51) 末次写入:", JSON.stringify(yeSets[yeSets.length - 1].preview));

console.log("\n=== env 访问记录（前 80） ===");
for (const r of accessLog.slice(0, 80)) console.log(`  ${r.kind.padEnd(11)} ${r.name.padEnd(4)} type=${r.t.padEnd(9)} ${r.preview}`);
console.log("总计访问记录:", accessLog.length);
console.log("闭包变量访问:", accessLog.filter(r => r.kind === "closure").length,
            " 闭包变量写入:", accessLog.filter(r => r.kind === "closure-set").length);

// ★ 获取解释器引用，注入闭包变量真实值
console.log("\n=== 注入闭包变量真实值 ===");
const intpr = sandbox.ye && sandbox.ye._u;
if (typeof intpr === 'function') {
  console.log("解释器已获取:", String(intpr).slice(0, 60));

  // VM 函数数据（从浏览器 bdms.init._v[2].p[29..51] 提取）
  const vmData = {
    'M': {pc: 0, param: 0}, 'q': {pc: 2732, param: 0}, 'D': {pc: 1540, param: 0},
    'H': {pc: 4663, param: 0}, 'V': {pc: 355, param: 0}, 'Q': {pc: 5864, param: 0},
    'J': {pc: 66, param: 0}, 'Z': {pc: 0, param: 0}, 'X': {pc: 696, param: 0},
    'K': {pc: 0, param: 0}, '$': {pc: 0, param: 0}, 'te': {pc: 474, param: 1},
    'ge': {pc: 1582, param: 6},
  };

  // 注入 me（环境配置对象）
  sandbox.me = { aid: 24, pageId: 6457, boe: false, ddrt: 3, paths: {}, track: {}, dump: true, rpU: '' };

  // 注入队列对象
  const queueNames = ['W','T','B','F','U','L','N'];
  for (const qn of queueNames) sandbox[qn] = { items: [], front: 0, rear: 0 };

  // 注入 Ie（sessionStorage 垫片）
  sandbox.Ie = function() { return { _s: '', _d: '' }; };

  // 创建 VM 函数包装器，用浏览器的 _v 数据
  for (const [name, data] of Object.entries(vmData)) {
    const fn = function e() { var r = e._v; return (0, e._u)(r[0], arguments, r[1], r[2], this); };
    fn._v = [data.pc, data.param, sandbox.me];
    fn._u = intpr;
    sandbox[name] = fn;
  }
  console.log("注入完成。VM函数:", Object.keys(vmData).length);

  // 测试签名
  console.log("\n=== 测试 ye 签名函数 ===");
  const testUrl = "https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web";
  try {
    const result = sandbox.ye(testUrl);
    console.log("ye(testUrl) 结果:", JSON.stringify(result));
    console.log("结果类型:", typeof result);
    if (typeof result === 'string') console.log("结果长度:", result.length, "前30:", result.slice(0, 30));
  } catch(e) {
    console.log("ye 调用异常:", e.message.slice(0, 300));
    console.log("堆栈:", (e.stack||'').split('\n').slice(0,6).join('\n'));
  }
} else {
  console.log("错误: 无法获取解释器引用!");
}
