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
// 【真实网络抓包数据闭环验证】
// ----------------------------------------------------
const REAL_COOKIE = "rErfdTBSErf7KTeir5ACECQKwWTwTsC3";
const REAL_SECRET = "5103d082102d36028078aafd488b7d7b5c66671849c3b1e8baa9042b3357ab6000333fd9";

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
