// early_hook_bdms_patch.js — 在 bdms.js 执行前 patch set 51，捕获 ye 到 window.__abogus_sign
// 用法：ch_page_inject_early(source=文件内容) → 导航刷新页面
(function () {
  if (window.__bdms_patch_hook_v1) return;
  window.__bdms_patch_hook_v1 = true;

  var PATCH_FROM = 'set 51(e){ye=e}';
  var PATCH_TO = 'set 51(e){ye=e;try{window.__abogus_sign=e;window.__abogus_sign_pc=e&&e._v&&e._v[0]}catch(_x){}}';

  /** 对 bdms 源码插桩 */
  function patchBdmsCode(code) {
    if (typeof code !== 'string' || code.indexOf(PATCH_FROM) < 0) return code;
    return code.replace(PATCH_FROM, PATCH_TO);
  }

  /** 同步拉取脚本（document_start 阶段可用） */
  function fetchSync(url) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.send(null);
      if (xhr.status >= 200 && xhr.status < 300) return xhr.responseText;
    } catch (e) { /* ignore */ }
    return '';
  }

  /** 用 patch 后的内联 script 替换外链 bdms */
  function injectPatchedScript(url, anchor) {
    var code = fetchSync(url);
    if (!code) return false;
    code = patchBdmsCode(code);
    var s = document.createElement('script');
    s.textContent = code;
    s.setAttribute('data-ch-patched-bdms', '1');
    var parent = (anchor && anchor.parentNode) || document.documentElement || document.head;
    if (anchor && anchor.parentNode) {
      parent.insertBefore(s, anchor);
      try { anchor.parentNode.removeChild(anchor); } catch (_) {}
    } else {
      parent.appendChild(s);
    }
    return true;
  }

  /** 判断是否 bdms 脚本 URL */
  function isBdmsUrl(url) {
    return typeof url === 'string' && /bdms\.js(\?|$)/i.test(url);
  }

  // --- 1) 拦截 appendChild / insertBefore ---
  var origAppend = Node.prototype.appendChild;
  var origInsert = Node.prototype.insertBefore;

  Node.prototype.appendChild = function (child) {
    try {
      if (child && child.tagName === 'SCRIPT') {
        var src = child.src || child.getAttribute('src') || '';
        if (isBdmsUrl(src)) {
          if (injectPatchedScript(src, child)) return child;
        }
      }
    } catch (_) { /* ignore */ }
    return origAppend.call(this, child);
  };

  Node.prototype.insertBefore = function (child, ref) {
    try {
      if (child && child.tagName === 'SCRIPT') {
        var src = child.src || child.getAttribute('src') || '';
        if (isBdmsUrl(src)) {
          if (injectPatchedScript(src, child)) return child;
        }
      }
    } catch (_) { /* ignore */ }
    return origInsert.call(this, child, ref);
  };

  // --- 2) 拦截 script.src setter（部分站点先 createElement 再设 src）---
  try {
    var srcDesc = Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype, 'src');
    if (srcDesc && srcDesc.set && srcDesc.get) {
      Object.defineProperty(HTMLScriptElement.prototype, 'src', {
        configurable: true,
        enumerable: srcDesc.enumerable,
        get: srcDesc.get,
        set: function (url) {
          if (isBdmsUrl(url)) {
            var self = this;
            if (injectPatchedScript(url, self)) return;
          }
          return srcDesc.set.call(this, url);
        },
      });
    }
  } catch (_) { /* ignore */ }

  window.__bdms_patch_hook_ready = true;
})();
