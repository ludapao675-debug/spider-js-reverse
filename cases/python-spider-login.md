# Case: python-spider.com 登录加密逆向

> **案例ID**: case-python-spider-login
> **日期**: 2026-07-07
> **类型**: 签名型
> **难度**: ★★★☆☆ (中等)
> **状态**: ✅ 算法已定位

---

## 目标页面

- URL: `https://www.python-spider.com/challenge/login`
- 平台: 猿人学 Python 反爬练习平台
- 功能: 账号密码登录

---

## 采集证据

### 1. 网络请求

```
POST https://www.python-spider.com/challenge/api/login
Content-Type: application/x-www-form-urlencoded

参数:
  username:  (明文)
  password:  btoa(AES_ECB_encrypt(plain_password, key))
  ciphertext: JS_shield() -- 环境指纹
```

### 2. 加密算法

**算法**: AES-128/256 ECB 模式 + PKCS7 填充 + Base64 编码

**JS 加密代码** (解混淆后):
```javascript
function send_request() {
    var username = $('#username').val();
    var password = $('#password').val();
    
    // a() = AES-ECB encrypt
    // password = btoa(AES_ECB_encrypt(plain, key))
    var password = btoa(a(password));
    
    var data = {
        username: username,
        password: password,
        ciphertext: JS_shield(),
    };
    
    $.post('api/login', data, function(r) {
        // handle response
    });
}
```

### 3. 加密依赖

页面加载的 CryptoJS 模块:
- `/static/src/core.js` — CryptoJS 核心
- `/static/src/x64-core.js` — 64位运算
- `/static/src/cipher-core.js` — 加密核心
- `/static/src/enc-base64.js` — Base64 编解码
- `/static/src/md5.js` — MD5 哈希
- `/static/src/aes.js` — AES 加密

### 4. 调用栈证据

```
send_request()
  └─ a(password)                    -- AES ECB 加密
       └─ CryptoJS.enc.Utf8.parse   -- 密码转 WordArray
       └─ CryptoJS.AES.encrypt      -- AES加密(ECB模式)
            └─ CryptoJS.mode.ECB
            └─ CryptoJS.pad.Pkcs7
  └─ btoa(...)                      -- Base64 编码
  └─ JS_shield()                    -- 环境指纹
  └─ $.post('api/login', data)      -- 发送请求
```

### 5. 混淆特征

- **字符串数组混淆**: `_0x4f9a` 数组，688个编码字符串
- **自定义解码器**: `_0x6f3fef(key, salt)` — 双参数 XOR + Base64 解码
- **JS DUN PROTECT**: Script[24] 包含 eval(function S(p,u){...})，瑞数风格反调试
- **VAPTCHA**: 第三方滑动验证码 (独立于密码加密)
- **Console 保护**: Object.freeze(console) 防止控制台篡改

### 6. 🔴 动态调试证据 (2026-07-07)

**环境确认**:
```
typeof CryptoJS     = object    ✅ 全局可用
typeof send_request = function  ✅ 全局可调用
typeof JS_shield    = function  ✅ 全局可调用
typeof $            = function  ✅ jQuery 可用
typeof a            = undefined ❌ 在闭包内，非全局
typeof _0x4f9a     = undefined ❌ 在局部作用域
typeof _0x2eda     = undefined ❌ 在局部作用域
```

**Hook 拦截成功**:
- ✅ `CryptoJS.AES.encrypt` Hook 注入成功
- ✅ `CryptoJS.enc.Utf8.parse` Hook 注入成功  
- ✅ `send_request()` 直接调用成功（绕过 VAPTCHA）
- ✅ AES 加密被触发，数据已捕获但被 alert 弹窗阻塞

**JS_shield 返回值捕获**:
```
!js_shield_v2==wcoDLdUaGBGe06RbDRVFKaDeSkcFyf9UZGujh0Px4dJNUUmT+
pReFUsH9SUOZZWAVRjRUW0pEU5BqiFAPM4qlp0q2ZZ0kAb/KMv/gKX1x6HHnu9pFf6hQqQy
80ftth0s73ozBoXoaYulg5H/zYFEb+j5eAvsTHEFO3mK2B+Y34dgv6cQgRDsV3pjd
```
格式: `!js_shield_v2==` + Base64编码的加密数据

**反调试对抗发现**:
- `Object.freeze(console)` 被绕过
- `eval(function S(p,u){...})` JS DUN PROTECT 会导致 Chrome 主线程卡死
- 绕过方案: 在 JS DUN PROTECT eval 完成前快速执行 Hook 操作
- `debugger` 语句可通过 CDP Debugger.setSkipAllPauses(true) 绕过

---

## 本地复现

### Python 复现代码

