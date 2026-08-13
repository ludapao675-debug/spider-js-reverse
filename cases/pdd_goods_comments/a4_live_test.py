# -*- coding: utf-8 -*-
"""活体判据实验：干净 a4 指纹注册 + sdenv token reviews（用户已批准，预算 a4×1 + reviews×1）

时序（对齐真实页面）：
  A. 浏览器侧零风险准备：取活体 Cookie / VerifyAuthToken / sdenv 离线生成 anti_content
  B1. 本地构造干净 a4（清洗 botD/cdpProxy/hookFuncs 自曝字段，时间戳平移到当前）
      → TLV→zlib→'0a'+b64 → SHA1 签名 → POST /proxy/api/xg/pfb/a4
      → 响应 result.a 写入 cookie njrpl（源码 _0x31ed45/_0xf9e592）
  B2. 同 Session 发 reviews（anti-content + verifyauthtoken + is_back=1）

判据：reviews 200+10条 = 纯本地路线打通；54001/verify_auth_token = 仍需 a3/ae4 链或指纹内容校验
失败即停，绝不重试。
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import zlib

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
HERE = os.path.dirname(os.path.abspath(__file__))
GOODS_ID = "976241093684"
PDDUID = "6772515013646"
SALT = "feHJ6793TJDI86DLS9D"
# 指纹内 UA 是 Edge 151，本地请求 UA 必须逐字一致（交叉校验）
FP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0")

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def api_post(path, payload, timeout=120):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── TLV 编解码（与 verify_a4_roundtrip.py 相同，已字节级验证）──
def zigzag(n):
    n &= 0xFFFFFFFF
    return ((n << 1) ^ (n >> 31)) & 0xFFFFFFFF


def varint(z):
    out = bytearray()
    while True:
        b = z & 0x7F
        z >>= 7
        out.append(b | 0x80 if z else b)
        if not z:
            break
    return bytes(out)


def enc_str(s):
    raw = s.encode("utf-8")
    return varint(zigzag(0xF1)) + varint(zigzag(len(raw))) + raw


def read_varint(buf, pos):
    val, shift = 0, 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return (val >> 1) ^ -(val & 1), pos


def decode_data(data_str):
    """'0a'+urlsafe_b64(zlib(TLV)) → 有序 kv 列表"""
    b64 = data_str[2:].replace("-", "+").replace("_", "/")
    b64 += "=" * (-len(b64) % 4)
    es = zlib.decompress(base64.b64decode(b64))
    pairs, pos, n = [], 0, len(es)
    while pos < n:
        assert es[pos] == 0xE2 and es[pos + 1] == 0x03
        pos += 2
        ln, pos = read_varint(es, pos)
        pairs.append(es[pos:pos + ln].decode("utf-8"))
        pos += ln
    return pairs


def encode_pairs(pairs):
    out = bytearray()
    for s in pairs:
        out += enc_str(s)
    return '0a' + base64.b64encode(
        zlib.compress(bytes(out))).decode().translate(
        str.maketrans("+/", "-_")).rstrip("=")


# ── A 阶段：浏览器侧零风险准备 ──────────────────────────────
def get_live_cookie_str():
    d = api_post("/api/browser/page/cookies",
                 {"all_domains": False, "all_info": False}, timeout=20)
    items = d.get("cookies") or []
    return "; ".join(f"{c.get('name')}={c.get('value')}"
                     for c in items if c.get("name"))


def get_verify_auth_token():
    r = api_post("/api/browser/page/run-js", {
        "code": "(localStorage.getItem('VerifyAuthToken')||'')",
        "timeout_sec": 10})
    return str(r.get("result") or "").strip()


def gen_anti_content(cookie_str):
    """复用 local_repro_experiment 的 bundle+sdenv 链（简化：直接读已验证脚本的 BUNDLE_JS）"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lre", os.path.join(HERE, "local_repro_experiment.py"))
    lre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lre)
    r = api_post("/api/browser/page/run-js", {
        "code": lre.BUNDLE_JS, "return_mode": "json",
        "await_promise": True, "timeout_sec": 60})
    res = r.get("result")
    if not isinstance(res, dict) or "bundle" not in res:
        if r.get("result_stashed") and r.get("result_file"):
            fname = os.path.basename(str(r["result_file"]))
            with urllib.request.urlopen(
                    f"{BACKEND}/api/browser/page/run-js/result?file={fname}",
                    timeout=30) as resp:
                res = (json.loads(resp.read().decode("utf-8"))).get("data") or {}
        else:
            raise RuntimeError(f"bundle 构建失败: {str(res)[:200]}")
    d = api_post("/api/sdenv/run-code", {
        "js_code": res["bundle"],
        "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookies": cookie_str, "super_env": True, "timeout": 60,
        "eval_expression": "globalThis.__sdenv_token"}, timeout=180)
    token = ""
    for part in str(d.get("cookies") or "").split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac="):]
            break
    if not token:
        ev = d.get("eval_result")
        if isinstance(ev, str) and ev.startswith("0as"):
            token = ev.strip()
    if not token.startswith("0as"):
        raise RuntimeError(f"sdenv 生成失败: {str(d.get('error'))[:200]}")
    return token


