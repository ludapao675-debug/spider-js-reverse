/**
 * 米画师 SignTool（mhs_fe_sign_bg.wasm）本地封装。
 * 签名：M-S = SignTool.sign(encodeURI(url), timestampSeconds)
 * WASM 运行时会读取：
 *   - meta[name='keywords'] 的 content
 *   - link[rel*='icon'] 的 href
 *   - navigator.webdriver（需为 false）
 *   - crypto.getRandomValues（ASCON 相关随机）
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { webcrypto } from "node:crypto";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
// getrandom 在 Node 路径会走 module.require('crypto')；保留兜底
globalThis.module = { require };

const __dirname = dirname(fileURLToPath(import.meta.url));
const WASM_PATH = join(__dirname, "mhs_fe_sign_bg.wasm");
const DEBUG = process.env.MHS_SIGN_DEBUG === "1";
const FIXED_RNG = process.env.MHS_SIGN_FIXED_RNG;
const domAccessLog = [];

// 可选：固定 getRandomValues，便于与浏览器对照
if (FIXED_RNG != null && FIXED_RNG !== "") {
  const byte = Number(FIXED_RNG) & 0xff;
  webcrypto.getRandomValues = (arr) => {
    for (let i = 0; i < arr.length; i++) arr[i] = byte;
    return arr;
  };
}

// 站点 HTML 中的固定关键词（签名输入之一）
const KEYWORDS =
  "米画师,mihuashi,约稿平台,约稿,插画外包,插画外包网站,美术外包平台,游戏美术外包,画师,绘师,美术外包,原画外包,插画师,原画师,原画外包网站";
const FAVICON_HREF = "https://js-assets.mihuashi.com/mhs-assets/legacy/favicon.ico";

function installDomMock() {
  const metaEl = {
    tagName: "META",
    // WASM 通过 Reflect.get 读 HTMLMetaElement.content，不只走 getAttribute
    name: "keywords",
    content: KEYWORDS,
    getAttribute(name) {
      const key = String(name);
      if (DEBUG) domAccessLog.push(["meta.getAttribute", key]);
      const lower = key.toLowerCase();
      if (lower === "content") return KEYWORDS;
      if (lower === "name") return "keywords";
      return null;
    },
  };
  const iconEl = {
    tagName: "LINK",
    // 同样优先属性 href/rel
    rel: "icon",
    href: FAVICON_HREF,
    getAttribute(name) {
      const key = String(name);
      if (DEBUG) domAccessLog.push(["icon.getAttribute", key]);
      const lower = key.toLowerCase();
      if (lower === "href") return FAVICON_HREF;
      if (lower === "rel") return "icon";
      return null;
    },
  };
  const document = {
    querySelector(sel) {
      const s = String(sel);
      if (DEBUG) domAccessLog.push(["querySelector", s]);
      // 必须精确匹配 wasm 内嵌选择器
      if (s === "meta[name='keywords']") return metaEl;
      if (s === "link[rel*='icon']") return iconEl;
      return null;
    },
  };
  // 与页面一致：navigator.webdriver === false
  const navigator = { webdriver: false };
  const windowObj = {
    document,
    navigator,
    crypto: webcrypto,
    msCrypto: undefined,
  };
  function Window() {}
  Object.setPrototypeOf(windowObj, Window.prototype);
  // Node 上 navigator 等可能是只读 getter，改用 defineProperty
  for (const [key, value] of Object.entries({
    window: windowObj,
    self: windowObj,
    document,
    navigator,
    crypto: webcrypto,
    Window,
  })) {
    try {
      Object.defineProperty(globalThis, key, {
        value,
        writable: true,
        configurable: true,
        enumerable: true,
      });
    } catch {
      try {
        globalThis[key] = value;
      } catch {
        /* ignore */
      }
    }
  }
  // Node 运行时标识保留给 CLI；wasm getrandom 的 Node 分支在 Se() 导入表里单独短路
}

