// dump_ye_env.js — 浏览器内序列化 bdms 环境（供 Node 离线注入）
// 用法：ch_page_run_js(code=fs.readFileSync('dump_ye_env.js'), return_mode=json)
(function () {
  if (typeof window.bdms === 'undefined' || !window.bdms.init) {
    return { ok: false, error: 'bdms 未加载' };
  }

  const seen = new WeakSet();

  /** 安全 JSON 化（队列/数组/浅对象） */
  function ser(v, depth) {
    if (depth > 8) return '[depth]';
    if (v == null || typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string') {
      return v;
    }
    if (typeof v === 'function') {
      const pc = v._v && v._v[0];
      return { __fn: true, pc: pc != null ? pc : null, len: String(v).length };
    }
    if (typeof v !== 'object') return String(v);
    if (seen.has(v)) return '[Circular]';
    seen.add(v);

    // 鼠标队列 {items, front, rear}
    if (v.items && typeof v.front === 'number' && typeof v.rear === 'number') {
      const items = [];
      const n = Math.min(v.rear, v.items.length, 512);
      for (let i = 0; i < n; i++) {
        const it = v.items[i];
        if (it && typeof it === 'object') {
          items.push({ x: it.x, y: it.y, ts: it.ts });
        } else {
          items.push(it);
        }
      }
      return { items, front: v.front, rear: v.rear };
    }

    if (Array.isArray(v)) {
      return v.map((x, i) => (i < 64 ? ser(x, depth + 1) : undefined));
    }

    const o = {};
    for (const k of Object.keys(v).slice(0, 32)) {
      try {
        o[k] = ser(v[k], depth + 1);
      } catch (e) {
        o[k] = '[err]';
      }
    }
    return o;
  }

  const initMe = window.bdms.init._v && window.bdms.init._v[2];
  const signFn = window.__abogus_sign;
  const out = {
    ok: true,
    ts: Date.now(),
    url: location.href,
    init_v: initMe ? ser(initMe, 0) : null,
    init_me_len: initMe ? initMe.length : 0,
    ye_from_window: typeof signFn,
    ye_pc: window.__abogus_sign_pc || (signFn && signFn._v && signFn._v[0]),
    ye_same_as_init: signFn === window.bdms.init,
    ye_me: signFn && signFn._v && signFn !== initMe ? ser(signFn._v[2], 0) : null,
    ye_call_log: window.__ye_call_log || [],
    captured_abogus: window.__captured_abogus_from_vm || null,
  };

  // 若已有 ye，试签一次 feed
  const testUrl = 'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web&msToken=dump_test';
  if (typeof window.__abogus_sign === 'function') {
    try {
      const r = window.__abogus_sign(testUrl);
      out.ye_test = { type: typeof r, len: r ? String(r).length : 0, preview: r ? String(r).slice(0, 80) : null };
    } catch (e) {
      out.ye_test = { error: e.message };
    }
  }

  return out;
})();
