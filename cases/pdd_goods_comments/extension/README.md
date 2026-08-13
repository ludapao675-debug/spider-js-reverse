# PDD Comments Extension RPC — skeleton (2026-08-06)

## Goal

Delivery mainline that does **not** use CDP:
- Manual Edge/Chrome (no `--remote-debugging-port`) → a4 registration stays clean (no `cdpProxy` / hook enum).
- MAIN-world one-shot call to webpack `45246.g()` + native `fetch` (same path as proven 200).
- Local Python talks to MV3 service worker over WebSocket.

## Layout

| File | Role |
|------|------|
| `manifest.json` | MV3, host_permissions pinduoduo + yangkeduo, alarms |
| `background.js` | WS client, tab registry, ping/pong, alarm keepalive |
| `content.js` | tab hello + MAIN inject bridge + chunked results |
| `ext_ws_server.py` | local `ws://127.0.0.1:18765` |

## Load (manual, zero risk budget)

1. `pip install websockets` then `python ext_ws_server.py`
2. Edge → `edge://extensions` → Developer mode → Load unpacked → this folder
3. Open `https://mobile.pinduoduo.com/goods_comments.html?goods_id=...` (logged in)
4. In server stdin: `tabs` → should list tabId/goodsId; `ping` → pong

## Not in skeleton (next)

- Harden `chrome.scripting.executeScript` from SW (prefer over DOM `<script>` bridge)
- Rate limit ≥5s / fuse on 54001 / `verify_auth_token`
- CLI parity with `pdd_comments_rpc.py` (`--pages`, `--interval`)
- postMessage chunk reassembly on Python side

## Isolation

Do **not** attach crypto-hunter CDP to the same profile used by this extension during production pulls.
