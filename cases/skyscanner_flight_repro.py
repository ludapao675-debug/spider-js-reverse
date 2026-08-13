# -*- coding: utf-8 -*-
"""
天巡 (Skyscanner) 机票搜索协议与全流程接口复现脚本
包含：
1. 城市/机场名称及 IATA 编码到 Skyscanner 内部 EntityID 的自动映射
2. 发起 POST /web-unified-search/ 搜索初始化与提取动态 sessionId
3. 轮询 GET /web-unified-search/<session_token> 获取实时机票低价与方案
"""

import uuid
import time
import requests


class SkyscannerFlightClient:
    """天巡机票搜索与 API 复现客户端"""

    BASE_SEARCH_URL = "https://www.tianxun.com/g/radar/api/v2/web-unified-search/"
    PRICE_PULSE_URL = "https://www.tianxun.com/g/drops-api/v5alpha/drops/pricePulse"

    # 常规热门城市/机场与 Skyscanner 内部 EntityID 字典库
    ENTITY_MAP = {
        "LAX": "27536211",   # 洛杉矶
        "LAXA": "27536211",  # 洛杉矶所有机场
        "PEK": "128668664",  # 北京首都
        "PKX": "135686664",  # 北京大兴
        "BJS": "128668664",  # 北京所有机场
        "TYO": "27545090",   # 东京
        "TYOA": "27545090",  # 东京所有机场
        "HND": "95565050",   # 东京羽田
        "NRT": "95565051",   # 东京成田
        "SHA": "27539656",   # 上海
        "SHAA": "27539656",  # 上海所有机场
        "PVG": "95565048",   # 上海浦东
        "SHA_APT": "95565049",# 上海虹桥
        "HKG": "27539446",   # 香港
        "HKGA": "27539446"   # 香港所有机场
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
        # 若传入纯数字 ID，直接返回
        if key.isdigit():
            return key
        # 默认回退为洛杉矶或根据自定义扩充
        return self.ENTITY_MAP.get("LAX")

    def search_flights(self, origin="LAX", destination="PEK", outbound_date="2026-08-21", inbound_date="2026-08-28"):
        """
        发起机票搜索全流程
        :param origin: 出发城市代码 (如 LAX, SHA, TYO)
        :param destination: 目的城市代码 (如 PEK, HKG)
        :param outbound_date: 去程日期 (YYYY-MM-DD)
        :param inbound_date: 返程日期 (YYYY-MM-DD)
        :return: 机票响应结果字典
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
            print(f"    - POST 状态码: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                context = data.get("context", {})
                session_token = context.get("sessionId")
                
                if session_token:
                    print(f"    - 成功提取 sessionId / sessionToken: {session_token[:50]}...")
                    agents = data.get("itineraries", {}).get("agents", [])
                    print(f"    - 捕获支持航司/代理平台: {len(agents)} 个 (如: {', '.join([a['name'] for a in agents[:5]])})")
                    return self._poll_results(session_token)
                else:
                    print(f"    - 未在 context 中查找到 sessionId")
                    return data
            else:
                print(f"    - 接口返回错误: {resp.text[:300]}")
                return None
        except Exception as e:
            print(f"[!] 请求异常: {e}")
            return None

    def _poll_results(self, session_token, max_retries=3):
        """根据 sessionToken 轮询机票价格与方案列表"""
        poll_url = f"{self.BASE_SEARCH_URL}{session_token}"
        print(f"[*] 2. 开始轮询机票方案 API...")
        
        for attempt in range(1, max_retries + 1):
            time.sleep(1.5)
            try:
                resp = self.session.get(poll_url, timeout=10)
                print(f"    - 第 {attempt} 次轮询 GET 状态码: {resp.status_code}")
                if resp.status_code == 200:
                    result = resp.json()
                    status = result.get("context", {}).get("status", "")
                    itineraries = result.get("itineraries", {}).get("results", [])
                    print(f"    - 搜索状态: {status}, 当前成功提取机票方案: {len(itineraries)} 条")
                    return result
            except Exception as e:
                print(f"[!] 轮询第 {attempt} 次异常: {e}")
        return None


if __name__ == "__main__":
    print("=== 天巡 Skyscanner 全链路机票搜索协议测试 ===")
    client = SkyscannerFlightClient()
    
    # 测试路线 1: 洛杉矶 (LAX) -> 北京 (PEK)
    print("\n--- 路线一: 洛杉矶 (LAX) -> 北京 (PEK) ---")
    client.search_flights(origin="LAX", destination="PEK", outbound_date="2026-08-21", inbound_date="2026-08-28")
    
    # 测试路线 2: 上海 (SHA) -> 东京 (TYO)
    print("\n--- 路线二: 上海 (SHA) -> 东京 (TYO) ---")
    client.search_flights(origin="SHA", destination="TYO", outbound_date="2026-09-01", inbound_date="2026-09-10")