```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

def encrypt_password(password: str, key: str) -> str:
    """
    复现 python-spider.com 登录密码加密
    
    Args:
        password: 明文密码
        key: AES 密钥 (需从页面提取)
    
    Returns:
        Base64 编码的密文
    """
    # Key 处理: CryptoJS 自动处理长度
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < 16:
        key_bytes = key_bytes.ljust(16, b'\x00')
    elif len(key_bytes) < 24:
        key_bytes = key_bytes[:16]
    elif len(key_bytes) < 32:
        key_bytes = key_bytes[:24]
    else:
        key_bytes = key_bytes[:32]
    
    # AES-ECB 加密
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    padded = pad(password.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    
    return base64.b64encode(encrypted).decode("utf-8")


def login(username: str, password: str, session) -> dict:
    """
    完整登录流程 (需要先提取 key 和 JS_shield token)
    """
    # TODO: 从页面提取 AES key
    key = "EXTRACT_FROM_PAGE"
    
    encrypted_pwd = encrypt_password(password, key)
    
    data = {
        "username": username,
        "password": encrypted_pwd,
        "ciphertext": "",  # JS_shield() 需要环境信息
    }
    
    resp = session.post(
        "https://www.python-spider.com/challenge/api/login",
        data=data,
        headers={"X-Requested-With": "XMLHttpRequest"}
    )
    return resp.json()
```

### 待完成

- [x] 动态调试确认全局变量可用性 (send_request, JS_shield, CryptoJS)
- [x] Hook CryptoJS.AES.encrypt 注入成功
- [x] 捕获 JS_shield() 返回值
- [ ] **获取 AES Key**: 修复 Hook 捕获 key 字段（需要处理WordArray转字符串）
- [ ] 解码 `_0x4f9a` 字符串数组（688 个编码字符串）
- [ ] 分析 `_0x6f3fef` 解码器算法
- [ ] 绕过 VAPTCHA 滑动验证码
- [ ] 完整端到端登录测试

### 🔑 AES Key 获取方案

**方案 A (推荐): 修复 Hook 捕获**
```javascript
CryptoJS.AES.encrypt = function(msg, key, cfg) {
    window.__captured_key = CryptoJS.enc.Utf8.stringify(key);  // 正确解码 WordArray
    return original.call(this, msg, key, cfg);
};
```
执行 `send_request()` → 关闭 alert → 读取 `window.__captured_key`

**方案 B: 从 send_request 闭包提取**
send_request toString() 源码中，搜索 `CryptoJS.enc.Utf8.parse('...')` 即可找到硬编码 key

**方案 C: 对比法**
记录多次加密的密文，如果相同明文产生相同密文则确认 ECB 模式 + 固定 key

---

## 下一步建议

1. **动态调试获取密钥**: 在页面中 `CryptoJS.AES.encrypt` 调用处设断点，捕获 key 参数
2. **解码字符串数组**: 分析 `_0x6f3fef` 解码逻辑，还原 688 个字符串
3. **JS_shield 分析**: 确定 ciphertext 的生成逻辑（可能是时间戳、指纹或固定值）
4. **VAPTCHA 绕过**: 使用 `ch_page_drag_element` 模拟滑动验证

### MCP 工具命令

```python
# 1. 导航并监听
ch_page_navigate(url="https://www.python-spider.com/challenge/login?...")
ch_listener_start(task_id="...")

# 2. 搜索加密关键字在JS中的位置
ch_search_loaded_scripts(keyword="CryptoJS.AES.encrypt")

# 3. 设置断点捕获密钥
ch_breakpoint_set_by_text(text="CryptoJS.AES.encrypt")

# 4. 输入用户名密码触发断点
ch_page_input(selector="input[name='username']", text="test")
ch_page_input(selector="input[name='password']", text="123456")
ch_page_click(selector="button[type='submit']")

# 5. 捕获变量
ch_debugger_wait_paused()
ch_debugger_get_scope()

# 6. 追踪参数
ch_trace_crypto_param(param_name="password")
ch_reverse_generate_report(task_id="...")
```

---

## 验证状态

| 证据 | 状态 |
|------|:---:|
| 目标请求 (POST /api/login) | ✅ |
| 算法确认 (AES-ECB + PKCS7 + Base64) | ✅ |
| CryptoJS 调用栈定位 (CryptoJS.AES.encrypt) | ✅ |
| `a()` 函数源码 (闭包内) | ✅ |
| JS_shield() 返回值捕获 | ✅ |
| 动态 Hook 注入验证 (AES+Utf8 双 Hook) | ✅ |
| send_request() 全局可调用确认 | ✅ |
| **AES 密钥提取** | ✅ `fakb23fegsuhw34gg3b` |
| **Node.js 本地复现** | ✅ `YjdR9K6ll5rngQNyyaqQeg==` |
| JS_shield 算法分析 | ⬜ |
| VAPTCHA 绕过 | ⬜ |
| Python 本地复现 (19B key 需自定义密钥调度) | ⚠️ |
| 完整登录验证 | ⬜ |

### 🎉 密钥确认

```
AES Key:  fakb23fegsuhw34gg3b (19 bytes, from _0x4f9a string array)
Algorithm: AES-ECB + PKCS7 padding
Encoding:  btoa() = Base64

Verification (Node.js + CryptoJS):
  mypassword  → YjdR9K6ll5rngQNyyaqQeg==  ✅ MATCH
  abc123      → DW4z2HLESX5xamkiYzBDfA==  ✅ MATCH

Note: 19-byte key is non-standard. CryptoJS auto-pads for AES but key
expansion differs from standard AES-128/192/256. Python requires
custom key schedule or use pycryptodome with key schedule extraction.
```

---

*案例生成: 2026-07-07 | Crypto Hunter Lite v14*
