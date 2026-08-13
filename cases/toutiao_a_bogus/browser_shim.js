// browser_shim.js — Node 浏览器垫片（从 toutiao_acrawler/replay_real.js 抽取，供 bdms 离线运行）
'use strict';
const fs = require('fs');
const path = require('path');
const { enableRealXhrNetwork } = require('./xhr_real_network');

function installProperXhr(g) {
  // bdms.init 钩在 XMLHttpRequest.prototype 上；replay_real  stub 返回 plain object 无法被 hook
  function XMLHttpRequest() {
    this.readyState = 0;
    this.responseURL = '';
    this.status = 0;
    this.responseText = '';
    this._method = 'GET';
    this._url = '';
    this.invokeList = undefined;
  }
  XMLHttpRequest.prototype.open = function open(method, url, async, user, password) {
    this._method = method;
    this._url = String(url);
    this.responseURL = this._url;
    this.readyState = 1;
    this.__async = async !== false;
  };
  XMLHttpRequest.prototype.send = function send(body) {
    this.readyState = 4;
    this.status = 200;
    this.responseText = '{"message":"success","data":[]}';
  };
  XMLHttpRequest.prototype.setRequestHeader = function setRequestHeader() {};
  XMLHttpRequest.prototype.getAllResponseHeaders = function getAllResponseHeaders() { return ''; };
  XMLHttpRequest.prototype.getResponseHeader = function getResponseHeader() { return null; };
  XMLHttpRequest.prototype.addEventListener = function addEventListener(evt, cb) {
    if (evt === 'load' && typeof cb === 'function') {
      // 真实网络路径会自行触发；假响应延迟一拍兼容 load 监听
      if (!this.__realPending) {
        setTimeout(() => cb({ type: 'load' }), 0);
      }
    }
  };
  XMLHttpRequest.prototype.overrideMimeType = function overrideMimeType() {};
  g.XMLHttpRequest = XMLHttpRequest;
}

/**
 * 构建 vm 沙箱用的 window/global 对象。
 * @param {string} pageUrl 页面 URL，影响 location/document
 * @param {object|null} envOverride 可选环境覆盖
 * @param {{realNetwork?: boolean}} opts realNetwork=true 时 mssdk 走真实 HTTPS
 */
function makeBrowserShim(pageUrl, envOverride, opts) {
  const TARGET_URL = pageUrl || 'https://www.toutiao.com/';
  const ENV_OVERRIDE = envOverride || null;
  const src = fs.readFileSync(path.join(__dirname, '..', 'toutiao_acrawler', 'replay_real.js'), 'utf8');
  const start = src.indexOf('function makeShim()');
  const end = src.indexOf('function main()');
  if (start < 0 || end <= start) {
    throw new Error('无法从 replay_real.js 抽取 makeShim');
  }
  const body = src.slice(start, end) + '\nreturn makeShim();';
  // eslint-disable-next-line no-new-func
  const g = new Function('TARGET_URL', 'ENV_OVERRIDE', body)(TARGET_URL, ENV_OVERRIDE);
  installProperXhr(g);
  // 必须在 bdms.init hook 之前启用：mssdk 回写 x-ms-token → me[24]
  if (!opts || opts.realNetwork !== false) {
    g.__xhr_real = enableRealXhrNetwork(g);
  }
  return g;
}

module.exports = { makeBrowserShim, installProperXhr };
