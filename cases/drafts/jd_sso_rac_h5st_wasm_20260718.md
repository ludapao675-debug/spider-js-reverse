# 草稿：京东 SSO `/sso/rac` h5st（WASM 待拆）

> 状态：入口与参数形态已确认；**纯本地 WASM/h5st 算法未完成**，后续专项逆向。  
> 工作笔记：`scratch/jd_sso_rac_20260718/NOTES.md`  
> 任务：`task_20260718_115156_cf346443` · 样本请求：`28696.1866`

## 目标

- 接口：`GET https://sso.jd.com/sso/rac`
- 关键加密参数：`s`（另有明文 `t` / `r` / `ua`）

## 已确认结论

1. `s` = 京东 **h5st v5.3** 整串，**不是** SummerCryptico / AKS（SM2+SM4）。
2. 生成：`ParamsSign({ appId: "73806", preRequest: true }).sign({ t, r })`，`_stk = "r,t"`。
3. 与 passport 登录页 h5st **同一 appId `73806`**；首页业务接口常见另一 appId（如 `b5216`）。
4. SDK 会加载 WASM：`https://storage.360buyimg.com/jsresource/ws_js/wasm/single.min.js`。
5. 前置：`POST https://jra.jd.com/jsTk.do` 取 tk；脚本含 `js-security-v3-rac.js`、`js_security_v3_*.js`。

### `s` 十段结构

`ts_fmt ; fp ; appId ; tk03... ; sha256 ; 5.3 ; t_ms ; cipher ; sha256 ; tail`

### 勿混淆

| 路径 | 壳 | WASM |
|------|----|------|
| `/uc/loginService` 的 `aksParamsU/B` | SummerCryptico SM2+SM4 | 否 |
| `/sso/rac` 的 `s` | h5st / ParamsSign | **是** |

## 运行时证据

- 抓包：`www.jd.com` 加载后自动打 `sso/rac`，响应例 `{"nfd":10}`。
- 页面取签：`scratch/jd_sso_rac_20260718/probe_sign_out.json`（`appIdInH5st=73806`，10 段）。
- 样本解析：`scratch/jd_sso_rac_20260718/sample_rac.json`。

## 后续待办（WASM / 纯本地）

1. 逆向 `ws_js/wasm/single.min.js` + `js_security_v3` / `js-security-v3-rac.js` 的 h5st 5.3 算法。
2. 复刻 `jra.jd.com/jsTk.do` 取 tk 流程。
3. 用本地生成的 `s` 打 `/sso/rac`，对比浏览器响应（含 Cookie / 登录态）。
4. 正式案例定稿前：补 reproduction 脚本 + 验证样本。

## 短期可用绕过

浏览器内调 `ParamsSign` 取 `s`，Python 只拼 URL + Cookie 发 GET（与当前 login 复现策略同级）。
