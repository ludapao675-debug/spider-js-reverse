// -*- coding: utf-8 -*-
/**
 * sdenv_extract.js — 用 sdenv(高保真 Chrome 环境) + Node 自洽捕获 acrawler 字节码执行轨迹。
 *
 * 关键发现：acrawler.js 是自包含的 —— 文件末尾直接
 *   (glb)._$jsvmprt("484e4f...[字节码]", glb, [env 数组])
 * 即用内嵌字节码 b 跑一遍 VM 来初始化 window.byted_acrawler，再由
 * byted_acrawler.sign({url}) 复用同一份 b 计算 _signature。
 * 因此无需活浏览器，sdenv 提供 window/navigator/document/screen 真值即可。
 *
 * 本脚本在一次运行内同时产出（自洽）：
 *   - bytelog : 所有 b[idx] 字节读（完整覆盖本次执行的取指路径，含分支）
 *   - dispatch: 每次取指的 j / x=13*j%241 / A / O(pc)
 *   - strpool : 实时解码的常量池 z -> 字符串（由 i.p / i.q / XOR 密钥 r 重建）
 *   - signature: 真实 _signature
 *   - url     : 触发 sign 的 url
 * 落盘到 sdenv_capture.json，供纯 Python 栈式 VM(stackvm.py) 离线端到端复现。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// 看门狗：超过 150s 直接退出，并留痕当前阶段
const STAGE_LOG = path.join(__dirname, '_sdenv_stage.txt');
fs.writeFileSync(STAGE_LOG, 'start\n');
function stage(s) { fs.appendFileSync(STAGE_LOG, s + '\n'); }
const watchdog = setTimeout(() => {
  stage('WATCHDOG_TIMEOUT');
  console.error('[sdenv_extract] 看门狗超时，强制退出');
  process.exit(2);
}, 270000);

// sdenv 用绝对路径 require（其 index.js 内部用相对路径加载 browser/utils，不受 cwd 影响）
const SDENV_DIR = 'F:\\AICode\\逆向工具\\sdenv-main\\sdenv-main';
const { jsdomFromText, browser } = require(SDENV_DIR);

const HERE = __dirname;
const RAW = path.join(HERE, 'raw', 'acrawler.js');
const OUT = path.join(HERE, 'sdenv_capture.json');

const TARGET_URL = 'https://www.toutiao.com/?wid=1783780226601';

function log(...a) { console.log('[sdenv_extract]', ...a); stage(a.map(String).join(' ')); }

function main() {
  const src = fs.readFileSync(RAW, 'utf8');
  log('acrawler.js 长度=%d', src.length);

  // ---- 1. 用 sdenv 构造高保真 Chrome 环境 ----
  const dom = jsdomFromText('<!DOCTYPE html><html><head></head><body></body></html>', {
    url: TARGET_URL,
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    browserType: 'chrome',
  });
  // browser() 在 Node/jsdom 下可能尝试 redefine 不可配置的原型属性（如 String.prototype.replace）
  // 而抛错并中断增强。这里临时把 Object.defineProperty 变为“不可配置则跳过”，让增强完整跑完，
  // 为 acrawler 提供 canvas/audio/webgl 等指纹所需的 mock，再恢复原实现。
  let sdenv = null;
  const _def = Object.defineProperty;
  try {
    Object.defineProperty = function (obj, prop, desc) {
      try { return _def(obj, prop, desc); }
      catch (e) { return obj; } // 跳过不可重定义的属性（如原生 replace）
    };
    sdenv = browser(dom.window, 'chrome');
    log('sdenv browser() 增强成功');
  } catch (e) {
    log('WARN: sdenv browser() 增强失败（%s），回退到原生 jsdom window', e.message);
  } finally {
    Object.defineProperty = _def;
  }
  log('navigator.userAgent=%s',
      (dom.window.navigator && dom.window.navigator.userAgent || '').slice(0, 60));

  // ---- 2. 插桩 ----
  // 2a. 入口包裹 b：每次 _$jsvmprt(b,...) 都把 b 包成 Proxy，记录所有单字节读
  const ENTRY_NEEDLE = '(glb="undefined"==typeof window?global:window)._$jsvmprt=function(b,e,f){';
  if (!src.includes(ENTRY_NEEDLE)) throw new Error('未找到入口定义（版本可能已变）');
  let patched = src.replace(ENTRY_NEEDLE,
    '(glb="undefined"==typeof window?global:window)._$jsvmprt=function(b,e,f){ b=window.__wrapBytecode(b);');

  // 2b. 派发点日志：j / x / A / O
  const DISPATCH_NEEDLE = 'var A=3&(x=13*j%241);';
  if (!patched.includes(DISPATCH_NEEDLE)) throw new Error('未找到派发点（版本可能已变）');
  patched = patched.split(DISPATCH_NEEDLE).join(
    'var A=3&(x=13*j%241);window.__DBG_da(j,x,A,O);');

  // 2c. 暴露常量池（解码后的 i.p / i.q 与 XOR 密钥 r），便于在 Node 侧重建 strpool
  const RETURN_NEEDLE = 'return K(b,E,O/2,[],e,f);';
  if (!patched.includes(RETURN_NEEDLE)) throw new Error('未找到入口 return K(...)（版本可能已变）');
  patched = patched.replace(RETURN_NEEDLE,
    'window.__i=i;window.__r=r;return K(b,E,O/2,[],e,f);');

  // 2d. 顶部注入插桩函数与日志数组（window 即 vm 上下文全局）
  const HEAD = `
window.__bytelog = [];
window.__dispatch = [];
window.__wrapBytecode = function(b){
  var log = window.__bytelog;
  var isStr = (typeof b === 'string');
  var target = isStr ? new String(b) : b;
  return new Proxy(target, {
    get: function(t, prop){
      if (prop !== 'length' && typeof prop === 'string' && /^\\d+$/.test(prop)) {
        var raw = t[prop];
        var ch = isStr ? String(raw) : String.fromCharCode(raw & 0xff);
        log.push({pc:+prop, ch:ch});
      }
      return t[prop];
    }
  });
};
window.__DBG_da = function(j,x,A,O){
  window.__dispatch.push({j:j,x:x,A:A,O:O});
  // 心跳：每 500 步打印当前步数/pc，用于在 stdout 中定位死循环位置
  if ((window.__dispatch.length % 500) === 0) {
    console.log('HB step=' + window.__dispatch.length + ' O=' + O);
  }
};
`;
  const full = HEAD + '\n' + patched;

  // ---- 3. 在 sdenv 窗口上下文执行 acrawler.js（初始化 byted_acrawler） ----
  stage('before_eval_acrawler');
  const ctx = dom.getInternalVMContext();
  vm.runInContext(full, ctx, { filename: 'acrawler.js' });
  stage('after_eval_acrawler');
  log('acrawler.js 执行完成（初始化 byted_acrawler）');

  // 校验 byted_acrawler 是否就绪
  const hasSign = (function () {
    try {
      const w = dom.window;
      return typeof w.byted_acrawler !== 'undefined' &&
             typeof w.byted_acrawler.sign === 'function';
    } catch (e) { return false; }
  })();
  if (!hasSign) throw new Error('byted_acrawler.sign 未就绪（初始化可能失败）');
  log('byted_acrawler.sign 就绪');

  // ---- 4. 清空日志 -> 触发 sign -> 只保留本次执行的轨迹 ----
  stage('before_sign');
  dom.window.__bytelog.length = 0;
  dom.window.__dispatch.length = 0;

  let sig = dom.window.byted_acrawler.sign({ url: TARGET_URL });
  stage('after_sign_call');

  // sign 可能返回 Promise（新版）或字符串（老版）
  const handle = (result) => {
    const signature = (typeof result === 'string') ? result : '';
    // ---- 5. 重建常量池 strpool ----
    const i = dom.window.__i;
    const r = dom.window.__r;
    const strpool = {};
    if (i && i.q && i.p) {
      for (let z = 0; z < i.q.length; z++) {
        let s = '';
        for (let P = i.q[z][0]; P < i.q[z][1]; P++) {
          s += String.fromCharCode((r & 0xff) ^ (i.p[P] & 0xff));
        }
        strpool[z] = s;
      }
    }
    const out = {
      url: TARGET_URL,
      signature: signature,
      bytelog: dom.window.__bytelog,
      dispatch: dom.window.__dispatch,
      strpool: strpool,
      stats: {
        bytelog_len: dom.window.__bytelog.length,
        dispatch_len: dom.window.__dispatch.length,
        strpool_len: Object.keys(strpool).length,
        first_pc: dom.window.__bytelog.length ? dom.window.__bytelog[0].pc : null,
        last_pc: dom.window.__bytelog.length ? dom.window.__bytelog[dom.window.__bytelog.length - 1].pc : null,
      },
    };
    fs.writeFileSync(OUT, JSON.stringify(out));
    log('已落盘: %s', OUT);
    log('signature=%s', signature);
    log('bytelog=%d, dispatch=%d, strpool=%d, pc范围=[%s..%s]',
        out.stats.bytelog_len, out.stats.dispatch_len, out.stats.strpool_len,
        out.stats.first_pc, out.stats.last_pc);
  };

  if (sig && typeof sig.then === 'function') {
    log('sign 返回 Promise，等待解析...');
    sig.then(handle).catch((e) => { throw new Error('sign Promise reject: ' + e); });
  } else {
    handle(sig);
  }
}

try {
  main();
} catch (e) {
  log('ERROR: ' + (e && e.stack ? e.stack : e));
  process.exit(1);
}
