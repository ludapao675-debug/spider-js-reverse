// 针对字节跳动 acrawler.js (_$jsvmprt) 的「取指插桩草案」
// ───────────────────────────────────────────────────────────────────
// 静态定位结论（见案例文档）：
//   - VM 运行时入口：(glb)._$jsvmprt = function(b, e, f){...}，字节码是参数 b
//   - 取指封装为闭包内辅助函数 y/s/p/v(b,e)：
//       y(b,e) = parseInt(""+b[e]+b[e+1],16)           读 1 字节
//       s(b,e) = parseInt(""+b[e..e+3],16) 有符号      读 1 字(4 hex)
//       p(b,e) = parseInt(""+b[e..e+7],16)             读 4 字节(8 hex)
//       v(b,e) = parseInt(""+b[e..e+3],16)             读 1 字
//   - 计数器变量混淆为 O / e / m 多套
//   - 取指有 1/2/4 字节多宽度
// 因此「全局 hook parseInt(2-hex)」会漏掉 s/p/v 的宽读 -> 必须改为 Proxy 包裹
//   字节码参数 b 的「每次单字节索引读」，才能覆盖所有辅助函数 + 所有宽度，
//   得到等价于 VM 字节码流（含 pc）的完整序列。
//
// 注入方式（草案，需浏览器验证）：
//   方案 A（首选，源码层）：请求拦截 acrawler.js，在
//     _$jsvmprt=function(b,e,f){
//     之后插入 `b = __wrapBytecode(b);`，在 VM 入口就地把 b 包成 Proxy。
//   方案 B（运行时，依赖全局引用）：把 window._$jsvmprt 替换为包装版。
//     风险：若 sign 内部用闭包局部引用而非 window._$jsvmprt，则方案 B 失效，
//           必须走方案 A。本草案默认实现方案 B，并提示方案 A 更稳。
// ───────────────────────────────────────────────────────────────────
(function () {
  var G = (typeof window !== "undefined") ? window : globalThis;
  var KEY = "__acrawler_bytelog";

  // 包裹字节码：拦截每次 b[idx] 单字节读（即 VM 取指），记录 (pc, 字节值)
  function wrapBytecode(b) {
    var log = [];
    var isStr = (typeof b === "string");
    var target = isStr ? new String(b) : b;
    var wrapped = new Proxy(target, {
      get: function (t, prop, recv) {
        if (prop !== "length" && typeof prop === "string" && /^\d+$/.test(prop)) {
          var raw = t[prop];
          var val = isStr ? raw.charCodeAt(0) : raw;
          log.push({ pc: +prop, val: val & 0xff, hex: (val & 0xff).toString(16).padStart(2, "0") });
        }
        return t[prop];
      },
    });
    wrapped.__log = log;
    return wrapped;
  }

  var _orig = G._$jsvmprt;
  if (typeof _orig === "function") {
    G._$jsvmprt = function (b, e, f) {
      var wb = wrapBytecode(b);
      var ret = _orig(wb, e, f);
      G[KEY] = (G[KEY] || []).concat(wb.__log);
      return ret;
    };
    console.log("[acrawler-instrument] _$jsvmprt 已包裹（方案B），等待 sign 触发");
  } else {
    console.log("[acrawler-instrument] 未找到 window._$jsvmprt（注入时机过早或 sign 用闭包局部引用 -> 需改方案A 源码层注入）");
  }

  // 触发签名并取字节流：返回 {signature, bytelog}
  // 兼容两种 sign 风格：新版 Promise（sign(url).then）与老版回调（sign(url, cb)）
  G.__acrawler_capture_sign = function (url, timeout) {
    return new Promise(function (resolve, reject) {
      timeout = timeout || 8000;
      var done = false;
      try { G[KEY] = []; } catch (e) {}
      if (typeof G.byted_acrawler === "undefined" || !G.byted_acrawler.sign) {
        return reject("byted_acrawler.sign 不可用");
      }
      // 新版 acrawler 的 sign 要求 nonce 为对象且含 url 属性：sign({url: ...})
      var ret = G.byted_acrawler.sign({ url: url });
      if (ret && typeof ret.then === "function") {
        // Promise 风格（新版 acrawler）
        ret.then(function (sig) {
          if (done) return;
          done = true;
          resolve({ signature: sig, bytelog: G[KEY] || [] });
        }).catch(function (e) {
          if (done) return;
          done = true;
          reject("sign reject: " + e);
        });
      } else {
        // 回调风格（老版 acrawler，同样传对象）
        G.byted_acrawler.sign({ url: url }, function (sig) {
          if (done) return;
          done = true;
          resolve({ signature: sig, bytelog: G[KEY] || [] });
        });
      }
      setTimeout(function () { if (!done) { done = true; reject("sign 超时"); } }, timeout);
    });
  };
})();
