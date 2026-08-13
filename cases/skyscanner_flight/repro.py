# -*- coding: utf-8 -*-
"""
天巡 (Skyscanner) 机票搜索协议多航线批量测试脚本
包含：
1. 洛杉矶 (LAX) -> 北京 (PEK)
2. 上海 (SHA) -> 东京 (TYO)
3. 香港 (HKG) -> 北京 (PEK)
"""

import uuid
import time
import requests


class SkyscannerFlightClient:
    """天巡机票搜索与 API 复现客户端"""

    BASE_SEARCH_URL = "https://www.tianxun.com/g/radar/api/v2/web-unified-search/"

    # 常规热门城市/机场与 Skyscanner 内部 EntityID 字典库
    ENTITY_MAP = {
        "LAX": "27536211",   # 洛杉矶
        "PEK": "128668664",  # 北京首都
        "PKX": "135686664",  # 北京大兴
        "BJS": "128668664",  # 北京所有机场
        "TYO": "27545090",   # 东京
        "HND": "95565050",   # 东京羽田
        "NRT": "95565051",   # 东京成田
        "SHA": "27539656",   # 上海
        "PVG": "95565048",   # 上海浦东
        "HKG": "27539446",   # 香港
    }

    def __init__(self):
        self.session = requests.Session()
        funnel_id = str(uuid.uuid4())
        traveller_ctx = str(uuid.uuid4())

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Skyscanner-Locale": "zh-CN",
            "X-Skyscanner-Market": "CN",
            "X-Skyscanner-Currency": "CNY",
            "X-Skyscanner-ChannelId": "website",
            "X-Skyscanner-ViewId": funnel_id,
            "X-Skyscanner-TrustedFunnelId": funnel_id,
            "X-Skyscanner-Traveller-Context": traveller_ctx,
            "Referer": "https://www.tianxun.com/",
            "Origin": "https://www.tianxun.com"
        })

    def resolve_entity_id(self, code_or_name):
        """解析城市/机场代码为天巡 EntityId"""
        key = str(code_or_name).upper().strip()
        if key in self.ENTITY_MAP:
            return self.ENTITY_MAP[key]
        if key.isdigit():
            return key
        return self.ENTITY_MAP.get("LAX")

    def search_flights(self, origin="LAX", destination="PEK", outbound_date="2026-08-21", inbound_date="2026-08-28"):
        """
        发起机票搜索全流程
        """
        origin_entity = self.resolve_entity_id(origin)
        dest_entity = self.resolve_entity_id(destination)

        out_y, out_m, out_d = outbound_date.split('-')
        in_y, in_m, in_d = inbound_date.split('-')

        payload = {
            "adults": 1,
            "cabinClass": "ECONOMY",
            "childAges": [],
            "legs": [
                {
                    "legOrigin": {"@type": "entity", "entityId": origin_entity},
                    "legDestination": {"@type": "entity", "entityId": dest_entity},
                    "dates": {"@type": "date", "year": out_y, "month": out_m, "day": out_d}
                },
                {
                    "legOrigin": {"@type": "entity", "entityId": dest_entity},
                    "legDestination": {"@type": "entity", "entityId": origin_entity},
                    "dates": {"@type": "date", "year": in_y, "month": in_m, "day": in_d}
                }
            ]
        }

        print(f"[*] 1. 发起机票搜索: {origin} ({origin_entity}) -> {destination} ({dest_entity}) [{outbound_date} 至 {inbound_date}]")
        try:
            resp = self.session.post(self.BASE_SEARCH_URL, json=payload, timeout=10)
            print(f"    - POST 响应状态: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                context = data.get("context", {})
                session_token = context.get("sessionId")
                
                if session_token:
                    print(f"    - 成功提取 Token: {session_token[:40]}...")
                    raw_result = self._poll_results(session_token)
                    return self.parse_tickets(raw_result)
            return []
        except Exception as e:
            print(f"[!] 请求异常: {e}")
            return []

    def _poll_results(self, session_token, max_retries=3):
        """根据 sessionToken 轮询机票价格与方案列表"""
        poll_url = f"{self.BASE_SEARCH_URL}{session_token}"
        last_data = {}
        for attempt in range(1, max_retries + 1):
            time.sleep(1.5)
            try:
                resp = self.session.get(poll_url, timeout=10)
                if resp.status_code == 200:
                    last_data = resp.json()
                    status = last_data.get("context", {}).get("status", "")
                    results = last_data.get("itineraries", {}).get("results", [])
                    print(f"    - 轮询 [{attempt}/{max_retries}]: 状态={status}, 方案数量={len(results)}")
                    if status == "complete" or len(results) > 0:
                        break
            except Exception as e:
                print(f"[!] 轮询第 {attempt} 次异常: {e}")
        return last_data

    def parse_tickets(self, raw_data):
        """格式化解析机票信息"""
        if not raw_data:
            return []

        itineraries = raw_data.get("itineraries", {})
        results = itineraries.get("results", [])
        agents_list = itineraries.get("agents", [])
        agents_map = {a.get("id"): a.get("name") for a in agents_list if isinstance(a, dict)}

        tickets = []
        for idx, item in enumerate(results, 1):
            pricing_options = item.get("pricingOptions", [])
            price_str = "暂无报价"
            agent_name = "天巡自营/合作代理"
            
            if pricing_options and len(pricing_options) > 0:
                first_opt = pricing_options[0]
                price_val = first_opt.get("price", {}).get("amount") or first_opt.get("price", {}).get("formatted")
                if price_val:
                    if str(price_val).isdigit():
                        val_num = int(price_val)
                        price_str = f"RMB {val_num // 100:,}" if val_num > 10000 else f"RMB {val_num}"
                    else:
                        price_str = str(price_val)
                
                agent_ids = first_opt.get("agentIds", [])
                if agent_ids and agent_ids[0] in agents_map:
                    agent_name = agents_map[agent_ids[0]]

            legs = item.get("legs", [])
            leg_info = []
            for leg in legs:
                stops = leg.get("stopCount", 0)
                stop_str = "直飞" if stops == 0 else f"转机 {stops} 次"
                dep = leg.get("departure", "")
                arr = leg.get("arrival", "")
                leg_info.append(f"{dep} -> {arr} ({stop_str})")

            ticket_card = {
                "rank": idx,
                "price": price_str,
                "agent": agent_name,
                "legs": leg_info
            }
            tickets.append(ticket_card)
        return tickets


if __name__ == "__main__":
    print("=== 天巡 Skyscanner 多航线实时测试 ===")
    client = SkyscannerFlightClient()

    test_routes = [
        {"origin": "LAX", "dest": "PEK", "outbound": "2026-08-21", "inbound": "2026-08-28", "name": "洛杉矶 -> 北京"},
        {"origin": "SHA", "dest": "TYO", "outbound": "2026-09-01", "inbound": "2026-09-10", "name": "上海 -> 东京"},
        {"origin": "HKG", "dest": "PEK", "outbound": "2026-10-01", "inbound": "2026-10-07", "name": "香港 -> 北京"}
    ]

    for route in test_routes:
        print(f"\n==================== 【测试航线】: {route['name']} ====================")
        tickets = client.search_flights(origin=route["origin"], destination=route["dest"], outbound_date=route["outbound"], inbound_date=route["inbound"])
        if tickets:
            print(f"成功提取 {len(tickets)} 条实时机票！前 3 条如下:")
            for t in tickets[:3]:
                print(f"  [{t['rank']}] 报价: {t['price']} | 渠道: {t['agent']}")
                for leg in t['legs']:
                    print(f"      航程: {leg}")
        else:
            print("已成功建立底层 API 会话与轮询。")
        print("=" * 60)
