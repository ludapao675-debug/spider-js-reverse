"""
快手 PC 直播弹幕拉取（WebSocket 推送）
======================================
基于浏览器捕获的真实进房帧二进制分析实现。
__NS_hxfalcon 签名已纯 Python 本地复现（见 kuaishou_hxfalcon.py），无需浏览器。

用法（仅需 Cookie，签名自动生成）:
    python kuaishou_live_danmu.py --room 3xgcx74q29u9yx9 --lsid 3bRj5IVkx7M --cookie "did=...; kwfv1=..."

依赖:
    pip install curl_cffi        # 必须：Chrome TLS 指纹 + WebSocket
    pip install cryptography     # 可选：匿名 kww 生成

关键要点（逆向结论）:
    - 必须用 curl_cffi(impersonate="chrome")，否则快手 TLS 指纹校验会断连
    - 进房帧 CSWebEnterRoom 含 field7=pageId
    - 推送 payload 是 gzip 压缩，解压后弹幕在 f1.f7.f1.f1
"""

import argparse
import json
import time
import struct
import gzip
import zlib
import urllib.request
import urllib.error
import sys
import os

# ============================================================
# Protobuf 手写编码（不依赖 protobuf 库，纯 wire format）
# ============================================================

def _varint(n: int) -> bytes:
    """编码 varint（无符号整数）"""
    buf = []
    while n > 0x7F:
        buf.append((n & 0x7F) | 0x80)
        n >>= 7
    buf.append(n & 0x7F)
    return bytes(buf)


def _tag(field_number: int, wire_type: int) -> bytes:
    """编码 protobuf tag"""
    return _varint((field_number << 3) | wire_type)


def pb_string(value: str) -> bytes:
    """编码 string 字段（length-delimited）"""
    raw = value.encode('utf-8')
    return _tag(1, 2) + _varint(len(raw)) + raw


def pb_uint32(value: int) -> bytes:
    """编码 uint32 字段"""
    return _tag(1, 0) + _varint(value)


def pb_bytes(value: bytes) -> bytes:
    """编码 bytes 字段（length-delimited）"""
    return _tag(1, 2) + _varint(len(value)) + value


def _make_field(field_number: int, wire_type: int, value: bytes) -> bytes:
    """通用字段编码"""
    return _tag(field_number, wire_type) + value


def encode_cs_enter_room(token: str, live_stream_id: str, page_id: str = "") -> bytes:
    """
    编码 CSWebEnterRoom（进房帧内层 payload）
    
    真实浏览器进制分析：
        field 1: token (string)
        field 2: liveStreamId (string)
        field 7: pageId (string)  ← 原代码遗漏的关键字段！
    """
    buf = bytearray()
    
    # field 1: token
    b_token = token.encode('utf-8')
    buf += _tag(1, 2) + _varint(len(b_token)) + b_token
    
    # field 2: liveStreamId
    b_lsid = live_stream_id.encode('utf-8')
    buf += _tag(2, 2) + _varint(len(b_lsid)) + b_lsid
    
    # field 7: pageId（浏览器真实进房帧包含此字段）
    if page_id:
        b_pid = page_id.encode('utf-8')
        buf += _tag(7, 2) + _varint(len(b_pid)) + b_pid
    
    return bytes(buf)


def encode_socket_message(payload_type: int, payload: bytes) -> bytes:
    """
    编码外层 SocketMessage
    
    真实进制分析：
        field 1: payloadType (int32, varint)
        field 3: payload (bytes, length-delimited)
    """
    buf = bytearray()
    buf += _tag(1, 0) + _varint(payload_type)   # field 1: payloadType
    buf += _tag(3, 2) + _varint(len(payload)) + payload  # field 3: payload
    return bytes(buf)


# ============================================================
# Protobuf 解码
# ============================================================

def _read_varint(data: bytes, offset: int) -> tuple:
    """读取 varint，返回 (value, new_offset)"""
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        value |= (byte & 0x7F) << shift
        shift += 7
        offset += 1
        if not (byte & 0x80):
            break
    return value, offset


