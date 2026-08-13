# -*- coding: utf-8 -*-
"""
纯本地复现可行性实验（sdenv 补环境路线）

链路：
1. 从活体页面 BFS dump webpack 模块 45246 的依赖闭包（123 模块 ~321KB）
2. 组装 mini webpack runtime 独立 bundle（携带真实 __webpack_require__ 帮助函数）
3. 提交 /api/sdenv/run-code（super_env 补环境 + 活体 Cookie）离线生成 anti_content
4. 判据对照（各限 1 次，风控预算极小）：
   C1 = sdenv 离线 token 本地 curl_cffi 发请求（预期 54001）
   C2 = 同枚离线 token 在浏览器内 fetch（判据：token 是否绑定活体上报会话）

零请求风险说明：步骤 1~3 不产生任何对拼多多的网络请求。
"""
import json
import os
import sys
import time
import urllib.request

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
GOODS_ID = "976241093684"
PDDUID = "6772515013646"

# ── 步骤 1：页面内构建自包含 bundle ──────────────────────────────
# BFS 闭包 + 序列化真实 webpack runtime（req.d/req.n/req.r 均为无闭包纯函数）
BUNDLE_JS = r"""(() => {
  const req = window.__wp_req;
  if (!req || !req.m || !req.m[45246]) return {err: 'no_webpack_require'};
  const seen = new Set([45246]);
  const queue = [45246];
  while (queue.length) {
    const id = queue.shift();
    const f = req.m[id];
    if (!f) continue;
    const s = String(f);
    // 各工厂的 require 形参名不同（r/n/e），用通配匹配单数字实参调用；
    // 误收的非模块 ID 在 req.m 中不存在，构建时自动跳过，只增不减
    const deps = (s.match(/\w\((\d{1,6})\)/g) || []).map(x => x.match(/\d+/)[0]);
    deps.forEach(d => { if (!seen.has(d)) { seen.add(d); queue.push(d); } });
  }
  const parts = [];
  seen.forEach(id => {
    if (!req.m[id]) return;
    const key = JSON.stringify(String(id));
    if (!key) return;  // 防御：序列化失败直接跳过，杜绝悬挂逗号
    parts.push(key + ':' + String(req.m[id]));
  });
  const mapSrc = '{' + parts.join(',') + '}';
  const bundle =
    '(function(){' +
    // 静默 SDK 噪声日志（API 响应 output 截断 5000 字符），
    // 只透传 BEGIN~END 之间的 token 行与诊断行（标志法：token 本身不含标记词）
    'var __cap=0,__origlog=console.log.bind(console);' +
    '["log","info","debug","warn"].forEach(function(k){' +
    'console[k]=function(){var s=Array.prototype.map.call(arguments,function(a){try{return typeof a==="string"?a:JSON.stringify(a)}catch(e){return "?"}}).join(" ");' +
    'if(s.indexOf("SDENV_TOKEN_BEGIN")>=0){__cap=1;__origlog(s);return}' +
    'if(s.indexOf("SDENV_TOKEN_END")>=0){__cap=0;__origlog(s);return}' +
    'if(__cap||s.indexOf("SDENV_GEN_")>=0)__origlog(s)};});' +
    'var __factories=' + mapSrc + ';' +
    'var __cache={};' +
    'function __wreq(id){id=String(id);' +
    'if(__cache[id])return __cache[id].exports;' +
    'var f=__factories[id];if(!f)throw new Error("module_not_bundled:"+id);' +
    'var m={exports:{}};__cache[id]=m;' +
    'f(m,m.exports,__wreq);' +
    'return m.exports;}' +
    // req.d/req.n 内部引用 runtime 私有变量（i.o）无法序列化，
    // 用 webpack 标准等价实现替代（语义完全一致）
    '__wreq.o=function(o,p){return Object.prototype.hasOwnProperty.call(o,p)};' +
    '__wreq.d=function(e,t){for(var r in t){if(__wreq.o(t,r)&&!__wreq.o(e,r)){' +
    'Object.defineProperty(e,r,{enumerable:true,get:t[r]})}}};' +
    '__wreq.n=function(e){var g=e&&e.__esModule?function(){return e["default"]}' +
    ':function(){return e};__wreq.d(g,{a:g});return g};' +
    '__wreq.r=function(e){if(typeof Symbol!=="undefined"&&Symbol.toStringTag){' +
    'Object.defineProperty(e,Symbol.toStringTag,{value:"Module"})}' +
    'Object.defineProperty(e,"__esModule",{enumerable:false,value:true})};' +
    // nmd（node module decorator）/ publicPath 等价实现
    '__wreq.nmd=function(m){m.children=[];m.paths=[];return m};' +
    '__wreq.p="/";' +
    'globalThis.__wreq=__wreq;' +
    // 外层 IIFE 返回该 Promise → runner 会 await 它，
    // 保证 cookie/eval 读取发生在生成完成之后
    'return (async function(){' +
    'var __done=0;setTimeout(function(){if(!__done)console.log("SDENV_GEN_TIMEOUT")},8000);' +
    'try{' +
    'var mod=__wreq("45246");' +
    'var ac=await mod.g();' +
    '__done=1;' +
    'globalThis.__sdenv_token=ac;' +
    // token 经 cookie 通道传出（output 有 5000 字符头部截断，cookie 字段不截断）
    'try{document.cookie="__sdenv_ac="+ac+"; path=/"}catch(e){}' +
    'console.log("SDENV_GEN_OK len="+(ac?ac.length:0));' +
    '}catch(e){__done=1;console.log("SDENV_GEN_ERROR:"+e);}})();' +
    '})();';
  return {modules: seen.size, bundle_len: bundle.length, bundle: bundle};
})()"""


