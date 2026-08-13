# -*- coding: utf-8 -*-
"""拼多多评论 — 纯本地 tls-client 交付（chrome_150，可无浏览器）。

稳态路径（无 CDP / 无页面 fetch）：
  1) 一次性（可选）: --dump-assets 从活体页导出 bundle + cookie → 落盘
  2) 日常: --cookie-file + --bundle-file → sdenv 出 0as → tls-client 翻页

Phase1 已证 chrome_150；出票层用缓存 webpack 45246 闭包 + sdenv，不再每页调浏览器。

用法：
  # 一次性导出（需要浏览器仍打开评论页）
  python pdd_comments_local_tls.py --dump-assets --tab_id <TAB>

  # 无浏览器翻页
  python pdd_comments_local_tls.py --confirm-local --pages 2 --start_page 45 --interval 5
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import phase1_utls_live as p1  # noqa: E402

BACKEND = "http://127.0.0.1:27183"  # 仅 dump-assets / browser 出票仍可能用到
SERVER_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "server"))
DEFAULT_BUNDLE = os.path.join(HERE, "webpack_45246_bundle.js")
DEFAULT_SESSION = os.path.join(HERE, "session_offline.json")
SDENV_RUNNER = os.path.join(SERVER_DIR, "sdenv_runner.js")
# 设 CRYPTO_HUNTER_SDENV_HTTP=1 才回落 HTTP 后端出票（调试用）
SDENV_HTTP_FALLBACK = str(os.environ.get("CRYPTO_HUNTER_SDENV_HTTP", "0")).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def api_post(path: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(BACKEND + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_session(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("cookie"):
        return data
    if isinstance(data, list):
        # [{name,value}, ...]
        cookie = "; ".join(
            f"{c['name']}={c['value']}" for c in data if c.get("name") and c.get("value") is not None
        )
        return {"cookie": cookie, "vat": "", "pdduid": "", "goods_id": ""}
    raise ValueError(f"bad session file: {path}")


def save_session(path: str, cookie: str, vat: str, goods_id: str, pdduid: str) -> None:
    jar = p1.cookie_dict(cookie)
    obj = {
        "cookie": cookie,
        "cookies": jar,
        "vat": vat or "",
        "goods_id": goods_id,
        "pdduid": pdduid or jar.get("pdd_user_id", ""),
        "saved_at": int(time.time()),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"[save] session → {path} ({len(jar)} cookies)")


def fetch_bundle_from_browser(tab_id: str) -> tuple[str, dict]:
    """Run BUNDLE_JS in page; handle result_stashed for large payload."""
    import local_repro_experiment as lre

    p1.TAB_ID = tab_id
    d = api_post(
        "/api/browser/page/run-js",
        {
            "tab_id": tab_id,
            "code": lre.BUNDLE_JS,
            "return_mode": "json",
            "await_promise": True,
            "timeout_sec": 90,
        },
        timeout=120,
    )
    if not d.get("ok"):
        raise RuntimeError(d)
    res = d.get("result")
    if isinstance(res, dict) and res.get("__json_parse_error__"):
        raise RuntimeError(res)
    if isinstance(res, dict) and "bundle" in res:
        return res["bundle"], {"modules": res.get("modules"), "bundle_len": res.get("bundle_len")}
    if d.get("result_stashed") and d.get("result_file"):
        fname = os.path.basename(str(d["result_file"]))
        rr = api_get(f"/api/browser/page/run-js/result?file={fname}", timeout=60)
        data = rr.get("data") or {}
        if "bundle" not in data:
            raise RuntimeError(f"stashed miss bundle: {list(data)[:10]}")
        return data["bundle"], {
            "modules": data.get("modules"),
            "bundle_len": data.get("bundle_len"),
            "stashed": fname,
        }
    raise RuntimeError(f"bundle fail: {str(res)[:240]}")


def dump_assets(tab_id: str, bundle_path: str, session_path: str, goods_id: str) -> None:
    print("[dump] cookies ...")
    p1.TAB_ID = tab_id
    cookie = p1.get_cookie_str()
    vat = p1.get_vat()
    jar = p1.cookie_dict(cookie)
    pdduid = jar.get("pdd_user_id") or p1.PDDUID
    save_session(session_path, cookie, vat, goods_id, pdduid)

    print("[dump] webpack 45246 bundle (may take ~30s) ...")
    bundle, meta = fetch_bundle_from_browser(tab_id)
    with open(bundle_path, "w", encoding="utf-8") as f:
        f.write(bundle)
    meta_path = bundle_path + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({**meta, "bytes": len(bundle), "tab_id": tab_id}, f, indent=2)
    print(f"[dump] bundle → {bundle_path} ({len(bundle)} chars, meta={meta})")


def check_sdenv_local() -> tuple[bool, str]:
    """出票前置：Node + sdenv_runner.js（不依赖 27183）。"""
    if not os.path.isfile(SDENV_RUNNER):
        return False, f"缺少 runner: {SDENV_RUNNER}"
    try:
        proc = subprocess.run(
            ["node", "-v"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return False, "node -v 失败"
        ver = (proc.stdout or proc.stderr or "").strip()
    except FileNotFoundError:
        return False, "未找到 node，请安装 Node.js 并加入 PATH"
    except Exception as e:
        return False, f"检测 node 失败: {e}"
    return True, f"node {ver}; runner={SDENV_RUNNER}"


def _extract_token_from_sdenv_payload(cookies: str, eval_result: Any, output: str = "") -> str:
    token = ""
    for part in str(cookies or "").split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac=") :]
            break
    if not token and isinstance(eval_result, str) and eval_result.startswith("0as"):
        token = eval_result.strip()
    if not token and output:
        # 兼容标记通道
        for line in str(output).splitlines():
            if "SDENV_TOKEN_BEGIN" in line:
                continue
            if line.strip().startswith("0as"):
                token = line.strip()
                break
    return token


def _run_in_sdenv_direct(
    bundle: str, cookie: str, goods_id: str, timeout: int = 180
) -> Any:
    if SERVER_DIR not in sys.path:
        sys.path.insert(0, SERVER_DIR)
    from sdenv_code_verifier import run_in_sdenv  # noqa: WPS433

    return run_in_sdenv(
        js_code=bundle,
        url=f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={goods_id}",
        cookies=cookie,
        super_env=True,
        timeout=float(timeout),
        eval_expression="globalThis.__sdenv_token",
        prefer_runner="sdenv-main",
    )


def gen_token_sdenv(bundle: str, cookie: str, goods_id: str, timeout: int = 180) -> str:
    """直调 server/sdenv_runner.js（经 sdenv_code_verifier.run_in_sdenv），默认不走 HTTP。"""
    ok, detail = check_sdenv_local()
    if not ok and not SDENV_HTTP_FALLBACK:
        raise RuntimeError(f"本地 sdenv 不可用: {detail}")

    if ok:
        print(f"[token] sdenv-direct ({detail})")
        result = _run_in_sdenv_direct(bundle, cookie, goods_id, timeout=timeout)
        raw = getattr(result, "_raw_data", None) or {}
        token = _extract_token_from_sdenv_payload(
            getattr(result, "cookies", "") or "",
            raw.get("eval_result"),
            getattr(result, "output", "") or "",
        )
        if token.startswith("0as"):
            return token
        err = getattr(result, "error", "") or "no 0as token"
        mode = getattr(result, "runner_mode", "")
        # 直调失败且允许 HTTP 时再回落
        if not SDENV_HTTP_FALLBACK:
            raise RuntimeError(
                f"sdenv-direct fail mode={mode} err={str(err)[:280]} "
                f"elapsed={getattr(result, 'execution_time', 0):.1f}s"
            )
        print(f"[token] WARN direct fail → HTTP fallback: {err}")

    print("[token] sdenv-http (CRYPTO_HUNTER_SDENV_HTTP=1)")
    d = api_post(
        "/api/sdenv/run-code",
        {
            "js_code": bundle,
            "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={goods_id}",
            "cookies": cookie,
            "super_env": True,
            "timeout": timeout,
            "eval_expression": "globalThis.__sdenv_token",
        },
        timeout=timeout + 90,
    )
    token = _extract_token_from_sdenv_payload(
        str(d.get("cookies") or ""), d.get("eval_result"), str(d.get("output") or "")
    )
    if not token.startswith("0as"):
        err = d.get("error") or d.get("error_type") or d
        raise RuntimeError(f"sdenv-http fail: {str(err)[:300]}")
    return token

def gen_token_browser(tab_id: str) -> str:
    from pdd_comments_rpc import get_anti_content

    return get_anti_content(tab_id)


def warmup(sess: p1.TlsClientSession, cookie: str, goods_id: str, pdduid: str) -> str:
    referer = f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={goods_id}"
    old_g, old_u = p1.GOODS_ID, p1.PDDUID
    p1.GOODS_ID, p1.PDDUID = goods_id, pdduid
    try:
        print("[warm] GET goods ...")
        try:
            r0 = sess.get(
                referer,
                headers=p1.base_headers(
                    cookie,
                    {
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "none",
                    },
                ),
                timeout_seconds=90,
            )
            cookie = p1.merge_set_cookie(cookie, r0)
            print(f"       http={getattr(r0, 'status_code', None)}")
        except Exception as e:
            print(f"       WARN goods GET skip: {e} — continue a3 on same session")

        print("[warm] GET a3 ...")
        r1 = sess.get(
            "https://mobile.pinduoduo.com/proxy/api/xg/pfb/a3",
            headers=p1.base_headers(cookie),
        )
        cookie = p1.merge_set_cookie(cookie, r1)
        print(f"       http={getattr(r1, 'status_code', None)}")

        print("[warm] POST ae4 ...")
        payload = json.dumps(
            {"u": pdduid, "f": "", "keys": "t,acc"}, separators=(",", ":")
        )
        body2 = json.dumps({"data": p1.shift(payload, 30)}, separators=(",", ":"))
        r2 = sess.post(
            "https://xg.pinduoduo.com/xg/pfb/ae4",
            headers=p1.base_headers(
                cookie,
                {
                    "content-type": "application/json;charset=UTF-8",
                    "sec-fetch-site": "same-site",
                },
            ),
            data=body2,
        )
        cookie = p1.merge_set_cookie(cookie, r2)
        print(f"       http={getattr(r2, 'status_code', None)}")

        print("[warm] POST a4 ...")
        a4body = json.dumps(p1.build_clean_a4_body(), separators=(",", ":"))
        r3 = sess.post(
            "https://mobile.pinduoduo.com/proxy/api/xg/pfb/a4",
            headers=p1.base_headers(
                cookie, {"content-type": "application/json;charset=UTF-8"}
            ),
            data=a4body,
        )
        cookie = p1.merge_set_cookie(cookie, r3)
        try:
            j3 = r3.json()
        except Exception:
            j3 = {}
        result_a = ((j3.get("result") or {}).get("a")) if isinstance(j3, dict) else None
        if result_a:
            jar = p1.cookie_dict(cookie)
            jar["njrpl"] = result_a
            cookie = "; ".join(f"{k}={v}" for k, v in jar.items())
        print(
            f"       http={getattr(r3, 'status_code', None)} "
            f"success={j3.get('success') if isinstance(j3, dict) else None}"
        )

        print("[warm] POST t.gif ...")
        tbody = p1.build_tgif_body(p1.cookie_dict(cookie))
        r4 = sess.post(
            "https://th.pinduoduo.com/t.gif",
            headers=p1.base_headers(
                cookie,
                {
                    "content-type": "application/x-www-form-urlencoded",
                    "sec-fetch-site": "same-site",
                },
            ),
            data=tbody,
        )
        cookie = p1.merge_set_cookie(cookie, r4)
        print(f"       http={getattr(r4, 'status_code', None)}")

        dwell = random.uniform(3.0, 6.0)
        print(f"[warm] dwell {dwell:.1f}s")
        time.sleep(dwell)
        return cookie
    finally:
        p1.GOODS_ID, p1.PDDUID = old_g, old_u


def fetch_page(
    sess: p1.TlsClientSession,
    cookie: str,
    vat: str,
    ac: str,
    goods_id: str,
    pdduid: str,
    page: int,
    size: int,
) -> tuple[str, dict]:
    url = (
        f"https://mobile.pinduoduo.com/proxy/api/reviews/{goods_id}/list"
        f"?label_id=0&page={page}&size={size}&enable_video=1&enable_group_review=1"
        f"&pdduid={pdduid}&is_back=1"
    )
    extra = {
        "content-type": "application/json;charset=UTF-8",
        "anti-content": ac,
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={goods_id}",
    }
    if vat:
        extra["verifyauthtoken"] = vat
    body = json.dumps(
        {"name": "goodsCommentListAxios", "anti_content": ac},
        separators=(",", ":"),
    )
    old_g = p1.GOODS_ID
    p1.GOODS_ID = goods_id
    try:
        resp = sess.post(url, headers=p1.base_headers(cookie, extra), data=body)
    finally:
        p1.GOODS_ID = old_g
    cookie = p1.merge_set_cookie(cookie, resp)
    try:
        j = resp.json()
    except Exception:
        j = {"raw": (getattr(resp, "text", "") or "")[:300]}
    items = []
    if isinstance(j.get("data"), list):
        for x in j["data"]:
            items.append(
                {
                    "name": x.get("name") or "",
                    "comment": str(x.get("comment") or "")[:120],
                    "time": x.get("time"),
                    "review_id": x.get("review_id"),
                    "pictures": len(x.get("pictures") or []),
                }
            )
    out = {
        "http": getattr(resp, "status_code", None),
        "n": len(items),
        "items": items,
        "error_code": j.get("error_code"),
        "verify": bool(j.get("verify_auth_token")),
        "msg": (j.get("error_msg") or "")[:80],
    }
    return cookie, out


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="PDD comments local tls-client chrome_150 (offline-capable)"
    )
    ap.add_argument(
        "--dump-assets",
        action="store_true",
        help="一次性从浏览器导出 bundle+cookie（之后可无浏览器）",
    )
    ap.add_argument(
        "--confirm-local",
        action="store_true",
        help="确认走本地 tls-client 发包",
    )
    ap.add_argument("--goods_id", default=p1.GOODS_ID)
    ap.add_argument("--pdduid", default="")
    ap.add_argument("--tab_id", default=p1.TAB_ID)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--start_page", type=int, default=45)
    ap.add_argument("--size", type=int, default=10)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument(
        "--token-source",
        choices=["sdenv", "browser"],
        default="sdenv",
        help="默认 sdenv（无浏览器出票）；browser 仅调试",
    )
    ap.add_argument("--bundle-file", default=DEFAULT_BUNDLE)
    ap.add_argument("--cookie-file", default=DEFAULT_SESSION)
    ap.add_argument(
        "--offline",
        action="store_true",
        help="强制只用落盘资产；缺文件则失败（不回落浏览器）",
    )
    ap.add_argument("--skip-warm", action="store_true")
    ap.add_argument(
        "--token-only",
        action="store_true",
        help="只测 sdenv 出票（不发 reviews，零业务预算）",
    )
    ap.add_argument(
        "--empty-fuse",
        type=int,
        default=2,
        help="连续 data=[] 次数后熔断（账号软限常见表现）",
    )
    ap.add_argument(
        "--save-session-after",
        action="store_true",
        help="翻页结束后把更新后的 cookie 写回 --cookie-file",
    )
    args = ap.parse_args()

    if args.dump_assets:
        dump_assets(args.tab_id, args.bundle_file, args.cookie_file, args.goods_id)
        return

    if not args.confirm_local and not args.token_only:
        print("ABORT: 翻页需 --confirm-local；导出资产用 --dump-assets；仅出票用 --token-only")
        sys.exit(2)
    if args.interval < 3.0 and not args.token_only:
        print("ABORT: --interval 勿低于 3")
        sys.exit(2)

    # ── load assets (prefer disk) ──
    cookie = ""
    vat = ""
    pdduid = args.pdduid
    goods_id = args.goods_id
    bundle = ""

    if os.path.isfile(args.cookie_file):
        sess_obj = load_session(args.cookie_file)
        cookie = sess_obj["cookie"]
        vat = sess_obj.get("vat") or ""
        pdduid = pdduid or sess_obj.get("pdduid") or ""
        goods_id = goods_id or sess_obj.get("goods_id") or p1.GOODS_ID
        print(f"[prep] cookie-file {args.cookie_file} ({len(p1.cookie_dict(cookie))} keys)")
    elif args.offline:
        print(f"ABORT: --offline 但缺少 {args.cookie_file}（先 --dump-assets）")
        sys.exit(2)
    else:
        print("[prep] no cookie-file → 从浏览器拉取（建议随后 --dump-assets）")
        p1.TAB_ID = args.tab_id
        cookie = p1.get_cookie_str()
        vat = p1.get_vat()
        pdduid = pdduid or p1.cookie_dict(cookie).get("pdd_user_id") or p1.PDDUID

    if not pdduid:
        pdduid = p1.cookie_dict(cookie).get("pdd_user_id") or p1.PDDUID

    if args.token_source == "sdenv":
        if os.path.isfile(args.bundle_file):
            bundle = open(args.bundle_file, encoding="utf-8").read()
            print(f"[prep] bundle-file {args.bundle_file} ({len(bundle)} chars)")
        elif args.offline:
            print(f"ABORT: --offline 但缺少 {args.bundle_file}")
            sys.exit(2)
        else:
            print("[prep] no bundle-file → 现场 dump 一次")
            dump_assets(args.tab_id, args.bundle_file, args.cookie_file, goods_id)
            bundle = open(args.bundle_file, encoding="utf-8").read()
            sess_obj = load_session(args.cookie_file)
            cookie, vat = sess_obj["cookie"], sess_obj.get("vat") or ""
            pdduid = pdduid or sess_obj.get("pdduid") or pdduid

    p1.TAB_ID = args.tab_id
    p1.GOODS_ID = goods_id
    p1.PDDUID = pdduid
    print(f"  goods={goods_id} pdduid={pdduid} vat={bool(vat)} token={args.token_source}")

    if args.token_only:
        if args.token_source != "sdenv" or not bundle:
            print("ABORT: --token-only 需要 sdenv + bundle-file")
            sys.exit(2)
        t0 = time.time()
        ac = gen_token_sdenv(bundle, cookie, goods_id)
        print(f"[token-only] OK {ac[:16]}... len={len(ac)} gen={time.time()-t0:.2f}s (no browser)")
        sys.exit(0)

    if not args.confirm_local:
        print("ABORT: 翻页需 --confirm-local")
        sys.exit(2)

    sess = p1.TlsClientSession("chrome_150")
    try:
        if not args.skip_warm:
            cookie = warmup(sess, cookie, goods_id, pdduid)

        ok_cnt = fail_cnt = empty_streak = 0
        all_items: list[dict[str, Any]] = []
        for i in range(args.pages):
            page = args.start_page + i
            if i > 0:
                time.sleep(args.interval)

            print(f"[token] page={page} source={args.token_source} ...")
            t_tok = time.time()
            if args.token_source == "browser":
                if args.offline:
                    print("ABORT: --offline 不能用 browser 出票")
                    sys.exit(2)
                ac = gen_token_browser(args.tab_id)
            else:
                ac = gen_token_sdenv(bundle, cookie, goods_id)
            print(f"        {ac[:12]}... len={len(ac)} gen={time.time()-t_tok:.2f}s")

            t0 = time.time()
            cookie, data = fetch_page(
                sess, cookie, vat, ac, goods_id, pdduid, page, args.size
            )
            elapsed = time.time() - t0
            if data["n"] > 0 and not data["verify"] and data.get("error_code") in (None, 0):
                names = [it["name"] for it in data["items"][:3]]
                print(f"[page={page}] OK n={data['n']} {elapsed:.2f}s first={names}")
                all_items.extend(data["items"])
                ok_cnt += 1
                empty_streak = 0
            else:
                print(
                    f"[page={page}] FAIL {elapsed:.2f}s http={data['http']} "
                    f"error_code={data.get('error_code')} verify={data.get('verify')} "
                    f"n={data.get('n')} msg={data.get('msg')}"
                )
                fail_cnt += 1
                if data.get("error_code") == 54001 or data.get("verify"):
                    print("!! 风控熔断，停止翻页")
                    break
                if data.get("n") == 0 and data.get("http") == 200:
                    empty_streak += 1
                    if empty_streak >= args.empty_fuse:
                        print(
                            f"!! 连续 {empty_streak} 次 data=[]（账号软限/会话失效常见），熔断；"
                            "请换号或浏览器确认同页是否也空"
                        )
                        break
                else:
                    empty_streak = 0

        if args.save_session_after or os.path.isfile(args.cookie_file):
            save_session(args.cookie_file, cookie, vat, goods_id, pdduid)

        print(f"\n结果: {ok_cnt} 成功 / {fail_cnt} 失败, 累计 {len(all_items)} 条")
        if all_items:
            out = os.path.join(HERE, f"comments_local_{goods_id}_p{args.start_page}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=1)
            print(f"已保存: {out}")
        sys.exit(0 if fail_cnt == 0 else 1)
    finally:
        sess.close()


if __name__ == "__main__":
    main()
