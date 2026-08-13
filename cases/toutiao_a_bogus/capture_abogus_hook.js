// capture_abogus_hook.js  (v2 — 结构化 input→output 对)
// 设计前提（来自调用栈分析 sdk-glue.js:14137 -> bdms.js e@225789）：
//   - 业务层调用 xhr.open(method, url) 时 url 尚【无】a_bogus（输入）。
//   - sdk-glue 包装了 open/send，持有原生 open 的私有引用；a_bogus 由 bdms VM 算出后
//     在 sdk-glue 内部把签名 URL 传给原生 open。
//   - 因此：JS 层【只能】在我们(包装在 sdk-glue 之上)的 open 钩子里看到【未签名输入】；
//     签名后的【输出 URL】由项目已有的网络监听器(final_capture)捕获。
//   - 本 hook 在 open 时记录结构化输入 + 关联键(msToken/offset/ts)，便于与网络监听器
//     捕获的签名 URL 按 (msToken,offset,ts) 关联，拼出完整 input→output 对。
//   - 防御式：若某条 URL 在 open 时已带 a_bogus（说明钩子落在 sdk-glue 之下），直接当作
//     完整对(record.input_url 为去 a_bogus 后的输入，record.abogus 为输出)。
//
// 用法：
//   ch_page_run_js(inject capture_abogus_hook.js)
//   触发/等待真实 a_bogus feed 请求
//   ch_page_run_js("return JSON.stringify(window.__abogus_trace)")
(function () {
  if (window.__abogus_hook_installed) return "already installed";
  window.__abogus_hook_installed = true;

  var trace = window.__abogus_trace || (window.__abogus_trace = {
    installed_at: Date.now(),
    pairs: [],          // 结构化 input→output 对
    first_stack: null   // 首个命中请求的构造栈(定位 VM 入口用)
  });

  var MAX_PAIRS = 60;

  function parseUrl(u) {
    try {
      var base = (window.location && window.location.href) || "https://www.toutiao.com/";
      var url = new URL(u, base);
      var params = {};
      url.searchParams.forEach(function (v, k) { params[k] = v; });
      var abogusKey = params.a_bogus ? "a_bogus" : (params.aBogus ? "aBogus" : null);
      var abogus = abogusKey ? params[abogusKey] : null;
      if (abogusKey) delete params[abogusKey];
      var inputUrl = url.origin + url.pathname + url.search; // 去 a_bogus 后的输入 URL
      return { ok: true, origin: url.origin, path: url.pathname, inputUrl: inputUrl, params: params, abogus: abogus };
    } catch (e) { return { ok: false, err: String(e) }; }
  }

  function hasSig(u) {
    return typeof u === "string" && (/[?&]a_bogus=/.test(u) || /[?&]msToken=/.test(u) || /[?&]aBogus=/.test(u));
  }

  function record(method, url) {
    if (trace.pairs.length >= MAX_PAIRS) return;
    var p = parseUrl(url);
    if (!p.ok) return;
    var pair = {
      method: method,
      input_url: p.inputUrl,        // 无 a_bogus 的输入 URL（VM 输入）
      input_params: p.params,       // 输入参数（不含 a_bogus）
      abogus: p.abogus,             // 若 open 时已带签名则为输出，否则 null(待网络监听器补全)
      has_abogus_at_open: !!p.abogus,
      msToken: p.params.msToken || null,
      offset: p.params.offset || null,
      ts: Date.now()
    };
    trace.pairs.push(pair);
    // 首个命中：记构造栈，用于定位 VM 入口 / 校验调用链
    if (!trace.first_stack && hasSig(url)) {
      var e = new Error();
      trace.first_stack = { url: url, stack: (e.stack || "").toString() };
    }
  }

  try {
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      try { record(method, url); } catch (_) {}
      return origOpen.apply(this, arguments);
    };
  } catch (_) {}

  try {
    var origFetch = window.fetch ? window.fetch.bind(window) : null;
    if (origFetch) {
      window.fetch = function (input, init) {
        try {
          var u = typeof input === "string" ? input : (input && input.url) ? input.url : "";
          if (u) record((init && init.method) || (input && input.method) || "GET", u);
        } catch (_) {}
        return origFetch(input, init);
      };
    }
  } catch (_) {}

  return "installed a_bogus capture hook v2 (input URL at open; MAX_PAIRS=" + MAX_PAIRS + ")";
})();
