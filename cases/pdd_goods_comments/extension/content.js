/**
 * Isolated world content script — registers tab, relays RPC.
 * MAIN world: one-shot <script> inject (no native hooks).
 * SW will later prefer chrome.scripting.executeScript({world:'MAIN'}).
 */
(() => {
  const goodsMatch = location.href.match(/[?&]goods_id=(\d+)/);
  chrome.runtime.sendMessage({
    type: "content_hello",
    goodsId: goodsMatch ? goodsMatch[1] : null,
  });

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "fetch_reviews") return;
    (async () => {
      try {
        const result = await bridgeViaDom(msg);
        await postResult(msg.reqId, true, result, null);
        sendResponse({ ok: true });
      } catch (e) {
        const err = String(e && e.message ? e.message : e);
        await postResult(msg.reqId, false, null, err);
        sendResponse({ ok: false, error: err });
      }
    })();
    return true;
  });

  function bridgeViaDom(msg) {
    return new Promise((resolve, reject) => {
      const reqId = msg.reqId || `r_${Date.now()}`;
      const onMsg = (ev) => {
        if (!ev.data || ev.data.source !== "pdd_rpc_main" || ev.data.reqId !== reqId) return;
        window.removeEventListener("message", onMsg);
        if (ev.data.ok) resolve(ev.data.result);
        else reject(new Error(ev.data.error || "main_failed"));
      };
      window.addEventListener("message", onMsg);
      const args = {
        goodsId: String(msg.goodsId || ""),
        page: Number(msg.page) || 1,
        size: Number(msg.size) || 10,
        reqId,
        post: true,
      };
      const s = document.createElement("script");
      s.textContent = `(${mainWorldFetchReviews.toString()})(${JSON.stringify(args)});`;
      (document.documentElement || document.head).appendChild(s);
      s.remove();
      setTimeout(() => {
        window.removeEventListener("message", onMsg);
        reject(new Error("main_timeout"));
      }, 30000);
    });
  }

  async function postResult(reqId, ok, result, error) {
    const payload = JSON.stringify({ result, error });
    const CHUNK = 24000;
    if (payload.length <= CHUNK) {
      chrome.runtime.sendMessage({ type: "rpc_result", reqId, ok, result, error });
      return;
    }
    const total = Math.ceil(payload.length / CHUNK);
    for (let i = 0; i < total; i++) {
      await chrome.runtime.sendMessage({
        type: "chunk",
        reqId,
        index: i,
        total,
        data: payload.slice(i * CHUNK, (i + 1) * CHUNK),
      });
    }
  }
})();

/** MAIN world — page webpack + native fetch; no native patches. */
async function mainWorldFetchReviews(args) {
  const post = !!args.post;
  const reqId = args.reqId || null;
  try {
    const req = window.__wp_req;
    if (!req || !req.m) throw new Error("no_webpack_require");
    let mod = window.__pdd_ac_mod;
    if (!mod || !mod.g) {
      const hit = Object.keys(req.m).find((id) => {
        try {
          return String(req.m[id]).includes("获取风控参数");
        } catch {
          return false;
        }
      });
      if (!hit) throw new Error("module_not_found");
      mod = req(hit);
      window.__pdd_ac_mod = mod;
    }
    const ac = await mod.g();
    if (typeof ac !== "string" || !ac.startsWith("0as")) throw new Error("bad_anti_content");

    let pdduid = "";
    const cm = document.cookie.match(/(?:^|;\s*)pdd_user_id=([^;]+)/);
    if (cm) pdduid = cm[1];

    const url =
      `https://mobile.pinduoduo.com/proxy/api/reviews/${args.goodsId}/list` +
      `?label_id=0&page=${args.page}&size=${args.size || 10}&enable_video=1&enable_group_review=1` +
      `&pdduid=${pdduid}&is_back=1`;

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        accept: "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "anti-content": ac,
      },
      body: JSON.stringify({ name: "goodsCommentListAxios", anti_content: ac }),
      credentials: "include",
    });
    const data = await resp.json();
    const out = {
      status: resp.status,
      n: Array.isArray(data.data) ? data.data.length : 0,
      error_code: data.error_code || null,
      verify: !!data.verify_auth_token,
      data: data.data || null,
      ac_prefix: ac.slice(0, 8),
      ac_len: ac.length,
    };
    if (post && reqId) {
      window.postMessage({ source: "pdd_rpc_main", reqId, ok: true, result: out }, "*");
    }
    return out;
  } catch (e) {
    const err = String(e && e.message ? e.message : e);
    if (post && reqId) {
      window.postMessage({ source: "pdd_rpc_main", reqId, ok: false, error: err }, "*");
    }
    throw e;
  }
}
