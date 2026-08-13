// capture_and_dump.js — 安装 VM 钩 → 触发 feed XHR → dump 环境
(function () {
  // 1) VM hook
  if (!window.__vm_sign_hook_v2) {
    window.__vm_sign_hook_v2 = true;
    window.__ye_call_log = [];
    var origCall = Function.prototype.call;
    Function.prototype.call = function (thisArg) {
      var args = Array.prototype.slice.call(arguments, 1);
      var ret = origCall.apply(this, [thisArg].concat(args));
      try {
        if (this && this._u && this._v && args.length) {
          var s0 = args[0];
          var urlLike = typeof s0 === 'string' && s0.indexOf('/api/pc/list/feed') >= 0;
          var retStr = typeof ret === 'string' && ret.length > 80 && ret.length < 300;
          if (urlLike || retStr) {
            window.__ye_call_log.push({
              pc: this._v[0], param: this._v[1],
              arg0: typeof s0 === 'string' ? s0.slice(0, 100) : typeof s0,
              retType: typeof ret, retLen: ret && ret.length,
              retPreview: retStr ? ret.slice(0, 80) : null,
            });
          }
          if (retStr && ret.indexOf('=') >= 0) {
            window.__captured_sign_fn = this;
            window.__captured_abogus_from_vm = ret;
            window.__captured_abogus_fn_pc = this._v[0];
          }
        }
      } catch (e) { /* ignore */ }
      return ret;
    };
  }

  var feedUrl = 'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web&msToken=RoY0L66jZkTDZdQPZWW3ZNSGAQRUNGs_jp187zBXvGSFAh6B8KNuIjcnw7ojDXP5fgywJJ0UwyqfnDkobuQCPTyxBjinv34QXS3_S4po9ZyGPAeUozPIwhXGoNjjHmop';

  function ser(v, depth, seen) {
    if (!seen) seen = new WeakSet();
    if (depth > 10) return '[depth]';
    if (v == null || typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') return v;
    if (typeof v === 'function') return { __fn: true, pc: v._v && v._v[0], param: v._v && v._v[1] };
    if (typeof v !== 'object') return String(v);
    if (seen.has(v)) return '[Circular]';
    seen.add(v);
    if (v.items && typeof v.front === 'number' && typeof v.rear === 'number') {
      var items = [];
      for (var i = 0; i < Math.min(v.rear, v.items.length, 512); i++) {
        var it = v.items[i];
        items.push(it && typeof it === 'object' ? { x: it.x, y: it.y, ts: it.ts } : it);
      }
      return { items: items, front: v.front, rear: v.rear };
    }
    if (Array.isArray(v)) return v.map(function (x, i) { return i < 64 ? ser(x, depth + 1, seen) : undefined; });
    var o = {};
    Object.keys(v).slice(0, 40).forEach(function (k) {
      try { o[k] = ser(v[k], depth + 1, seen); } catch (e) { o[k] = '[err]'; }
    });
    return o;
  }

  return new Promise(function (resolve) {
    var xhr = new XMLHttpRequest();
    xhr.onload = function () {
      var signFn = window.__captured_sign_fn;
      var initMe = window.bdms && window.bdms.init && window.bdms.init._v && window.bdms.init._v[2];
      var out = {
        ok: true,
        xhr_abogus: (xhr.responseURL.match(/a_bogus=([^&]+)/) || [])[1],
        responseURL: xhr.responseURL.slice(0, 200),
        ye_call_log: window.__ye_call_log || [],
        captured_fn_pc: window.__captured_abogus_fn_pc,
        captured_abogus_vm: window.__captured_abogus_from_vm,
        init_me: initMe ? ser(initMe, 0) : null,
        sign_fn_me: signFn && signFn._v ? ser(signFn._v[2], 0) : null,
        sign_fn_v: signFn && signFn._v ? [signFn._v[0], signFn._v[1]] : null,
      };
      // 浏览器内 oracle：若捕获到 sign fn，试签
      if (signFn && typeof signFn === 'function') {
        try {
          var r2 = signFn(feedUrl);
          out.sign_fn_retest = { type: typeof r2, len: r2 ? r2.length : 0, preview: r2 ? r2.slice(0, 80) : null };
        } catch (e) { out.sign_fn_retest = { error: e.message }; }
      }
      resolve(out);
    };
    xhr.onerror = function () { resolve({ ok: false, error: 'xhr failed' }); };
    xhr.open('GET', feedUrl);
    xhr.send();
  });
})();
