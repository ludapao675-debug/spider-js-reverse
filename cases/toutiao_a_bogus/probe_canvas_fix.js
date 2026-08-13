// probe_canvas_fix.js — 对齐真实 PNG toDataURL / OfflineAudio / UA-CH，探测能否产出 176
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784599930&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

// 1x1 透明 PNG（合法 magic）；也可换成活体采集的长 dataURL
const PNG_1X1 =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

function loadLiveCanvasFixture() {
  const p = path.join(HERE, 'live_canvas_dataurl.txt');
  if (fs.existsSync(p)) return fs.readFileSync(p, 'utf8').trim();
  return null;
}

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

function patchInitEnv(g) {
  const snapPath = path.join(HERE, 'browser_env_snapshot.json');
  if (!fs.existsSync(snapPath)) return 0;
  const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;
  let patched = 0;
  for (let i = 0; i < initMeSrc.length; i++) {
    const v = initMeSrc[i];
    if (v == null || (v && v.__fn)) continue;
    if (v && v.items && typeof v.front === 'number') {
      initMe[i] = {
        items: v.items.slice(),
        front: v.front || 0,
        rear: v.rear != null ? v.rear : v.items.length,
      };
    } else if (typeof v === 'object' && !Array.isArray(v)) {
      initMe[i] = JSON.parse(JSON.stringify(v));
    } else if (typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') {
      initMe[i] = v;
    } else continue;
    patched++;
  }
  return patched;
}

/** 强化垫片：合法 PNG、OfflineAudio、UA-CH 对齐 Chrome150 */
function hardenShim(g, opts = {}) {
  const dataUrl = opts.dataUrl || PNG_1X1;
  const access = (g.__env_access = []);

  // 补 HTMLCanvasElement 原型链（部分检测会看 constructor 名）
  function HTMLCanvasElement() {}
  g.HTMLCanvasElement = HTMLCanvasElement;

  const origCreate = g.document.createElement.bind(g.document);
  g.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() === 'canvas') {
      access.push('createElement:canvas');
      el.constructor = HTMLCanvasElement;
      const _getContext = el.getContext.bind(el);
      el.getContext = function (type) {
        access.push('getContext:' + type);
        const ctx = _getContext(type);
        if (ctx && type === '2d') {
          const _toData = el.toDataURL.bind(el);
          // canvas 自身 toDataURL 优先返回合法 PNG
          el.toDataURL = function () {
            access.push('canvas.toDataURL');
            return dataUrl;
          };
          if (typeof ctx.toDataURL === 'function') {
            ctx.toDataURL = el.toDataURL;
          }
        }
        return ctx;
      };
      el.toDataURL = function () {
        access.push('canvas.toDataURL');
        return dataUrl;
      };
    }
    return el;
  };

  // OfflineAudioContext：startRendering + getChannelData 非零
  function OfflineAudioContext(channels, length, sampleRate) {
    access.push('OfflineAudioContext');
    this.numberOfChannels = channels || 1;
    this.length = length || 44100;
    this.sampleRate = sampleRate || 44100;
    this.destination = {};
    this.currentTime = 0;
    this.state = 'suspended';
  }
  OfflineAudioContext.prototype.createOscillator = function () {
    return {
      type: 'triangle',
      frequency: { value: 10000, setValueAtTime() {} },
      connect() {},
      start() {},
      stop() {},
    };
  };
  OfflineAudioContext.prototype.createDynamicsCompressor = function () {
    return {
      threshold: { value: -50 },
      knee: { value: 40 },
      ratio: { value: 12 },
      reduction: { value: -20 },
      attack: { value: 0 },
      release: { value: 0.25 },
      connect() {},
    };
  };
  OfflineAudioContext.prototype.createAnalyser = function () {
    return {
      frequencyBinCount: 1024,
      getFloatFrequencyData(a) {
        if (a) for (let i = 0; i < a.length; i++) a[i] = -90 + (i % 40);
      },
      connect() {},
    };
  };
  OfflineAudioContext.prototype.startRendering = function () {
    access.push('OfflineAudio.startRendering');
    const ch = this.numberOfChannels;
    const len = this.length;
    const buf = {
      numberOfChannels: ch,
      length: len,
      sampleRate: this.sampleRate,
      duration: len / this.sampleRate,
      getChannelData(i) {
        access.push('getChannelData:' + i);
        const arr = new Float32Array(len);
        for (let j = 0; j < len; j++) {
          // 非零音频指纹
          arr[j] = Math.sin(j * 0.01 + i) * 0.1 + ((((j * 2654435761) >>> 0) & 0xff) / 2550);
        }
        return arr;
      },
    };
    return Promise.resolve(buf);
  };
  g.OfflineAudioContext = OfflineAudioContext;
  g.webkitOfflineAudioContext = OfflineAudioContext;

  // UA Client Hints 对齐 Chrome 150（与活体 fingerprint 一致）
  if (g.navigator) {
    g.navigator.userAgent =
      opts.ua ||
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36';
    g.navigator.appVersion =
      '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36';
    g.navigator.userAgentData = {
      brands: [
        { brand: 'Not;A=Brand', version: '8' },
        { brand: 'Chromium', version: '150' },
        { brand: 'Google Chrome', version: '150' },
      ],
      mobile: false,
      platform: 'Windows',
      getHighEntropyValues: () =>
        Promise.resolve({
          architecture: 'x86',
          bitness: '64',
          model: '',
          platformVersion: '15.0.0',
          uaFullVersion: '150.0.0.0',
          wow64: false,
        }),
    };
  }

  // 屏幕对齐活体
  if (g.screen && opts.screen) Object.assign(g.screen, opts.screen);
  if (opts.dpr != null) g.devicePixelRatio = opts.dpr;
  if (opts.innerWidth) {
    g.innerWidth = opts.innerWidth;
    g.innerHeight = opts.innerHeight || g.innerHeight;
    g.outerWidth = opts.outerWidth || opts.innerWidth;
    g.outerHeight = opts.outerHeight || opts.innerHeight || g.outerHeight;
  }

  // 嵌套 performance.memory（fingerprint 里的点号键无效）
  if (!g.performance) g.performance = { now: () => Date.now(), timing: { navigationStart: Date.now() } };
  g.performance.memory = {
    usedJSHeapSize: 23898516,
    totalJSHeapSize: 25165916,
    jsHeapSizeLimit: 4395630592,
  };

  return access;
}

