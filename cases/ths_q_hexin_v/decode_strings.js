// 同花顺 chameleon 字符串数组解码脚本（隔离执行，无 DOM 依赖）
// 原理：脚本末尾 IIFE 实参为 4 个常量数组 + window/document 等；
// 解码器 Xn/Hn/Kn/Vn 仅依赖数组常量，可提取后全量求值并回代源码。
const fs = require('fs');
const vm = require('vm');

const src = fs.readFileSync(__dirname + '/chameleon.1.7.min.js', 'utf8');

// 1) 定位最外层 IIFE 的实参列表起点：源码以 }()}([ ... ]); 结尾
//    从第一个 "}([",即 IIFE 调用点切出数组段
const callIdx = src.indexOf('}()}(');
if (callIdx < 0) throw new Error('未找到 IIFE 调用点');
// 实参从 callIdx + "}()}(".length 开始，到结尾 ");" 前
const argsStart = callIdx + '}()}('.length;
const argsText = src.slice(argsStart, src.lastIndexOf(');'));

// 2) 括号配平切分顶层实参（数组字面量 / 标识符）
function splitTopLevelArgs(text) {
  const args = [];
  let depth = 0, start = 0, inStr = false, strCh = '';
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (ch === '\\') { i++; continue; }
      if (ch === strCh) inStr = false;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { inStr = true; strCh = ch; continue; }
    if (ch === '[' || ch === '(' || ch === '{') depth++;
    else if (ch === ']' || ch === ')' || ch === '}') depth--;
    else if (ch === ',' && depth === 0) {
      args.push(text.slice(start, i).trim());
      start = i + 1;
    }
  }
  args.push(text.slice(start).trim());
  return args;
}

const argTexts = splitTopLevelArgs(argsText);
console.log('实参数量:', argTexts.length);

// 3) 在沙箱里求值每个实参（window/document 用占位对象）
const sandbox = {
  window: {}, document: { head: {}, body: {}, documentElement: {} },
  navigator: {}, Array, Map, Function, String, RegExp, Date, Object,
  ActiveXObject: function(){}, localStorage: {}, parseInt, encodeURIComponent,
};
const ctx = vm.createContext(sandbox);
const args = argTexts.map((t, i) => {
  try { return vm.runInContext('(' + t + ')', ctx); }
  catch (e) { return { __placeholder: i, text: t.slice(0, 40) }; }
});

// 4) 复刻 4 个解码器（逻辑从源码提取）
//    形参绑定：!function(n,t,r,e){...}，n=args[0], t=args[1], r=args[2], e=args[3]
const [n, t, r, e] = args;
function Xn() { // n[25]^... 异或解码，i 初值 r[26]，模 n[26]，偏移 r[27]
  const a = arguments[0];
  if (!a) return '';
  let o = '', i = n[25], u = r[27];
  for (; u < a.length; u++) {
    const c = a.charCodeAt(u), s = c ^ i;
    i = (i * u) % n[26] + r[27];
    o += String.fromCharCode(s);
  }
  return o;
}
function Hn() { // 滚动密钥表 t[34]/t[35]
  const rr = arguments[0];
  if (!rr) return '';
  let a = '', o = t[34], i = t[35];
  for (let u = 0; u < rr.length; u++) {
    let c = rr.charCodeAt(u);
    i = (i + n[30]) % o.length;
    c ^= o.charCodeAt(i);
    a += String.fromCharCode(c);
  }
  return a;
}
function Kn() { // 前字符异或
  const rr = arguments[0];
  if (!rr) return '';
  let a = '', o = n[25], i = n[29];
  for (; i < rr.length; i++) {
    const u = rr.charCodeAt(i), c = u ^ o;
    o = u;
    a += String.fromCharCode(c);
  }
  return a;
}
function Vn() { // 反转字符串
  return arguments[0].split('').reverse().join('');
}

// 5) 把 Xn/Hn/Kn/Vn 注入沙箱，遍历源码中所有调用并求值
const sandbox2 = vm.createContext({ Xn, Hn, Kn, Vn, n, t, r, e, parseInt, String, RegExp });
const callRe = /(?:Xn|Hn|Kn|Vn)\((?:(?:n|t|r|e)\[\d+\]\s*,?\s*)+\)/g;
let out = src, replaced = 0, failed = 0;
const seen = new Map();
for (const m of src.matchAll(callRe)) {
  const expr = m[0];
  if (!seen.has(expr)) {
    try {
      const val = vm.runInContext(expr, sandbox2);
      seen.set(expr, typeof val === 'string' ? val : null);
    } catch (err) { seen.set(expr, null); failed++; }
  }
}
for (const [expr, val] of seen) {
  if (val === null) continue;
  const safe = JSON.stringify(val);
  out = out.split(expr).join(safe);
  replaced++;
}
console.log('唯一调用数:', seen.size, '成功回代:', replaced, '失败:', failed);

// 6) 再对 n[i]/t[i]/r[i]/e[i] 的字面量常量做直接回代（数组元素为原始值时）
function tryLiteral(idx) {
  const v = [n, t, r, e][idx[0]][parseInt(idx[1])];
  if (typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return null;
}
let replaced2 = 0;
out = out.replace(/\b([ntre])\[(\d+)\]/g, (mm, arr, i) => {
  const idx = [['n',0],['t',1],['r',2],['e',3]].find(x => x[0] === arr);
  const lit = tryLiteral([idx[1], i]);
  if (lit !== null) { replaced2++; return lit; }
  return mm;
});
console.log('数组索引直接回代:', replaced2);

fs.writeFileSync(__dirname + '/chameleon.readable.js', out, 'utf8');
console.log('已写出 chameleon.readable.js, 长度', out.length);
