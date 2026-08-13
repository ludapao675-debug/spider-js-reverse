// browser_capture_ye.js — 注入 early hook → 刷新 → dump ye 环境
'use strict';
const fs = require('fs');
const http = require('http');
const path = require('path');

const HERE = __dirname;
const BID = process.env.BROWSER_ID || '5528b4bd-701f-46a9-994e-ed644716d566';
const TID = process.env.TAB_ID || 'B8E50D2AE0C8B35754BBBA25427A04FF';

function post(apiPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: '127.0.0.1',
      port: 27183,
      path: apiPath,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
    }, (res) => {
      let d = '';
      res.on('data', (c) => { d += c; });
      res.on('end', () => {
        try { resolve(JSON.parse(d)); } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

function readJs(name) {
  return fs.readFileSync(path.join(HERE, name), 'utf8').replace(/^\/\/[^\n]*\n/, '').trim();
}

async function main() {
  const source = fs.readFileSync(path.join(HERE, 'early_hook_bdms_patch.js'), 'utf8');
  const inj = await post('/api/browser/page/inject-early', {
    source, action: 'add', run_immediately: true, browser_id: BID, tab_id: TID,
  });
  console.log('[capture] inject early:', inj.ok, inj.identifier || inj.data?.identifier);

  await new Promise((r) => setTimeout(r, 1500));

  const nav = await post('/api/browser/page/navigate', {
    url: 'https://www.toutiao.com/article/7664136988722790964/',
    wait_until: 'domcontentloaded',
    timeout_sec: 60,
    browser_id: BID,
    tab_id: TID,
  });
  console.log('[capture] navigate:', nav.ok, nav.tab?.url || nav.data?.tab?.url, nav.error);

  await new Promise((r) => setTimeout(r, 4000));

  const dump = await post('/api/browser/page/run-js', {
    code: readJs('dump_ye_env.js'),
    as_expr: true,
    return_mode: 'json',
    timeout_sec: 30,
    browser_id: BID,
    tab_id: TID,
  });
  const r = dump.result;
  if (!r || !r.ok) {
    console.error('[capture] dump failed:', JSON.stringify(dump).slice(0, 500));
    process.exit(2);
  }

  console.log('[capture] ye:', r.ye_from_window, 'pc:', r.ye_pc, 'test:', r.ye_test);
  console.log('[capture] init me24:', r.init_v?.[24]);

  const snap = {
    _meta: { source: 'dump_ye_env+early_patch', ts: new Date().toISOString(), url: r.url },
    init_me: r.init_v,
    sign_fn_me: r.ye_me,
    sign_fn_pc: r.ye_pc,
    ye_test: r.ye_test,
  };
  fs.writeFileSync(path.join(HERE, 'browser_env_snapshot.json'), JSON.stringify(snap, null, 2));
  console.log('[capture] saved browser_env_snapshot.json, ye_me slots:', r.ye_me ? Object.keys(r.ye_me).length : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