// ---- 以下为从 http.9rkHNSHB.js 抽出的 wasm-bindgen SignTool 胶水（已改本地 wasm 路径） ----
installDomMock();

let _;
const p = new Array(128).fill(void 0);
p.push(void 0, null, true, false);
function i(t) {
  return p[t];
}
let q = p.length;
function l(t) {
  q === p.length && p.push(p.length + 1);
  const e = q;
  return (q = p[e]), (p[e] = t), e;
}
function S(t, e) {
  try {
    return t.apply(this, e);
  } catch (n) {
    _.__wbindgen_export_0(l(n));
  }
}
function T(t) {
  return t == null;
}
const ie = new TextDecoder("utf-8", { ignoreBOM: true, fatal: true });
let L = null;
function U() {
  return (L === null || L.byteLength === 0) && (L = new Uint8Array(_.memory.buffer)), L;
}
function M(t, e) {
  return (t = t >>> 0), ie.decode(U().subarray(t, t + e));
}
let C = 0;
const k = new TextEncoder("utf-8");
const he =
  typeof k.encodeInto === "function"
    ? function (t, e) {
        return k.encodeInto(t, e);
      }
    : function (t, e) {
        const n = k.encode(t);
        return e.set(n), { read: t.length, written: n.length };
      };
function F(t, e, n) {
  if (n === void 0) {
    const f = k.encode(t),
      b = e(f.length, 1) >>> 0;
    return U().subarray(b, b + f.length).set(f), (C = f.length), b;
  }
  let r = t.length,
    s = e(r, 1) >>> 0;
  const c = U();
  let a = 0;
  for (; a < r; a++) {
    const f = t.charCodeAt(a);
    if (f > 127) break;
    c[s + a] = f;
  }
  if (a !== r) {
    a !== 0 && (t = t.slice(a));
    s = n(s, r, (r = a + t.length * 3), 1) >>> 0;
    const f = U().subarray(s + a, s + r),
      b = he(t, f);
    (a += b.written), (s = n(s, r, a, 1) >>> 0);
  }
  return (C = a), s;
}
let E = null;
function m() {
  return (
    (E === null ||
      E.buffer.detached === true ||
      (E.buffer.detached === void 0 && E.buffer !== _.memory.buffer)) &&
      (E = new DataView(_.memory.buffer)),
    E
  );
}
function me(t) {
  t < 132 || ((p[t] = q), (q = t));
}
function P(t) {
  const e = i(t);
  return me(t), e;
}
function G(t) {
  const e = typeof t;
  if (e == "number" || e == "boolean" || t == null) return `${t}`;
  if (e == "string") return `"${t}"`;
  if (e == "symbol") {
    const s = t.description;
    return s == null ? "Symbol" : `Symbol(${s})`;
  }
  if (e == "function") {
    const s = t.name;
    return typeof s == "string" && s.length > 0 ? `Function(${s})` : "Function";
  }
  if (Array.isArray(t)) {
    const s = t.length;
    let c = "[";
    s > 0 && (c += G(t[0]));
    for (let a = 1; a < s; a++) c += ", " + G(t[a]);
    return (c += "]"), c;
  }
  const n = /\[object ([^\]]+)\]/.exec(toString.call(t));
  let r;
  if (n && n.length > 1) r = n[1];
  else return toString.call(t);
  if (r == "Object")
    try {
      return "Object(" + JSON.stringify(t) + ")";
    } catch {
      return "Object";
    }
  return t instanceof Error ? `${t.name}: ${t.message}\n${t.stack}` : r;
}
const ne =
  typeof FinalizationRegistry > "u"
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry((t) => _.__wbg_signtool_free(t >>> 0, 1));