def api_post(path, payload, timeout=120):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def unwrap(result):
    if isinstance(result, dict) and result.get("__json_parse_error__"):
        return result.get("raw_preview", "")
    return result


def get_live_cookie():
    """从后端取活体 Cookie（比硬编码新鲜）"""
    d = api_post("/api/browser/page/cookies",
                 {"tab_id": TAB_ID, "all_domains": False, "all_info": False}, timeout=20)
    items = d.get("cookies") or []
    return "; ".join(f"{c.get('name')}={c.get('value')}" for c in items if c.get("name"))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    # 步骤 1：构建 bundle（页面内，零风控风险）
    print("[1] 页面内构建 webpack 闭包 bundle ...")
    r = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID, "code": BUNDLE_JS,
        "return_mode": "json", "await_promise": True, "timeout_sec": 60})
    res = unwrap(r.get("result"))
    if not isinstance(res, dict) or "bundle" not in res:
        # 大结果可能被落盘（run_js_dumps），用 GET 接口读回
        if r.get("result_stashed") and r.get("result_file"):
            import os as _os
            fname = _os.path.basename(str(r["result_file"]))
            with urllib.request.urlopen(
                    f"{BACKEND}/api/browser/page/run-js/result?file={fname}",
                    timeout=30) as resp:
                rr = json.loads(resp.read().decode("utf-8"))
            res = rr.get("data") or {}
        else:
            print(f"bundle 构建失败: {str(res)[:300]}")
            sys.exit(1)
    bundle = res["bundle"]
    print(f"    模块数={res.get('modules')} bundle体积={len(bundle)//1024}KB")
    out_js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdenv_bundle.js")
    with open(out_js, "w", encoding="utf-8") as f:
        f.write(bundle)

    # 步骤 2：sdenv 离线执行（零网络请求）
    print("[2] sdenv 离线执行生成 anti_content ...")
    cookie = get_live_cookie()
    print(f"    活体 Cookie {len(cookie)} 字符")
    t0 = time.time()
    d = api_post("/api/sdenv/run-code", {
        "js_code": bundle,
        "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookies": cookie,
        "super_env": True,
        "timeout": 60,
        # 备用通道：runner 在 await 主代码 Promise 后求值
        "eval_expression": "globalThis.__sdenv_token",
    }, timeout=180)
    print(f"    ok={d.get('ok')} error_type={d.get('error_type')} "
          f"missing_ref={d.get('missing_ref')} {time.time()-t0:.1f}s")
    out = d.get("output") or ""
    if d.get("error"):
        print(f"    error: {str(d.get('error'))[:300]}")
    # 提取 token：优先 cookie 通道（__sdenv_ac），其次 output 标记
    token = ""
    ck = str(d.get("cookies") or "")
    for part in ck.split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac="):]
            break
    if not token:
        ev = d.get("eval_result")
        if isinstance(ev, str) and ev.startswith("0as"):
            token = ev.strip()
    print(f"    token: {token[:40]}... len={len(token)}")
    if not token.startswith("0as"):
        print("    离线生成失败，输出尾部 500 字符：")
        print(out[-500:])
        sys.exit(2)

    # 步骤 3-C1：本地 curl_cffi 发 1 次（预期 54001）
    print("[3] C1: sdenv token 本地 curl_cffi 发请求（限 1 次）...")
    url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
           f"?label_id=0&page=20&size=10&enable_video=1"
           f"&enable_group_review=1&pdduid={PDDUID}")
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookie": cookie,
        "anti-content": token,
        # 与浏览器真实请求完全一致的客户端提示头（排除头不一致这一变量）
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
        "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "accept-language": "zh-CN,zh;q=0.9",
    }
    resp = crl.post(url, headers=headers,
                    json={"name": "goodsCommentListAxios", "anti_content": token},
                    impersonate="chrome", timeout=15)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:150]}
    ok_local = isinstance(body, dict) and isinstance(body.get("data"), list)
    print(f"    C1 本地: status={resp.status_code} "
          f"{'OK n=' + str(len(body.get('data', []))) if ok_local else 'REJECT ' + str(body)[:120]}")

    # 步骤 3-C2：同枚 token 浏览器内 fetch（判据实验，限 1 次；C1 已通过则跳过省预算）
    if ok_local:
        print("[4] C1 已通过，跳过 C2（节省风控预算）")
        res2 = None
    else:
        print("[4] C2: 同枚 sdenv token 浏览器内 fetch（限 1 次）...")
        c2_js = ("(async () => { const resp = await fetch("
                 "'https://mobile.pinduoduo.com/proxy/api/reviews/" + GOODS_ID +
                 "/list?label_id=0&page=21&size=10&enable_video=1&enable_group_review=1&pdduid=" +
                 PDDUID + "', {method:'POST',"
                 "headers:{'accept':'application/json, text/plain, */*',"
                 "'content-type':'application/json;charset=UTF-8','anti-content':$args.ac},"
                 "body:JSON.stringify({name:'goodsCommentListAxios',anti_content:$args.ac})});"
                 "const d = await resp.json();"
                 "return {status:resp.status,n:Array.isArray(d.data)?d.data.length:0,"
                 "error_code:d.error_code||null,verify:!!d.verify_auth_token}; })()")
        c2_js = ("(() => { const $args = " + json.dumps({"ac": token}) +
                 "; return " + c2_js + "; })()")
        r2 = api_post("/api/browser/page/run-js", {
            "tab_id": TAB_ID, "code": c2_js,
            "return_mode": "json", "await_promise": True, "timeout_sec": 30})
        res2 = unwrap(r2.get("result"))
        print(f"    C2 浏览器内: {json.dumps(res2, ensure_ascii=False)[:200]}")

    # 结论输出
    print("\n═══ 判据结论 ═══")
    c2_ok = isinstance(res2, dict) and res2.get("status") == 200 and res2.get("n", 0) > 0
    if ok_local:
        print("sdenv 离线 token 本地直接通过 → 纯本地复现成立！")
    elif c2_ok:
        print("离线 token 浏览器内通过/本地拒 → 阻碍在请求通道环境关联（非 token 计算）")
    else:
        print("离线 token 浏览器内也被拒 → token 绑定 SDK 活体上报会话，"
              "纯本地须完整还原指纹上报链")


if __name__ == "__main__":
    main()
