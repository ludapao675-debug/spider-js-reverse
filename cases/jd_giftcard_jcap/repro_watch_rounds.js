/**
 * 多轮肉眼对照：附着 Edge，换不同 GAP_BIAS 连跑。
 *   set JCAP_CDP=http://127.0.0.1:9222
 *   node repro_watch_rounds.js
 */
const { spawnSync } = require('child_process');
const path = require('path');

function sleep(ms) {
  const n = Number(ms) || 0;
  if (n <= 0) return;
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, n);
  } catch (e) {
    const end = Date.now() + n;
    while (Date.now() < end) {}
  }
}

const cdp = process.env.JCAP_CDP || 'http://127.0.0.1:9222';
const biases = (process.env.JCAP_BIAS_LIST || '0,2,-2,4,-4')
  .split(',')
  .map((s) => s.trim())
  .filter((s) => s.length);
const pause = process.env.JCAP_WATCH_PAUSE_MS || '2500';
const script = path.join(__dirname, 'repro_node_headless_blink.js');

console.log(`CDP=${cdp} rounds=${biases.length} biases=[${biases}] pause=${pause}ms`);
console.log('请盯着验证码：每轮拖前/拖后会停顿，看拼图块相对缺口偏左还是偏右。\n');

const summary = [];
for (let i = 0; i < biases.length; i++) {
  const bias = biases[i];
  console.log(`\n========== ROUND ${i + 1}/${biases.length}  GAP_BIAS=${bias} ==========\n`);
  const env = {
    ...process.env,
    JCAP_CDP: cdp,
    JCAP_GAP_BIAS: String(bias),
    JCAP_WATCH_PAUSE_MS: String(pause),
  };
  const r = spawnSync(process.execPath, [script], {
    cwd: __dirname,
    env,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const out = `${r.stdout || ''}${r.stderr || ''}`;
  process.stdout.write(out);
  const mOff = out.match(/GAP_BIAS=(-?\d+)\s*→\s*offsetCss=(\d+)/);
  const mBest = out.match(/"bestX":\s*(\d+)/);
  const mCode = out.match(/\/check 响应 code=(\d+)/) || out.match(/"code":\s*(\d+)/);
  const row = {
    round: i + 1,
    bias: Number(bias),
    bestX: mBest ? Number(mBest[1]) : null,
    offsetCss: mOff ? Number(mOff[2]) : null,
    code: mCode ? Number(mCode[1]) : null,
    exit: r.status,
  };
  summary.push(row);
  console.log(`\n--- ROUND ${i + 1} 摘要:`, JSON.stringify(row));
  sleep(pause);
}

console.log('\n========== 全部轮次汇总 ==========');
console.log(JSON.stringify(summary, null, 2));
const ok = summary.some((s) => s.code === 0);
process.exit(ok ? 0 : 3);
