# -*- coding: utf-8 -*-
"""小红书 mnsv2 真身捕获（自包含复现脚本，置于 cases/xhs_acrawler/）。

原理：signV2Init 内 String.raw(__makeTemplateObject([...])) 拼出 ob 混淆代码，
末尾 eval(code) 触发 _0x5ae8 解密 + _0xe762c0(0xNN) 解密 + 自解密 IIFE +
glb[_0xe762c0(0x73)]=function(...) 动态挂载（即 mnsv2 真身）。

本脚本用捕获式 String.raw 拦截 code 取值，并在全局作用域执行 signV2Init()
触发 eval(code)，使 mnsv2 真身挂到 global["_AUuXfEG27Xa3x"]，保存其函数体。

依赖：本目录的 xhs_signV2Init.js（自解密入口源码）、Node.js（执行 eval）。
"""
import subprocess
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(HERE, "xhs_signV2Init.js")

node_code = r"""
global.window = global;
global.self = global;
global.document = {
  createElement: function(){return {style:{}, setAttribute:function(){}};},
  body:{appendChild:function(){}}, documentElement:{}, cookie:"",
  addEventListener:function(){}, getElementById:function(){return null;}, querySelector:function(){return null;}
};
global.navigator = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", platform:"Win32" };
global.location = { href:"https://www.xiaohongshu.com/explore", protocol:"https:", hostname:"www.xiaohongshu.com" };
global.localStorage = { getItem:function(){return null;}, setItem:function(){} };
global.sessionStorage = { getItem:function(){return null;}, setItem:function(){} };
global.addEventListener = function(){}; global.removeEventListener = function(){};
global.console = console;
if (typeof performance === 'undefined') { global.performance = { now: function(){return Date.now();} }; }
if (typeof setTimeout === 'undefined') { global.setTimeout = function(fn){ return 0; }; }

// 必须挂到 global：signV2Init 经间接 eval 在全局作用域执行，需解析到这些符号
global.__makeTemplateObject = function(cooked, raw) {
  if (Object.defineProperty) { Object.defineProperty(cooked, "raw", { value: raw || cooked }); }
  else { cooked.raw = raw || cooked; }
  return cooked;
};
global.templateObject_1 = undefined;

let __obCode = null;
const _origRaw = String.raw;
String.raw = function(t) {
  let s;
  if (t && t.raw) { s = Array.isArray(t.raw) ? t.raw.join('') : String(t.raw); }
  else if (Array.isArray(t)) { s = t.join(''); }
  else { s = _origRaw.apply(null, arguments); }
  __obCode = s;
  return s;
};

const fs = require('fs');
const src = fs.readFileSync(%r, 'utf8');
(0, eval)(src);
console.log('[node] signV2Init 已定义 =', typeof signV2Init);

const before = new Set(Object.getOwnPropertyNames(global));
try { signV2Init(); console.log('[node] signV2Init() 完成'); }
catch(e){ console.log('[node] signV2Init() 抛错:', e.message); }
console.log('[node] obCode 长度 =', __obCode ? __obCode.length : 0);

const after = new Set(Object.getOwnPropertyNames(global));
let mnsv2_fn = null;
for (const k of [...after].filter(k => !before.has(k))) {
  const v = global[k];
  if (typeof v === 'function' && v.length === 3) {
    console.log('[node] 3参数函数 key =', k, ' head:', (v+'').slice(0, 80));
    mnsv2_fn = {k:k, v:v};
  }
}
if (mnsv2_fn) {
  const body = mnsv2_fn.v + '';
  fs.writeFileSync(%r, body, 'utf8');
  console.log('[node] 已保存 mnsv2 真身到 xhs_mnsv2_real.js, 长度=', body.length, ' key=', mnsv2_fn.k);
}
if (__obCode) {
  fs.writeFileSync(%r, __obCode, 'utf8');
  console.log('[node] 已保存 obCode 到 xhs_obcode_full.js');
}
// 说明：离线调用 mnsv2(url, md5(url), md5(data)) 会触发 err:d93135 参数校验，
// 因首参需特定 hex 编码 payload；属预期强混淆，需浏览器原环境/专用重放才能完整复现 x-s。
""" % (src_path, os.path.join(HERE, "xhs_mnsv2_real.js"), os.path.join(HERE, "xhs_obcode_full.js"))

node_path = os.path.join(HERE, "xhs_run_node.js")
open(node_path, "w", encoding="utf-8").write(node_code)

try:
    r = subprocess.run(["node", node_path], capture_output=True, text=True, timeout=120)
    print("=== NODE STDOUT ===\n" + r.stdout)
    if r.stderr.strip():
        print("=== NODE STDERR ===\n" + r.stderr[:5000])
except subprocess.TimeoutExpired:
    print("[!] Node 执行超时")
except FileNotFoundError:
    print("[!] Node 不可用")
