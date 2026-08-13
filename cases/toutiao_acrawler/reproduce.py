# -*- coding: utf-8 -*-
"""reproduce.py — 今日头条 PC 端 _signature 协议复现客户端（路径B固化版）

把已验证的端到端能力固化为标准可复用客户端：
  1) 调用 node replay_real.js 在本地 Node vm 沙箱离线计算 _signature（路径B）
  2) 将签名拼到目标接口 URL 的 _signature 参数
  3) 发送 HTTP GET 请求，拉取真实返回数据

说明：
  - 本地签名走 acrawler 降级分支产出 47 字符短签名；结合 verify_result.json，
    今日头条 PC 端对 _signature 弱校验（serverEnforcesSignature=false），
    短签名已被所有接口接受，可正常拉到数据。
  - 用法：
      python reproduce.py                              # 跑预设接口（feed / hot_board / tab_comments）
      python reproduce.py --url "https://..."          # 复现指定接口
      python reproduce.py --group-id <id> --item-id <id>   # 复现 tab_comments（指定文章）
"""
import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_OUT = os.path.join(HERE, "replay_real_out.json")        # replay_real.js 的中间产物
RESULT_OUT = os.path.join(HERE, "reproduce_result.json")     # 本脚本的结果落盘

# 真机采集 UA（mcp_golden_evidence.json），Referer 指向 toutiao 首页
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
REFERER = "https://www.toutiao.com/"


def gen_signature(url, node_timeout=120):
    """调用本地 Node 沙箱计算 _signature，返回签名字符串。

    复用 replay_real.js（Node vm + 浏览器垫片加载 raw/acrawler.js），
    签名结果写入 NODE_OUT 后由本函数读取。
    """
    try:
        subprocess.run(
            ["node", "replay_real.js", url],
            cwd=HERE, check=True, timeout=node_timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError("replay_real.js 执行失败: %s" % e)
    except subprocess.TimeoutExpired:
        raise RuntimeError("replay_real.js 超时(%ds)" % node_timeout)
    with open(NODE_OUT, encoding="utf-8") as f:
        return json.load(f)["signature"]


def fetch_signed(url, sig):
    """带 _signature 发请求，返回 (http_status, body_str)。

    sig 为空时不附加签名参数（用于接口宽松、可无签名访问的场景，例如取 feed id）。
    """
    full = url
    if sig:
        sep = "&" if "?" in url else "?"
        full = url + sep + "_signature=" + urllib.parse.quote(sig, safe="")
    req = urllib.request.Request(full, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": REFERER,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # 网络错误等
        return None, "ERR: %s" % e


def summarize(body):
    """把返回 body 解析为简要摘要。"""
    try:
        j = json.loads(body)
    except Exception:
        return {"http": "PARSE_FAIL", "preview": body[:80]}
    if isinstance(j, dict):
        data = j.get("data")
        cnt = len(data) if isinstance(data, list) else (1 if data else 0)
        return {"status": j.get("status"), "message": j.get("message"),
                "data_count": cnt}
    return {"type": type(j).__name__}


def run_interface(name, url):
    """对单个接口执行「算签名 → 发请求 → 汇总」，返回结果行。"""
    sig = gen_signature(url)
    http, body = fetch_signed(url, sig)
    info = summarize(body)
    row = {"interface": name, "url": url, "signature": sig,
           "sig_len": len(sig), "http": http, "result": info}
    print("[%s] http=%s sig_len=%d -> %s" %
          (name, http, len(sig), json.dumps(info, ensure_ascii=False)))
    return row


def build_comments_url(group_id, item_id=None):
    iid = item_id or group_id
    return ("https://www.toutiao.com/article/v4/tab_comments/"
            "?aid=24&app_name=news_article&group_id=%s"
            "&item_id=%s&offset=0&count=20" % (group_id, iid))


def main():
    args = sys.argv[1:]
    url_arg = group_id = item_id = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--url" and i + 1 < len(args):
            url_arg = args[i + 1]; i += 2; continue
        if a == "--group-id" and i + 1 < len(args):
            group_id = args[i + 1]; i += 2; continue
        if a == "--item-id" and i + 1 < len(args):
            item_id = args[i + 1]; i += 2; continue
        i += 1

    report = {"generated_at": datetime.now().isoformat(), "interfaces": []}

    if url_arg:
        # 指定单接口复现
        report["interfaces"].append(run_interface("custom", url_arg))
    else:
        # 预设接口：feed + hot_board
        feed_url = ("https://www.toutiao.com/api/pc/feed/"
                    "?category=news_hot&utm_source=toutiao&widen=1"
                    "&max_behot_time=0&max_behot_time_tmp=0&tadrequire=true")
        report["interfaces"].append(run_interface("feed", feed_url))
        report["interfaces"].append(run_interface(
            "hot_board",
            "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"))

        # 从 feed 返回取首个真实文章 id，自动复现 tab_comments（接口宽松，可无签名访问）
        _, fb = fetch_signed(feed_url, "")
        try:
            fj = json.loads(fb)
            d0 = (fj.get("data") or [None])[0]
            if d0:
                gid = d0.get("group_id") or d0.get("GroupId")
                iid = d0.get("item_id") or d0.get("ItemId") or gid
                if gid:
                    report["interfaces"].append(
                        run_interface("tab_comments(自动id)",
                                      build_comments_url(gid, iid)))
        except Exception as e:
            print("[warn] 取 tab_comments id 失败: %s" % e)

    # 显式指定文章 id 复现 tab_comments
    if group_id:
        report["interfaces"].append(
            run_interface("tab_comments(指定id)",
                          build_comments_url(group_id, item_id)))

    with open(RESULT_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n结果已落盘: %s" % RESULT_OUT)


if __name__ == "__main__":
    main()
