# -*- coding: utf-8 -*-
"""
采招网（bidcenter.com.cn）搜索分页请求本地复现脚本

逆向结论（来源 searchv16.js）：
- 分页主接口：POST https://interface.bidcenter.com.cn/search/GetSearchProHandler.ashx
- 请求体（form-urlencoded）：from/location/guid/token/next_token/keywords/mod/page
  - token / next_token 为空，无签名参数
- 响应体为 Base64 密文，前端用 CryptoJS.AES 解密：
    AES-128-CBC，key/iv 为固定 WordArray，ZeroPadding
    key : [863652730, 2036741733, 1164342596, 1782662963]
    iv  : [1719227713, 1314533489, 1397643880, 1749959510]
  解密后 UTF-8 字符串为 JSON，含 pageSearchJson 字段（二次 eval 得列表）

本脚本：1) 直接发分页请求  2) AES 解密响应  3) 提取招投标列表
依赖：requests, pycryptodome
"""

import base64
import json
import struct

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ---------- 静态密钥（来自 searchv16.js line 49-50）----------
def _words_to_bytes(words):
    """CryptoJS WordArray.words -> 字节。

    CryptoJS 每个 word 是 32 位大端整数（最高有效字节在高位），
    故用 '>I'（大端）拆成 4 字节。
    """
    return b"".join(struct.pack(">I", w) for w in words)

KEY = _words_to_bytes([863652730, 2036741733, 1164342596, 1782662963])
IV = _words_to_bytes([1719227713, 1314533489, 1397643880, 1749959510])

BASE_URL = "https://interface.bidcenter.com.cn/search/GetSearchProHandler.ashx"
REFERER = "https://search.bidcenter.com.cn/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": REFERER,
    "Origin": REFERER,
    "Accept": "text/plain, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


def decrypt_response(cipher_b64: str) -> dict:
    """AES-128-CBC + ZeroPadding 解密响应密文 -> JSON dict"""
    raw = base64.b64decode(cipher_b64)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    padded = cipher.decrypt(raw)
    # ZeroPadding：去掉尾随的 \x00
    clean = padded.rstrip(b"\x00")
    text = clean.decode("utf-8")
    return json.loads(text)


def fetch_page(keywords: str, page: int, guid: str,
               from_code: str = "6137", location: str = "6138",
               cookies: dict | None = None) -> dict:
    """发起一次分页搜索请求并返回解密后的 JSON。

    cookies: 登录态 Cookie（含 biduid/bidguid 等）。未登录时接口返回
    聚合统计页（recordcount/pagecount），明细列表需登录态才返回。
    """
    data = {
        "from": from_code,
        "guid": guid,
        "location": location,
        "token": "",
        "next_token": "",
        "keywords": keywords,
        "mod": "0",
        "page": str(page),
    }
    resp = requests.post(BASE_URL, data=data, headers=HEADERS,
                         cookies=cookies or {}, timeout=15)
    resp.raise_for_status()
    return decrypt_response(resp.text)


def parse_list(decrypted: dict) -> dict:
    """从解密结果中提取 pageSearchJson 对象（与前端 resultData 对齐）。

    实际响应结构（已验证）：decrypted.other2.pageSearchJson -> JSON 字符串
    其中的 zhaobiao/daili/zhongbiao/hangye 为各分类明细列表（登录态才有）。
    """
    other2 = decrypted.get("other2")
    if isinstance(other2, str):
        other2 = json.loads(other2)
    if isinstance(other2, dict) and "pageSearchJson" in other2:
        ps = other2["pageSearchJson"]
        return json.loads(ps) if isinstance(ps, str) else ps
    return decrypted


def extract_items(parsed: dict) -> dict[str, list]:
    """提取各分类明细列表，返回 {分类: 条目列表}"""
    out = {}
    for cat in ("zhaobiao", "daili", "zhongbiao", "hangye"):
        v = parsed.get(cat)
        if isinstance(v, list) and v:
            out[cat] = v
    return out


if __name__ == "__main__":
    # 用抓包得到的真实 guid 复现 page=3（python 搜索）
    # 登录态：把浏览器 Cookie（含 biduid 等）以 dict 形式传给 cookies=
    GUID = "74a94c66-b5ce-4b64-b994-437a07e8992f"
    result = fetch_page("python", page=3, guid=GUID)
    print(f"[+] 解密成功，返回顶层字段：{list(result.keys())}")
    parsed = parse_list(result)
    print(f"[+] pageSearchJson 字段数：{len(parsed)}")
    print(f"[+] 分页统计：recordcount={parsed.get('recordcount')} "
          f"pagecount={parsed.get('pagecount')} page={parsed.get('page')} "
          f"pagesize={parsed.get('pagesize')}")
    items = extract_items(parsed)
    if items:
        for cat, lst in items.items():
            print(f"[+] {cat} 明细：{len(lst)} 条")
            print(f"    首条：{json.dumps(lst[0], ensure_ascii=False)[:300]}")
    else:
        print("[*] 未登录态：仅返回聚合统计，登录后传 cookies= 可拿明细列表")
