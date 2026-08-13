// validate_browser_unsigned_fetch.js — 浏览器内对未签名 URL fetch（服务端可用性 oracle）
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');

const HERE = __dirname;
const OUT_JSON = path.join(HERE, 'replay_bdms_offline_out.json');
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

/** 去掉 msToken / a_bogus，得到未签名 base URL */
function toUnsignedUrl(raw) {
  const u = new URL(raw);
  u.searchParams.delete('a_bogus');
  u.searchParams.delete('msToken');
  return u.href;
}

/** 浏览器内 fetch 未签名 URL（bdms hook 现场加签） */
async function browserUnsignedFetch(unsignedUrl) {
  const setup = `
    window.__unsignedFetchPromise = fetch(${JSON.stringify(unsignedUrl)})
      .then(function(r) { return r.text().then(function(t) {
        var msg = null, dc = 0;
        try { var j = JSON.parse(t); msg = j.message; dc = (j.data || []).length; } catch(e) {}
        return {
          status: r.status,
          final_url: r.url,
          body_len: t.length,
          message: msg,
          data_count: dc,
          has_abogus: r.url.indexOf('a_bogus=') >= 0,
          has_mstoken: r.url.indexOf('msToken=') >= 0,
        };
      }); })
      .catch(function(e) { return { error: String(e) }; });
  `;
  await post('/api/browser/page/run-js', { code: setup, as_expr: false, timeout_sec: 60 });
  const out = await post('/api/browser/page/run-js', {
    code: 'window.__unsignedFetchPromise',
    as_expr: true,
    await_promise: true,
    timeout_sec: 60,
  });
  return out.result || out.data?.result;
}

async function main() {
  const argUrl = process.argv.slice(2).find((a) => !a.startsWith('--'));
  let unsignedUrl = argUrl;
  if (!unsignedUrl && fs.existsSync(OUT_JSON)) {
    unsignedUrl = toUnsignedUrl(JSON.parse(fs.readFileSync(OUT_JSON, 'utf8')).input_url);
  }
  if (!unsignedUrl) {
    const ts = Math.floor(Date.now() / 1000);
    unsignedUrl = `https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=${ts}&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web`;
  } else {
    unsignedUrl = toUnsignedUrl(unsignedUrl);
  }

  console.log('[unsigned_fetch] URL:', unsignedUrl.slice(0, 120) + '...');
  let result;
  try {
    result = await browserUnsignedFetch(unsignedUrl);
  } catch (err) {
    console.error('[unsigned_fetch] 失败:', err.message || err);
    process.exit(2);
  }

  const report = {
    unsigned_url: unsignedUrl,
    result,
    ok: result && result.status === 200 && result.message === 'success' && (result.data_count || 0) > 0,
    note: '这是服务端可用性 oracle：仅未签名 URL + 浏览器 fetch 可返回 JSON；预签名 URL 重放无效',
  };

  const outPath = path.join(HERE, 'validate_unsigned_fetch_result.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log('[unsigned_fetch] 已写入', path.basename(outPath));

  if (!report.ok) process.exit(2);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
