# -*- coding: utf-8 -*-
"""
终极判据：遥测配对的全纯本地复现
时序（模拟真实页面）：
  1. 本地发 t.gif 曝光遥测（前置）
  2. 本地发 reviews 请求（sdenv 离线 token + verifyauthtoken + is_back=1）
  3. 本地发 t.gif 浏览时长遥测（后置）

风控预算：本次 reviews 仅 1 条；失败立即停止（当日账号预算已近耗尽）。
"""
import json
import os
import random
import re
import string
import sys
import time
import urllib.request
from urllib.parse import urlencode

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
HERE = os.path.dirname(os.path.abspath(__file__))
GOODS_ID = "976241093684"
PDDUID = "6772515013646"
B36 = string.digits + string.ascii_lowercase


def api_post(path, payload, timeout=180):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def b36(n):
    return "".join(random.choice(B36) for _ in range(n))


class LocalSession:
    """纯本地会话：cookie/上下文/遥测/请求全部本地构造"""

    def __init__(self):
        rc = api_post("/api/browser/page/cookies", {"tab_id": TAB_ID}, timeout=20)
        self.cookies = {c["name"]: c["value"] for c in (rc.get("cookies") or [])}
        r = api_post("/api/browser/page/run-js", {
            "tab_id": TAB_ID,
            "code": ("(() => ({page_id: new URLSearchParams(location.search).get('page_id') || '',"
                     "refer_page_name: new URLSearchParams(location.search).get('refer_page_name') || '',"
                     "refer_page_id: new URLSearchParams(location.search).get('refer_page_id') || '',"
                     "is_back: new URLSearchParams(location.search).get('is_back') || '',"
                     "vat: localStorage.getItem('VerifyAuthToken') || '',"
                     "sw: screen.width, sh: screen.height, dpr: window.devicePixelRatio}))()"),
            "return_mode": "json"}, timeout=20)
        self.ctx = r.get("result") or {}
        self.session = crl.Session(impersonate="chrome")
        self.dcf_counter = random.randint(20, 26)

    def _tl_headers(self):
        h = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://mobile.pinduoduo.com",
            "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
            "cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()
                                if k in ("api_uid", "jrpl")),
            "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
        }
        if self.ctx.get("vat"):
            h["verifyauthtoken"] = self.ctx["vat"]
        return h

    def send_telemetry(self, op="impr", extra=None):
        """构造并发送一条 t.gif 遥测（载荷结构对照活体样本）"""
        now = int(time.time() * 1000)
        nano_fp = self.cookies.get("_nano_fp", "")
        pdd_vds = self.cookies.get("pdd_vds", "")
        self.dcf_counter += 1
        fields = {
            "goods_id": GOODS_ID,
            "page_sn": "10058",
            "page_id": self.ctx.get("page_id", ""),
            "refer_page_name": self.ctx.get("refer_page_name", ""),
            "refer_page_id": self.ctx.get("refer_page_id", ""),
            "refer_page_sn": "10390",
            "is_back": self.ctx.get("is_back", "1"),
            "op": op,
            "time": str(now),
            "log_id": f"{now}{b36(16)}",
            "user_id": self.cookies.get("pdd_user_id", ""),
            "uin": self.cookies.get("pdd_user_uin", ""),
            "app_id": "",
            "screen_width": str(self.ctx.get("sw", 2560)),
            "screen_height": str(self.ctx.get("sh", 1600)),
            "dpr": str(self.ctx.get("dpr", 1)),
            "app_version": "",
            "platform": "unknown",
            "cookie_fp": nano_fp,
            "storage_fp": nano_fp,
            "dcf": f"{pdd_vds}.{self.dcf_counter}.{random.randint(100000000, 3999999999)}",
        }
        if extra:
            fields.update(extra)
        payload = urlencode(fields)
        resp = self.session.post("https://th.pinduoduo.com/t.gif",
                                 headers=self._tl_headers(), data=payload, timeout=15)
        return resp.status_code

    def gen_token_sdenv(self):
        """sdenv 离线生成 anti_content（webpack 闭包 bundle）"""
        src = open(os.path.join(HERE, "local_repro_experiment.py"), encoding="utf-8").read()
        bundle_js = re.search(r'BUNDLE_JS = r"""(.*?)"""', src, re.S).group(1)
        rb = api_post("/api/browser/page/run-js", {
            "tab_id": TAB_ID, "code": bundle_js,
            "return_mode": "json", "await_promise": True, "timeout_sec": 60}, timeout=90)
        res = rb.get("result")
        if not isinstance(res, dict) and rb.get("result_stashed"):
            fn = os.path.basename(str(rb.get("result_file") or ""))
            rr = json.loads(urllib.request.urlopen(
                f"{BACKEND}/api/browser/page/run-js/result?file={fn}", timeout=30).read())
            res = rr.get("data") or {}
        bundle = (res or {}).get("bundle", "")
        if not bundle:
            raise RuntimeError(f"bundle 构建失败: {str(res)[:150]}")
        cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        d = api_post("/api/sdenv/run-code", {
            "js_code": bundle,
            "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
            "cookies": cookie_str, "super_env": True, "timeout": 60}, timeout=180)
        ck = str(d.get("cookies") or "")
        for part in ck.split(";"):
            kv = part.strip()
            if kv.startswith("__sdenv_ac="):
                return kv[len("__sdenv_ac="):]
        raise RuntimeError(f"sdenv 生成失败: {str(d.get('output'))[-200:]}")

    def fetch_reviews(self, page, token):
        """本地发 reviews 请求（全头对齐 + verifyauthtoken + is_back）"""
        url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
               f"?label_id=0&page={page}&size=10&enable_video=1"
               f"&enable_group_review=1&pdduid={PDDUID}&is_back=1")
        cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://mobile.pinduoduo.com",
            "referer": (f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}"
                        f"&is_back=1"),
            "cookie": cookie_str,
            "anti-content": token,
            "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
            "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "accept-language": "zh-CN,zh;q=0.9",
        }
        if self.ctx.get("vat"):
            headers["verifyauthtoken"] = self.ctx["vat"]
        resp = self.session.post(
            url, headers=headers,
            json={"name": "goodsCommentListAxios", "anti_content": token}, timeout=15)
        return resp


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    s = LocalSession()
    print(f"[1] 会话数据就绪 vat={bool(s.ctx.get('vat'))}")

    st = s.send_telemetry("impr")
    print(f"[2] 前置遥测: status={st}")

    token = s.gen_token_sdenv()
    print(f"[3] sdenv token: {token[:24]}... len={len(token)}")

    resp = s.fetch_reviews(26, token)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:200]}
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        print(f"[4] ★★★ reviews 本地通过！status=200 n={len(body['data'])} "
              f"first={body['data'][0].get('name') if body['data'] else ''}")
        st2 = s.send_telemetry("impr", {"browse_time": str(random.randint(800, 1500))})
        print(f"[5] 后置遥测: status={st2}")
        print("\n═══ 纯本地复现成立：遥测配对 + sdenv token + 全头对齐 ═══")
    else:
        print(f"[4] reviews 仍被拒: status={resp.status_code} {str(body)[:150]}")
        print("═══ 遥测配对仍不足，阻碍在更深层（连接画像/xg·pfb 指纹链），停止实验 ═══")


if __name__ == "__main__":
    main()
