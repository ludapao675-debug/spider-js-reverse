// hook_vm_sign.js — 钩 VM 调用以捕获 a_bogus 签名函数
(function () {
  if (window.__vm_sign_hook_v2) return 'already';
  window.__vm_sign_hook_v2 = true;
  window.__ye_call_log = [];
  window.__captured_sign_fn = null;

  const origCall = Function.prototype.call;
  Function.prototype.call = function (thisArg) {
    const args = Array.prototype.slice.call(arguments, 1);
    const ret = origCall.apply(this, [thisArg].concat(args));
    try {
      if (this && this._u && this._v && args.length) {
        const s0 = args[0];
        const urlLike = typeof s0 === 'string' && s0.indexOf('/api/pc/list/feed') >= 0;
        const retStr = typeof ret === 'string' && ret.length > 80 && ret.length < 300;
        if (urlLike || retStr) {
          window.__ye_call_log.push({
            pc: this._v[0],
            param: this._v[1],
            arg0: typeof s0 === 'string' ? s0.slice(0, 100) : typeof s0,
            retType: typeof ret,
            retLen: ret && ret.length,
            retPreview: retStr ? ret.slice(0, 80) : null,
          });
        }
        if (retStr && /^[A-Za-z0-9+\/_-]+=*$/.test(ret.slice(0, 20))) {
          window.__captured_sign_fn = this;
          window.__captured_abogus_from_vm = ret;
          window.__captured_abogus_fn_pc = this._v[0];
        }
      }
    } catch (e) { /* ignore */ }
    return ret;
  };
  return 'hooked v2';
})();
