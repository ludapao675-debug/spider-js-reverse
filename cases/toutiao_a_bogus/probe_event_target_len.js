// probe_event_target_len.js — 验证 EventTarget 补丁 + me[2] 喂点能否抬升 Node 签长
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');
const { hardenAbogusShim, waitEnvReady } = require('./shim_abogus_harden');
const { fireMouseMoves, feedMe2Behavior } = require('./shim_event_target');
const { seedLocalStorage, readCache, importFromSnapshot } = require('./mstoken_store');

const HERE = __dirname;
const BDMS = fs.readFileSync(path.join(HERE, 'raw', 'bdms.js'), 'utf8');
const FEED =
  'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784622000&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web';

async function runCase(label, opts) {
  const g = makeBrowserShim('https://www.toutiao.com/', null);
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;
  const hard = hardenAbogusShim(g);
  if (!readCache()) importFromSnapshot();
  seedLocalStorage(g, { allowStale: true });

  // 统计 bdms 是否真的挂上了 listener，并记录 type
  let listenerAdds = 0;
  const listenerTypes = [];
  const _add = g.document.addEventListener;
  g.document.addEventListener = function (type, fn, opt) {
    listenerTypes.push('doc:' + type);
    if (/mouse|pointer|touch|scroll/i.test(String(type))) listenerAdds++;
    return _add.call(this, type, fn, opt);
  };
  const _wadd = g.addEventListener;
  g.addEventListener = function (type, fn, opt) {
    listenerTypes.push('win:' + type);
    if (/mouse|pointer|touch|scroll/i.test(String(type))) listenerAdds++;
    return _wadd.call(this, type, fn, opt);
  };

  vm.runInContext(BDMS, vm.createContext(g), { timeout: 90000, filename: 'bdms.js' });
  g.bdms.init({ aid: 24, pageId: 6457, paths: ['/api/pc/list/feed', '/api/pc/list/user/feed'] });

  let mouse = null;
  let me2 = null;
  if (opts.mouse) mouse = fireMouseMoves(g, { rounds: opts.mouseRounds || 10, perRound: 40 });
  await waitEnvReady(opts.waitMs != null ? opts.waitMs : 4500);
  if (opts.mouseAfter) mouse = fireMouseMoves(g, { rounds: opts.mouseAfter || 5, perRound: 30 });
  if (opts.feedMe2) me2 = feedMe2Behavior(g, opts.feedMe2);

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', FEED);
  xhr.send();
  const signed = xhr.responseURL || xhr._url || FEED;
  const m = String(signed).match(/[?&]a_bogus=([^&]+)/);
  const ab = m ? decodeURIComponent(m[1]) : null;

  return {
    label,
    len: ab ? ab.length : 0,
    head: ab ? ab.slice(0, 40) : null,
    me23: g.bdms.init._v[2][23],
    listenerAdds,
    listenerTypes,
    events_patched: hard.flags && hard.flags.events_patched,
    mouse,
    me2,
  };
}

async function main() {
  const cases = [
    { label: 'baseline_events_only', opts: { waitMs: 4000 } },
    { label: 'mousemove_dispatch', opts: { waitMs: 4000, mouse: true, mouseRounds: 10, mouseAfter: 6 } },
    { label: 'me2_feed_80', opts: { waitMs: 3500, feedMe2: 80 } },
    { label: 'mouse_plus_me2', opts: { waitMs: 4500, mouse: true, mouseRounds: 12, mouseAfter: 8, feedMe2: 120 } },
  ];
  const results = [];
  for (const c of cases) {
    console.error('[case]', c.label);
    // eslint-disable-next-line no-await-in-loop
    const r = await runCase(c.label, c.opts);
    results.push(r);
    console.error('  -> len=%d listeners=%d', r.len, r.listenerAdds);
  }
  const out = { ts: new Date().toISOString(), results };
  fs.writeFileSync(path.join(HERE, 'probe_event_target_len_out.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
