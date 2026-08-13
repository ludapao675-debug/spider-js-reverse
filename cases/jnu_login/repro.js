/**
 * 暨南大学 JNU 统一身份认证 (icas.jnu.edu.cn) — 密码加密参数复现
 * ================================================================
 * 加密算法：东软(Neusoft) CAS 自定义 3DES 风格算法（des.js 的 strEnc）。
 *
 *   明文 = username + password + lt      (lt 为页面隐藏字段，每次登录变化)
 *   rsa  = strEnc(明文, '1', '2', '3')    (十六进制，无填充，定长 16 字节/块)
 *
 * 同时页面还会回填：
 *   ul = username.length
 *   pl = password.length
 *
 * 提交（login10.js L210-217）：
 *   POST /cas/login  (form submit)
 *     rsa, ul, pl, lt, execution, _eventId, not_exit_number, service_id
 *
 * 复现方式：直接加载页面真实 des.js（已下载到同目录 des.js），
 * 用其中的 strEnc 加密，保证与浏览器逐字节一致。
 */
const fs = require("fs");
const path = require("path");

// 加载真实 des.js，将其内部函数（strEnc/strDec/getKeyBytes/enc/strToBt/bt64ToHex …）
// 暴露到当前作用域。CommonJS 非严格模式下直接 eval 的 function 声明会进入本作用域。
const desSrc = fs.readFileSync(path.join(__dirname, "des.js"), "utf8");
eval(desSrc);

/**
 * 复现 JNU 登录的 rsa 字段加密。
 * @param {string} username 账号
 * @param {string} password 密码明文
 * @param {string} lt       页面隐藏字段 lt（每次登录变化）
 * @returns {{rsa:string, ul:number, pl:number}}
 */
function encrypt_login(username, password, lt) {
  const plain = username + password + lt;
  const rsa = strEnc(plain, "1", "2", "3");
  return { rsa, ul: username.length, pl: password.length };
}

function main() {
  const username = process.argv[2] || "user123";
  const password = process.argv[3] || "Pass5678";
  const lt = process.argv[4] || "LT-250745-abc";

  const { rsa, ul, pl } = encrypt_login(username, password, lt);
  console.log(`[*] 明文(明文=username+password+lt) = ${username}${password}${lt}`);
  console.log(`[*] ul = ${ul} (username.length)`);
  console.log(`[*] pl = ${pl} (password.length)`);
  console.log(`[*] rsa = ${rsa}`);
  console.log(`[*] rsa 长度(十六进制字符) = ${rsa.length}`);

  // 自洽校验：用 strDec 应能还原明文
  const dec = strDec(rsa, "1", "2", "3");
  console.log(`[*] strDec 还原 = ${dec}`);
  console.log(`[*] 闭环一致 = ${dec === username + password + lt}`);
}

if (require.main === module) {
  main();
}

module.exports = { encrypt_login };