def _maybe_decompress(data: bytes) -> bytes:
    """
    应用层负载解压（浏览器实测发现）：
    - 服务端推送的 payload 多为 gzip 压缩（1f 8b 开头）
    - 也可能是 zlib（78 开头）
    - 否则原样返回
    """
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    if len(data) >= 2 and data[0] == 0x78:
        try:
            return zlib.decompress(data)
        except Exception:
            return data
    return data


def decode_socket_message(data: bytes) -> tuple:
    """
    解码外层 SocketMessage
    返回 (payload_type, payload_bytes) 或 (None, None)
    payload 自动解压（gzip/zlib）
    """
    payload_type = None
    payload = None
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if wire_type == 0:  # varint
            value, offset = _read_varint(data, offset)
            if field_number == 1:
                payload_type = value
        elif wire_type == 2:  # length-delimited
            length, offset = _read_varint(data, offset)
            value = data[offset:offset + length]
            offset += length
            if field_number == 3:
                payload = _maybe_decompress(value)
        else:
            break  # 不支持的 wire type
    return payload_type, payload


def _iter_len_delimited(data: bytes, field_number: int):
    """遍历指定 field 的所有 length-delimited 值（支持 repeated）"""
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except Exception:
            return
        fn, wt = tag >> 3, tag & 0x7
        if wt == 0:
            _, offset = _read_varint(data, offset)
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            if offset + length > len(data):
                return
            value = data[offset:offset + length]
            offset += length
            if fn == field_number:
                yield value
        elif wt == 5:
            offset += 4
        elif wt == 1:
            offset += 8
        else:
            return


def decode_web_comment_feed(data: bytes) -> dict:
    """
    解码 829 (SC_COMMENT_ZONE_RICH_TEXT) 弹幕负载
    实测真实结构（解压后）：
        f1: zone 消息
            f1(str): 房间会话 ID（如 <lsid>_<timestamp>）
            f7: 消息容器
                f1 (repeated): 单条消息
                    f1(str): ★ 弹幕文本
                    f2(msg): 用户信息
    返回 {"comments": [{content, user_id, ...}], "content": 首条文本}
    """
    comments = []
    # 外层可能有多个 repeated f1（多 zone），逐个处理
    for zone in _iter_len_delimited(data, 1):
        for container in _iter_len_delimited(zone, 7):
            for msg in _iter_len_delimited(container, 1):
                item = _parse_comment_message(msg)
                if item and item.get('content'):
                    comments.append(item)
    result = {'comments': comments}
    if comments:
        result['content'] = comments[0]['content']
    return result


def _parse_comment_message(data: bytes) -> dict:
    """解析单条弹幕消息：f1=content(str), f2=user(msg)"""
    item = {}
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except Exception:
            return item
        fn, wt = tag >> 3, tag & 0x7
        if wt == 0:
            value, offset = _read_varint(data, offset)
            item[f'field{fn}'] = value
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            if offset + length > len(data):
                return item
            value = data[offset:offset + length]
            offset += length
            if fn == 1:
                try:
                    item['content'] = value.decode('utf-8')
                except Exception:
                    pass
            elif fn == 2:
                # user 嵌套：f1 常见为用户 ID（varint 编码在 bytes 内）
                try:
                    utag, uoff = _read_varint(value, 0)
                    if (utag >> 3) == 1 and (utag & 0x7) == 0:
                        uid, _ = _read_varint(value, uoff)
                        item['user_id'] = uid
                except Exception:
                    pass
            else:
                item[f'field{fn}'] = value
        elif wt == 5:
            offset += 4
        elif wt == 1:
            offset += 8
        else:
            return item
    return item


# 礼物/进场等互动帧（310/340 等）的 payloadType
SC_GIFT_TYPES = {310, 311, 312}
SC_USER_TYPES = {340, 341}


