// 解码真实 hexin-v Cookie，交叉验证 buffer 布局
// Qn 编码链：[c=3, checksum] + XOR流加密 + 自定义base64(A-Za-z0-9-_)
//
// 用法：传入真实 hexin-v Cookie 值（运行时自动获取，仓库不携带真实 Cookie）
//   node decode_v.js <hexin-v Cookie 值>
// 自动获取方式：打开同花顺行情页（https://q.10jqka.com.cn），DevTools → Application →
// Cookies → q.10jqka.com.cn → 复制名为 hexin-v 的 Cookie 值作为命令行参数传入。
const REAL_V = process.argv[2] || null;
if (!REAL_V) {
  console.error(
    '[ERROR] 缺少 hexin-v Cookie 参数。\n' +
    '用法: node decode_v.js <hexin-v Cookie 值>\n' +
    '自动获取: 浏览器打开同花顺页面 → DevTools → Application → Cookies → 复制 hexin-v 值。'
  );
  process.exit(1);
}

const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
const idx = {};
for (let i = 0; i < 64; i++) idx[ALPHA[i]] = i;

// 1) 自定义 base64 解码（每 4 字符 → 3 字节）
function b64decode(s) {
  const out = [];
  for (let w = 0; w < s.length; ) {
    const y = idx[s[w++]] << 18 | idx[s[w++]] << 12 | idx[s[w++]] << 6 | idx[s[w++]];
    out.push(y >> 16, (y >> 8) & 0xff, y & 0xff);
  }
  return out;
}

// 2) XOR 流解密：先用当前 u 低 8 位异或，再 u = ~(u * 0x83)（32位回绕）
function xorDecrypt(bytes, startKey) {
  let u = startKey;
  const out = [];
  for (const b of bytes) {
    out.push(b ^ (u & 0xff));
    u = (~(u * 0x83)) >>> 0;
  }
  return out;
}

// 3) strhash：a=(a<<5)-a+charCode，32 位回绕（兼容字符串与字节数组入参）
function strhash(s) {
  const chars = typeof s === "string" ? s : Array.from(s, (b) => String.fromCharCode(b)).join("");
  let a = 0;
  for (let i = 0; i < chars.length; i++) a = (((a << 5) - a + chars.charCodeAt(i)) >>> 0);
  return a;
}

const raw = b64decode(REAL_V);
console.log('base64解码字节数:', raw.length);
const c = raw[0], checksum = raw[1];
console.log('首字节c:', c, '校验和:', checksum);
const payload = xorDecrypt(raw.slice(2), checksum);
console.log('解密payload(hex):', Buffer.from(payload).toString('hex'));

// 校验和自验证
const calc = strhash(payload) & 0xff;
console.log('重算校验和:', calc, calc === checksum ? '✔ 匹配' : '✘ 不匹配');

// 4) 按候选宽度布局拆字段（总宽 = payload 长度）
function parseFields(bytes, widths) {
  const fields = [];
  let p = 0;
  for (const w of widths) {
    let v = 0;
    for (let i = 0; i < w; i++) v = (v << 8) + bytes[p++];
    fields.push(v);
  }
  return fields;
}

// 候选 A：[4,4,4,4,1,1,1,3,2,2,2,2,2,2,2,4,2,1]（总宽46）
const widthsA = [4,4,4,4,1,1,1,3,2,2,2,2,2,2,2,4,2,1];
if (widthsA.reduce((a,b)=>a+b,0) === payload.length) {
  const f = parseFields(payload, widthsA);
  console.log('\n候选A布局(总宽46):');
  const names = ['0:randomID','1:serverTime','2:timeNow','3:uaHash','4:version?','5:browserFeature','6:platform','7:browserIndex?','8:pluginNum','9:mouseMove','10:mouseClick','11:wheel','12:keyDown','13:clickX','14:clickY','15:counter','16:unknown','17:flag'];
  f.forEach((v, i) => {
    let extra = '';
    if (v > 1600000000 && v < 2000000000) extra = ` (时间戳: ${new Date(v*1000).toISOString()})`;
    console.log(`  ${names[i] || i} = ${v} (0x${v.toString(16)})${extra}`);
  });
}
