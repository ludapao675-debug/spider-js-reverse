// refresh_env_snapshot.js — 从当前浏览器 tab dump 并写入 browser_env_snapshot.json
'use strict';

const { refreshSnapshot, compareSnapshotWithLive } = require('./env_snapshot_util');

async function main() {
  const checkOnly = process.argv.includes('--check');
  if (checkOnly) {
    const cmp = await compareSnapshotWithLive();
    console.log(JSON.stringify(cmp, null, 2));
    if (!cmp.match || cmp.stale) process.exit(2);
    return;
  }

  console.log('[refresh] dump 浏览器 bdms 环境 ...');
  const r = await refreshSnapshot();
  console.log('[refresh] 已写入 browser_env_snapshot.json');
  console.log('[refresh] me[24].inner =', r.me24 ? `${r.me24.slice(0, 48)}...` : '(空)');
}

main().catch((err) => {
  console.error('[refresh] ERROR:', err.message || err);
  process.exit(1);
});
