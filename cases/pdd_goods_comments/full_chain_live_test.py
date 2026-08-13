# -*- coding: utf-8 -*-
"""全链活体判据：a3 → ae4 → a4 → reviews（用户批准，4 次请求，失败即停）

协议（已静态逆向）：
  a3 : GET  mobile.pinduoduo.com/proxy/api/xg/pfb/a3（无 body，axios withCredentials）
  ae4: POST xg.pinduoduo.com/xg/pfb/ae4（跨域，body={"data": shift30(JSON({u,f:"",keys:"t,acc"}))}）
       响应 result.data → shift(-30) → JSON（账号配置，acc 标志）
  a4 : POST mobile.pinduoduo.com/proxy/api/xg/pfb/a4（干净指纹，复用 a4_live_test 构造）
  reviews: POST（sdenv token + 全 cookie + verifyauthtoken + is_back=1）

shift30 = 每字符 charCode+30（_0x31bc2f/_0x23b186，源码已确认）
"""
import json
import os
import re
import sys
import time
import hashlib

from curl_cffi import requests as crl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 复用 a4_live_test 的 TLV/签名/准备函数
import a4_live_test as alt

GOODS_ID = "976241093684"
UID = "9505538327527"  # pdd_user_id（活体 cookie）


def shift(s, n):
    # _0x23b186：逐字符 charCode 偏移
    return "".join(chr(ord(ch) + n) for ch in s)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    from curl_cffi.requests import BrowserType
    edges = sorted([b for b in dir(BrowserType) if b.startswith("edge")])
    imp = getattr(BrowserType, edges[-1])
    print(f"impersonate={edges[-1]}")

    print("[A] 浏览器侧零风险准备 ...")
    cookie_str = alt.get_live_cookie_str()
    vat = alt.get_verify_auth_token()
    ac = alt.gen_anti_content(cookie_str)
    print(f"    cookie {len(cookie_str)}B, vat {len(vat)}B, token len={len(ac)}")

    sess = crl.Session(impersonate=imp)
    base = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": alt.FP_UA,
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
    }

    # ── 1) a3 ──
    print("[1] GET a3 ...")
    r1 = sess.get("https://mobile.pinduoduo.com/proxy/api/xg/pfb/a3",
                  headers={**base, "cookie": cookie_str}, timeout=30)
    print(f"    HTTP {r1.status_code}, body: {r1.text[:200]}")

    # ── 2) ae4（跨域，payload={u,f:"",keys:"t,acc"} shift30）──
    print("[2] POST ae4 ...")
    payload = json.dumps({"u": UID, "f": "", "keys": "t,acc"},
                         separators=(",", ":"))
    body2 = json.dumps({"data": shift(payload, 30)}, separators=(",", ":"))
    r2 = sess.post("https://xg.pinduoduo.com/xg/pfb/ae4",
                   headers={**base, "content-type": "application/json;charset=UTF-8",
                            "cookie": cookie_str},
                   data=body2, timeout=30)
    print(f"    HTTP {r2.status_code}")
    ae4_conf = None
    try:
        j2 = r2.json()
        raw = (((j2.get("result") or {}).get("data")) or "")
        if raw:
            ae4_conf = json.loads(shift(raw, -30))
        print(f"    解码后配置: {json.dumps(ae4_conf, ensure_ascii=False)[:300]}")
    except Exception as e:
        print(f"    响应解析失败: {e}, body: {r2.text[:200]}")

    # ── 3) a4（干净指纹）──
    print("[3] POST a4（干净指纹注册）...")
    src = open(os.path.join(HERE, "verify_a4_sign.py"), encoding="utf-8").read()
    DATA0 = re.search(r'DATA = "([^"]+)"', src).group(1)
    pairs = alt.decode_data(DATA0)
    kv = dict(zip(pairs[0::2], pairs[1::2]))
    now_ms = int(time.time() * 1000)
    delta = now_ms - int(kv["reportTimestamp"])
    kv["botD"] = '{"bot":false,"botKind":""}'
    kv["botKinds"] = ""
    kv["botSignals"] = ('{"detectPluginsArray":"unknown",'
                        '"detectWebDriverDescriptor":"unknown"}')
    kv["cdpProxy"] = "false"
    kv["hookFuncs"] = "[]"
    kv["reportTimestamp"] = str(now_ms)
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
    new_pairs = []
    for i in range(0, len(pairs), 2):
        new_pairs.append(pairs[i])
        new_pairs.append(kv[pairs[i]])
    data_new = alt.encode_pairs(new_pairs)
    ts_str = str(now_ms)
    sign = hashlib.sha1((alt.SALT + ts_str + data_new).encode()).hexdigest()
    r3 = sess.post("https://mobile.pinduoduo.com/proxy/api/xg/pfb/a4",
                   headers={**base, "content-type": "application/json;charset=UTF-8",
                            "cookie": cookie_str},
                   data=json.dumps({"data": data_new, "timestamp": ts_str,
                                    "appKey": "fe", "sign": sign},
                                   separators=(",", ":")),
                   timeout=30)
    j3 = r3.json() if r3.status_code == 200 else {}
    result_a = ((j3.get("result") or {}).get("a"))
    print(f"    HTTP {r3.status_code}, success={j3.get('success')}, "
          f"result.a={(result_a or '')[:20]}...")
    if result_a:
        cookie_str += f"; njrpl={result_a}"

    # ── 4) reviews 判据 ──
    print("[4] POST reviews（最终判据）...")
    url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
           f"?label_id=0&page=27&size=10&enable_video=1"
           f"&enable_group_review=1&pdduid=6772515013646&is_back=1")
    h4 = {**base, "content-type": "application/json;charset=UTF-8",
          "cookie": cookie_str, "anti-content": ac}
    if vat:
        h4["verifyauthtoken"] = vat
    r4 = sess.post(url, headers=h4,
                   data=json.dumps({"name": "goodsCommentListAxios",
                                    "anti_content": ac},
                                   separators=(",", ":")),
                   timeout=30)
    try:
        j4 = r4.json()
    except Exception:
        j4 = {"raw": r4.text[:300]}
    n = len(j4.get("data")) if isinstance(j4.get("data"), list) else 0
    print(f"    HTTP {r4.status_code}, error_code={j4.get('error_code')}, "
          f"条数={n}, verify_auth_token={bool(j4.get('verify_auth_token'))}")

    if r4.status_code == 200 and n > 0 and not j4.get("verify_auth_token"):
        print("\n★★★ 全链判据通过：a3→ae4→a4→reviews 纯本地复现打通 ★★★")
        # 样本落盘
        with open(os.path.join(HERE, "full_chain_sample.json"), "w",
                  encoding="utf-8") as f:
            json.dump(j4.get("data"), f, ensure_ascii=False, indent=1)
    else:
        print("\n判据失败：全链注册后仍被拒，障碍指向连接级画像或指纹内容深层校验。")

    ev = {"ts": now_ms, "a3": r1.status_code, "ae4_conf": ae4_conf,
          "a4_success": j3.get("success"), "reviews_status": r4.status_code,
          "reviews_error_code": j4.get("error_code"), "count": n}
    json.dump(ev, open(os.path.join(HERE, "full_chain_evidence.json"),
                       "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("证据已落盘: full_chain_evidence.json")


if __name__ == "__main__":
    main()
