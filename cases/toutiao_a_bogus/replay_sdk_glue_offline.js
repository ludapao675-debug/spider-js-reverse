// replay_sdk_glue_offline.js — Node 加载 bdms + sdk-glue，走 XHR 链签名
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');

const HERE = __dirname;
const RAW_BDMS = path.join(HERE, 'raw', 'bdms.js');
const RAW_GLUE = path.join(HERE, '..', 'toutiao_acrawler', 'raw', 'sdk-glue.js');
const TIMEOUT = 90000;

const INPUT_URL = process.argv[2]
  || 'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web&msToken=test';

/** 安装 XHR 追踪 */
function installXhrTrace(g) {
  const trace = [];
  g.__xhr_trace = trace;
  const NativeXHR = g.XMLHttpRequest;

  function wrap(name, fn) {
    return function (...args) {
      trace.push({ phase: name, args: args.map((a) => (typeof a === 'string' ? a.slice(0, 120) : typeof a)) });
      return fn.apply(this, args);
    };
  }

  // 保留原生构造，但 trace open/send
  const Orig = NativeXHR;
  g.XMLHttpRequest = function XMLHttpRequest() {
    const x = new Orig();
    const open0 = x.open.bind(x);
    const send0 = x.send.bind(x);
    x.open = wrap('open', open0);
    x.send = wrap('send', send0);
    return x;
  };
  g.XMLHttpRequest.prototype = Orig.prototype;
  Object.setPrototypeOf(g.XMLHttpRequest, Orig);
}

/** 模拟 sdk-glue 动态加载 bdms（避免重复拉 CDN） */
function patchDynamicLoader(g) {
  g.__loaded_scripts = g.__loaded_scripts || {};
  const origCreate = g.document.createElement.bind(g.document);
  g.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() === 'script') {
      let _src = '';
      Object.defineProperty(el, 'src', {
        configurable: true,
        enumerable: true,
        get() { return _src; },
        set(url) {
          _src = url;
          if (/bdms\.js/i.test(url)) {
            // bdms 已在上下文 eval，标记 Loaded
            g.__loaded_scripts.bdms = true;
            if (el.onload) setTimeout(el.onload, 0);
            if (el.onreadystatechange) setTimeout(() => el.onreadystatechange(), 0);
          }
        },
      });
      el.setAttribute = function (k, v) {
        if (k === 'src') el.src = v;
      };
    }
    return el;
  };
}

function loadScripts(g) {
  const ctx = vm.createContext(g);
  patchDynamicLoader(g);

  console.log('[glue] 加载 bdms.js ...');
  vm.runInContext(fs.readFileSync(RAW_BDMS, 'utf8'), ctx, { filename: 'bdms.js', timeout: TIMEOUT });

  if (typeof g.bdms?.init !== 'function') {
    throw new Error('bdms.init 未就绪');
  }

  console.log('[glue] 加载 sdk-glue.js ...');
  vm.runInContext(fs.readFileSync(RAW_GLUE, 'utf8'), ctx, { filename: 'sdk-glue.js', timeout: TIMEOUT });

  return ctx;
}

/** 手动 bdms.init（与页面/article 一致） */
function manualInit(g) {
  const cfg = {
    aid: 24,
    pageId: 6457,
    boe: false,
    ddrt: 3,
    paths: { include: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    track: {},
    dump: true,
    rpU: '',
  };
  try {
    g.bdms.init(cfg);
    console.log('[glue] bdms.init 完成');
  } catch (e) {
    console.warn('[glue] bdms.init 异常:', e.message);
  }
}

function patchSnapshot(g) {
  const snapPath = path.join(HERE, 'browser_env_snapshot.json');
  if (!fs.existsSync(snapPath)) return;
  const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !snap.init_me) return;
  for (let i = 0; i < snap.init_me.length; i++) {
    const v = snap.init_me[i];
    if (v == null || (v && v.__fn)) continue;
    if (typeof v === 'object' && !Array.isArray(v)) initMe[i] = JSON.parse(JSON.stringify(v));
    else if (typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') initMe[i] = v;
  }
  console.log('[glue] 已注入 browser_env_snapshot init_me');
}

function main() {
  const g = makeBrowserShim('https://www.toutiao.com/article/7664136988722790964/');
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  // sdk-glue 版本门控
  g._SdkGlueInit = true;
  g._sdkGlueVersionMap = { sdkGlueVersion: '1.0.0.55' };

  installXhrTrace(g);
  loadScripts(g);
  manualInit(g);
  patchSnapshot(g);

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', INPUT_URL);
  xhr.send();

  const final = xhr.responseURL || INPUT_URL;
  const m = final.match(/[?&]a_bogus=([^&]+)/);
  const abogus = m ? decodeURIComponent(m[1]) : null;

  console.log('INPUT :', INPUT_URL.slice(0, 100));
  console.log('FINAL :', final.slice(0, 140));
  console.log('a_bogus:', abogus ? `${abogus.slice(0, 72)}... len=${abogus.length}` : null);
  console.log('trace:', JSON.stringify(g.__xhr_trace, null, 2));

  if (!abogus || abogus.length < 80) process.exit(2);
}

main();
