// Node 功能等价性验证：raw（live 抽取，保留 w_0x25f3 字符串解码器间接调用）vs deob（webcrack 静态还原纯解码）
// 两者运行在同一 _0x458f30 字符串数组上，对同一条 hex 配置串解码，比较 _0x408609 数组是否逐元素相等。
const fs = require('fs');
const DIR = 'f:/AICode/逆向工具/crypto-hunter-lite/cases/drafts/deob_test/';

// 1) 真实字符串数组（来自 live 页抓取，与 deob 测试同一份）+ 解码器
const liveArr = fs.readFileSync(DIR + 'live_arr.js', 'utf8');   // var _0x458f30=[...];  (live 真实数组)
const w25 = fs.readFileSync(DIR + 'w25_func.js', 'utf8');      // function w_0x25f3(...){ var _0x4173a9=w_0x42f5(); ... }
const raw = fs.readFileSync(DIR + 'raw_short.js', 'utf8');     // function w_0x5c3140(...){ var _0x2145df=w_0x25f3; ... return _0x408609; }
const deob = fs.readFileSync(DIR + 'w5c_deob_short.js', 'utf8'); // 纯解码（已内联 String.fromCharCode / slice，无 w_0x25f3 调用）

// 2) 真实配置串（来自 live 页数组索引 5，与 deob 测试同一份）
const hex = fs.readFileSync(DIR + 'live_hex.txt', 'utf8').trim();

// 3) 构建共享上下文：_0x458f30 数组（live 真实）+ w_0x42f5 + w_0x25f3（原始间接解码器）
const ctx = {};
const ctxFactory = new Function('OUT',
  liveArr + '\n' +
  'OUT._arr = _0x458f30;' + '\n' +
  'w_0x42f5 = function(){return _0x458f30;};' + '\n' +
  w25 + '\n' +
  'OUT.w_0x42f5 = w_0x42f5; OUT.w_0x25f3 = w_0x25f3;');
ctxFactory(ctx);

// 4) 在两个独立作用域实例化 raw / deob 解码函数（deob 不需要 w_0x25f3，因为它已纯静态内联）
const rawFn = new Function('w_0x25f3', 'w_0x42f5', raw + '\n return w_0x5c3140;')(ctx.w_0x25f3, ctx.w_0x42f5);
const deobFn = new Function(deob + '\n return w_0x5c3140;')();

// 5) 运行
let a, b, errA = null, errB = null;
try { a = rawFn(hex, {}, {}); } catch (e) { errA = String(e); }
try { b = deobFn(hex, {}, {}); } catch (e) { errB = String(e); }

function eq(x, y) {
  if (!Array.isArray(x) || !Array.isArray(y)) return false;
  if (x.length !== y.length) return false;
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return false;
  return true;
}

const same = (errA === null && errB === null) && eq(a, b);
console.log('errA:', errA);
console.log('errB:', errB);
console.log('aLen:', a ? a.length : null, 'bLen:', b ? b.length : null);
console.log('same:', same);
if (!same) {
  console.log('aSample:', a ? JSON.stringify(a.slice(0, 5)) : null);
  console.log('bSample:', b ? JSON.stringify(b.slice(0, 5)) : null);
}
process.exit(same ? 0 : 1);