class SignTool {
  __destroy_into_raw() {
    const e = this.__wbg_ptr;
    return (this.__wbg_ptr = 0), ne.unregister(this), e;
  }
  free() {
    const e = this.__destroy_into_raw();
    _.__wbg_signtool_free(e, 0);
  }
  constructor() {
    const e = _.signtool_new();
    return (this.__wbg_ptr = e >>> 0), ne.register(this, this.__wbg_ptr, this), this;
  }
  sign(e, n) {
    let r, s;
    try {
      const y = _.__wbindgen_add_to_stack_pointer(-16),
        fe = F(e, _.__wbindgen_export_1, _.__wbindgen_export_2),
        le = C;
      _.signtool_sign(y, this.__wbg_ptr, fe, le, n);
      var c = m().getInt32(y + 0, true),
        a = m().getInt32(y + 4, true),
        f = m().getInt32(y + 8, true),
        b = m().getInt32(y + 12, true),
        x = c,
        A = a;
      if (b) throw ((x = 0), (A = 0), P(f));
      return (r = x), (s = A), M(x, A);
    } finally {
      _.__wbindgen_add_to_stack_pointer(16), _.__wbindgen_export_3(r, s, 1);
    }
  }
}

function Se() {
  const t = {};
  return (
    (t.wbg = {}),
    (t.wbg.__wbg_buffer_609cc3eee51ed158 = function (e) {
      const n = i(e).buffer;
      return l(n);
    }),
    (t.wbg.__wbg_call_672a4d21634d4a24 = function () {
      return S(function (e, n) {
        const r = i(e).call(i(n));
        return l(r);
      }, arguments);
    }),
    (t.wbg.__wbg_call_7cccdd69e0791ae2 = function () {
      return S(function (e, n, r) {
        const s = i(e).call(i(n), i(r));
        return l(s);
      }, arguments);
    }),
    (t.wbg.__wbg_crypto_ed58b8e10a292839 = function (e) {
      const n = i(e).crypto;
      return l(n);
    }),
    (t.wbg.__wbg_document_d249400bd7bd996d = function (e) {
      const n = i(e).document;
      return T(n) ? 0 : l(n);
    }),
    (t.wbg.__wbg_getAttribute_ea5166be2deba45e = function (e, n, r, s) {
      const c = i(n).getAttribute(M(r, s));
      var a = T(c) ? 0 : F(c, _.__wbindgen_export_1, _.__wbindgen_export_2),
        f = C;
      m().setInt32(e + 4, f, true), m().setInt32(e + 0, a, true);
    }),
    (t.wbg.__wbg_getRandomValues_bcb4912f16000dc4 = function () {
      return S(function (e, n) {
        i(e).getRandomValues(i(n));
      }, arguments);
    }),
    (t.wbg.__wbg_get_67b2ba62fc30de12 = function () {
      return S(function (e, n) {
        const obj = i(e);
        const key = i(n);
        // 隐藏 Node 特征，避免签名 AAD 走 Node 分支
        if (key === "process" || key === "versions" || key === "node") {
          if (DEBUG) domAccessLog.push(["Reflect.get.hidden", String(key)]);
          return l(undefined);
        }
        const r = Reflect.get(obj, key);
        if (DEBUG)
          domAccessLog.push([
            "Reflect.get",
            String(key),
            typeof r === "string" ? r.slice(0, 48) : typeof r,
          ]);
        return l(r);
      }, arguments);
    }),
    (t.wbg.__wbg_instanceof_Window_def73ea0955fc569 = function (e) {
      let n;
      try {
        n = i(e) instanceof Window;
      } catch {
        n = false;
      }
      if (DEBUG) domAccessLog.push(["instanceof_Window", n]);
      return n;
    }),
    (t.wbg.__wbg_msCrypto_0a36e2ec3a343d26 = function (e) {
      const n = i(e).msCrypto;
      return l(n);
    }),
    (t.wbg.__wbg_navigator_1577371c070c8947 = function (e) {
      const n = i(e).navigator;
      return l(n);
    }),
    (t.wbg.__wbg_new_a12002a7f91c75be = function (e) {
      const n = new Uint8Array(i(e));
      return l(n);
    }),
    (t.wbg.__wbg_newnoargs_105ed471475aaf50 = function (e, n) {
      const r = new Function(M(e, n));
      return l(r);
    }),
    (t.wbg.__wbg_newwithbyteoffsetandlength_d97e637ebe145a9a = function (e, n, r) {
      const s = new Uint8Array(i(e), n >>> 0, r >>> 0);
      return l(s);
    }),
    (t.wbg.__wbg_newwithlength_a381634e90c276d4 = function (e) {
      const n = new Uint8Array(e >>> 0);
      return l(n);
    }),
    (t.wbg.__wbg_node_02999533c4ea02e3 = function (e) {
      // 短路 Node 检测，强制 getrandom 走 WebCrypto
      return 0;
    }),
    (t.wbg.__wbg_process_5c1d670bc53614b8 = function (e) {
      return 0;
    }),
    (t.wbg.__wbg_querySelector_c69f8b573958906b = function () {
      return S(function (e, n, r) {
        const s = i(e).querySelector(M(n, r));
        return T(s) ? 0 : l(s);
      }, arguments);
    }),
    (t.wbg.__wbg_randomFillSync_ab2cfe79ebbf2740 = function () {
      return S(function (e, n) {
        i(e).randomFillSync(P(n));
      }, arguments);
    }),
    (t.wbg.__wbg_require_79b1e9274cde3c87 = function () {
      return S(function () {
        const e = module.require;
        return l(e);
      }, arguments);
    }),
    (t.wbg.__wbg_set_65595bdd868b3009 = function (e, n, r) {
      i(e).set(i(n), r >>> 0);
    }),
    (t.wbg.__wbg_set_bb8cecf6a62b9f46 = function () {
      return S(function (e, n, r) {
        return Reflect.set(i(e), i(n), i(r));
      }, arguments);
    }),
    (t.wbg.__wbg_static_accessor_GLOBAL_88a902d13a557d07 = function () {
      const e = typeof global > "u" ? null : global;
      return T(e) ? 0 : l(e);
    }),
    (t.wbg.__wbg_static_accessor_GLOBAL_THIS_56578be7e9f832b0 = function () {
      const e = typeof globalThis > "u" ? null : globalThis;
      return T(e) ? 0 : l(e);
    }),
    (t.wbg.__wbg_static_accessor_PROCESS_2c90d3b3264f2c90 = function () {
      return 0;
    }),
    (t.wbg.__wbg_static_accessor_SELF_37c5d418e4bf5819 = function () {
      const e = typeof self > "u" ? null : self;
      return T(e) ? 0 : l(e);
    }),
    (t.wbg.__wbg_static_accessor_WINDOW_5de37043a91a9c40 = function () {
      const e = typeof window > "u" ? null : window;
      return T(e) ? 0 : l(e);
    }),
    (t.wbg.__wbg_subarray_aa9065fa9dc5df96 = function (e, n, r) {
      const s = i(e).subarray(n >>> 0, r >>> 0);
      return l(s);
    }),
    (t.wbg.__wbg_versions_c71aa1626a93e0a1 = function (e) {
      return 0;
    }),
    (t.wbg.__wbindgen_boolean_get = function (e) {
      const n = i(e);
      return typeof n == "boolean" ? (n ? 1 : 0) : 2;
    }),
    (t.wbg.__wbindgen_debug_string = function (e, n) {
      const r = G(i(n)),
        s = F(r, _.__wbindgen_export_1, _.__wbindgen_export_2),
        c = C;
      m().setInt32(e + 4, c, true), m().setInt32(e + 0, s, true);
    }),
    (t.wbg.__wbindgen_is_function = function (e) {
      return typeof i(e) == "function";
    }),
    (t.wbg.__wbindgen_is_object = function (e) {
      const n = i(e);
      return typeof n == "object" && n !== null;
    }),
    (t.wbg.__wbindgen_is_string = function (e) {
      return typeof i(e) == "string";
    }),
    (t.wbg.__wbindgen_is_undefined = function (e) {
      return i(e) === void 0;
    }),
    (t.wbg.__wbindgen_memory = function () {
      const e = _.memory;
      return l(e);
    }),
    (t.wbg.__wbindgen_number_new = function (e) {
      return l(e);
    }),
    (t.wbg.__wbindgen_object_clone_ref = function (e) {
      const n = i(e);
      return l(n);
    }),
    (t.wbg.__wbindgen_object_drop_ref = function (e) {
      P(e);
    }),
    (t.wbg.__wbindgen_string_get = function (e, n) {
      const r = i(n),
        s = typeof r == "string" ? r : void 0;
      var c = T(s) ? 0 : F(s, _.__wbindgen_export_1, _.__wbindgen_export_2),
        a = C;
      m().setInt32(e + 4, a, true), m().setInt32(e + 0, c, true);
    }),
    (t.wbg.__wbindgen_string_new = function (e, n) {
      const r = M(e, n);
      return l(r);
    }),
    (t.wbg.__wbindgen_throw = function (e, n) {
      throw new Error(M(e, n));
    }),
    t
  );
}

