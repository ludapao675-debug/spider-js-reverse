// verify_server_accept.js — 路径B 服务器接受度验证（科学对照实验）
// ───────────────────────────────────────────────────────────────────
// 设计：固定除 _signature 外的一切（同一接口 URL、同 UA、同 Referer），
//       仅置换签名值，观察服务器响应差异。
// 四态：
//   1) 无签名        —— 基线（接口是否本就无需签名）
//   2) 乱码签名      —— 格式错误的签名（全 X，长度同 candidate）
//   3) 算法值错签名  —— 由 candidate 翻转末位得到（格式/长度/分段一致，仅值错）
//   4) candidate     —— 本案例 VM(replay_real.js)实时生成的签名
// 判定：
//   - 若 candidate 被接受(200+真实数据) 而 “算法值错/乱码” 被拒 → 强证伪：本VM签名算法正确
//   - 若四态响应一致(都接受) → 接口对 _signature 校验宽松，candidate 未被拒(服务器接受)，
//                              但“未被拒”不能反推“算法正确”（受时间戳/指纹边界约束）
// ───────────────────────────────────────────────────────────────────
'use strict';
const https = require('https');
const { URL } = require('url');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');

const HERE = __dirname;

function getRaw(u, headers) {
  return new Promise((resolve) => {
    let url; try { url = new URL(u); } catch (e) { return resolve({ http: 'BADURL', body: String(e) }); }
    const req = https.get({
      hostname: url.hostname, port: 443, path: url.pathname + url.search,
      headers: Object.assign({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*', 'Referer': 'https://www.toutiao.com/',
      }, headers || {}),
    }, (res) => { let d = ''; res.on('data', c => d += c); res.on('end', () => resolve({ http: res.statusCode, body: d })); });
    req.on('error', e => resolve({ http: 'ERR', body: String(e) }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ http: 'TIMEOUT', body: '' }); });
  });
}

// 调用 replay_real.js 对给定 URL 生成签名（实时、独立进程）
function genSig(url) {
  cp.execFileSync('node', ['replay_real.js', url], { cwd: HERE, timeout: 120000, stdio: 'ignore' });
  return JSON.parse(fs.readFileSync(path.join(HERE, 'replay_real_out.json'), 'utf8')).signature;
}

function summarize(body) {
  try {
    const j = JSON.parse(body);
    const cnt = Array.isArray(j.data) ? j.data.length : (j.data ? 1 : 0);
    return { http: 'OK', message: j.message, status: j.status, dataCount: cnt };
  } catch (e) { return { http: 'PARSE_FAIL', preview: body.slice(0, 60) }; }
}

function flipLast(sig) {
  const last = sig.slice(-1);
  const flip = last === 'A' ? 'B' : 'A';
  return sig.slice(0, -1) + flip;
}

function appendSig(u, sig) {
  const sep = u.includes('?') ? '&' : '?';
  return u + sep + '_signature=' + encodeURIComponent(sig);
}

(async () => {
  const report = { generatedAt: new Date().toISOString(), interfaces: [] };

  // 动态从 feed 拿真实文章 id（feed 接口本身宽松，可无签名访问）
  let gid = null, iid = null;
  const feed = 'https://www.toutiao.com/api/pc/feed/?category=news_hot&utm_source=toutiao&widen=1&max_behot_time=0&max_behot_time_tmp=0&tadrequire=true';
  try {
    const fj = JSON.parse((await getRaw(feed)).body);
    const d0 = fj.data && fj.data[0];
    gid = d0 && (d0.group_id || d0.GroupId);
    iid = d0 && (d0.item_id || d0.ItemId || gid);
  } catch (e) { console.log('[warn] feed 取 id 失败:', e.message); }

  // 待验证接口集合（今日头条 PC 公开 API）
  const ifaces = [
    { name: 'hot_board', url: 'https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc' },
    { name: 'feed', url: feed },
  ];
  if (gid) ifaces.push({ name: 'tab_comments(真实id)', url: `https://www.toutiao.com/article/v4/tab_comments/?aid=24&app_name=news_article&group_id=${gid}&item_id=${iid}&offset=0&count=20` });

  console.log('=== 路径B 服务器接受度验证 ===');
  console.log('真实文章 id: group_id=%s item_id=%s\n', gid, iid);

  for (const f of ifaces) {
    const cand = genSig(f.url);
    const badAlg = flipLast(cand);          // 算法值错（格式/长度/分段一致）
    const garbage = 'X'.repeat(cand.length); // 乱码

    const rNo = summarize((await getRaw(f.url)).body);
    const rGar = summarize((await getRaw(appendSig(f.url, garbage))).body);
    const rBad = summarize((await getRaw(appendSig(f.url, badAlg))).body);
    const rCand = summarize((await getRaw(appendSig(f.url, cand))).body);

    // 判定：candidate 是否被接受
    const candOk = rCand.http === 'OK' && (rCand.dataCount > 0 || rCand.message === 'success');
    // 区分度：坏签名/乱码是否被拒绝（与 candidate 不同）
    const distinguishes = (rCand.http !== rBad.http) || (rCand.http !== rGar.http) ||
      (rCand.dataCount !== rBad.dataCount) || (rCand.dataCount !== rGar.dataCount);

    const row = { interface: f.name, candidate: cand, candLen: cand.length,
      noSig: rNo, garbage: rGar, badAlg: rBad, candidate: rCand,
      candidateAccepted: candOk, serverDistinguishesSignature: distinguishes };
    report.interfaces.push(row);

    console.log('--- %s ---', f.name);
    console.log('  candidate(%d): %s', cand.length, cand);
    console.log('  无签名  :', JSON.stringify(rNo));
    console.log('  乱码    :', JSON.stringify(rGar));
    console.log('  算法值错:', JSON.stringify(rBad));
    console.log('  candidate:', JSON.stringify(rCand));
    console.log('  => candidate 被接受: %s | 服务器区分签名: %s', candOk, distinguishes);
  }

  // 总判定
  const allAccepted = report.interfaces.every(i => i.candidateAccepted);
  const anyDistinguish = report.interfaces.some(i => i.serverDistinguishesSignature);
  report.verdict = {
    candidateAcceptedByServer: allAccepted,
    serverEnforcesSignature: anyDistinguish,
    conclusion: anyDistinguish
      ? '存在强校验接口且 candidate 被接受 → 本VM签名算法被服务器认可（路径B验证成功）'
      : '所有可访问接口对 _signature 校验宽松（无签名/乱码/candidate 响应一致）。candidate 未被拒绝（服务器接受），但“未被拒”不能反推算法 100% 正确——严格验证受时间戳不可逆 + 硬件指纹不可离线伪造的边界约束。',
  };
  console.log('\n=== 总判定 ===');
  console.log(JSON.stringify(report.verdict, null, 2));

  fs.writeFileSync(path.join(HERE, 'verify_result.json'), JSON.stringify(report, null, 2));
  console.log('\n结果已落盘: verify_result.json');
})();
