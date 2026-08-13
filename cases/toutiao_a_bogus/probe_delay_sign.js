// probe_delay_sign.js — 验证：init 后延迟/触发环境采集，是否能把 a_bogus 拉到 176
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784599930&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function decodeAb(ab) {
  if (!ab) return null;
  let s = ab.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

function patchInitEnv(g) {
  const snap = JSON.parse(fs.readFileSync(path.join(HERE, 'browser_env_snapshot.json'), 'utf8'));
  const initMeSrc = snap.init_me || snap.init_v;
  const initMe = g.bdms?.init?._v?.[2];
  if (!initMe || !initMeSrc) return 0;
  let n = 0;
  for (let i = 0; i < initMeSrc.length; i++) {
    const v = initMeSrc[i];
    if (v == null || (v && v.__fn)) continue;
    if (v && v.items && typeof v.front === 'number') {
      initMe[i] = { items: v.items.slice(), front: v.front || 0, rear: v.rear != null ? v.rear : v.items.length };
    } else if (typeof v === 'object' && !Array.isArray(v)) initMe[i] = JSON.parse(JSON.stringify(v));
    else if (['boolean', 'number', 'string'].includes(typeof v)) initMe[i] = v;
    else continue;
    n++;
  }
  return n;
}

function installAccessLog(g) {
  const log = (g.__access = []);
  const wrapGet = (obj, key, tag) => {
    try {
      const desc = Object.getOwnPropertyDescriptor(obj, key);
      if (!desc || !desc.configurable) return;
      let val = obj[key];
      Object.defineProperty(obj, key, {
        configurable: true,
        enumerable: true,
        get() {
          log.push(tag);
          return val;
        },
        set(v) {
          val = v;
        },
      });
    } catch (e) {
      /* ignore */
    }
  };
  wrapGet(g, 'OfflineAudioContext', 'g.OfflineAudioContext');
  wrapGet(g, 'AudioContext', 'g.AudioContext');
  wrapGet(g.navigator || {}, 'plugins', 'nav.plugins');
  wrapGet(g.navigator || {}, 'userAgentData', 'nav.userAgentData');
  const origCreate = g.document.createElement.bind(g.document);
  g.document.createElement = function (tag) {
    log.push('create:' + tag);
    return origCreate(tag);
  };
  return log;
}

function sign(g) {
  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  const raw = decodeAb(ab);
  return { len: ab ? ab.length : 0, raw: raw ? raw.length : 0, head: ab ? ab.slice(0, 40) : null, ab };
}

async function runCase(label, waitMs, poke) {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  // 完整 OfflineAudio
  g.OfflineAudioContext = function OfflineAudioContext(c, l, s) {
    this.numberOfChannels = c || 1;
    this.length = l || 44100;
    this.sampleRate = s || 44100;
    this.destination = {};
  };
  g.OfflineAudioContext.prototype.createOscillator = function () {
    return { connect() {}, start() {}, frequency: { value: 10000 }, type: 'triangle' };
  };
  g.OfflineAudioContext.prototype.createDynamicsCompressor = function () {
    return { threshold: { value: -50 }, knee: { value: 40 }, ratio: { value: 12 }, attack: { value: 0 }, release: { value: 0.25 }, connect() {} };
  };
  g.OfflineAudioContext.prototype.startRendering = function () {
    const len = this.length;
    return Promise.resolve({
      numberOfChannels: 1,
      length: len,
      getChannelData() {
        const a = new Float32Array(len);
        for (let i = 0; i < len; i++) a[i] = Math.sin(i * 0.01) * 0.1;
        return a;
      },
    });
  };
  g.webkitOfflineAudioContext = g.OfflineAudioContext;

  const log = installAccessLog(g);
  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });
  patchInitEnv(g);

  if (poke) {
    // 触发常见指纹路径
    try {
      const c = g.document.createElement('canvas');
      c.width = 300;
      c.height = 150;
      const ctx = c.getContext('2d');
      if (ctx) {
        ctx.fillText('test', 2, 2);
        c.toDataURL();
      }
      c.getContext('webgl');
    } catch (e) {
      /* ignore */
    }
    try {
      const ac = new g.OfflineAudioContext(1, 44100, 44100);
      await ac.startRendering();
    } catch (e) {
      /* ignore */
    }
  }

  if (waitMs > 0) {
    await new Promise((r) => setTimeout(r, waitMs));
    // 冲刷微任务 / 定时器
    await new Promise((r) => setImmediate(r));
  }

  const out = sign(g);
  const row = {
    label,
    waitMs,
    poke: !!poke,
    len: out.len,
    raw: out.raw,
    head: out.head,
    access_n: log.length,
    access_uniq: [...new Set(log)].slice(0, 30),
  };
  console.log(JSON.stringify(row));
  return row;
}

async function main() {
  const results = [];
  for (const [label, wait, poke] of [
    ['sync0', 0, false],
    ['wait200', 200, false],
    ['wait1000', 1000, false],
    ['wait3000', 3000, false],
    ['poke_sync', 0, true],
    ['poke_wait1000', 1000, true],
    ['poke_wait3000', 3000, true],
  ]) {
    try {
      results.push(await runCase(label, wait, poke));
    } catch (e) {
      console.log(JSON.stringify({ label, err: String(e && e.stack ? e.stack : e).slice(0, 300) }));
    }
  }
  fs.writeFileSync(path.join(HERE, 'probe_delay_sign_out.json'), JSON.stringify(results, null, 2));
  const best = results.reduce((a, b) => (b.len > (a.len || 0) ? b : a), { len: 0 });
  console.log('[probe] best', best.label, best.len, 'raw', best.raw);
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