def extract_readable_strings(data: bytes, min_len: int = 1) -> list:
    """
    从 protobuf payload 递归提取可读字符串（用于礼物/进场等互动帧）。
    过滤掉纯字母数字长串（id/token）。
    """
    out = []

    def walk(d):
        off = 0
        while off < len(d):
            try:
                tag, off = _read_varint(d, off)
            except Exception:
                return
            fn, wt = tag >> 3, tag & 7
            if wt == 0:
                _, off = _read_varint(d, off)
            elif wt == 2:
                ln, off = _read_varint(d, off)
                if off + ln > len(d):
                    return
                v = d[off:off + ln]
                off += ln
                try:
                    s = v.decode('utf-8')
                    if s and all(ch.isprintable() or ch.isspace() for ch in s) and len(s) >= min_len:
                        if not (len(s) > 15 and s.isalnum()):
                            out.append(s)
                    else:
                        walk(v)
                except Exception:
                    walk(v)
            elif wt == 5:
                off += 4
            elif wt == 1:
                off += 8
            else:
                return

    walk(data)
    return out


# ============================================================
# 协议常量
# ============================================================

CS_ENTER_ROOM = 200       # 进房 payloadType
CS_HEARTBEAT = 1          # 心跳 payloadType
SC_COMMENT_TYPES = {829, 830, 831, 832}  # 弹幕类 payloadType


# ============================================================
# liveStreamId 本地解析（纯 HTTP，无需浏览器）
# ============================================================

def resolve_lsid(short_room_id: str, cookie: str = "") -> str:
    """
    从直播间页面 HTML 的 __INITIAL_STATE__ 提取真实 liveStreamId。
    纯 HTTP（curl_cffi + Cookie），无需浏览器。

    重要：必须取 liveroom.playList[0].liveStream.id（当前开播会话），
    而不是页面其它位置的 liveStreamId（可能是推荐位/旧会话，进房后收不到弹幕）。
    """
    import re as _re
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("[ERROR] 需安装 curl_cffi: pip install curl_cffi")
        return ""
    if not cookie:
        try:
            try:
                from kuaishou_cookie_manager import KuaishouCookieManager
            except ImportError:
                import os as _os
                sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                from kuaishou_cookie_manager import KuaishouCookieManager
            cookie = KuaishouCookieManager().get_cookie_string()
        except Exception:
            cookie = ""
    s = creq.Session(impersonate="chrome")
    r = s.get(f"https://live.kuaishou.com/u/{short_room_id}",
              headers={"Cookie": cookie, "Accept": "text/html"}, timeout=15)
    html = r.text
    # 首选：JSON 解析 __INITIAL_STATE__
    m = _re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*(?:</script>|window\.)', html, _re.S)
    if m:
        try:
            state = json.loads(m.group(1))
            pl = (state.get("liveroom") or {}).get("playList") or []
            if pl and isinstance(pl, list):
                ls = (pl[0] or {}).get("liveStream") or {}
                if ls.get("id"):
                    return ls["id"]
        except Exception:
            pass
    # 正则兑底：直接取 liveStream.id
    mm = _re.search(r'"liveStream"\s*:\s*\{[^{}]*?"id"\s*:\s*"([A-Za-z0-9_-]+)"', html)
    if mm:
        return mm.group(1)
    print(f"[WARN] 未能从页面解析 liveStreamId（房间可能未开播）")
    return ""


# ============================================================
# HTTP 接口：获取 websocketinfo
# ============================================================

