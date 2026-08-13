// dump_browser_fingerprint.js — 从浏览器 tab 采集 ENV_OVERRIDE 字段（供 Node 垫片对齐）
(function () {
  function flat(obj, prefix, out) {
    if (obj == null || typeof obj !== 'object') {
      out[prefix] = obj;
      return;
    }
    if (Array.isArray(obj)) {
      out[prefix] = obj;
      return;
    }
    Object.keys(obj).forEach(function (k) {
      var key = prefix ? prefix + '.' + k : k;
      var v = obj[k];
      if (v != null && typeof v === 'object' && !Array.isArray(v)) flat(v, key, out);
      else out[key] = v;
    });
  }

  var raw = {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    languages: navigator.languages ? Array.prototype.slice.call(navigator.languages) : [],
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory,
    maxTouchPoints: navigator.maxTouchPoints,
    webdriver: navigator.webdriver,
    vendor: navigator.vendor,
    cookieEnabled: navigator.cookieEnabled,
    devicePixelRatio: window.devicePixelRatio,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    outerWidth: window.outerWidth,
    outerHeight: window.outerHeight,
    screen: {
      width: screen.width,
      height: screen.height,
      availWidth: screen.availWidth,
      availHeight: screen.availHeight,
      colorDepth: screen.colorDepth,
      pixelDepth: screen.pixelDepth,
    },
    location_href: location.href,
    location_host: location.host,
    performance_memory: performance && performance.memory ? {
      usedJSHeapSize: performance.memory.usedJSHeapSize,
      totalJSHeapSize: performance.memory.totalJSHeapSize,
      jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
    } : null,
    bdms_me24: window.bdms && window.bdms.init && window.bdms.init._v && window.bdms.init._v[2]
      ? (window.bdms.init._v[2][24] && window.bdms.init._v[2][24].inner) : null,
  };

  var env = {};
  flat(raw, '', env);

  // replay_real ENV_OVERRIDE 键名映射
  var override = {
    'navigator.userAgent': raw.userAgent,
    'navigator.platform': raw.platform,
    'navigator.language': raw.language,
    'navigator.languages': raw.languages,
    'navigator.hardwareConcurrency': raw.hardwareConcurrency,
    'navigator.deviceMemory': raw.deviceMemory,
    'navigator.maxTouchPoints': raw.maxTouchPoints,
    'navigator.webdriver': raw.webdriver,
    'navigator.vendor': raw.vendor,
    'navigator.cookieEnabled': raw.cookieEnabled,
    devicePixelRatio: raw.devicePixelRatio,
    innerWidth: raw.innerWidth,
    innerHeight: raw.innerHeight,
    outerWidth: raw.outerWidth,
    outerHeight: raw.outerHeight,
    'screen.width': raw.screen.width,
    'screen.height': raw.screen.height,
    'screen.availWidth': raw.screen.availWidth,
    'screen.availHeight': raw.screen.availHeight,
    'screen.colorDepth': raw.screen.colorDepth,
    'screen.pixelDepth': raw.screen.pixelDepth,
    'location.href': raw.location_href,
    'location.host': raw.location_host,
  };

  if (raw.performance_memory) {
    override['performance.memory.usedJSHeapSize'] = raw.performance_memory.usedJSHeapSize;
    override['performance.memory.totalJSHeapSize'] = raw.performance_memory.totalJSHeapSize;
    override['performance.memory.jsHeapSizeLimit'] = raw.performance_memory.jsHeapSizeLimit;
  }

  return {
    ok: true,
    ts: Date.now(),
    url: location.href,
    raw: raw,
    env_override: override,
    me24_head: raw.bdms_me24 ? String(raw.bdms_me24).slice(0, 32) : null,
  };
})();
