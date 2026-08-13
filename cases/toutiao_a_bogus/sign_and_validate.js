// sign_and_validate.js — 一键：刷新环境 → 离线签名 → oracle + unsigned fetch 验收
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { refreshSnapshot, compareSnapshotWithLive } = require('./env_snapshot_util');

const HERE = __dirname;

function runNode(script, args = []) {
  const r = spawnSync('node', [path.join(HERE, script), ...args], {
    cwd: HERE,
    encoding: 'utf8',
    timeout: 180000,
  });
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
  return r.status ?? 1;
}

function buildFeedUrl() {
  const ts = Math.floor(Date.now() / 1000);
  return `https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=${ts}&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web`;
}

async function main() {
  const skipRefresh = process.argv.includes('--skip-refresh');
  const skipFingerprint = process.argv.includes('--skip-fingerprint');
  const feedUrl = process.argv.find((a) => a.startsWith('http')) || buildFeedUrl();

  console.log('[pipeline] feed URL:', feedUrl.slice(0, 100) + '...');

  if (!skipRefresh) {
    console.log('[pipeline] 1/5 刷新 browser_env_snapshot ...');
    const snap = await refreshSnapshot();
    console.log('[pipeline] me[24] =', snap.me24 ? `${snap.me24.slice(0, 40)}...` : '(空)');
  } else {
    const cmp = await compareSnapshotWithLive().catch(() => null);
    if (cmp && !cmp.match) {
      console.warn('[pipeline] 警告: 快照 token 与 live 不一致，建议去掉 --skip-refresh');
    }
  }

  if (!skipFingerprint && fs.existsSync(path.join(HERE, 'refresh_browser_fingerprint.js'))) {
    console.log('[pipeline] 2/5 刷新 browser_fingerprint ...');
    const code = runNode('refresh_browser_fingerprint.js');
    if (code !== 0) console.warn('[pipeline] fingerprint 刷新失败，继续');
  } else {
    console.log('[pipeline] 2/5 跳过 fingerprint');
  }

  console.log('[pipeline] 3/5 离线签名 ...');
  if (runNode('replay_bdms_offline.js', ['--skip-stale-warn', feedUrl]) !== 0) {
    process.exit(2);
  }

  console.log('[pipeline] 4/5 浏览器 XHR oracle 对比 ...');
  const oracleCode = runNode('validate_offline_browser.js');

  console.log('[pipeline] 5/5 浏览器 unsigned fetch 服务端验收 ...');
  const fetchCode = runNode('validate_browser_unsigned_fetch.js', [feedUrl]);

  const report = {
    feed_url: feedUrl,
    oracle_exit: oracleCode,
    unsigned_fetch_exit: fetchCode,
    sign: JSON.parse(fs.readFileSync(path.join(HERE, 'replay_bdms_offline_out.json'), 'utf8')),
    oracle: fs.existsSync(path.join(HERE, 'validate_oracle_result.json'))
      ? JSON.parse(fs.readFileSync(path.join(HERE, 'validate_oracle_result.json'), 'utf8'))
      : null,
    unsigned_fetch: fs.existsSync(path.join(HERE, 'validate_unsigned_fetch_result.json'))
      ? JSON.parse(fs.readFileSync(path.join(HERE, 'validate_unsigned_fetch_result.json'), 'utf8'))
      : null,
    ok: oracleCode === 0 && fetchCode === 0,
  };

  const outPath = path.join(HERE, 'sign_and_validate_report.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log('[pipeline] 报告已写入', path.basename(outPath));
  console.log('[pipeline] 完成 ok=%s a_bogus_len=%s anchor=%s unsigned_ok=%s',
    report.ok,
    report.sign.abogus_len,
    report.oracle?.compare?.anchor_match,
    report.unsigned_fetch?.ok,
  );

  if (!report.ok) process.exit(2);
}

main().catch((e) => {
  console.error('[pipeline] ERROR:', e.message || e);
  process.exit(1);
});
