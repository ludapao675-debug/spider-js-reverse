# -*- coding: utf-8 -*-
"""
下载今日头条首页相关的签名/风控 SDK 源码，作为本地静态分析与离线复现的取证素材。

目标文件（来自页面 performance resource 列表）：
- acrawler.js        : Argus/ACrawler 签名 SDK，生成 _signature（JSVMP 类）
- sdk-glue.js         : rc-client-security glue
- runtime_bundler_52.js : security secsdk 运行时（VM 运行时）
- bdms.js             : rc-client-security 稳定版
"""
import os
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = {
    "acrawler.js": "https://lf3-cdn-tos.bytescm.com/obj/rc-web-sdk/acrawler.js",
    "sdk-glue.js": "https://lf-c-flwb.bytetos.com/obj/rc-client-security/web/glue/1.0.0.55/sdk-glue.js",
    "runtime_bundler_52.js": "https://lf-security.bytegoofy.com/obj/security-secsdk/runtime_bundler_52.js",
    "bdms.js": "https://lf-headquarters-speed.yhgfb-cn-static.com/obj/rc-client-security/web/stable/1.0.1.7/bdms.js",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def download(name, url):
    dest = os.path.join(OUT_DIR, name)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        size_kb = len(data) / 1024.0
        print(f"[OK]   {name:24s} {size_kb:8.1f} KB  <- {url}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name:24s} {e}  <- {url}")


if __name__ == "__main__":
    for name, url in TARGETS.items():
        download(name, url)
    print("done. 输出目录:", OUT_DIR)
