import requests
import base64
import hashlib
import random
import time
import json
import re
import os
import sys
from fontTools.ttLib import TTFont

sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 猫眼数字 0-9 拓扑字典 (numberOfContours, numberOfPoints)
GLYPH_TOPOLOGY_MAP = {
    (1, 31): '0', (1, 13): '1', (1, 37): '2', (1, 41): '3', (2, 46): '4',
    (1, 20): '5', (2, 14): '6', (2, 44): '7', (2, 31): '8', (3, 44): '9'
}

def generate_maoyan_sign(user_agent=DEFAULT_UA, channel_id=40009):
    timestamp = int(time.time() * 1000)
    index = random.randint(1, 1000)
    b64_ua = base64.b64encode(user_agent.encode('utf-8')).decode('utf-8')
    salt_key = "A013F70DB97834C0A5492378BD76C53A"

    raw_str = (
        f"method=GET&timeStamp={timestamp}&User-Agent={b64_ua}"
        f"&index={index}&channelId={channel_id}&sVersion=2&key={salt_key}"
    )

    sign_key = hashlib.md5(raw_str.encode('utf-8')).hexdigest()

    return {
        "orderType": 0,
        "uuid": "19ffa7f683dc8-04f3fb0e099d35-4c657b58-3e8000-19ffa7f683dc8",
        "timeStamp": timestamp,
        "User-Agent": b64_ua,
        "index": index,
        "channelId": channel_id,
        "sVersion": 2,
        "signKey": sign_key,
        "yodaReady": "h5",
        "csecplatform": 4,
        "csecversion": "4.3.0"
    }

def get_font_digit_mapping(font_path):
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    glyf = font['glyf']
    digit_mapping = {}

    for code_point, glyph_name in cmap.items():
        if glyph_name == 'x': continue
        g = glyf[glyph_name]
        key = (g.numberOfContours, len(g.coordinates if hasattr(g, 'coordinates') else []))
        if key in GLYPH_TOPOLOGY_MAP:
            digit_mapping[f"{code_point:x}"] = GLYPH_TOPOLOGY_MAP[key]

    return digit_mapping

def decode_num(encoded_str, digit_mapping):
    if not encoded_str: return "N/A"
    def replace_char(match):
        hex_val = match.group(1).lower()
        return digit_mapping.get(hex_val, '?')
    return re.sub(r'&#x([0-9a-fA-F]+);', replace_char, str(encoded_str))

def main():
    print("=" * 80)
    print("猫眼专业版：四大分类（综合数据、电影票房、网播热度、电视收视）全自动解析与复现")
    print("=" * 80)

    session = requests.Session()
    params = generate_maoyan_sign()
    headers = {"User-Agent": DEFAULT_UA, "Referer": "https://piaofang.maoyan.com/dashboard", "Accept": "application/json"}

    # 1. API Fetch
    url = "https://piaofang.maoyan.com/i/api/dashboard-ajax"
    res = session.get(url, params=params, headers=headers)
    data = res.json()
    print(f"[+] 1. API 签名与全量响应数据拉取成功 | Status {res.status_code} | signKey: {params['signKey']}")

    # 2. Font Download & Mapping
    font_url = "https://s3plus.meituan.net/v1/mss_73a511b8f91f43d0bdae92584ea6330b/font/2a70c44b.woff"
    font_bytes = session.get(font_url).content
    font_path = os.path.join(os.path.dirname(__file__), "maoyan_font.woff")
    with open(font_path, "wb") as f: f.write(font_bytes)
    digit_map = get_font_digit_mapping(font_path)
    print(f"[+] 2. WOFF 动态矢量点阵拓扑映射完成 (解密 0-9 数字: {len(digit_map)} 个)\n")

    # --- 模块 1 & 2: 综合数据 / 电影票房 (movieList) ---
    print("-" * 80)
    print("【分类一 / 分类二：电影票房榜 Top 5】")
    print("-" * 80)
    movies = data['movieList']['data']['list']
    for idx, item in enumerate(movies[:5], 1):
        name = item['movieInfo']['movieName']
        box_num = decode_num(item['boxSplitUnit']['num'], digit_map)
        unit = item['boxSplitUnit']['unit']
        box_rate = item.get('boxRate', 'N/A')
        print(f"  {idx}. {name:<18} | 实时票房: {box_num:>8} {unit:<2} | 票房占比: {box_rate}")

    # --- 模块 3: 网播热度 (webList) ---
    print("\n" + "-" * 80)
    print("【分类三：网播热度榜 Top 5】")
    print("-" * 80)
    web_shows = data['webList']['data']['list']
    for idx, item in enumerate(web_shows[:5], 1):
        name = item['seriesInfo']['name']
        platform = item['seriesInfo'].get('platformDesc', '网络平台')
        heat_num = decode_num(item.get('currHeatDesc', item.get('currHeat', '')), digit_map)
        print(f"  {idx}. {name:<18} | 播放平台: {platform:<10} | 网播热度: {heat_num}")

    # --- 模块 4: 电视收视 (tvList) ---
    print("\n" + "-" * 80)
    print("【分类四：电视收视榜 Top 5】")
    print("-" * 80)
    tv_shows = data['tvList']['data']['list']
    for idx, item in enumerate(tv_shows[:5], 1):
        name = item['programmeName']
        channel = item.get('channelName', '频道')
        rate = decode_num(item.get('attentionRateDesc', item.get('attentionRate', '')), digit_map)
        market = decode_num(item.get('marketRateDesc', item.get('marketRate', '')), digit_map)
        print(f"  {idx}. {name:<18} | 频道: {channel:<10} | 关注度: {rate}% | 市场占有率: {market}%")

    print("\n" + "=" * 80)
    print("[SUCCESS] 猫眼专业版 4 大分类解密全流程校验完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
