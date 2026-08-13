// refresh_browser_fingerprint.js — 采集浏览器指纹并写入 browser_fingerprint.json
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');

const HERE = __dirname;
const OUT = path.join(HERE, 'browser_fingerprint.json');
const BACKEND_HOST = process.env.CRYPTO_HUNTER_HOST || '127.0.0.1';
const BACKEND_PORT = Number(process.env.CRYPTO_HUNTER_PORT || 27183);

function post(apiPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: apiPath,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

async function main() {
  const code = fs.readFileSync(path.join(HERE, 'dump_browser_fingerprint.js'), 'utf8')
    .replace(/^\/\/[^\n]*\n/, '')
    .trim();

  console.log('[fingerprint] 采集浏览器 ENV_OVERRIDE ...');
  const out = await post('/api/browser/page/run-js', {
    code,
    as_expr: true,
    return_mode: 'json',
    timeout_sec: 30,
  });

  const r = out.result || out.data?.result;
  if (!r || !r.ok) {
    console.error('[fingerprint] 失败:', JSON.stringify(out).slice(0, 500));
    process.exit(2);
  }

  const snap = {
    _meta: { source: 'dump_browser_fingerprint', ts: new Date().toISOString(), url: r.url },
    env_override: r.env_override,
    raw: r.raw,
    me24_head: r.me24_head,
  };

  fs.writeFileSync(OUT, JSON.stringify(snap, null, 2));
  console.log('[fingerprint] 已写入 browser_fingerprint.json');
  console.log('[fingerprint] me24_head =', r.me24_head);
}

main().catch((err) => {
  console.error('[fingerprint] ERROR:', err.message || err);
  process.exit(1);
});