function signOnce(label, hardenOpts = {}, useEnvOverride = false) {
  let envOverride = null;
  if (useEnvOverride) {
    try {
      envOverride = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_fingerprint.json'), 'utf8')).env_override;
    } catch (e) {
      /* ignore */
    }
  }
  const g = makeBrowserShim('https://www.toutiao.com/', envOverride);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  const access = hardenShim(g, hardenOpts);
  vm.runInContext(BDMS, vm.createContext(g), { timeout: 60000, filename: 'bdms.js' });
  g.bdms.init({
    aid: 24,
    pageId: 6457,
    paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'],
  });
  patchInitEnv(g);

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);
  const row = {
    label,
    len: ab ? ab.length : 0,
    raw: raw ? raw.length : 0,
    head: ab ? ab.slice(0, 40) : null,
    anchor5f5: !!(ab && ab.includes('5f5LfY3qV')),
    access: access.slice(0, 40),
    access_n: access.length,
  };
  console.log(JSON.stringify(row));
  return row;
}

async function main() {
  const live = loadLiveCanvasFixture();
  const results = [];
  const cases = [
    ['baseline_no_harden', null, false],
    ['png1x1', { dataUrl: PNG_1X1 }, false],
    ['png1x1_screen', { dataUrl: PNG_1X1, dpr: 1, screen: { width: 2560, height: 1600, availWidth: 2560, availHeight: 1600 }, innerWidth: 1904, innerHeight: 929 }, false],
  ];
  if (live) {
    cases.push(['live_canvas', { dataUrl: live, dpr: 1, screen: { width: 2560, height: 1600, availWidth: 2560, availHeight: 1600 }, innerWidth: 1904, innerHeight: 929 }, false]);
    cases.push(['live_canvas_plus_fp', { dataUrl: live, dpr: 1, screen: { width: 2560, height: 1600, availWidth: 2560, availHeight: 1600 }, innerWidth: 1904, innerHeight: 929 }, true]);
  }

  for (const [label, opts, useFp] of cases) {
    try {
      results.push(signOnce(label, opts || {}, useFp));
    } catch (e) {
      console.log(JSON.stringify({ label, err: String(e && e.message ? e.message : e) }));
    }
  }

  fs.writeFileSync(path.join(HERE, 'probe_canvas_fix_out.json'), JSON.stringify(results, null, 2));
  console.log('[probe] done, best len=', Math.max(...results.map((r) => r.len || 0)));
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
