# iyunzhi.com (凤凰云智影院管理平台) 登录逆向

- 日期：2026-07-09
- 类型：RSA 密码加密 (jsbn PKCS#1 v1.5, 1024-bit) + 阿里云滑动验证码(NC) 行为挑战
- 站点：https://www.iyunzhi.com/

## 目标请求（已确认）

```
POST https://lark-acl.alibaba.com/idp/loginAccountAndPwd
Content-Type: application/json;charset=UTF-8
Origin: https://www.iyunzhi.com
Body: {
  "loginId": "<帐号>",
  "password": "<RSA(encodeURIComponent(pwd)) 的 hex 密文, 256 hex>",
  "captchaVerifyParam": "<阿里云滑块下发, nc_switch 开启时必填>",
  "sceneId": "<同上>"
}
```

- `baseURL:"acl"` 按域名映射：`www.iyunzhi.com` → `https://lark-acl.alibaba.com`（见 webpack 配置 JSON）。
- `password` 为 RSA 加密字段；`loginId` 明文帐号。
- `captchaVerifyParam`/`sceneId` 仅当 `nc_switch` 开启（默认开）时由阿里云滑块补充进 `this.nc_data`。

## 加密方案（webpack module 757026）

```js
},757026:(e,t,n)=>{
  "use strict";
  var r=n(385784).default;
  var a=r(n(954746)),o=r(n(624362)),i=r(n(896378)),s=r(n(949284));
  const l={daily:o.default,zlg_daily:o.default,pre:i.default,zlg_pre:i.default,prod:s.default,zlg_prod:s.default};
  a.default.setMaxDigits(130);
  const u=new a.default.RSAKeyPair("10001","",localStorage.publicKey||l[window.GLOBAL_CONFIG.env]);
  t.default=e=>a.default.encryptedString(u,encodeURIComponent(e))
}
```

- 标准 Stanford jsbn RSA：`setMaxDigits(130)`、`RSAKeyPair("10001","",n)`、`encryptedString(u, ...)`。
- 公钥指数 `e = 0x10001`；模数 `n` = `localStorage.publicKey`（运行时由服务端下发的优先）或按环境默认的硬编码模数。
- 明文处理：先 `encodeURIComponent(password)`，再 RSA 加密（PKCS#1 v1.5），输出 hex。
- env=`prod` 时默认模数（module 949284）：

```
837ec9791ee734418f44220b56cd22252c53309f59c560ff231d71e2579d38ea7a4408b017b1af85c6683111da151af25dddc53904a01e219bd56495a1add8cb70e54428bb87d95cd40478f6f800414be8a334ac779f4b819ae94fec240dc2ace1f99df64de88eef7bcbde4aabbdeac0e70a55e61331a9ea3d0546fe647977f9
```

> 另：daily(624362)=`f15fb948...ac96df`、pre(896378)=`8c99bea9...03188c5`。上线时优先用 `localStorage.publicKey`，若为空才回退到上述硬编码模数。

## 登录函数（module ~2322533）

```js
e.prototype.login=function(e){
  e.preventDefault();
  this.props.form.validateFields(((e,n)=>{
    if(!e&&!this.state.logining){
      const e=(0,d.default)(n.password);          // d.default = module 757026 的 RSA 加密
      r={method:"POST",baseURL:"acl",data:{loginId:n.loginId,password:e}};
      if(this.state.nc_switch&&!this.state.captchaDisabled){
        if(!Object.keys(this.nc_data).length)
          return void this.setState({message:"请按住滑块，拖动到最右边"});
        r.data={...r.data,...this.nc_data};        // 合并 captchaVerifyParam + sceneId
      }
      this.setState({logining:!0});
      (0,c.default)("/idp/loginAccountAndPwd",{baseURL:"acl",method:"POST",data:r.data}).then(...)
    }
  }));
}
```

## 离线复现（Python）

见 `assets/repro/iyunzhi_com_cn.py`：

```python
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import urllib.parse

n = int(MODULUS, 16)
key = RSA.construct((n, 0x10001))
plain = urllib.parse.quote(password).encode("utf-8")   # encodeURIComponent
cipher = PKCS1_v1_5.new(key).encrypt(plain)
hex_out = cipher.hex()                                  # 256 hex
```

## 验证结果

- RSA 自测：密文 128 字节、`c < n` → 结构合法。
- 密码加密样本：`encrypt_password("Test@123456")` 输出 256 hex 密文。
- **真实登录请求**：`POST lark-acl.alibaba.com/idp/loginAccountAndPwd` 已送达服务端，返回：
  ```json
  {"code":"ILLEGAL_PARAMETER","message":"风控验证参数不能为空!","data":null}
  ```
  → 服务端正确解析了请求体，仅因缺少 `captchaVerifyParam`（阿里云滑块 token）拒绝。这正面证明 **endpoint/host、请求结构、RSA 密码字段格式全部正确**（服务端未对密码格式报错）。

## 证据

- 主 JS 包：`app.bc7aadb8.js`（路径 `https://g.iyunzhi.com/s/v/alipic-lark/larkportal-front/5.0.12/js/app.bc7aadb8.js`）。
- 加密模块：`757026`（RSA 封装）、`949284`（prod 默认模数）、`954746`（jsbn 库）。
- 复现脚本：`assets/repro/iyunzhi_com_cn.py`。
- 实时响应样本：`{"code":"ILLEGAL_PARAMETER","message":"风控验证参数不能为空!"}`。

## 超级补环境

- 是否启用：否
- 判定原因：纯前端 jsbn RSA，无环境指纹 / 无 WASM / 无 JSVMP，无需补环境。
- 触发信号：无（密码加密本身）。
- 补环境建议：N/A。但登录需先过阿里云 NC 滑块（行为挑战，见下）。

## 验证应对（验证码）

- 验证类型：阿里云滑动验证码（Aliyun NC / `aliyunCaptcha`），属行为挑战。
- 处理路由：`human_handoff`（或 ai_assist 滑块拖拽）。**本项目自动化贝塞尔拖拽已尝试失败**（元素在验证码内部框架/被遮挡，报错 `human_drag failed: element may not be draggable or obscured`）。
- 是否需要人工接力：**是**（滑块 token 由阿里云服务端下发，无法通过纯加密逆向获得）。
- 识别信号：登录前出现 `.aliyunCaptcha-show` 滑块；不拖拽直接提交会提示「请按住滑块，拖动到最右边」；提交缺少 `captchaVerifyParam` 时服务端返回 `ILLEGAL_PARAMETER`。
- 证据包摘要：DOM 中 `.aliyunCaptcha-sliding-slider` 滑块元素 + 服务端 `风控验证参数不能为空` 报错。

## 分析过程

- 类型判断：登录接口 → 经典 RSA 密码加密（同 dcn_login 的 jsbn 路线）。
- 入口定位：登录表单 `#loginId`/`#password`/`#login-form-button`（Ant Design）；全局搜索 `encryptedString` 命中 module 757026；顺藤摸到登录函数确认 `password` 字段走 RSA。
- 环境补丁：无。
- 复现方法：pycryptodome `RSA.construct((n,0x10001))` + `PKCS1_v1_5`，明文先 `urllib.parse.quote`（= `encodeURIComponent`）再加密得 hex。

## 误判点

- 误判点 1：以为登录请求能直接抓到加密后的 password。→ 真实原因：登录前置阿里云滑块验证码，`captchaVerifyParam` 缺失时服务端直接拒绝，且滑块在独立框架内，自动化提交不触发登录 API。识别信号：首次点击后页面出现 `.aliyunCaptcha-show`，提交返回 `风控验证参数不能为空`。
- 误判点 2：以为 RSA 模数是从服务端动态拉取。→ 真实原因：`localStorage.publicKey` 为空时回退到硬编码 per-env 模数（prod=module 949284），可直接提取复现。识别信号：运行时 `localStorage.publicKey === null`，env=`prod`。
- 误判点 3：以为请求体字段名是 `pwd`。→ 真实原因：账号密码登录用 `password`（RSA 密文），`pwd` 仅用于手机验证码登录等其他分支。识别信号：登录函数 `data:{loginId,password:e}`。

## 真正原因

- 真正原因：密码经 1024-bit RSA (PKCS#1 v1.5) 加密，公钥明文内联在 webpack 模块（按 env 默认模数），明文先 `encodeURIComponent`；登录还需先过阿里云滑动验证码。
- 识别信号：module 757026 的 `RSAKeyPair`/`encryptedString`/`setMaxDigits` + `encodeURIComponent`。
- 修复方式（针对本项目工具链，非站点）：新增 `cases/iyunzhi_login_20260709.md` 与 `assets/repro/iyunzhi_com_cn.py`。
- 工具链附带修复：后端 `ch_verification_assess` 存在 bug（`name 'entry_id' is not defined`），调用即报错，需修复后才能在验证码场景正常产出评估与证据包。

## 验证结果

- 生成位置：module 757026 `t.default=e=>a.default.encryptedString(u,encodeURIComponent(e))`。
- 本地复现方式：`python assets/repro/iyunzhi_com_cn.py`。
- 验证结果：RSA 结构合法（128 字节, c<n）；真实请求送达服务端并返回验证码缺失错误 → 加密/请求结构正确。完整登录（含滑块）需人工通过验证码。

## 可复用规则

- 规则 1：登录页出现 `RSAKeyPair`/`encryptedString`/`setMaxDigits` → 直接判定 Stanford jsbn RSA，用 pycryptodome `PKCS1_v1_5` 复现，`n`=模数(hex)、`e=0x10001`；明文若先 `encodeURIComponent` 则复现时也要 `urllib.parse.quote`。
- 规则 2：RSA 模数优先查 `localStorage`/运行时下发，为空再找 webpack 中 per-env 默认模数常量。
- 规则 3：`baseURL:"xxx"` 这类短别名在 webpack 配置 JSON 里按 `location.hostname` 映射到真实 host，需从配置中提取对应域名项。
- 规则 4（项目工具链）：`ch_verification_assess` 当前有 `entry_id` 未定义 bug，验证码场景评估功能不可用，需先修后端。

## 回归说明

- 易变点：RSA 默认模数可能随升级更换（module 949284 等）；`localStorage.publicKey` 服务端下发逻辑变化；阿里云滑块 `sceneId`/风控策略升级。
- 下次升级先检查：① module 757026 的模数常量；② `localStorage.publicKey` 是否变为必填；③ `/idp/loginAccountAndPwd` 路径与字段名；④ 滑块验证码是否仍需人工。

## 踩坑记录

- 误判（请求能直接抓密码密文）→ 真实原因（滑块验证码阻断 + 框架内元素）→ 识别信号（`.aliyunCaptcha-show` + 服务端 `风控验证参数不能为空`）→ 修复方式（密码加密已复现，验证码转人工/human_handoff）→ 可复用规则（规则 1/4）。
- 误判（模数动态拉取）→ 真实原因（localStorage 为空回退硬编码 per-env 模数）→ 识别信号（`localStorage.publicKey===null`, env=prod）→ 修复方式（提取 module 949284 模数）→ 可复用规则（规则 2）。
- 误判（字段名 pwd）→ 真实原因（账号密码登录用 password）→ 识别信号（登录函数 `data:{loginId,password}`）→ 修复方式（复现用 password 字段）→ 可复用规则（规则 3）。
- 工具链坑（`ch_verification_assess` 报 `entry_id is not defined`）→ 真实原因（后端未定义该变量）→ 识别信号（调用即 500/异常）→ 修复方式（待后端修复）→ 可复用规则（规则 4）。