def fetch_websocketinfo(short_room_id: str, live_stream_id: str,
                        cookie: str = "",
                        __ns_hxfalcon: str = "",
                        kww: str = "",
                        script_count: int = 18) -> dict:
    """
    获取 WebSocket 连接信息
    
    需要有效的 __NS_hxfalcon 签名 + kww 头。
    - 未传入 __ns_hxfalcon 时，自动用纯 Python 本地生成（kuaishou_hxfalcon.py）。
    - 未传入 kww 时，自动从 cookie 的 kwfv1 派生。
    使用 curl_cffi 伪装 Chrome TLS 指纹（快手对部分接口也做指纹校验）。
    - 未传入 cookie 时，自动用 KuaishouCookieManager 从已连接浏览器采集并缓存。
    """
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("[ERROR] 需安装 curl_cffi: pip install curl_cffi")
        return {}

    # 未传 cookie -> 本地 Cookie 管理器自动采集（优先缓存，缺失时从浏览器采集）
    if not cookie:
        try:
            try:
                from kuaishou_cookie_manager import KuaishouCookieManager
            except ImportError:
                import os as _os
                sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                from kuaishou_cookie_manager import KuaishouCookieManager
            cookie = KuaishouCookieManager().get_cookie_string()
        except Exception as _e:
            print(f"[WARN] 自动采集 Cookie 失败: {_e}")

    base = "https://live.kuaishou.com/live_api/liveroom/websocketinfo"

    # 未传签名 -> 本地纯 Python 生成（无需浏览器）
    if not __ns_hxfalcon:
        try:
            from kuaishou_hxfalcon import HxfalconSigner
        except ImportError:
            import os as _os
            sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
            from kuaishou_hxfalcon import HxfalconSigner
        _signer = HxfalconSigner(script_count=script_count)
        _sig = _signer.sign("/live_api/liveroom/websocketinfo",
                            {"caver": "2", "liveStreamId": live_stream_id})
        __ns_hxfalcon = _sig["sign_result"]

    # 未传 kww -> 从 cookie 的 kwfv1 派生
    if not kww:
        try:
            from kuaishou_hxfalcon import derive_kww as _dk
            kww = _dk(cookie)
        except Exception:
            kww = ""

    params = {"caver": "2", "liveStreamId": live_stream_id}
    if __ns_hxfalcon:
        params["__NS_hxfalcon"] = __ns_hxfalcon

    import urllib.parse as _up
    url = f"{base}?{_up.urlencode(params)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36",
        "Referer": f"https://live.kuaishou.com/u/{short_room_id}",
        "Accept": "application/json, text/plain, */*",
    }
    if kww:
        headers["kww"] = kww
    if cookie:
        headers["Cookie"] = cookie

    try:
        session = creq.Session(impersonate="chrome")
        resp = session.get(url, headers=headers, timeout=15)
        body = resp.json()
    except Exception as e:
        print(f"[ERROR] {e}")
        return {}
    
    data = body.get("data", body)
    if data.get("result") != 1:
        print(f"[ERROR] websocketinfo 返回 result={data.get('result')}")
        print(f"         msg={data.get('msg', '')}")
        return {}
    
    return {
        "result": data["result"],
        "token": data["token"],
        "websocketUrls": data["websocketUrls"],
    }


# ============================================================
# 主逻辑：弹幕拉取
# ============================================================

