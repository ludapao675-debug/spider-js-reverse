# -*- coding: utf-8 -*-
"""
拼多多移动端商品评论 RPC 复现（最终交付形态）

架构结论（多轮实验证实）:
- 评论接口 POST /proxy/api/reviews/{goods_id}/list 强制要求 anti_content
- anti_content 由 RCF 风控 SDK 生成（webpack 模块 45246 导出 g()），
  内部依赖浏览器实时指纹/会话状态（jrpl/dilx/_nano_fp + SubtleCrypto），
  服务端校验绑定浏览器环境：同一活体 token 浏览器内 fetch 通过、
  本地 curl_cffi 秒级重放被 54001 风控拒绝 → 纯本地算法复现不可行
- 解决方案: RPC 桥 —— 本地 Python 经 crypto-hunter 后端 HTTP API
  在活体页面调用 webpack 模块生成新鲜 token，并直接在页面内 fetch 发请求，
  本地只取回数据（限速 + 风控熔断，防止再触发 psnl_verification）

依赖: 后端 http://127.0.0.1:27183 运行中，且浏览器已打开拼多多页面
     （探针丢失时脚本自动重装）

用法: python pdd_comments_rpc.py --goods_id 976241093684 --pages 3 --interval 5
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

BACKEND = "http://127.0.0.1:27183"
DEFAULT_TAB = "3AC01DA691EDCC73060A21A21F94ADDD"  # 2026-08-06 Edge attach 活跃评论页；过期时用 --tab_id 覆盖

# （遗留）浏览器活体 Cookie，仅供本地负向实验脚本 repro.py/fast_replay.py 参考；
# 闭环模式下请求留在浏览器内，无需本地携带 Cookie
COOKIE = ("api_uid=Ck0sQWpy7ftD0wCATLoUAg==; "
          "_nano_fp=XpmJnpUan5Uxn0Tano_~3Y94UM5nFvdl7Ned~u4A; webp=1; "
          "jrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "njrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "dilx=EyTdULuNd3eV84ph3tTFA; "
          "PDDAccessToken=KAUXXQ4M5SAGCLYRBHLEBSZ5VPOEORJLE6MN56ANOKFGGQZXPQSQ1200e08; "
          "pdd_user_id=6772515013646; "
          "pdd_user_uin=6SBCSWT3HUMGRNK6AAKTKPWKWE_GEXDA; "
          "pdd_vds=gaHWpYTYBTuCvpBqhqDHBWTeYWHrZHuevBHBpcvrZqThDcThfWBDTHuZDHpf")

# webpack runtime 探针：捕获 __webpack_require__，按源码指纹定位模块 45246
# （源码含"获取风控参数"字符串的模块即 anti_content 生成模块，导出 g）
PROBE_JS = r"""(() => {
  if (window.__pdd_ac_mod) return 'ready';
  const arr = window.__LOADABLE_LOADED_CHUNKS__;
  if (!arr) return 'no_chunks_array';
  const origPush = Array.prototype.push;
  try {
    Array.prototype.push = function(...args) {
      try {
        if (this === arr && args.length === 1 && Array.isArray(args[0])
            && args[0].length === 3 && typeof args[0][2] === 'function') {
          args[0][2](function probeReq() { throw new Error('probe_stop'); });
          args[0][2] = function(req) { window.__wp_req = req; };
        }
      } catch(e) {}
      return origPush.apply(this, args);
    };
    arr.push([['__probe_' + Date.now()], {}, function(req) { window.__wp_req = req; }]);
  } finally { Array.prototype.push = origPush; }
  const req = window.__wp_req;
  if (!req || !req.m) return 'no_webpack_require';
  const hit = Object.keys(req.m).find(id => {
    try { return String(req.m[id]).includes('\u83b7\u53d6\u98ce\u63a7\u53c2\u6570'); }
    catch(e) { return false; }
  });
  if (!hit) return 'module_not_found';
  window.__pdd_ac_mod = req(hit);
  return 'installed:' + hit;
})()"""

GEN_JS = "(async () => { const ac = await window.__pdd_ac_mod.g(); return {ac: ac}; })()"

# 页面内 fetch 闭环 JS：生成 token + 发请求 + 取数全部留在浏览器环境
# （本地发包已被实验证伪：环境绑定 token 本地重放必 54001）
# $args 由调用方结构化注入 {goods_id, page, size, pdduid}
PAGE_FETCH_JS = r"""(async () => {
  if (!window.__pdd_ac_mod || !window.__pdd_ac_mod.g) return {err: 'probe_missing'};
  const ac = await window.__pdd_ac_mod.g();
  const url = 'https://mobile.pinduoduo.com/proxy/api/reviews/' + $args.goods_id +
    '/list?label_id=0&page=' + $args.page + '&size=' + $args.size +
    '&enable_video=1&enable_group_review=1&pdduid=' + $args.pdduid + '&is_back=1';
  const resp = await fetch(url, {
    method: 'POST',
    headers: {'accept': 'application/json, text/plain, */*',
              'content-type': 'application/json;charset=UTF-8',
              'anti-content': ac},
    body: JSON.stringify({name: 'goodsCommentListAxios', anti_content: ac})
  });
  const d = await resp.json();
  if (resp.status !== 200 || !Array.isArray(d.data)) {
    return {status: resp.status, err: 'risk_or_empty',
            error_code: d.error_code || null,
            verify: !!d.verify_auth_token};
  }
  return {status: resp.status, n: d.data.length,
          items: d.data.map(x => ({
            name: x.name || '', comment: String(x.comment || '').slice(0, 120),
            time: x.time || null, review_id: x.review_id || null,
            pictures: (x.pictures || []).length}))};
})()"""


def run_js(code, tab_id, args=None, timeout=20):
    """经后端 HTTP API 在页面执行 JS（RPC 通道）

    注意：后端 /api/browser/page/run-js 不支持 args 注入（$args 替换只在
    MCP sidecar 层做），此处 args 非空时由本函数拼接 const $args 前缀。
    """
    if args is not None:
        # $args 是合法 JS 标识符，用外层 IIFE 注入常量后返回原表达式
        code = ("(() => { const $args = " + json.dumps(args, ensure_ascii=False)
                + "; return " + code + "; })()")
    payload = json.dumps({
        "tab_id": tab_id, "code": code,
        "return_mode": "json", "await_promise": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        BACKEND + "/api/browser/page/run-js", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"run_js failed: {data.get('error')}")
    return data.get("result")


def _unwrap(result):
    """后端对非 JSON 字符串结果返回 __json_parse_error__ 包装，取原始值"""
    if isinstance(result, dict) and result.get("__json_parse_error__"):
        return result.get("raw_preview", "")
    return result


def _gen_once(tab_id):
    r = _unwrap(run_js(GEN_JS, tab_id))
    if isinstance(r, dict):
        return r.get("ac", "")
    return r if isinstance(r, str) else ""


def get_anti_content(tab_id):
    """RPC 取一枚新鲜 anti_content（约 100ms）"""
    ac = _gen_once(tab_id)
    if not (isinstance(ac, str) and ac.startswith("0as")):
        # 探针可能未安装（页面重载过），先装再取
        probe = _unwrap(run_js(PROBE_JS, tab_id))
        if not str(probe).startswith(("ready", "installed")):
            raise RuntimeError(f"probe failed: {probe}")
        ac = _gen_once(tab_id)
    if not (isinstance(ac, str) and ac.startswith("0as")):
        raise RuntimeError(f"gen failed: {str(ac)[:100]}")
    return ac


def fetch_comments(goods_id, page, pdduid, tab_id, size=10):
    """最终形态：页面内 fetch 闭环（请求留在浏览器，本地只取数）

    返回 (status, result_dict)；result_dict 含 items 或 err 标记。
    注：旧的本地 curl_cffi 发包路径已被实验证伪（环境绑定 token 必 54001），
    保留在 repro.py / fast_replay.py 作为负向证据。
    """
    r = _unwrap(run_js(
        PAGE_FETCH_JS, tab_id,
        args={"goods_id": goods_id, "page": page, "size": size, "pdduid": pdduid},
        timeout=30))
    if not isinstance(r, dict):
        return 0, {"err": "bad_result", "raw": str(r)[:150]}
    # 探针丢失（页面重载）→ 自动重装修复一次
    if r.get("err") == "probe_missing":
        probe = _unwrap(run_js(PROBE_JS, tab_id))
        if not str(probe).startswith(("ready", "installed")):
            return 0, {"err": f"probe_failed:{probe}"}
        r = _unwrap(run_js(
            PAGE_FETCH_JS, tab_id,
            args={"goods_id": goods_id, "page": page, "size": size, "pdduid": pdduid},
            timeout=30))
    return (r or {}).get("status", 0), (r if isinstance(r, dict) else {})


def main():
    # Windows GBK 控制台无法输出评论中的 emoji，重配置容错避免崩溃
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="拼多多评论 RPC 复现（浏览器内 fetch 闭环）")
    ap.add_argument("--goods_id", default="976241093684")
    ap.add_argument("--pdduid", default="6772515013646")
    ap.add_argument("--tab_id", default=DEFAULT_TAB)
    ap.add_argument("--pages", type=int, default=3, help="连续抓取页数（多样本验证）")
    ap.add_argument("--start_page", type=int, default=12)
    ap.add_argument("--interval", type=float, default=5.0,
                    help="请求间隔秒数（风控红线：勿低于 3）")
    args = ap.parse_args()

    ok_cnt, fail_cnt, risk_cnt = 0, 0, 0
    all_items = []
    for i in range(args.pages):
        page = args.start_page + i
        if i > 0:
            time.sleep(args.interval)  # 限速：避免再次触发 psnl_verification
        t0 = time.time()
        try:
            status, data = fetch_comments(args.goods_id, page, args.pdduid, args.tab_id)
        except Exception as e:
            print(f"[page={page}] EXCEPTION {e}")
            fail_cnt += 1
            continue
        elapsed = time.time() - t0
        if status == 200 and isinstance(data.get("items"), list):
            first = [it["name"] for it in data["items"][:3]]
            print(f"[page={page}] OK n={data['n']} {elapsed:.2f}s first={first}")
            all_items.extend(data["items"])
            ok_cnt += 1
        else:
            code = data.get("error_code")
            print(f"[page={page}] FAIL {elapsed:.2f}s status={status} "
                  f"error_code={code} verify={data.get('verify')}")
            fail_cnt += 1
            # 熔断：命中风控（54001/verify_auth_token）立即停，防止升级为安全验证页
            if code == 54001 or data.get("verify") or data.get("err") == "risk_or_empty":
                risk_cnt += 1
                print("!! 命中风控信号，熔断停止，请人工确认浏览器页面状态后再继续")
                break

    print(f"\n结果: {ok_cnt} 成功 / {fail_cnt} 失败 (共 {args.pages} 页), "
          f"累计 {len(all_items)} 条评论")
    # 落盘输出（snake_case 命名，敏感数据仅本地保存；固定写到 case 目录）
    if all_items:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"comments_{args.goods_id}_p{args.start_page}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=1)
        print(f"已保存: {out}")
    sys.exit(0 if fail_cnt == 0 else 1)


if __name__ == "__main__":
    main()