def main():
    # 选最新 edge impersonate（对齐指纹内 Edge 系 TLS 档位）
    from curl_cffi.requests import BrowserType
    edges = sorted([b for b in dir(BrowserType) if b.startswith("edge")])
    imp = getattr(BrowserType, edges[-1])
    print(f"impersonate={edges[-1]}")

    print("[A1] 取活体 Cookie / VerifyAuthToken ...")
    cookie_str = get_live_cookie_str()
    vat = get_verify_auth_token()
    print(f"     cookie {len(cookie_str)}B, verifyauthtoken {len(vat)}B")

    print("[A2] sdenv 离线生成 anti_content ...")
    ac = gen_anti_content(cookie_str)
    print(f"     token: {ac[:30]}... len={len(ac)}")

    # ── B1：构造干净 a4 ──────────────────────────────
    print("[B1] 构造干净 a4 指纹并注册（1 次请求）...")
    src = open(os.path.join(HERE, "verify_a4_sign.py"), encoding="utf-8").read()
    DATA0 = re.search(r'DATA = "([^"]+)"', src).group(1)
    pairs = decode_data(DATA0)
    kv = dict(zip(pairs[0::2], pairs[1::2]))

    now_ms = int(time.time() * 1000)
    old_ts = int(kv["reportTimestamp"])
    delta = now_ms - old_ts
    # 清洗自曝字段（最小改动原则：只动明确判定 bot 的字段）
    kv["botD"] = '{"bot":false,"botKind":""}'
    kv["botKinds"] = ""
    kv["botSignals"] = ('{"detectPluginsArray":"unknown",'
                        '"detectWebDriverDescriptor":"unknown"}')
    kv["cdpProxy"] = "false"
    kv["hookFuncs"] = "[]"
    kv["reportTimestamp"] = str(now_ms)
    # 行为事件/pageId 内嵌时间戳同步平移，保持内部一致性
    try:
        mv = json.loads(kv["moveData"])
        for e in mv:
            if "timestamp" in e:
                e["timestamp"] += delta
        kv["moveData"] = json.dumps(mv, separators=(",", ":"))
    except Exception:
        pass
    m = re.match(r"^(.*~JtK)(\d+)$", kv["pageId"])
    if m:
        kv["pageId"] = m.group(1) + str(int(m.group(2)) + delta)

    # 按原序重建（保持字段顺序与原始一致）
    new_pairs = []
    for i in range(0, len(pairs), 2):
        new_pairs.append(pairs[i])
        new_pairs.append(kv[pairs[i]])
    data_new = encode_pairs(new_pairs)
    ts_str = str(now_ms)
    sign = hashlib.sha1((SALT + ts_str + data_new).encode()).hexdigest()
    print(f"     data {len(data_new)}B, sign={sign[:16]}...")

    sess = crl.Session(impersonate=imp)
    base_headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "user-agent": FP_UA,
    }
    r1 = sess.post(
        "https://mobile.pinduoduo.com/proxy/api/xg/pfb/a4",
        headers={**base_headers, "cookie": cookie_str},
        data=json.dumps({"data": data_new, "timestamp": ts_str,
                         "appKey": "fe", "sign": sign},
                        separators=(",", ":")),
        timeout=30)
    print(f"     a4 → HTTP {r1.status_code}")
    try:
        j1 = r1.json()
    except Exception:
        j1 = {"raw": r1.text[:300]}
    print(f"     响应: {json.dumps(j1, ensure_ascii=False)[:300]}")
    result_a = ((j1.get("result") or {}).get("a")) if isinstance(j1, dict) else None
    if result_a:
        # 源码：result.a 写 cookie njrpl（365天）+ localStorage h_wjrpl
        cookie_str += f"; njrpl={result_a}"
        print(f"     指纹凭证 result.a={result_a[:24]}... 已并入会话 cookie")
    else:
        print("     !! a4 未返回指纹凭证，reviews 判据置信度下降")

    # ── B2：reviews 判据（1 次请求）──────────────────────────────
    print("[B2] reviews 判据请求（1 次）...")
    url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
           f"?label_id=0&page=26&size=10&enable_video=1"
           f"&enable_group_review=1&pdduid={PDDUID}&is_back=1")
    h2 = {**base_headers, "cookie": cookie_str, "anti-content": ac}
    if vat:
        h2["verifyauthtoken"] = vat
    r2 = sess.post(url, headers=h2,
                   data=json.dumps({"name": "goodsCommentListAxios",
                                    "anti_content": ac},
                                   separators=(",", ":")),
                   timeout=30)
    try:
        j2 = r2.json()
    except Exception:
        j2 = {"raw": r2.text[:300]}
    n = len(j2.get("data")) if isinstance(j2.get("data"), list) else 0
    print(f"     reviews → HTTP {r2.status_code}, error_code="
          f"{j2.get('error_code')}, 条数={n}, "
          f"verify_auth_token={bool(j2.get('verify_auth_token'))}")

    # ── 判据结论 ──────────────────────────────
    if r2.status_code == 200 and n > 0 and not j2.get("verify_auth_token"):
        print("\n★★★ 判据通过：干净 a4 注册 + 全本地 reviews 成功，纯本地路线打通 ★★★")
    else:
        print("\n判据失败：a4 注册链不足以放行 reviews。"
              "剩余嫌疑：a3/ae4 前置链 / 指纹内容深层校验 / 连接画像。")

    # 证据落盘
    ev = {"ts": now_ms, "impersonate": edges[-1],
          "a4_status": r1.status_code, "a4_resp": j1,
          "reviews_status": r2.status_code, "reviews_resp_head": str(j2)[:800]}
    json.dump(ev, open(os.path.join(HERE, "a4_live_test_evidence.json"),
                       "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("证据已落盘: a4_live_test_evidence.json")


if __name__ == "__main__":
    main()
