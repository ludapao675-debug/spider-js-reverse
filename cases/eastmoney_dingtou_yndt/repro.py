# -*- coding: utf-8 -*-
"""
天天基金「近1年定投收益排行」接口复现脚本
==========================================
目标页面: https://fund.eastmoney.com/dingtou/syph_yndt.html
数据接口: GET https://fund.eastmoney.com/api/Dtshph.ashx (JSONP)

逆向结论
--------
- 纯 jQuery JSONP 数据接口，无加密、无签名、无动态 Cookie 依赖。
- 页面内联脚本调用: $.getJSON("//fund.eastmoney.com/api/Dtshph.ashx?t=0&c=yndt&s=desc&issale=1"
    + "&page=" + pageIndex + "&psize=" + pageSize + "&callback=?", ...)
- 参数说明:
    t       = 0        固定
    c       = yndt     指标类型(近1年定投收益; endt/sndt/wndt 分别对应 近2/3/5 年)
    s       = desc     排序方向 asc|desc
    issale  = 1        在售过滤(1=可购 0=全部)
    page    = N        页码
    psize   = N        每页条数
    callback= 任意名   JSONP 回调名(本地可写 jsonp 或 cb，无需 jQuery 格式)
    _       = 毫秒时间戳 防缓存(可省略)
- 响应: callback({"total":16082,"pageIndex":1,"data":"<table>...</table>"})
    data 为服务端渲染的 HTML 表格，字段含 代码/简称/单位净值/日期/各周期定投收益。

用法
----
    python repro.py                      # 抓取第 1 页
    python repro.py --page 2             # 抓取第 2 页
    python repro.py --pages 1-3          # 抓取 1-3 页
    python repro.py --indicator endt     # 切换为近2年定投收益
"""
import argparse
import json
import re
import time

import requests

BASE_URL = "https://fund.eastmoney.com/api/Dtshph.ashx"
REFERER = "https://fund.eastmoney.com/dingtou/syph_yndt.html"
HEADERS = {
    "Referer": REFERER,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Accept": "text/javascript, application/javascript, application/ecmascript, */*; q=0.01",
}


def fetch_page(page: int, psize: int = 100, indicator: str = "yndt",
               sort: str = "desc", issale: int = 1, timeout: int = 15) -> dict:
    """请求一页数据，剥离 JSONP 包裹并返回解析后的 dict。"""
    params = {
        "t": 0,
        "c": indicator,
        "s": sort,
        "issale": issale,
        "page": page,
        "psize": psize,
        "callback": "jsonp",
        "_": int(time.time() * 1000),
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    # 响应形如 jsonp({...})，去掉函数壳后即为 JSON
    text = resp.text.strip()
    payload = re.sub(r"^[\w$]+\(|\)\s*;?\s*$", "", text, flags=re.S)
    return json.loads(payload)


def parse_rows(html: str) -> list:
    """从服务端返回的 HTML 表格中提取 (基金代码, 简称, 单位净值, 日期, 近1年定投收益)。"""
    rows = []
    # 每行形如:
    # <tr><td><input value="021608,南方上证科创板芯片ETF发起联接C" .../></td>
    # <td>301</td><td><a href="/021608.html">021608</a></td>
    # <td class="tl"><a href="/021608.html">简称</a></td>...
    for tr in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(tds) < 7:
            continue
        code_m = re.search(r"value=\"(\d{6}),", tds[0])
        name_m = re.search(r">([^<]+)</a>", tds[3])
        nav_m = re.search(r"([\d.]+)", tds[5])
        date_m = re.search(r"(\d{2}-\d{2})", tds[6])
        yndt_m = re.search(r"([-+]?[\d.]+%)", tds[7]) if len(tds) > 7 else None
        rows.append({
            "code": code_m.group(1) if code_m else "",
            "name": name_m.group(1) if name_m else "",
            "nav": nav_m.group(1) if nav_m else "",
            "date": date_m.group(1) if date_m else "",
            "yndt": yndt_m.group(1) if yndt_m else "",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="天天基金定投收益排行复现")
    parser.add_argument("--page", type=int, default=1, help="单页页码")
    parser.add_argument("--pages", type=str, default="", help="页码区间 1-3")
    parser.add_argument("--psize", type=int, default=100, help="每页条数")
    parser.add_argument("--indicator", type=str, default="yndt",
                        help="yndt=近1年 endt=近2年 sndt=近3年 wndt=近5年")
    args = parser.parse_args()

    if args.pages:
        start, end = (int(x) for x in args.pages.split("-"))
        pages = range(start, end + 1)
    else:
        pages = [args.page]

    for page in pages:
        data = fetch_page(page, args.psize, args.indicator)
        rows = parse_rows(data.get("data", ""))
        print(f"[page {data.get('pageIndex')}] total={data.get('total')} rows={len(rows)}")
        for row in rows[:5]:
            print("  ", row)
        time.sleep(0.5)  # 轻节流


if __name__ == "__main__":
    main()
