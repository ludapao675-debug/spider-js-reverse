/**
 * 酷我音乐排行榜 Secret 加密脱机复现脚本
 * 环境：Node.js
 */

function generateSecret(cookieVal, fixed_d = null) {
  var salt = "Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324";
  if (null == salt || salt.length <= 0) return null;
  
  for (var n = "", i = 0; i < salt.length; i++) {
    n += salt.charCodeAt(i).toString();
  }
    
  var o = Math.floor(n.length / 5);
  var r = parseInt(
      n.charAt(o) +
      n.charAt(2 * o) +
      n.charAt(3 * o) +
      n.charAt(4 * o) +
      n.charAt(5 * o)
  );
    
  var c = Math.ceil(salt.length / 2);
  var l = Math.pow(2, 31) - 1;
  if (r < 2) return null;
  
  // 如果提供了 fixed_d 用于验证闭环，则不生成随机数
  var d = fixed_d !== null ? fixed_d : (Math.round(1e9 * Math.random()) % 1e8);
  
  for (n += d; n.length > 10;) {
    n = (
      parseInt(n.substring(0, 10)) + parseInt(n.substring(10, n.length))
    ).toString();
  }
    
  n = (r * n + c) % l;
  
  var f = "", h = "";
  for (i = 0; i < cookieVal.length; i++) {
    f = parseInt(cookieVal.charCodeAt(i) ^ Math.floor((n / l) * 255));
    if (f < 16) {
      h += "0" + f.toString(16);
    } else {
      h += f.toString(16);
    }
    n = (r * n + c) % l;
  }
    
  for (d = d.toString(16); d.length < 8;) {
    d = "0" + d;
  }
  
  return h + d;
}

// ----------------------------------------------------
// 【抓包数据闭环验证】
// ----------------------------------------------------
// 仓库不携带真实抓包样本（Cookie/Secret 属敏感数据，请运行时自动获取）：
//   1. 浏览器打开酷我音乐排行榜页（https://www.kuwo.cn/rankList），
//      DevTools → Network 抓取任意含 Secret 参数的请求；
//   2. 复制该请求的 Cookie 与 Secret 值作为命令行参数传入：
//        node repro.js <真实Cookie> <真实Secret>
//   3. 脚本验证本地算法生成的 Secret 是否与抓包 Secret 一致（闭环）。
const REAL_COOKIE = process.argv[2] || null;
const REAL_SECRET = process.argv[3] || null;

if (!REAL_COOKIE || !REAL_SECRET) {
  console.log("== 酷我音乐 Secret 加密演示（未传入抓包样本） ==");
  const demo = generateSecret("demo_cookie_value");
  console.log("输入 Cookie : demo_cookie_value");
  console.log("生成的 Secret:", demo);
  console.log("\n闭环验证模式（需真实抓包数据）:");
  console.log("  node repro.js <真实Cookie> <真实Secret>");
  process.exit(0);
}

// 从真实的 Secret 尾部提取最后 8 个字符作为反推的 d
const extracted_d_hex = REAL_SECRET.slice(-8);
const fixed_d = parseInt(extracted_d_hex, 16);

console.log("== 酷我音乐 Secret 闭环验证 ==");
console.log("输入 Cookie: ", REAL_COOKIE);
console.log("反推的 D值 : ", extracted_d_hex);

const generated = generateSecret(REAL_COOKIE, fixed_d);

console.log("本地生成的 Secret:", generated);
console.log("网络真实抓包 Secret:", REAL_SECRET);

if (generated === REAL_SECRET) {
  console.log("--> ✅ 闭环验证成功！");
} else {
  console.log("--> ❌ 闭环验证失败！");
}