function Te(t, e) {
  return (_ = t.exports), (E = null), (L = null), _;
}

async function initWasm() {
  if (_ !== void 0) return _;
  const bytes = readFileSync(WASM_PATH);
  const imports = Se();
  const { instance, module } = await WebAssembly.instantiate(bytes, imports);
  return Te(instance, module);
}

let toolPromise = null;
async function getSignTool() {
  if (!toolPromise) {
    toolPromise = (async () => {
      await initWasm();
      let lastErr = null;
      // 子进程下偶发 signtool_new unreachable，短重试即可
      for (let i = 0; i < 5; i++) {
        try {
          return new SignTool();
        } catch (e) {
          lastErr = e;
          await new Promise((r) => setTimeout(r, 30 + i * 20));
        }
      }
      throw lastErr;
    })();
  }
  return toolPromise;
}

/** 与前端拦截器一致：sign(encodeURI(url), unixSeconds) */
export async function makeSign(url, timestampSec) {
  const tool = await getSignTool();
  const encoded = encodeURI(String(url));
  const ts = Number(timestampSec);
  const ms = tool.sign(encoded, ts);
  if (DEBUG) {
    // 供对照脚本读取
    makeSign.lastDomAccess = domAccessLog.slice();
  }
  return ms;
}
export function getDomAccessLog() {
  return domAccessLog.slice();
}

