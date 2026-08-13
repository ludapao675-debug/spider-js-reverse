// probe_init_me.js — 浏览器内探测 bdms.init._v[2] 各槽类型（供离线 patch 分析）
(function () {
  if (!window.bdms || !window.bdms.init) {
    return { ok: false, error: 'bdms 未加载' };
  }
  const initMe = window.bdms.init._v && window.bdms.init._v[2];
  if (!initMe) return { ok: false, error: 'init._v[2] 缺失' };

  function describe(v, idx) {
    if (v == null) return { idx, type: 'null' };
    const t = typeof v;
    if (t === 'boolean' || t === 'number' || t === 'string') {
      return { idx, type: t, value: t === 'string' && v.length > 80 ? v.slice(0, 80) + '...' : v };
    }
    if (t === 'function') {
      return { idx, type: 'function', pc: v._v && v._v[0] };
    }
    if (Array.isArray(v)) {
      return { idx, type: 'array', len: v.length };
    }
    if (v.items && typeof v.front === 'number') {
      return {
        idx, type: 'queue', front: v.front, rear: v.rear,
        sample: v.items.slice(0, 3).map(function (it) {
          return it && typeof it === 'object' ? { x: it.x, y: it.y, ts: it.ts } : it;
        }),
      };
    }
    const keys = Object.keys(v).slice(0, 8);
    const preview = {};
    keys.forEach(function (k) {
      const x = v[k];
      preview[k] = typeof x === 'function' ? { fn: true, pc: x._v && x._v[0] }
        : (x && x.items ? { queue: true, rear: x.rear } : typeof x);
    });
    return { idx, type: 'object', keys: keys.length, preview: preview };
  }

  const slots = [];
  for (let i = 0; i < initMe.length; i++) {
    slots.push(describe(initMe[i], i));
  }
  const patchable = slots.filter(function (s) {
    return s.type !== 'function' && s.type !== 'array' || (s.type === 'array' && s.len === 0);
  });

  return {
    ok: true,
    len: initMe.length,
    me24: initMe[24],
    patchable_indices: patchable.map(function (s) { return s.idx; }),
    slots: slots,
  };
})();
