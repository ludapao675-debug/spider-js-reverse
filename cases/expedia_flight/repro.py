# -*- coding: utf-8 -*-
"""
Expedia (expedia.com) 机票搜索 API 纯本地复现脚本 v3.1
==============================================
深度逆向分析结论（已验证 2026-08-13）：
1. 核心接口：FlightsSearchResultsLoadedQuery
   Hash: ab6332b2d911a61d0002f1abdf1b63f3a987b4682f8d2f0321be0c8304fef6ff
2. 必须携带的请求头：x-enable-apq: true（APQ 开关）
3. 价格字段路径：listingResult.listings[n].priceDisplay.rows[0].elements[0].price.text
4. Cookie 来源：需要从真实浏览器会话提取（含 datadome/bm_sz 等 Akamai 组件）
5. 两步流程：① FormLoaded → ② SearchResultsLoaded

使用方法：
  1) 浏览器打开 expedia.com/cn/Flights，通过人机验证
  2) F12 -> Console -> document.cookie，复制全部内容
  3) 填入 BROWSER_COOKIE，运行脚本
"""

import uuid
import json
from datetime import datetime
from curl_cffi import requests

# ─────────────────────────────────────────────
# 【配置区】从浏览器 Console 复制 document.cookie 填入此处
# ─────────────────────────────────────────────
BROWSER_COOKIE = ""   # 粘贴完整 Cookie 字符串

# DUAID：从浏览器 DUAID Cookie 值复制
DUAID = "de93668a-f781-43b8-9bd7-5f563b773145"

# ─────────────────────────────────────────────
# GraphQL APQ Hash（从真实请求抓包得到）
# ─────────────────────────────────────────────
HASH_FORM_LOADED   = "d0854dbabaf7f50353b9a08580d90aa60e783ca50e4161253bc955da91001cbb"
HASH_SEARCH_RESULTS = "ab6332b2d911a61d0002f1abdf1b63f3a987b4682f8d2f0321be0c8304fef6ff"
HASH_CHEAPEST_FARE  = "abfc217dc846e91097583eef5463e2f8ae221dce3ac6afe1aa1d44e2c1f75561"

GRAPHQL_URL = "https://www.expedia.com/graphql"
HOME_URL    = "https://www.expedia.com/cn/Flights"


