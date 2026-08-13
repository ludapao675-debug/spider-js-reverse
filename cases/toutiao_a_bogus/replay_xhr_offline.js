// replay_xhr_offline.js — 纯 Node：bdms.init 后走 XHR 链签名（与浏览器一致）
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { makeBrowserShim } = require('./browser_shim');

const HERE = __dirname;
const RAW_BDMS = path.join(HERE, 'raw', 'bdms.js');
const TIMEOUT = 90000;

const INPUT_URL = process.argv[2]
  || 'https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=1784004887&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web&msToken=test';

function installXhrCapture(g) {
  const NativeXHR = g.XMLHttpRequest;
  const trace = [];

  function CapturingXHR() {
    const inner = new NativeXHR();
    const self = this;
    this._method = 'GET';
    this._url = '';
    this._headers = {};
    this.responseURL = '';
    this.status = 0;
    this.responseText = '';

    this.open = function (method, url) {
      self._method = method;
      self._url = String(url);
      trace.push({ phase: 'open_in', method, url: self._url });
      try {
        inner.open(method, url);
      } catch (e) {
        trace.push({ phase: 'open_err', err: e.message });
      }
      // bdms 可能在 open 时改写 url
      if (inner.responseURL) self.responseURL = inner.responseURL;
      trace.push({ phase: 'open_out', url: self._url, innerResp: inner.responseURL || '' });
    };

    this.setRequestHeader = function (k, v) {
      self._headers[k] = v;
      if (inner.setRequestHeader) inner.setRequestHeader(k, v);
    };

    this.send = function (body) {
      trace.push({ phase: 'send_in', url: self._url });
      if (inner.send) {
        try {
          inner.send(body);
        } catch (e) {
          trace.push({ phase: 'send_err', err: e.message });
        }
      }
      self.responseURL = inner.responseURL || self._url;
      self.status = inner.status || 200;
      self.responseText = inner.responseText || '{"message":"offline_stub"}';
      trace.push({ phase: 'send_out', responseURL: self.responseURL });
    };

    this.addEventListener = function (evt, cb) {
      if (evt === 'load' && cb) setTimeout(() => cb({ type: 'load' }), 0);
      if (inner.addEventListener) inner.addEventListener(evt, cb);
    };
  }

  g.XMLHttpRequest = CapturingXHR;
  g.__xhr_trace = trace;
}

function loadBdms(g) {
  const src = fs.readFileSync(RAW_BDMS, 'utf8');
  vm.runInContext(src, vm.createContext(g), { timeout: TIMEOUT, filename: 'bdms.js' });
}

function main() {
  const g = makeBrowserShim('https://www.toutiao.com/');
  g.window = g;
  g.self = g;

  installXhrCapture(g);

  console.log('[replay_xhr_offline] 加载 bdms ...');
  loadBdms(g);

  console.log('[replay_xhr_offline] bdms.init ...');
  g.bdms.init({
    aid: 24,
    pageId: 6457,
    boe: false,
    ddrt: 3,
    paths: { include: ['/api/pc/list/feed', '/api/pc/list/user/feed'] },
    track: {},
    dump: true,
  });

  const xhr = new g.XMLHttpRequest();
  xhr.open('GET', INPUT_URL);
  xhr.send();

  const final = xhr.responseURL || INPUT_URL;
  const m = final.match(/[?&]a_bogus=([^&]+)/);
  const abogus = m ? decodeURIComponent(m[1]) : null;

  console.log('INPUT :', INPUT_URL.slice(0, 100));
  console.log('FINAL :', final.slice(0, 120));
  console.log('a_bogus:', abogus ? abogus.slice(0, 80) + '... len=' + abogus.length : null);
  console.log('trace:', JSON.stringify(g.__xhr_trace, null, 2));

  if (!abogus || abogus.length < 80) {
    process.exit(2);
  }
}

main();