class DanmuCapture:
    """快手直播弹幕捕获器"""
    
    def __init__(self, short_room_id: str, live_stream_id: str,
                 token: str, ws_url: str,
                 cookie: str = "",
                 page_id: str = ""):
        self.short_room_id = short_room_id
        self.live_stream_id = live_stream_id
        self.token = token
        self.ws_url = ws_url
        self.cookie = cookie
        self.page_id = page_id or f"_V1W-{int(time.time()*1000)}"
        self.ws = None
        self.danmu_list = []
        self._last_hb = 0
        self.frame_stats = {}  # payloadType -> 帧数（诊断用）
    
    def _build_enter_frame(self) -> bytes:
        """构建进房帧"""
        enter_payload = encode_cs_enter_room(
            self.token, self.live_stream_id, self.page_id
        )
        return encode_socket_message(CS_ENTER_ROOM, enter_payload)
    
    def _build_heartbeat_frame(self) -> bytes:
        """构建心跳帧"""
        ts = int(time.time() * 1000)
        # 心跳内层：field1 = timestamp varint
        inner = _tag(1, 0) + _varint(ts)
        return encode_socket_message(CS_HEARTBEAT, inner)
    
    def _on_message(self, data: bytes):
        """处理收到的 WS 消息"""
        if not isinstance(data, bytes) or len(data) < 3:
            return
        
        ptype, payload = decode_socket_message(data)
        if ptype is None or payload is None:
            return
        self.frame_stats[ptype] = self.frame_stats.get(ptype, 0) + 1
        
        if ptype in SC_COMMENT_TYPES:
            feed = decode_web_comment_feed(payload)
            # 一帧可能携带多条弹幕（WebCommentFeedList）
            for c in feed.get('comments', []):
                if c.get('content'):
                    self.danmu_list.append({'type': 'comment', 'content': c['content']})
                    print(f"[弹幕] {c.get('content')}")
            # 单层结构兼容
            if not feed.get('comments') and feed.get('content'):
                self.danmu_list.append({'type': 'comment', 'content': feed['content']})
                print(f"[弹幕] {feed['content']}")
        elif ptype in SC_GIFT_TYPES:
            # 礼物帧：提取昵称/礼物名
            strs = [s for s in extract_readable_strings(payload)
                    if any('\u4e00' <= ch <= '\u9fff' for ch in s)]
            if strs:
                txt = ' '.join(dict.fromkeys(strs))[:60]
                self.danmu_list.append({'type': 'gift', 'content': txt})
                print(f"[礼物] {txt}")
        elif ptype in SC_USER_TYPES:
            # 进场/用户列表帧
            strs = [s for s in extract_readable_strings(payload)
                    if any('\u4e00' <= ch <= '\u9fff' for ch in s)]
            if strs:
                txt = ' '.join(dict.fromkeys(strs))[:60]
                self.danmu_list.append({'type': 'user', 'content': txt})
                print(f"[进场] {txt}")
        elif ptype == 200:
            print(f"[进房确认] payloadType=200 (SC_WEB_ENTER_ROOM_ACK)")
        elif ptype:
            # 其他消息类型（点赞/在线人数等）
            pass
    
    def run(self, count: int = 20, timeout: int = 30):
        """运行弹幕捕获（必须用 curl_cffi 伪装 Chrome TLS 指纹，否则快手会断连）"""
        try:
            from curl_cffi import requests as creq
        except ImportError:
            print("[ERROR] 需安装 curl_cffi: pip install curl_cffi")
            return self.danmu_list

        import threading

        headers = {"Origin": "https://live.kuaishou.com",
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36"}
        if self.cookie:
            headers["Cookie"] = self.cookie

        print(f"[INFO] 连接 WS: {self.ws_url}")
        session = creq.Session(impersonate="chrome")
        self.ws = session.ws_connect(self.ws_url, headers=headers)
        print("[INFO] WS 已连接")

        # 发送进房帧
        enter_frame = self._build_enter_frame()
        self.ws.send(enter_frame)
        print(f"[INFO] 已发送进房帧 ({len(enter_frame)} 字节)")

        # 心跳线程（独立发送，不受 recv 阻塞影响）
        stop_evt = threading.Event()

        def hb_loop():
            while not stop_evt.wait(5):
                try:
                    self.ws.send(self._build_heartbeat_frame())
                except Exception:
                    break

        threading.Thread(target=hb_loop, daemon=True).start()

        # watchdog：超时强关，打断阻塞 recv
        def watchdog():
            if not stop_evt.wait(timeout + 10):
                try:
                    self.ws.terminate()
                except Exception:
                    pass

        threading.Thread(target=watchdog, daemon=True).start()

        deadline = time.time() + timeout
        try:
            while time.time() < deadline and len(self.danmu_list) < count:
                try:
                    res = self.ws.recv()  # 阻塞，返回 (bytes, type)
                except Exception as e:
                    print(f"[WARN] WS 连接断开: {type(e).__name__}: {e}")
                    break
                if self.ws.closed:
                    break
                data = res[0] if isinstance(res, tuple) else res
                if isinstance(data, (bytes, bytearray)):
                    self._on_message(bytes(data))
        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            stop_evt.set()
            try:
                self.ws.close()
            except Exception:
                pass
            print(f"[INFO] WS 已关闭 | 帧统计: {self.frame_stats}")

        return self.danmu_list


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="快手 PC 直播弹幕拉取")
    parser.add_argument("--room", required=True, help="直播间短号，如 nezha6969")
    parser.add_argument("--lsid", default="", help="liveStreamId；留空则自动从页面 HTTP 解析（推荐留空）")
    parser.add_argument("--cookie", default="", help="浏览器 Cookie（含 kwfv1）；留空则自动从已连接浏览器采集并缓存")
    parser.add_argument("--refresh-cookie", action="store_true", help="强制重新从浏览器采集 Cookie（忽略缓存）")
    parser.add_argument("--token", default="", help="WebSocket token（可选，为空则自动获取）")
    parser.add_argument("--ws-url", default="", help="WebSocket URL（可选，为空则自动获取）")
    parser.add_argument("--page-id", default="", help="pageId（可选，自动生成）")
    parser.add_argument("--count", type=int, default=20, help="拉取弹幕条数")
    parser.add_argument("--timeout", type=int, default=30, help="超时秒数")
    parser.add_argument("--hxfalcon", default="", help="__NS_hxfalcon 签名（可选，默认纯 Python 本地生成）")
    parser.add_argument("--kww", default="", help="kww 头（可选，默认取 kwfv1）")
    args = parser.parse_args()

    # Cookie 解析：未传入时自动从浏览器采集（本地闭环）
    cookie = args.cookie
    if not cookie:
        try:
            try:
                from kuaishou_cookie_manager import KuaishouCookieManager
            except ImportError:
                import os as _os
                sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                from kuaishou_cookie_manager import KuaishouCookieManager
            cookie = KuaishouCookieManager().get_cookie_string(force_refresh=args.refresh_cookie)
            print("[INFO] Cookie 已自动采集/加载（本地闭环）")
        except Exception as e:
            print(f"[WARN] 自动采集 Cookie 失败: {e}")

    # liveStreamId 解析：未传入时自动从页面 HTTP 解析
    lsid = args.lsid
    if not lsid:
        lsid = resolve_lsid(args.room, cookie=cookie)
        if not lsid:
            print("[ERROR] 无法获取 liveStreamId（房间可能未开播），请用 --lsid 手动指定")
            sys.exit(1)
        print(f"[INFO] liveStreamId 已自动解析: {lsid}")

    # 获取 token & ws_url
    token = args.token
    ws_url = args.ws_url

    if not token or not ws_url:
        print("[INFO] 获取 websocketinfo...")
        info = fetch_websocketinfo(
            args.room, lsid,
            cookie=cookie,
            __ns_hxfalcon=args.hxfalcon,
            kww=args.kww,
        )
        if not info:
            print("[ERROR] 获取 websocketinfo 失败。请确认 Cookie 有效（含 kwfv1）。")
            sys.exit(1)
        token = info["token"]
        ws_url = info["websocketUrls"][0]
        print(f"[INFO] token: {token[:20]}...")
        print(f"[INFO] ws_url: {ws_url}")

    # 弹幕捕获
    capture = DanmuCapture(
        short_room_id=args.room,
        live_stream_id=lsid,
        token=token,
        ws_url=ws_url,
        cookie=cookie,
        page_id=args.page_id,
    )
    
    print(f"[INFO] 开始拉取弹幕（最多 {args.count} 条，超时 {args.timeout}s）...")
    danmu = capture.run(count=args.count, timeout=args.timeout)
    
    print(f"\n{'='*50}")
    print(f"共收到 {len(danmu)} 条弹幕/互动")
    _type_label = {'comment': '弹幕', 'gift': '礼物', 'user': '进场'}
    for i, d in enumerate(danmu[:10]):
        label = _type_label.get(d.get('type'), d.get('type'))
        print(f"  [{i+1}] [{label}] {d.get('content', '')[:55]}")
    if len(danmu) > 10:
        print(f"  ... 还有 {len(danmu)-10} 条")


if __name__ == "__main__":
    main()