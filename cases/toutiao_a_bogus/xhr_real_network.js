// xhr_real_network.js — 为 mssdk 等关键接口提供真实 HTTPS XHR（同步/异步）
'use strict';

const https = require('https');
const http = require('http');
const { URL } = require('url');
const { spawnSync } = require('child_process');

/** 需要真实出网的主机（msToken 来自 mssdk 响应头 x-ms-token） */
const REAL_HOST_RE = /(^|\.)mssdk\.bytedance\.com$/i;

function shouldRealNetwork(urlStr) {
  try {
    const u = new URL(String(urlStr));
    return REAL_HOST_RE.test(u.hostname);
  } catch (e) {
    return false;
  }
}

/**
 * 子进程同步 HTTPS（bdms 可能 sync XHR 打 mssdk）
 * @returns {{status:number, body:string, headers:Object<string,string>}}
 */
function syncHttps(method, urlStr, headers, body) {
  const payload = JSON.stringify({
    method: method || 'GET',
    url: String(urlStr),
    headers: headers || {},
    body: body == null ? null : String(body),
  });
  const worker = `
const https=require('https');const http=require('http');const {URL}=require('url');
const req=JSON.parse(process.argv[1]);
const u=new URL(req.url);
const lib=u.protocol==='http:'?http:https;
const opts={method:req.method,hostname:u.hostname,port:u.port|| (u.protocol==='http:'?80:443),path:u.pathname+u.search,headers:req.headers||{},timeout:20000};
const r=lib.request(opts,res=>{
  const chunks=[];
  res.on('data',c=>chunks.push(c));
  res.on('end',()=>{
    const headers={};
    for(const [k,v] of Object.entries(res.headers||{})){
      headers[String(k).toLowerCase()]=Array.isArray(v)?v.join(', '):String(v);
    }
    process.stdout.write(JSON.stringify({status:res.statusCode||0,body:Buffer.concat(chunks).toString('utf8'),headers}));
  });
});
r.on('error',e=>{process.stdout.write(JSON.stringify({status:0,body:'',headers:{},error:String(e.message||e)}));});
if(req.body!=null) r.write(req.body);
r.end();
`;
  const r = spawnSync(process.execPath, ['-e', worker, payload], {
    encoding: 'utf8',
    timeout: 25000,
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (r.error) {
    return { status: 0, body: '', headers: {}, error: String(r.error.message || r.error) };
  }
  try {
    return JSON.parse(r.stdout || '{}');
  } catch (e) {
    return { status: 0, body: r.stdout || '', headers: {}, error: 'bad_json', stderr: r.stderr };
  }
}

/** 异步 HTTPS */
function asyncHttps(method, urlStr, headers, body) {
  return new Promise((resolve) => {
    try {
      const u = new URL(String(urlStr));
      const lib = u.protocol === 'http:' ? http : https;
      const opts = {
        method: method || 'GET',
        hostname: u.hostname,
        port: u.port || (u.protocol === 'http:' ? 80 : 443),
        path: u.pathname + u.search,
        headers: headers || {},
        timeout: 20000,
      };
      const req = lib.request(opts, (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const h = {};
          for (const [k, v] of Object.entries(res.headers || {})) {
            h[String(k).toLowerCase()] = Array.isArray(v) ? v.join(', ') : String(v);
          }
          resolve({
            status: res.statusCode || 0,
            body: Buffer.concat(chunks).toString('utf8'),
            headers: h,
          });
        });
      });
      req.on('error', (e) => resolve({ status: 0, body: '', headers: {}, error: String(e.message || e) }));
      if (body != null) req.write(String(body));
      req.end();
    } catch (e) {
      resolve({ status: 0, body: '', headers: {}, error: String(e.message || e) });
    }
  });
}

/**
 * 给已有 XMLHttpRequest 垫片打上真实网络能力（仅匹配 REAL_HOST_RE）
 * @param {object} g window/global
 */