// CLI: node sign_tool.mjs <url> [timestamp] [--batch=N]
// 不依赖 argv[1] 路径绝对/相对比对（Windows/子进程下易不一致）
const isDirectRun = process.argv[1] && /sign_tool\.mjs$/i.test(String(process.argv[1]).replace(/\\/g, "/"));
if (isDirectRun && process.argv.length >= 2) {
  const url = process.argv[2] || "/api/v1/stalls";
  const ts = Number(process.argv[3] || Math.floor(Date.now() / 1000));
  // --batch=N：单进程内连续签 N 个（ts 递增去重），供 Python 逐个尝试，摊薄 node 启动开销
  const batchArg = process.argv.find((a) => /^--batch=/.test(String(a)));
  const batchN = batchArg ? Math.max(1, Number(batchArg.split("=")[1]) || 0) : 0;
  if (batchN > 0) {
    (async () => {
      const rows = [];
      for (let i = 0; i < batchN; i++) {
        const t = ts + i;
        const ms = await makeSign(url, t);
        rows.push({ "M-T": String(t), "M-S": ms });
      }
      process.stdout.write(JSON.stringify({ ok: true, url, encoded: encodeURI(url), rows }));
    })().catch((err) => {
      process.stderr.write(String(err && err.stack ? err.stack : err));
      process.exit(1);
    });
  } else {
  makeSign(url, ts)
    .then((ms) => {
      const payload = {
        ok: true,
        url,
        encoded: encodeURI(url),
        "M-T": String(ts),
        "M-S": ms,
      };
      if (DEBUG) payload.dom_access = domAccessLog.slice();
      process.stdout.write(JSON.stringify(payload));
    })
    .catch((err) => {
      process.stderr.write(String(err && err.stack ? err.stack : err));
      process.exit(1);
    });
  }
}
