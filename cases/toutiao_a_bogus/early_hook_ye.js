// early_hook_ye.js — 在 bdms IIFE 写 ye 时捕获（Page.addScriptToEvaluateOnNewDocument）
(function () {
  if (window.__early_ye_hook) return;
  window.__early_ye_hook = true;
  var _desc = Object.defineProperty;
  Object.defineProperty = function (obj, prop, desc) {
    try {
      if (prop === 51 && desc && typeof desc.set === 'function') {
        var origSet = desc.set;
        desc.set = function (fn) {
          try {
            window.__abogus_sign = fn;
            window.__abogus_sign_pc = fn && fn._v && fn._v[0];
          } catch (e) { /* ignore */ }
          return origSet.call(this, fn);
        };
      }
    } catch (e) { /* ignore */ }
    return _desc.apply(this, arguments);
  };
})();