function enableRealXhrNetwork(g) {
  const XHR = g.XMLHttpRequest;
  if (!XHR || !XHR.prototype) return { ok: false, reason: 'no_xhr' };

  const proto = XHR.prototype;
  const _open = proto.open;
  const _send = proto.send;
  const _setRequestHeader = proto.setRequestHeader;

  proto.open = function open(method, url, async) {
    this.__async = async !== false;
    this.__reqHeaders = {};
    this.__loadListeners = [];
    this.__realPending = false;
    return _open.apply(this, arguments);
  };

  const _addEventListener = proto.addEventListener;
  proto.addEventListener = function addEventListener(evt, cb) {
    if (evt === 'load' && typeof cb === 'function') {
      if (!this.__loadListeners) this.__loadListeners = [];
      this.__loadListeners.push(cb);
    }
    if (typeof _addEventListener === 'function') {
      try { return _addEventListener.apply(this, arguments); } catch (e) { /* ignore */ }
    }
    return undefined;
  };

  proto.setRequestHeader = function setRequestHeader(k, v) {
    if (!this.__reqHeaders) this.__reqHeaders = {};
    this.__reqHeaders[String(k)] = String(v);
    if (typeof _setRequestHeader === 'function') {
      try { _setRequestHeader.apply(this, arguments); } catch (e) { /* ignore */ }
    }
  };

  proto.getResponseHeader = function getResponseHeader(name) {
    if (!this.__respHeaders) return null;
    return this.__respHeaders[String(name).toLowerCase()] || null;
  };

  proto.getAllResponseHeaders = function getAllResponseHeaders() {
    if (!this.__respHeaders) return '';
    return Object.entries(this.__respHeaders)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\r\n');
  };

  proto.send = function send(body) {
    const url = this._url || this.responseURL || '';
    if (!shouldRealNetwork(url)) {
      return _send.apply(this, arguments);
    }

    this.__realPending = true;
    const method = (this._method || 'GET').toUpperCase();
    const headers = Object.assign({
      'user-agent': (g.navigator && g.navigator.userAgent) || 'Mozilla/5.0',
      referer: 'https://www.toutiao.com/',
      origin: 'https://www.toutiao.com',
      accept: '*/*',
    }, this.__reqHeaders || {});

    const applyResult = (res) => {
      this.__respHeaders = res.headers || {};
      this.status = res.status || 0;
      this.responseText = res.body || '';
      this.responseURL = url;
      this.readyState = 4;
      this.__realPending = false;
      g.__mssdk_last = {
        url,
        status: this.status,
        x_ms_token: this.getResponseHeader('x-ms-token'),
        body_len: (this.responseText || '').length,
        error: res.error || null,
      };
      if (typeof this.onreadystatechange === 'function') {
        try { this.onreadystatechange(); } catch (e) { /* ignore */ }
      }
      const loadEvt = { type: 'load', target: this };
      if (typeof this.onload === 'function') {
        try { this.onload(loadEvt); } catch (e) { /* ignore */ }
      }
      for (const cb of this.__loadListeners || []) {
        try { cb(loadEvt); } catch (e) { /* ignore */ }
      }
    };

    if (this.__async === false) {
      const res = syncHttps(method, url, headers, body);
      applyResult(res);
      return;
    }

    this.readyState = 2;
    asyncHttps(method, url, headers, body).then((res) => {
      applyResult(res);
    });
  };

  return { ok: true, hosts: ['mssdk.bytedance.com'] };
}

/** 等待 me[24].inner 出现（mssdk 回写后） */
async function waitMsToken(g, timeoutMs = 15000, intervalMs = 100) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const me = g.bdms && g.bdms.init && g.bdms.init._v && g.bdms.init._v[2];
    const inner = me && me[24] && me[24].inner;
    if (inner && String(inner).length >= 32) {
      return { ok: true, msToken: String(inner), waited_ms: Date.now() - t0 };
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return {
    ok: false,
    msToken: null,
    waited_ms: timeoutMs,
    last_mssdk: g.__mssdk_last || null,
  };
}

module.exports = {
  shouldRealNetwork,
  enableRealXhrNetwork,
  waitMsToken,
  syncHttps,
  asyncHttps,
};
