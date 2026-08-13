// 权威校验: 直接加载 zjuam 线上的 security.js (RSAUtils), 用真实公钥加密测试密码,
// 输出 modulus / exponent / enc, 用于与 Python 复现结果交叉验证。
async function main() {
  const pkRes = await fetch('https://zjuam.zju.edu.cn/cas/v2/getPubKey');
  const pk = await pkRes.json();

  const jsRes = await fetch('https://zjuam.zju.edu.cn/cas/js/login/security.js');
  const js = await jsRes.text();

  // 经典 RSAUtils 是纯 JS (BigInteger), 无 DOM 依赖; 在 Function 作用域内取其 RSAUtils
  // 该站 security.js 引用了 window, 提供一个最小 stub 即可
  const fakeWindow = {};
  const RSAUtils = new Function('window', 'document',
    js + '\n; return (typeof RSAUtils !== "undefined") ? RSAUtils : (window.RSAUtils || null);'
  )(fakeWindow, {});

  if (!RSAUtils) {
    console.error('未能从 security.js 解析出 RSAUtils');
    process.exit(2);
  }

  RSAUtils.setMaxDigits(130);
  const key = RSAUtils.getKeyPair(pk.exponent, '', pk.modulus);

  const plaintext = process.argv[2] || 'Zju@Test2026Rand';
  const enc = RSAUtils.encryptedString(key, plaintext);

  console.log(JSON.stringify({
    modulus: pk.modulus,
    exponent: pk.exponent,
    plaintext,
    enc,
    enc_len: enc.length,
  }));
}

main().catch(e => { console.error(e); process.exit(1); });
