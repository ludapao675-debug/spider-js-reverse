# -*- coding: utf-8 -*-
# 本地桥接服务：收到页面传来的 m 后立即请求 page=5（UA=yuanrenxue）
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SESSION = 'ywfvjln56lffpud0cve84455ogga32o1'
UA_YRX = 'yuanrenxue'


def fetch_page5(m):
    url = 'https://match.yuanrenxue.cn/api/question/9?page=5&pageSize=10&kw='
    req = urllib.request.Request(url, headers={
        'User-Agent': UA_YRX,
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://match.yuanrenxue.cn/match/9',
        'Cookie': f'sessionid={SESSION}; m={m}',
    })
    body = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
    return body


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # CORS
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        try:
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            m = q.get('m', [''])[0]
            print(f'[RECV m] len={len(m)} tail={m[-12:]}', flush=True)
            body = fetch_page5(m)
            print(f'[PAGE5 RESP] len={len(body)} head={body[:100]}', flush=True)
            self.wfile.write(body.encode('utf-8'))
        except Exception as e:
            print(f'[ERR] {e}', flush=True)
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def log_message(self, *a):
        pass


print('[SERVER] listening on 127.0.0.1:8765', flush=True)
HTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
