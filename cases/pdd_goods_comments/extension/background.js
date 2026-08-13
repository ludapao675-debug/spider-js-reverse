/**
 * MV3 service worker — holds WS to local Python, tab registry, ping/pong.
 * Production fetch path: content → MAIN world one-shot inject (not hooked).
 */
const DEFAULT_WS = "ws://127.0.0.1:18765";
const PING_ALARM = "pdd_rpc_ping";
const RECONNECT_ALARM = "pdd_rpc_reconnect";

/** @type {WebSocket|null} */
let ws = null;
/** @type {Map<number, {tabId:number, goodsId:string|null, url:string, title:string, lastSeen:number}>} */
const tabs = new Map();
let seq = 0;
let lastPongAt = 0;

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(PING_ALARM, { periodInMinutes: 0.4 }); // ~24s
  chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 0.5 });
  connect();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(PING_ALARM, { periodInMinutes: 0.4 });
  chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 0.5 });
  connect();
});

chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === PING_ALARM) sendPing();
  if (a.name === RECONNECT_ALARM && (!ws || ws.readyState !== WebSocket.OPEN)) connect();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!tab.url || !isPddUrl(tab.url)) return;
  if (changeInfo.status === "complete" || changeInfo.url) {
    upsertTab(tab);
    notify("tab_upsert", tabs.get(tabId));
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabs.delete(tabId)) notify("tab_remove", { tabId });
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;
  if (msg.type === "content_hello" && sender.tab) {
    upsertTab(sender.tab, msg.goodsId || null);
    notify("tab_upsert", tabs.get(sender.tab.id));
    sendResponse({ ok: true, ws: wsState() });
    return true;
  }
  if (msg.type === "chunk") {
    // large JSON shard from content/MAIN → forward to local WS
    notify("chunk", {
      tabId: sender.tab?.id,
      reqId: msg.reqId,
      index: msg.index,
      total: msg.total,
      data: msg.data,
    });
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "rpc_result") {
    notify("rpc_result", {
      tabId: sender.tab?.id,
      reqId: msg.reqId,
      ok: msg.ok,
      result: msg.result,
      error: msg.error,
    });
    sendResponse({ ok: true });
    return true;
  }
  return false;
});

function isPddUrl(url) {
  try {
    const h = new URL(url).hostname;
    return h.endsWith("pinduoduo.com") || h.endsWith("yangkeduo.com");
  } catch {
    return false;
  }
}

function upsertTab(tab, goodsId) {
  if (!tab?.id) return;
  const url = tab.url || "";
  let gid = goodsId || null;
  if (!gid) {
    const m = url.match(/[?&]goods_id=(\d+)/);
    if (m) gid = m[1];
  }
  tabs.set(tab.id, {
    tabId: tab.id,
    goodsId: gid,
    url,
    title: tab.title || "",
    lastSeen: Date.now(),
  });
}

function wsState() {
  if (!ws) return "null";
  return ["CONNECTING", "OPEN", "CLOSING", "CLOSED"][ws.readyState] || String(ws.readyState);
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(DEFAULT_WS);
  } catch (e) {
    console.warn("[pdd-rpc] ws construct fail", e);
    return;
  }
  ws.onopen = () => {
    console.log("[pdd-rpc] ws open");
    notify("hello", {
      role: "extension",
      version: chrome.runtime.getManifest().version,
      tabs: [...tabs.values()],
    });
    sendPing();
  };
  ws.onclose = () => {
    console.log("[pdd-rpc] ws close");
    ws = null;
  };
  ws.onerror = (e) => console.warn("[pdd-rpc] ws error", e);
  ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleServer(msg);
  };
}

function send(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(obj));
  return true;
}

function notify(type, payload) {
  return send({ type, ts: Date.now(), seq: ++seq, payload });
}

function sendPing() {
  const ok = notify("ping", { lastPongAt });
  if (!ok) connect();
}

async function handleServer(msg) {
  if (msg.type === "pong") {
    lastPongAt = Date.now();
    return;
  }
  if (msg.type === "ping") {
    notify("pong", { echo: msg.payload || null });
    return;
  }
  if (msg.type === "list_tabs") {
    // refresh from chrome.tabs then reply
    const all = await chrome.tabs.query({});
    for (const t of all) {
      if (t.url && isPddUrl(t.url)) upsertTab(t);
    }
    notify("tabs", [...tabs.values()]);
    return;
  }
  if (msg.type === "fetch_reviews") {
    // Phase skeleton: route to content script; MAIN inject comes next.
    const tabId = msg.payload?.tabId;
    if (!tabId || !tabs.has(tabId)) {
      notify("rpc_result", {
        reqId: msg.payload?.reqId,
        ok: false,
        error: "tab_not_registered",
      });
      return;
    }
    try {
      await chrome.tabs.sendMessage(tabId, {
        type: "fetch_reviews",
        reqId: msg.payload?.reqId,
        goodsId: msg.payload?.goodsId,
        page: msg.payload?.page,
        size: msg.payload?.size || 10,
      });
    } catch (e) {
      notify("rpc_result", {
        reqId: msg.payload?.reqId,
        ok: false,
        error: String(e),
      });
    }
  }
}