class ExpediaFlightClient:
    """Expedia 机票搜索 API 纯本地客户端（逆向 v3.1）"""

    def __init__(self, cookie_str: str = "", duaid: str = ""):
        # curl_cffi 伪造 Chrome120 TLS/JA3 指纹
        self.session = requests.Session(impersonate="chrome120")
        self.duaid = duaid or str(uuid.uuid4())
        self.search_id = str(uuid.uuid4())
        self.cookie_str = cookie_str.strip()

        # 基础请求头（来自真实浏览器抓包）
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Origin": "https://www.expedia.com",
            "Referer": "https://www.expedia.com/cn/Flights",
        })

        if self.cookie_str:
            self.session.headers["Cookie"] = self.cookie_str
            print(f"[+] 已注入浏览器 Cookie（{len(self.cookie_str)} 字节）")
        else:
            print("[!] 未提供 Cookie，尝试 curl_cffi 预热（成功率低）...")
            self._warmup()

    def _warmup(self):
        """curl_cffi 预热（仅获取基础 Cookie，无 datadome）"""
        try:
            resp = self.session.get(HOME_URL, timeout=15)
            print(f"    预热状态: {resp.status_code}, Cookie 数量: {len(self.session.cookies)}")
        except Exception as e:
            print(f"[!] 预热异常: {e}")

    def _ctx(self):
        return {
            "siteId": 1, "locale": "zh_CN", "eapid": 0, "tpid": 1,
            "currency": "USD", "device": {"type": "DESKTOP"},
            "identity": {"duaid": self.duaid, "authState": "ANONYMOUS"},
            "privacyTrackingState": "CAN_TRACK",
        }

    def _journey(self, origin, dest, out_date, in_date=None):
        y, m, d = map(int, out_date.split("-"))
        legs = [{
            "departureDate": {"year": y, "month": m, "day": d},
            "destination": dest, "origin": origin,
            "originAirportLocationType": "UNSPECIFIED",
            "destinationAirportLocationType": "UNSPECIFIED",
        }]
        if in_date:
            y2, m2, d2 = map(int, in_date.split("-"))
            legs.append({
                "departureDate": {"year": y2, "month": m2, "day": d2},
                "destination": origin, "origin": dest,
                "originAirportLocationType": "UNSPECIFIED",
                "destinationAirportLocationType": "UNSPECIFIED",
            })
        return legs

    def _hdrs(self):
        return {
            "Content-Type": "application/json",
            "client-info": "flights-shopping-pwa,latest,external",
            "device-user-agent-id": self.duaid,
            "x-page-id": "page.Flight-Search-Roundtrip.Out,F,20",
            "x-enable-apq": "true",    # 关键！启用 APQ（从抓包发现之前一直漏了这个）
        }

    def step1_form_loaded(self, origin, dest, out_date, in_date=None):
        """步骤一：FormLoaded —— 告知服务端搜索表单已加载"""
        trip = "ROUND_TRIP" if in_date else "ONE_WAY"
        payload = {
            "variables": {
                "context": self._ctx(),
                "flightsSearchContext": {
                    "tripType": trip,
                    "hasCreditRedemptionIntent": None,
                    "originalBookingId": None,
                    "searchId": self.search_id,
                },
                "journeyCriteria": self._journey(origin, dest, out_date, in_date),
                "queryState": "LOADED",
                "searchPreferences": {"cabinClass": "COACH"},
                "travelerDetails": [{"travelerType": "ADULT", "count": 1}],
                "shoppingContext": None,
            },
            "operationName": "FlightsShoppingPwaFlightSearchFormLoaded",
            "extensions": {
                "persistedQuery": {"sha256Hash": HASH_FORM_LOADED, "version": 1}
            },
        }
        return self.session.post(GRAPHQL_URL, json=payload, headers=self._hdrs(), timeout=15)

    def step2_search_results(self, origin, dest, out_date, in_date=None, start=0, size=25):
        """步骤二：SearchResultsLoaded —— 获取机票列表（核心接口）"""
        trip = "ROUND_TRIP" if in_date else "ONE_WAY"
        payload = [{
            "operationName": "FlightsSearchResultsLoadedQuery",
            "variables": {
                "faresSeparationType": "BASE_AND_UPSELL",
                "searchFilterValuesList": [],
                "flightsSearchContext": {
                    "tripType": trip,
                    "previousOriginalBookingId": None,
                    "journeysContinuationId": None,
                    "hasCreditRedemptionIntent": None,
                    "originalBookingId": None,
                    "searchId": self.search_id,
                },
                "journeyCriteria": self._journey(origin, dest, out_date, in_date),
                "searchPreferences": {"cabinClass": "COACH"},
                "sortOption": None,
                "travelerDetails": [{"travelerType": "ADULT", "count": 1}],
                "searchPagination": {"size": size, "startingIndex": start},
                "flightsSearchComponentCriteria": {"queryParams": []},
                "shoppingContext": None,
                "virtualAgentContext": None,
                "context": self._ctx(),
                "queryState": "LOADED",
            },
            "extensions": {
                "persistedQuery": {"version": 1, "sha256Hash": HASH_SEARCH_RESULTS}
            },
        }]
        return self.session.post(GRAPHQL_URL, json=payload, headers=self._hdrs(), timeout=20)

    def parse_flights(self, data: list) -> list:
        """
        解析 FlightsSearchResultsLoadedQuery 响应
        数据路径：data[0].data.flightsSearch.listingResult.listings
        价格路径：listings[n].priceDisplay.rows[0].elements[0].price.text
        仅处理 typename==FlightsStandardOffer 的条目
        """
        results = []
        try:
            listings = (
                data[0]["data"]["flightsSearch"]["listingResult"]["listings"]
            )
            for item in listings:
                if item.get("__typename") != "FlightsStandardOffer":
                    continue
                # 价格
                price = "N/A"
                for row in (item.get("priceDisplay") or {}).get("rows") or []:
                    for elem in row.get("elements") or []:
                        p = elem.get("price") or {}
                        if p.get("text"):
                            price = p["text"]
                            break
                    if price != "N/A":
                        break
                # 赞助标注
                sponsor = (item.get("sponsoredAirline") or {}).get("airlineName", "")
                results.append({
                    "price": price,
                    "sponsored": bool(sponsor),
                    "sponsor_name": sponsor,
                })
        except (KeyError, IndexError, TypeError) as e:
            print(f"[!] 解析异常: {e}")
        return results

    def search(self, origin="LAX", dest="PEK",
               out_date="2026-08-25", in_date="2026-09-02"):
        """完整两步搜索"""
        sep = "=" * 58
        print(f"\n{sep}")
        print(f"  Expedia 机票:  {origin} --> {dest}")
        print(f"  去程: {out_date}   返程: {in_date or '(单程)'}")
        print(sep)

        print("[1/2] FormLoaded...")
        r1 = self.step1_form_loaded(origin, dest, out_date, in_date)
        print(f"      HTTP {r1.status_code}")
        if r1.status_code != 200:
            print(f"      {r1.text[:200]}")
            print("      Cookie 可能已过期，请重新从浏览器复制")
            return None

        print("[2/2] SearchResultsLoaded...")
        r2 = self.step2_search_results(origin, dest, out_date, in_date)
        print(f"      HTTP {r2.status_code}")
        if r2.status_code != 200:
            print(f"      {r2.text[:200]}")
            return None

        data = r2.json()
        flights = self.parse_flights(data)

        print(f"\n[OK] 获取到 {len(flights)} 条机票：\n")
        for i, f in enumerate(flights, 1):
            tag = f"  [赞助: {f['sponsor_name']}]" if f["sponsored"] else ""
            print(f"  #{i:02d}  {f['price']}{tag}")

        return data, flights


def main():
    print("=" * 60)
    print("  Expedia 机票 GraphQL 纯本地复现 v3.1")
    print("  逆向策略: curl_cffi TLS + APQ + 两步流程 + 浏览器 Cookie")
    print("=" * 60)

    client = ExpediaFlightClient(cookie_str=BROWSER_COOKIE, duaid=DUAID)

    routes = [
        ("LAX", "PEK", "2026-08-25", "2026-09-02"),
        ("SHA", "PEK", "2026-09-01", "2026-09-08"),
    ]

    for origin, dest, out_date, in_date in routes:
        result = client.search(origin, dest, out_date, in_date)
        if result:
            data, flights = result
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = f"cases/expedia_{origin}_{dest}_{ts}.json"
            with open(out_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            print(f"\n[OK] 完整数据已保存: {out_path}")


if __name__ == "__main__":
    main()
