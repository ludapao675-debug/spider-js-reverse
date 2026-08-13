// shim_event_target.js — 给 Node 垫片补上可工作的 EventTarget（bdms 靠它收 mousemove）
// 根因：toutiao_acrawler/replay_real.js 里 addEventListener/dispatchEvent 是空实现
'use strict';

/**
 * 在对象上安装简易监听表
 * @param {object} target
 */
function installListeners(target) {
  if (!target || target.__ab_evt) return target;
  const map = new Map(); // type -> Set<fn>
  target.__ab_evt = map;

  target.addEventListener = function addEventListener(type, fn, options) {
    if (typeof fn !== 'function') return;
    const t = String(type);
    if (!map.has(t)) map.set(t, new Set());
    map.get(t).add(fn);
    // capture/once 简化忽略
    void options;
  };

  target.removeEventListener = function removeEventListener(type, fn) {
    const set = map.get(String(type));
    if (set) set.delete(fn);
  };

  target.dispatchEvent = function dispatchEvent(evt) {
    if (!evt || evt.type == null) return false;
    const set = map.get(String(evt.type));
    if (!set || set.size === 0) return true;
    for (const fn of Array.from(set)) {
      try {
        fn.call(target, evt);
      } catch (e) {
        // 与浏览器类似：单个 listener 异常不阻断其余
      }
    }
    return true;
  };

  return target;
}

/** 构造最小 MouseEvent */
function makeMouseEvent(g, type, init) {
  const i = init || {};
  return {
    type: String(type),
    bubbles: !!i.bubbles,
    cancelable: !!i.cancelable,
    clientX: i.clientX || 0,
    clientY: i.clientY || 0,
    screenX: i.screenX != null ? i.screenX : i.clientX || 0,
    screenY: i.screenY != null ? i.screenY : i.clientY || 0,
    pageX: i.pageX != null ? i.pageX : i.clientX || 0,
    pageY: i.pageY != null ? i.pageY : i.clientY || 0,
    movementX: i.movementX || 0,
    movementY: i.movementY || 0,
    button: i.button || 0,
    buttons: i.buttons || 0,
    which: i.which || 0,
    ctrlKey: !!i.ctrlKey,
    shiftKey: !!i.shiftKey,
    altKey: !!i.altKey,
    metaKey: !!i.metaKey,
    timeStamp: i.timeStamp || Date.now(),
    target: i.target || (g && g.document) || null,
    currentTarget: null,
    srcElement: i.target || null,
    view: g || null,
    preventDefault() {},
    stopPropagation() {},
    stopImmediatePropagation() {},
  };
}

/**
 * 给 makeBrowserShim 产物打补丁：window / document / body / documentElement
 * @returns {{patched:string[]}}
 */
function installEventTargetShim(g) {
  const patched = [];
  if (!g) return { patched };

  // 覆盖空实现
  installListeners(g);
  patched.push('window');

  if (g.document) {
    installListeners(g.document);
    patched.push('document');
    if (g.document.body) {
      installListeners(g.document.body);
      // body 需要能冒泡到 document：dispatch 时可选再派 document
      const bodyDispatch = g.document.body.dispatchEvent.bind(g.document.body);
      g.document.body.dispatchEvent = function (evt) {
        const ok = bodyDispatch(evt);
        try {
          if (evt && evt.bubbles && g.document && g.document !== this) {
            g.document.dispatchEvent(evt);
          }
        } catch (e) {
          /* ignore */
        }
        return ok;
      };
      patched.push('body');
    }
    if (g.document.documentElement) {
      installListeners(g.document.documentElement);
      patched.push('documentElement');
    }
  }

  // MouseEvent 构造器
  g.MouseEvent = function MouseEvent(type, init) {
    return makeMouseEvent(g, type, init);
  };
  g.PointerEvent = g.MouseEvent;
  g.Event = function Event(type, init) {
    return { type: String(type), bubbles: !!(init && init.bubbles), preventDefault() {}, stopPropagation() {} };
  };

  return { patched };
}

/**
 * 派发一串拟人 mousemove（同步）
 */
function fireMouseMoves(g, opts) {
  const o = opts || {};
  const rounds = o.rounds != null ? o.rounds : 8;
  const perRound = o.perRound != null ? o.perRound : 40;
  const targets = [];
  if (g.document) targets.push(g.document);
  if (g.document && g.document.body) targets.push(g.document.body);
  targets.push(g);

  let n = 0;
  for (let r = 0; r < rounds; r++) {
    for (let i = 0; i < perRound; i++) {
      const ev = makeMouseEvent(g, 'mousemove', {
        clientX: 60 + i * 17 + r * 3,
        clientY: 90 + ((i * 13) % 420),
        bubbles: true,
        timeStamp: Date.now() + i,
      });
      for (const t of targets) {
        try {
          t.dispatchEvent(ev);
          n++;
        } catch (e) {
          /* ignore */
        }
      }
    }
  }
  return { dispatched: n, rounds, perRound };
}

/**
 * 直接喂 bdms me[2] 行为队列（活体验证：me[2]([x,y,ts]) 可调）
 */
function feedMe2Behavior(g, count) {
  const me = g.bdms && g.bdms.init && g.bdms.init._v && g.bdms.init._v[2];
  if (!me || typeof me[2] !== 'function') return { ok: false, reason: 'no_me2' };
  const f = me[2];
  let ok = 0;
  const n = count != null ? count : 80;
  for (let i = 0; i < n; i++) {
    try {
      f([80 + i * 11, 120 + ((i * 7) % 500), Date.now() + i]);
      ok++;
    } catch (e) {
      return { ok: false, reason: String(e.message || e), fed: ok };
    }
  }
  return { ok: true, fed: ok };
}

module.exports = {
  installEventTargetShim,
  fireMouseMoves,
  feedMe2Behavior,
  makeMouseEvent,
};
