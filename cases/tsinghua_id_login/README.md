# 清华大学用户电子身份服务 — 登录密码 SM2 加密逆向

> 站点：`https://id.tsinghua.edu.cn/f/login`  
> 目标：`POST /security_check`  
> 日期：2026-07-19  
> 任务：`task_20260719_061900_d4dfb70d`

## 结论：密码用 **国密 SM2（C1C3C2）** 加密后提交

`ch_detect_login_encryption` 曾误判为 `plaintext`（置信度 0.7）。真实链路是 SM2：

```js
// res/selfservice/login.js
var publicKey = $("#sm2publicKey").text();
var pass = $("#password").val();
var encryptPass = sm2Util.doEncryptStr(pass, publicKey);
$("#sm2pass").val(encryptPass);  // name="password"
```

```js
// sm2Util.doEncryptStr
return "04" + sm2.doEncrypt(pass, publicKey, 1);  // cipherMode=1 → C1C3C2
```

### 加密公式
```
password_field = "04" + SM2_Encrypt_C1C3C2(utf8(明文密码), 公钥XY)
```

- 公钥：页面元素 `#sm2publicKey` 文本（未压缩 `04||X||Y`，130 hex）
- 可见 `#password` **无 name**，不会提交明文；隐藏 `#sm2pass` 的 `name=password` 才是密文字段
- 密文长度：`2 + 128 + 64 + 2*len(utf8(password))` hex（前缀04 + C1xy + C3 + C2）

### 实测公钥（2026-07-19）
```
04d0c9e1ae89279fe05b435d63e3eba437bf510e09da5f71558974a19dc59672
4227f08dc2fc6e74bbb9d8b468d4dd5205e9b6793a3bbc48df3fdf219b3ea140e3
```

## 提交参数（POST `/security_check`）

| 字段 | 说明 |
|------|------|
| `username` | 账号明文 |
| `password` | **SM2 密文**（`04` 开头 hex） |
| `fingerPrint` | 设备指纹（页面预填） |
| `fingerGenPrint` / `fingerGenPrint3` | 本地指纹（`localstorageUtil.getFinger3FromLocal`） |
| `deviceName` | 如 `windows,Chrome/150` |
| `i_captcha` | 图形验证码（`/captcha.jpg`），前端要求 4 位且校验通过 |

随机账号样本（仅结构，登录失败预期）：
```
username=thu_rand_20260719
password=04....（224 hex for 15-byte password）
i_captcha=0000
```

## 验证

- SM2 含随机数，无法逐字节比对浏览器密文
- `--self-test`：前缀 `04`、长度公式、表单字段名通过
- 页面内 `sm2Util.doEncryptStr` 对同口令产出同结构密文

## 复现

```bash
pip install gmssl
python cases/tsinghua_id_login/repro.py --self-test
python cases/tsinghua_id_login/repro.py <username> <password> [captcha]
```

完整协议登录还需：有效 `JSESSIONID`、正确验证码、指纹字段；本 case 聚焦**密码字段算法复现**。

## 工具踩坑（本案例暴露）

| 问题 | 现象 | 建议 |
|------|------|------|
| `ch_detect_login_encryption` 漏检 SM2 | 有 `#sm2pass` + `sm2Util.js` 仍报 `plaintext` | 探针应识别 `sm2Util`/`#sm2pass`/`sm2publicKey`，新增 `sm2` 分类 |
| listener 文档导航 POST | `POST /security_check` 302 后只剩 `GET /f/login`，`post_data` 空，但 headers 仍带 `content-type: x-www-form-urlencoded` | 保留 redirect 链原始 POST body；过滤勿把 `login` 子串扩到整站静态资源 |
| `url_include: ["login"]` 过宽 | css/js 大量误命中 | 登录场景优先精确 `security_check` |
| `Network.getResponseBody` 字体失败 | listener.error 刷屏 | 对 Font 类型跳过 body 拉取 |

## 参考案例
- 对比：`cases/pku_login`（RSA/JSEncrypt）——算法不同，勿混用
- 误参考：`cases/chsi_login`（明文）——仅因 detect 误判时被推荐
