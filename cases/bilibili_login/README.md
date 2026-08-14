# B 站 (bilibili) 网页登录加密逆向

**样本**: `https://passport.bilibili.com/login`（账号密码登录）
**状态**: 密码 RSA 加密协议已 100% 还原并本地复现

## 逆向链路

1. 监听器捕获登录页加载 → 定位登录脚本 `index.6bb6210f.js`（Vue webpack 打包）
2. `ch_search_loaded_scripts` 定位加密逻辑 → 发现 `bili-sc-sdk`（WASM 设备指纹）与 `passport` 登录模块
3. 本地验证 `getKey` 接口 → 拿到 RSA-1024 公钥 + hash
4. 用 `pycryptodome` 实现 RSA/ECB/PKCS1v15 加密 → 提交登录

## 加密协议

### 1. 密码加密（RSA-1024）

```
GET /x/passport-login/web/key
  → {"code":0,"data":{"hash":"84b96ccb...","key":"-----BEGIN PUBLIC KEY-----..."}}
```

| 字段 | 说明 |
|------|------|
| `key` | RSA-1024 公钥 PEM，**每次请求动态生成** |
| `hash` | 16 位十六进制随机串，**每次请求动态生成** |

```
明文   = hash + password                  # 关键: hash 前缀拼接
密文   = RSA/ECB/PKCS1v15(明文) → base64   # 与 JSEncrypt.encrypt() 完全一致
```

### 2. 登录提交

```
POST /x/passport-login/web/login
form: username=<账号>&password=<RSA密文>&keep=0&challenge=&validate=&seccode=&challenges={}
```

### 3. 响应 code 语义

| code | 含义 |
|------|------|
| `0` | 登录成功（Set-Cookie: SESSDATA/bili_jct/...） |
| `-105` | 验证码错误（未传 geetest 验证码；**密码 RSA 加密已通过**） |
| `-855` | 密码错误 / 账号不存在（加密格式错误才会走此分支） |

**本地实测返回 `-105` = RSA 密码加密 100% 正确**，仅剩 geetest 滑块验证码拦截。

## 验证码链路（geetest 3.0 点击验证，已确认）

```
点击登录 → 前端调 B 站风控接口 → 返回 {gt, challenge}
        → initGeetest({gt, challenge}) 加载极验 fullpage SDK
        → SDK 生成 w 参数（极验核心加密）→ 提交验证
        → 成功返回 validate/seccode → 带回 login 接口
```

| 项 | 值 |
|----|-----|
| gt | `ac597a4506fee079629df5d8b66dd4fe`（固定，B 站专属，全局变量 `GeeGT`） |
| challenge | B 站风控接口动态下发（每次登录不同，3 分钟过期，过期报 `old challenge`） |
| SDK | `fullpage.9.2.0-guwyxh.js`（点击验证，`type:click`，`pic_type:word`） |
| w 参数 | 极验混淆 JS 加密（`$_HBIp` 字符串数组），长度 50-100，形如 `CxKv6uMCXjjeb2TQqrrmQScMbAEaMLV)Onpn7C...` |

**结论**：`w` 参数是极验（geetest）第三方验证码的核心加密，位于 `fullpage.9.2.0` 混淆 JS 内，
独立于 B 站自身加密。逆向需先 `ch_deobfuscate_auto` 解混淆再定位 w 生成函数，
或对接打码平台/复用开源 geetest w 生成器。

## 风控（bili-sc-sdk WASM）

- 页面加载 `bili-sc-sdk.umd.js`（Rust → WASM 编译），采集设备指纹
  （Canvas / WebGL / 字体 / 屏幕 / 时间戳）经 `encrypt_data()` 加密后
  上报 `//api.bilibili.com/x/internal/gaia-gateway/...`
- 设备指纹用于风控画像，**不影响登录请求的 RSA 密码加密**（登录只需正确密码密文）

## 复现脚本

```
python repro.py --user test@bilibili.com --pass test123456   # 登录（需验证码）
python repro.py --show-key                                   # 仅看公钥+加密结果
```

验证结果：本地 `getKey` → RSA 加密 → 提交，返回 `-105 验证码错误`，
证明密码加密格式与前端完全一致（若格式错会返回 `-855 密码错误`）。

## 未完成项
- **geetest `w` 参数逆向**：极验第三方混淆 JS（`fullpage.9.2.0`）内的核心加密。
  路径：`ch_deobfuscate_auto` 解混淆 → 定位 `w` 生成函数 → sdenv 复现验证；
  备选：对接打码平台 / 开源 geetest w 生成器（`validate`/`seccode` 需过验证后回填 login）
- 扫码登录（`qrcode` 接口 + `buvid3` 校验）

## 已归档证据
- RSA 密码加密 100% 还原（getKey → hash+password → RSA/ECB/PKCS1v15 → login）
- 本地提交返回 `code:-105 验证码错误`（RSA 校验通过，仅卡验证码）
- geetest 3.0 链路确认：gt 固定 / challenge 动态 / fullpage SDK / w 参数位置
