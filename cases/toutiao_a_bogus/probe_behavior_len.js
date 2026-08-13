// probe_behavior_len.js — 模拟鼠标/滚动，观察 Node a_bogus 是否从 168 抬升
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');
const { seedLocalStorage, readCache, importFromSnapshot } = require('./mstoken_store');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784621000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

function fireBehavior(g, rounds) {
  const doc = g.document;
  for (let r = 0; r < rounds; r++) {
    for (let i = 0; i < 50; i++) {
      const x = 80 + i * 19 + r * 3;
      const y = 100 + ((i * 11) % 400);
      try {
        const Ev = g.MouseEvent || function MouseEvent(type, init) {
          this.type = type;
          Object.assign(this, init || {});
        };
        const ev = new Ev('mousemove', { clientX: x, clientY: y, bubbles: true });
        if (typeof doc.dispatchEvent === 'function') doc.dispatchEvent(ev);
        else if (doc.onmousemove) doc.onmousemove(ev);
      } catch (e) {
        /* ignore */
      }
    }
  }
}

async function signAfter(label, opts) {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  hardenAbogusShim(g);
  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });

  if (opts.behaviorRounds) {
    fireBehavior(g, opts.behaviorRounds);
  }
  await waitEnvReady(opts.waitMs != null ? opts.waitMs : 4000);
  if (opts.behaviorAfterWait) {
    fireBehavior(g, opts.behaviorAfterWait);
    await new Promise((r) => setTimeout(r, 500));
  }

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;
  return {
    label,
    len: ab ? ab.length : 0,
    head: ab ? ab.slice(0, 48) : null,
    me23: g.bdms.init._v[2][23],
  };
}

async function main() {
  const cases = [
    { label: 'wait4_no_mouse', opts: { waitMs: 4000, behaviorRounds: 0 } },
    { label: 'mouse3_wait4', opts: { waitMs: 4000, behaviorRounds: 3 } },
    { label: 'mouse8_wait6', opts: { waitMs: 6000, behaviorRounds: 8, behaviorAfterWait: 3 } },
    { label: 'mouse15_wait8', opts: { waitMs: 8000, behaviorRounds: 15, behaviorAfterWait: 5 } },
  ];
  const results = [];
  for (const c of cases) {
    console.error('[case]', c.label);
    // eslint-disable-next-line no-await-in-loop
    const r = await signAfter(c.label, c.opts);
    results.push(r);
    console.error('  ->', r.len);
  }
  const out = { ts: new Date().toISOString(), note: 'live climbs 168→172→176 with mouse; test Node', results };
  fs.writeFileSync(path.join(HERE, 'probe_behavior_len_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
