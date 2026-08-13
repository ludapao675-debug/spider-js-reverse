# JS Reverse & Protocol Lab | 爬虫逆向与协议复现实战库

> 🚀 本仓库专注于 **Web/API 逆向分析、签名解密、风控协议复现与网络抓包实战**。
> 包含大量真实站点的加密逆向代码、完整分析文档与踩坑经验总结。

---

## 📌 案例矩阵 (Case Matrix)

| 序号 | 目标站点 | 业务分类 | 核心技术 / 加密算法 | 防护 / 风控机制 | 复现状态 | 案例文档 |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **01** | **Expedia** | 国际机票 | GraphQL APQ (Persisted Query) | Akamai Bot Manager + DataDome | ⚠️ 协议复现 | [查看文档](cases/expedia_flight/README.md) |
| **02** | **Skyscanner (天巡)** | 航班搜索 | 自定义 Request Signature 签名 | 接口频率限制 | ✅ 纯协议闭环 | [查看文档](cases/skyscanner_flight/README.md) |
| **03** | **JNU CAS (暨南大学)** | 统一身份认证 | 东软 3DES 算法 (`strEnc`) | 验证码 + 混淆 | ✅ 纯协议闭环 | [查看文档](cases/jnu_login/README.md) |
| **04** | **CHSI (学信网)** | 统一登录 | 明文 HTTPS 提交 | 基础防护 | ✅ 纯协议闭环 | [查看文档](cases/chsi_login/README.md) |
| **05** | **NJU CAS (南京大学)** | 统一登录 | AES-128-CBC 隐藏盐动态加密 | 验证码 | ✅ 纯协议闭环 | [查看文档](cases/nju_login/README.md) |
| **06** | **PKU CAS (北京大学)** | 统一登录 | RSA-2048 / PKCS#1 v1.5 | 动态 Key 注入 | ✅ 纯协议闭环 | [查看文档](cases/pku_login/README.md) |
| **07** | **阅文通行证** | 统一登录 | RSA-1024 / PKCS#1 v1.5（JSBN hex） | JSONP + ywtoken | ✅ 纯协议闭环 | [查看文档](cases/yuewen_login/README.md) |

---

## 🛠️ 逆向踩坑与技术总结 (Technical Insights)

我们记录了逆向分析过程中的真实技术瓶颈与解决方案，欢迎查阅：

- 📖 **[逆向踩坑与经验总结日志 (mcp_pitfalls.md)](docs/mcp_pitfalls.md)**
  - `curl_cffi` 伪造 Chrome TLS / JA3 指纹绕过 WAF
  - Akamai `bm_sz` 配额与 `429 Too Many Requests` 限流对策
  - Apollo GraphQL APQ (`x-enable-apq`) 请求头误落坑排查
  - 浏览器跨域 (CORS) 服务端直连替代方案
  - DrissionPage CDP 接管与拟人化交互避坑

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备

推荐使用 Python 3.9+ 环境：

```bash
git clone https://github.com/your-username/crypto-hunter-lite.git
cd crypto-hunter-lite

pip install -r requirements.txt
# 或者手动安装核心依赖：
pip install curl_cffi requests drissionpage
```

### 2. 运行案例

以 Skyscanner 航班搜索为例：

```bash
python cases/skyscanner_flight/repro.py
```

对于依赖浏览器 Cookie 保持信任态的案例（如 Expedia）：
1. 打开浏览器登录/通过人机验证；
2. F12 Console 执行 `document.cookie`；
3. 将 Cookie 复制填入对应 `repro.py` 中的 `BROWSER_COOKIE` 变量后运行。

---

## 📂 项目目录结构 (Directory Layout)

```text
crypto-hunter-lite/
├── README.md                   # 项目主页（本文件）
├── docs/                       # 逆向技术文档与踩坑日志
│   ├── mcp_pitfalls.md         # 逆向踩坑与实战经验总结
│   └── js_positioning_methods.md # JS 定位与逆向方法论
├── cases/                      # 逆向案例汇总
│   ├── expedia_flight/         # Expedia 机票 GraphQL + APQ
│   ├── skyscanner_flight/      # 天巡机票接口签名
│   ├── jnu_login/              # 东软 3DES 登录加密
│   ├── nju_login/              # AES-CBC 动态盐登录
│   ├── pku_login/              # RSA-2048 登录
│   └── yuewen_login/           # 阅文 RSA-1024 hex JSONP 登录
└── server/                     # 分析自动化辅助工具集
```

---

## ⚖️ 免责声明 (Legal Disclaimer)

1. 本仓库所有代码与文档仅供 **学术交流、安全研究与技术探讨** 使用。
2. 严禁利用本项目中的代码或思路从事任何形式的非法爬虫、商业抓取或网络攻击行为。
3. 请遵守目标网站的 `robots.txt` 协议与相关法律法规。由于使用本仓库代码而引发的任何法律纠纷，由使用者自行承担，与本项目作者无关。
4. 若有相关站点认为相关案例侵犯了其合法权益，请联系作者进行删改。

---

## ⭐️ Star History

如果本项目对你的逆向学习或爬虫开发有所帮助，欢迎点个 **Star** 🌟 支持一下！
