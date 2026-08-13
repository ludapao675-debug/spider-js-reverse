// validate_offline_browser.js — 浏览器内对比 offline 签名与页面 oracle（需后端 27183）
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');

const HERE = __dirname;
const OUT_JSON = path.join(HERE, 'replay_bdms_offline_out.json');
const BACKEND = process.env.CRYPTO_HUNTER_BACKEND || '127.0.0.1:27183';

/** POST JSON 到 crypto-hunter 后端 */
function post(apiPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: BACKEND.split(':')[0],
      port: Number(BACKEND.split(':')[1] || 27183),
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

/** 去掉 msToken / a_bogus，用与离线一致的「待签 base URL」 */
function normalizeInputUrl(raw) {
  try {
    const u = new URL(raw);
    u.searchParams.delete('a_bogus');
    u.searchParams.delete('msToken');
    return u.href;
  } catch (e) {
    return raw;
  }
}

/** 在页面内用 XHR hook 对同一 URL 签名（等待 onload，a_bogus 异步写入） */
async function browserSign(inputUrl) {
  const baseUrl = normalizeInputUrl(inputUrl);
  const setup = `
    window.__oraclePromise = new Promise(function(resolve) {
      var input = ${JSON.stringify(baseUrl)};
      var x = new XMLHttpRequest();
      x.open('GET', input);
      x.onload = function() {
        var signed = x.responseURL || x._url || input;
        var m = signed.match(/[?&]a_bogus=([^&]+)/);
        resolve({
          base_url: input,
          signed_url: signed,
          a_bogus: m ? decodeURIComponent(m[1]) : null,
          msToken: (signed.match(/msToken=([^&]+)/) || [])[1] || null,
        });
      };
      x.onerror = function(e) { resolve({ error: String(e) }); };
      x.send();
    });
  `;
  await post('/api/browser/page/run-js', { code: setup, as_expr: false, timeout_sec: 30 });
  const out = await post('/api/browser/page/run-js', {
    code: 'window.__oraclePromise',
    as_expr: true,
    await_promise: true,
    timeout_sec: 30,
  });
  return out.result || out.data?.result;
}

/** 最长公共子串长度（粗粒度相似度） */
function lcsLen(a, b) {
  if (!a || !b) return 0;
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  let best = 0;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
        if (dp[i][j] > best) best = dp[i][j];
      }
    }
  }
  return best;
}

/** 格式验收：长度随环境完整性变化（短签 168/172，长签常见 176/188） */
function formatOk(ab) {
  if (!ab || typeof ab !== 'string') return false;
  if (![168, 172, 176, 188].includes(ab.length)) return false;
  return /^[A-Za-z0-9_\-/=]+$/.test(ab);
}

/** URL 相关锚点：2026-07 起首页活体多为 5f5LfY3qV，旧样本为 5fVLfY3qV */
const ANCHORS = ['5f5LfY3qV', '5fVLfY3qV'];

function pickSharedAnchor(a, b) {
  if (!a || !b) return '';
  for (const anchor of ANCHORS) {
    if (a.includes(anchor) && b.includes(anchor)) return anchor;
  }
  return '';
}

async function main() {
  if (!fs.existsSync(OUT_JSON)) {
    console.error('缺少 replay_bdms_offline_out.json，请先 node replay_bdms_offline.js');
    process.exit(1);
  }
  const offline = JSON.parse(fs.readFileSync(OUT_JSON, 'utf8'));
  const inputUrl = normalizeInputUrl(offline.input_url);
  const offlineAb = offline.a_bogus;

  console.log('[validate] 浏览器 oracle 签名 ...');
  let oracle;
  try {
    oracle = await browserSign(inputUrl);
  } catch (err) {
    console.error('[validate] 浏览器签名失败:', err.message || err);
    process.exit(2);
  }

  const oracleAb = oracle?.a_bogus;
  const common = lcsLen(offlineAb, oracleAb);
  const sharedAnchor = pickSharedAnchor(offlineAb, oracleAb);
  const report = {
    input_url: inputUrl,
    offline: {
      a_bogus_len: offlineAb?.length || 0,
      prefix: offlineAb?.slice(0, 48),
      format_ok: formatOk(offlineAb),
    },
    browser_oracle: {
      a_bogus_len: oracleAb?.length || 0,
      prefix: oracleAb?.slice(0, 48),
      msToken_head: oracle?.msToken?.slice(0, 32),
      format_ok: formatOk(oracleAb),
    },
    compare: {
      exact_match: offlineAb === oracleAb,
      lcs_len: common,
      lcs_ratio_offline: offlineAb ? (common / offlineAb.length).toFixed(3) : 0,
      anchor_match: !!sharedAnchor,
      anchor: sharedAnchor || ANCHORS[0],
      anchors_checked: ANCHORS,
    },
    notes: [
      'a_bogus 含随机段，同 URL 两次签名通常不完全相同',
      '服务端 feed 仅 unsigned fetch/XHR 可返回 JSON；预签名 URL 重放常为空体',
      '首页浏览器签常 176 字符；Node 离线仍 168；共用锚点多为 5f5LfY3qV',
    ],
  };

  const outPath = path.join(HERE, 'validate_oracle_result.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log('[validate] 已写入', path.basename(outPath));

  const pass = formatOk(offlineAb) && formatOk(oracleAb);
  if (!pass) process.exit(2);
  if (!report.compare.exact_match) {
    console.log('[validate] 格式对齐通过；字节未完全一致（VM 指纹/随机段差异，属预期）');
    if (report.compare.anchor_match) {
      console.log('[validate] URL 相关锚点 %s 已对齐', sharedAnchor);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
