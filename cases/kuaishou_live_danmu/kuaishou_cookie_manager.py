# -*- coding: utf-8 -*-
"""
快手直播 Cookie 本地管理器
==========================
职责：程序化从已连接浏览器采集快手访客 Cookie（did/kwfv1/...），缓存到本地，
供签名与请求链路复用，实现"无需手动复制 Cookie"的闭环。

背景结论（逆向所得）：
- did / clientid / client_key / kpn：服务端 Set-Cookie 下发（访问首页即可获得）。
- kwfv1：由 kwf 指纹 SDK（kwf-0.0.2，Brook JSVMP）在真实浏览器内采集设备指纹后生成。
  * 纯 HTTP 无法获得（首页 Set-Cookie 不含 kwfv1）。
  * 在 sdenv/Node 沙箱运行 kwf SDK 会报 "Failed to process fingerprint"（缺真实
    canvas/WebGL/字体等指纹），且伪造指纹会触发服务端风控（result=400002）。
  * 因此 kwfv1 必须来自真实浏览器。本管理器通过后端 API 从工具自身浏览器一次性
    采集并缓存，之后无需再依赖浏览器。
- kww 请求头 == kwfv1（有 kwfv1 时直接复用）。

用法:
    from kuaishou_cookie_manager import KuaishouCookieManager
    mgr = KuaishouCookieManager()
    cookie_str = mgr.get_cookie_string()      # 有缓存用缓存，否则自动采集
    kww = mgr.get_kww()                        # == kwfv1
"""
import json
import os
import time
import urllib.request

BACKEND = "http://127.0.0.1:27183"
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "kuaishou_cookies.json")

# 快手直播请求实际需要的 Cookie 名（其余可忽略）
NEEDED_KEYS = [
    "did", "clientid", "client_key", "kpn", "kwpsecproductname",
    "kwfv1", "kwssectoken", "kwscode", "kuaishou.live.bfb1s",
]
# 只保留这些域名的 Cookie（过滤掉 bing/msn 等无关项）
RELEVANT_DOMAINS = ("kuaishou.com", "kwai", "yximgs")


class KuaishouCookieManager:
    def __init__(self, backend: str = BACKEND, cache_path: str = CACHE_PATH):
        self.backend = backend.rstrip("/")
        self.cache_path = cache_path

    # ------------------------------------------------------------
    # 从已连接浏览器采集 Cookie
    # ------------------------------------------------------------
    def harvest_from_browser(self, all_domains: bool = True) -> dict:
        """调用后端 /api/browser/page/cookies 采集浏览器全部 Cookie，筛出快手所需项。"""
        url = f"{self.backend}/api/browser/page/cookies?all_domains={'true' if all_domains else 'false'}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        if not payload.get("ok"):
            raise RuntimeError(f"采集 Cookie 失败: {payload.get('error')}")

        cookies = payload.get("cookies") or []
        picked = {}
        # 优先级：.live.kuaishou.com > .kuaishou.com > 其它快手域
        def domain_rank(dom: str) -> int:
            dom = (dom or "").lstrip(".")
            if dom == "live.kuaishou.com":
                return 3
            if dom == "kuaishou.com":
                return 2
            if any(d in dom for d in RELEVANT_DOMAINS):
                return 1
            return 0

        for c in cookies:
            name = c.get("name")
            dom = c.get("domain") or ""
            if name not in NEEDED_KEYS:
                continue
            if not any(d in dom for d in RELEVANT_DOMAINS):
                continue
            val = c.get("value")
            if val is None or val == "":
                continue
            rank = domain_rank(dom)
            # 记录 (rank, value)，取 rank 最高者
            prev = picked.get(name)
            if prev is None or rank > prev[0]:
                picked[name] = (rank, val)

        result = {k: v[1] for k, v in picked.items()}
        if "kwfv1" not in result:
            raise RuntimeError("未采集到 kwfv1（请确认浏览器已打开过快直播页面）")
        return result

    # ------------------------------------------------------------
    # 缓存读写
    # ------------------------------------------------------------
    def save_cache(self, cookies: dict):
        data = {"cookies": cookies, "harvested_at": int(time.time())}
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_cache(self) -> dict:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("cookies") or {}
        except Exception:
            return {}

    # ------------------------------------------------------------
    # 对外主入口
    # ------------------------------------------------------------
    def get_cookies(self, force_refresh: bool = False) -> dict:
        """返回快手所需 Cookie 字典；优先用缓存，缺失或强制时重新采集。"""
        if not force_refresh:
            cached = self.load_cache()
            if cached.get("kwfv1") and cached.get("did"):
                return cached
        cookies = self.harvest_from_browser()
        self.save_cache(cookies)
        return cookies

    def get_cookie_string(self, force_refresh: bool = False) -> str:
        """返回可直接放入 Cookie 请求头的字符串。"""
        cookies = self.get_cookies(force_refresh=force_refresh)
        # 按快手请求习惯排序输出
        ordered = []
        for k in NEEDED_KEYS:
            if k in cookies:
                ordered.append(f"{k}={cookies[k]}")
        # 追加其它已采集项
        for k, v in cookies.items():
            if k not in NEEDED_KEYS:
                ordered.append(f"{k}={v}")
        return "; ".join(ordered)

    def get_kww(self, force_refresh: bool = False) -> str:
        """kww 请求头 == kwfv1。"""
        return self.get_cookies(force_refresh=force_refresh).get("kwfv1", "")


if __name__ == "__main__":
    mgr = KuaishouCookieManager()
    import sys
    force = "--refresh" in sys.argv
    ck = mgr.get_cookies(force_refresh=force)
    print("采集/缓存到的关键 Cookie：")
    for k in NEEDED_KEYS:
        v = ck.get(k, "")
        print(f"  {k} = {v[:60]}{'...' if len(v) > 60 else ''}")
    print("\nkww (= kwfv1):", mgr.get_kww()[:60], "...")
    print("\ncookie_string:", mgr.get_cookie_string()[:200], "...")
    print("\n缓存文件:", mgr.cache_path)
