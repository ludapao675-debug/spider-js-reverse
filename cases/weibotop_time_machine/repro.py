# -*- coding: utf-8 -*-
"""
weibotop.cn（热搜时光机）API 协议复现
====================================
目标站点: https://www.weibotop.cn/  （微博热搜历史查询）

逆向结论
--------------------------------------------------------------
所有 /api/* 均走统一加密通道（前端模块 7374 封装 + 模块 14624 解密）：

1. 响应解密: {"encrypted": true, "data": "<base64 密文>"}
   AES-256-CBC + PKCS7
   key = aa6218e56ddc05e908ec0842ae36fb8746b38cd6b7dc140b8df6826ca00b81d8  (64 hex, 32字节)
   iv  = fc3c868a2ffa7d1d45bccc0a4b4f4cca                                     (32 hex, 16字节)
   密文用 CryptoJS 输出（标准 base64，非 URL-safe）

2. GET 请求参数加密:
   _e = AES-256-CBC-PKCS7.encrypt(JSON.stringify(params)).toString()  # base64
   URL = path + "?_e=" + _e
   无参数接口（thermometer/hotspot）直接裸 GET

3. 词条 id -> topicId 编码（模块 44047）:
   topicId = base64url( 4字节大端( (0x5A7F55DD ^ id) >>> 0 ) )
            + 替换 -_ 去 = 填充
   解码函数 G.x(str) 为逆运算

4. 鉴权: wt_client cookie 由服务端 Set-Cookie 下发（HttpOnly），非前端生成；
   /api/history-token 用于历史快照（防爬，触发阿里云飞连滑块验证码）

已知接口:
   /api/hotlist?limit=N                 实时热搜榜（明文参数，加密响应）
   /api/ranking/rising                  上升最快
   /api/ranking/new                     新上榜
   /api/ai/hotspot                      今日热点 AI 解读
   /api/ai/brief?_e={"topicId":...}     单条词条 AI 简报
   /api/sentiment/thermometer           舆情情绪温度计
   /api/subscriptions                   订阅列表

用法
----
    python repro.py hotspot          # AI 热点解读（无参数）
    python repro.py thermometer      # 情绪温度计（无参数）
    python repro.py hotlist          # 实时热搜榜
    python repro.py brief --id 834724   # 指定词条 AI 简报（topicId 自动编码）
"""
import argparse
import base64
import json

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

KEY = bytes.fromhex("aa6218e56ddc05e908ec0842ae36fb8746b38cd6b7dc140b8df6826ca00b81d8")
IV = bytes.fromhex("fc3c868a2ffa7d1d45bccc0a4b4f4cca")
XOR_KEY = 1518025885  # 0x5A7F55DD

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Referer": "https://www.weibotop.cn/",
    "Content-Type": "application/json",
}


def aes_decrypt(data: str) -> str:
    """CryptoJS AES-CBC-PKCS7 密文(base64) -> UTF8 明文。"""
    raw = base64.b64decode(data)
    return unpad(AES.new(KEY, AES.MODE_CBC, IV).decrypt(raw), 16).decode("utf-8")


def aes_encrypt(plaintext: str) -> str:
    """UTF8 明文 -> CryptoJS 风格 base64 密文。"""
    raw = pad(plaintext.encode("utf-8"), 16)
    return base64.b64encode(AES.new(KEY, AES.MODE_CBC, IV).encrypt(raw)).decode("utf-8")


def topicid_encode(id_: int) -> str:
    """词条 id -> topicId（模块 44047 的 G.T）。"""
    i = (XOR_KEY ^ id_) & 0xFFFFFFFF
    b = bytes([(i >> 24) & 255, (i >> 16) & 255, (i >> 8) & 255, i & 255])
    return base64.b64encode(b).decode().replace("+", "-").replace("/", "_").rstrip("=")


def topicid_decode(s: str) -> int:
    """topicId -> 词条 id（模块 44047 的 G.x）。"""
    s = s.replace("-", "+").replace("_", "/") + "=" * (-len(s) % 4)
    b = base64.b64decode(s)
    if len(b) != 4:
        raise ValueError("topicId 长度异常")
    return (XOR_KEY ^ int.from_bytes(b, "big")) & 0xFFFFFFFF


def api_request(session: requests.Session, path: str, params: dict = None) -> dict:
    """按前端协议请求 /api/* 并自动解密。"""
    url = "https://www.weibotop.cn" + path
    if params:
        url += "?_e=" + aes_encrypt(json.dumps(params))
    r = session.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    d = r.json()
    if d.get("encrypted"):
        return json.loads(aes_decrypt(d["data"]))
    return d


def main() -> None:
    parser = argparse.ArgumentParser(description="weibotop.cn 热搜时光机协议复现")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("hotspot", help="AI 热点解读")
    sub.add_parser("thermometer", help="情绪温度计")
    sub.add_parser("hotlist", help="实时热搜榜")
    pr = sub.add_parser("ranking", help="榜单接口(rising/new)")
    pr.add_argument("--type", choices=["rising", "new"], default="rising")
    p = sub.add_parser("brief", help="单条词条 AI 简报")
    p.add_argument("--id", type=int, default=834724, help="词条数字 id")
    pht = sub.add_parser("history-token", help="历史快照 token(防爬)")
    pht.add_argument("--date", default="2026-08-12", help="日期 yyyy-MM-dd")
    pht.add_argument("--at", default="12:00", help="时刻 HH:mm")
    args = parser.parse_args()

    s = requests.Session()
    # 首页获取 wt_client cookie（服务端下发）
    s.get("https://www.weibotop.cn/", headers=HEADERS, timeout=15)

    if args.cmd == "hotspot":
        print(json.dumps(api_request(s, "/api/ai/hotspot"), ensure_ascii=False, indent=1)[:2000])
    elif args.cmd == "thermometer":
        print(json.dumps(api_request(s, "/api/sentiment/thermometer"), ensure_ascii=False, indent=1)[:2000])
    elif args.cmd == "hotlist":
        d = api_request(s, "/api/hotlist", {"limit": 50})
        for item in d.get("data", [])[:10]:
            tid = topicid_encode(item["id"])
            print(f"rank={item['rank']:>2} id={item['id']} topicId={tid} "
                  f"{item['name']} 热度={item['hotindex']}")
    elif args.cmd == "brief":
        tid = topicid_encode(args.id)
        print(f"topicId: {tid} (decode 校验={topicid_decode(tid)})")
        d = api_request(s, "/api/ai/brief", {"topicId": tid})
        print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
    elif args.cmd == "ranking":
        params = {"limit": 50}
        if args.type == "new":
            params["hours"] = 24
        d = api_request(s, f"/api/ranking/{args.type}", params)
        for item in d.get("data", [])[:10]:
            extra = ""
            if args.type == "rising":
                extra = f" 升{item.get('rankChange')}名" + (" [新]" if item.get("isNew") else "")
            elif item.get("starttime"):
                extra = f" 首上{item.get('starttime')[:10]}"
            print(f"rank={item['rank']:>2} id={item['id']} {item['name']} "
                  f"热度={item['hotindex']}{extra}")
    elif args.cmd == "history-token":
        # POST /api/history-token  body={"date","at"}  (防爬, <3月免登录但触发滑块, >=3月需登录)
        url = "https://www.weibotop.cn/api/history-token"
        r = s.post(url, headers=HEADERS,
                   data=json.dumps({"date": args.date, "at": args.at}), timeout=15)
        print(f"HTTP {r.status_code}")
        print(r.text[:800])


if __name__ == "__main__":
    main()
