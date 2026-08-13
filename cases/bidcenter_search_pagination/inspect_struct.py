# -*- coding: utf-8 -*-
"""最终精确化：提取分页内的招投标列表条目（zhaobiao/daili/zhongbiao）"""
import base64
import json
import struct

import requests
from Crypto.Cipher import AES

def _words_to_bytes(words):
    return b"".join(struct.pack(">I", w) for w in words)

KEY = _words_to_bytes([863652730, 2036741733, 1164342596, 1782662963])
IV = _words_to_bytes([1719227713, 1314533489, 1397643880, 1749959510])

data = {
    "from": "6137", "guid": "74a94c66-b5ce-4b64-b994-437a07e8992f",
    "location": "6138", "token": "", "next_token": "",
    "keywords": "python", "mod": "0", "page": "3",
}
resp = requests.post(
    "https://interface.bidcenter.com.cn/search/GetSearchProHandler.ashx",
    data=data,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://search.bidcenter.com.cn/",
        "Origin": "https://search.bidcenter.com.cn/",
    },
    timeout=15,
)
raw = base64.b64decode(resp.text)
text = AES.new(KEY, AES.MODE_CBC, IV).decrypt(raw).rstrip(b"\x00").decode("utf-8")
obj = json.loads(text)
ps = json.loads(obj["other2"]["pageSearchJson"])

print("recordcount=", ps.get("recordcount"), "pagecount=", ps.get("pagecount"),
      "page=", ps.get("page"), "pagesize=", ps.get("pagesize"))

for cat in ("zhaobiao", "daili", "zhongbiao", "hangye"):
    v = ps.get(cat)
    if isinstance(v, list) and v:
        print(f"\n=== {cat} 列表，{len(v)} 条 ===")
        first = v[0]
        if isinstance(first, dict):
            print("字段:", list(first.keys()))
            show = {k: (str(val)[:40]) for k, val in first.items()}
            print("首条:", json.dumps(show, ensure_ascii=False))
