# -*- coding: utf-8 -*-
"""Extension RPC local WS server (skeleton).

Listens ws://127.0.0.1:18765 — ping/pong + tab registry.
Production fetch_reviews wiring arrives after Phase 0 / Extension inject harden.

Usage:
  python ext_ws_server.py
  # then load cases/pdd_goods_comments/extension as unpacked MV3 in Edge/Chrome
  # (manual browser, NO --remote-debugging-port)

Isolation: this is the delivery mainline — zero PDD reviews risk budget.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "need websockets: pip install websockets\n" + str(e)
    ) from e

HOST = "127.0.0.1"
PORT = 18765


class Bridge:
    def __init__(self) -> None:
        self.clients: set[WebSocketServerProtocol] = set()
        self.tabs: dict[int, dict[str, Any]] = {}
        self.last_ping: dict[int, float] = {}

    async def handler(self, ws: WebSocketServerProtocol) -> None:
        self.clients.add(ws)
        peer = getattr(ws, "remote_address", None)
        print(f"[+] connect {peer} clients={len(self.clients)}")
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"type": "error", "error": "bad_json"}))
                    continue
                await self.on_message(ws, msg)
        finally:
            self.clients.discard(ws)
            print(f"[-] disconnect {peer} clients={len(self.clients)}")

    async def on_message(self, ws: WebSocketServerProtocol, msg: dict[str, Any]) -> None:
        t = msg.get("type")
        payload = msg.get("payload") or {}
        if t == "ping":
            await ws.send(json.dumps({"type": "pong", "ts": int(time.time() * 1000), "payload": payload}))
            return
        if t == "pong":
            self.last_ping[id(ws)] = time.time()
            print(f"[pong] {payload}")
            return
        if t == "hello":
            print(f"[hello] {json.dumps(payload, ensure_ascii=False)[:300]}")
            for tab in payload.get("tabs") or []:
                tid = tab.get("tabId")
                if tid is not None:
                    self.tabs[int(tid)] = tab
            await ws.send(json.dumps({"type": "hello_ack", "tabs": list(self.tabs.values())}))
            return
        if t == "tab_upsert":
            tid = payload.get("tabId")
            if tid is not None:
                self.tabs[int(tid)] = payload
                print(f"[tab+] {tid} goods={payload.get('goodsId')} url={str(payload.get('url'))[:80]}")
            return
        if t == "tab_remove":
            tid = payload.get("tabId")
            if tid is not None:
                self.tabs.pop(int(tid), None)
                print(f"[tab-] {tid}")
            return
        if t == "tabs":
            self.tabs = {int(x["tabId"]): x for x in payload if x.get("tabId") is not None}
            print(f"[tabs] n={len(self.tabs)}")
            return
        if t in ("rpc_result", "chunk"):
            print(f"[{t}] {json.dumps(payload, ensure_ascii=False)[:240]}")
            return
        print(f"[?] {t} {str(payload)[:120]}")

    async def server_ping_loop(self) -> None:
        while True:
            await asyncio.sleep(20)
            dead = []
            for ws in list(self.clients):
                try:
                    await ws.send(json.dumps({"type": "ping", "ts": int(time.time() * 1000)}))
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)

    async def cli_loop(self) -> None:
        """stdin commands: tabs | ping | quit"""
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, input)
            cmd = (line or "").strip().lower()
            if cmd in ("q", "quit", "exit"):
                raise SystemExit(0)
            if cmd == "tabs":
                print(json.dumps(list(self.tabs.values()), ensure_ascii=False, indent=2))
                for ws in list(self.clients):
                    await ws.send(json.dumps({"type": "list_tabs"}))
            elif cmd == "ping":
                for ws in list(self.clients):
                    await ws.send(json.dumps({"type": "ping", "ts": int(time.time() * 1000)}))
            else:
                print("commands: tabs | ping | quit")


async def main(host: str, port: int) -> None:
    bridge = Bridge()
    print(f"PDD Extension WS skeleton on ws://{host}:{port}")
    print("Load unpacked extension, open PDD comments tab (no CDP). Commands: tabs | ping | quit")
    async with websockets.serve(bridge.handler, host, port, max_size=8 * 1024 * 1024):
        await asyncio.gather(bridge.server_ping_loop(), bridge.cli_loop())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    asyncio.run(main(args.host, args.port))
