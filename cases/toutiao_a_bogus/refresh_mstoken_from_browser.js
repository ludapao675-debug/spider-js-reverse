// refresh_mstoken_from_browser.js — 从已打开的头条页拉 xmst/me[24] 写入 mstoken_cache.json
'use strict';

const { refreshSnapshot } = require('./env_snapshot_util');
const { writeCache, importFromSnapshot, readCache } = require('./mstoken_store');

async function main() {
  console.log('[mstoken] dump 浏览器环境 → snapshot ...');
  const r = await refreshSnapshot();
  const token = r.me24 || (r.xmst || null);
  if (token && String(token).length >= 32) {
    const out = writeCache(String(token), { source: 'browser_refresh' });
    console.log('[mstoken] 已写入 cache len=%d ts=%s', out.len, out.ts);
  } else {
    const imported = importFromSnapshot();
    if (imported) {
      console.log('[mstoken] snapshot 导入 cache len=%d', imported.len);
    } else {
      console.error('[mstoken] 未拿到 msToken（页面需已加载 bdms）');
      process.exit(2);
    }
  }
  console.log('[mstoken] current=', JSON.stringify(readCache(), null, 2));
}

main().catch((e) => {
  console.error('[mstoken] ERROR', e.message || e);
  process.exit(1);
});
