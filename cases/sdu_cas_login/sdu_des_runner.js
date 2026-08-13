// 用页面真实 des.js (Guapo) 执行 strEnc，保证与浏览器字节级一致。
// 用法: node sdu_des_runner.js <data> <k1> <k2> <k3>
// 说明: des.js 内部 DES 实现与标准 pycryptodome DES 不同，
//       因此必须通过加载页面真实源码来复现，而非自行移植置换表。
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const desPath = path.join(__dirname, "sdu_des.js");
const src = fs.readFileSync(desPath, "utf8");
const ctx = {};
vm.createContext(ctx);
// 将 strEnc 暴露到 ctx，供后续调用
vm.runInContext(src + "\nthis.strEnc = strEnc;", ctx);

const [, , data, k1 = "1", k2 = "2", k3 = "3"] = process.argv;
if (data === undefined) {
  process.stderr.write("usage: node sdu_des_runner.js <data> <k1> <k2> <k3>\n");
  process.exit(1);
}
process.stdout.write(ctx.strEnc(data, k1, k2, k3));
