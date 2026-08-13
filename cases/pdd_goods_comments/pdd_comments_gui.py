# -*- coding: utf-8 -*-
"""拼多多评论 — 多账号运维 GUI（customtkinter）。

编排层：账号档案 + 写 session_offline.json + 子进程调用 pdd_comments_local_tls.py。
不重写出票 / TLS。启动：python pdd_comments_gui.py
"""
from __future__ import annotations

import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk
from tkinter import messagebox

HERE = Path(__file__).resolve().parent
ACCOUNTS_DIR = HERE / "accounts"
SESSION_FILE = HERE / "session_offline.json"
BUNDLE_FILE = HERE / "webpack_45246_bundle.js"
CLI_SCRIPT = HERE / "pdd_comments_local_tls.py"
# 翻页间隔：前端不填，随机秒
INTERVAL_MIN = 13.0
INTERVAL_MAX = 45.0
DEFAULT_SIZE = 10
DEFAULT_EMPTY_FUSE = 2

STATUS_READY = "ready"
STATUS_ACTIVE = "active"
STATUS_HEATED = "heated"
STATUS_COOLDOWN = "cooldown"

PAGE_OK_RE = re.compile(r"\[page=(\d+)\]\s+OK\s+n=(\d+)")
PAGE_FAIL_RE = re.compile(
    r"\[page=(\d+)\]\s+FAIL.*?error_code=(\S+).*?verify=(\S+)", re.I
)
HEATED_RE = re.compile(r"风控熔断|error_code=54001", re.I)
EMPTY_FUSE_RE = re.compile(r"连续\s*\d+\s*次\s*data=\[\]")
SAVED_RE = re.compile(r"已保存:\s*(.+)")


# ── cookie / account IO ──────────────────────────────────────────────


def cookie_dict_from_str(cookie: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (cookie or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def cookie_str_from_dict(d: dict[str, Any]) -> str:
    return "; ".join(f"{k}={v}" for k, v in d.items() if v is not None and str(v) != "")


def parse_cookie_input(raw: str) -> dict[str, Any]:
    """Accept cookie string / session JSON / cookies dict / [{name,value}]."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Cookie 为空")

    cookie = ""
    vat = ""
    goods_id = ""
    note = ""

    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        if isinstance(data, list):
            cookie = "; ".join(
                f"{c['name']}={c['value']}"
                for c in data
                if isinstance(c, dict) and c.get("name") and c.get("value") is not None
            )
        elif isinstance(data, dict):
            if data.get("cookie"):
                cookie = str(data["cookie"])
            elif isinstance(data.get("cookies"), dict):
                cookie = cookie_str_from_dict(data["cookies"])
            elif all(isinstance(v, (str, int, float)) for v in data.values()):
                # flat name->value map
                cookie = cookie_str_from_dict(data)
            else:
                raise ValueError("JSON 需含 cookie / cookies / 或 [{name,value}]")
            vat = str(data.get("vat") or "")
            goods_id = str(data.get("goods_id") or "")
            note = str(data.get("note") or data.get("remark") or "")
        else:
            raise ValueError("不支持的 JSON 类型")
    else:
        cookie = text

    jar = cookie_dict_from_str(cookie)
    if not jar.get("PDDAccessToken"):
        raise ValueError("缺少 PDDAccessToken")
    uid = str(jar.get("pdd_user_id") or "").strip()
    if not uid:
        raise ValueError("缺少 pdd_user_id")

    return {
        "cookie": cookie_str_from_dict(jar),
        "cookies": jar,
        "vat": vat,
        "goods_id": goods_id,
        "pdduid": uid,
        "note": note,
    }


def ensure_accounts_dir() -> None:
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)


def account_path(uid: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", str(uid))
    return ACCOUNTS_DIR / f"{safe}.json"


def load_account(uid: str) -> Optional[dict[str, Any]]:
    path = account_path(uid)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_accounts() -> list[dict[str, Any]]:
    ensure_accounts_dir()
    items: list[dict[str, Any]] = []
    for path in sorted(ACCOUNTS_DIR.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict) and obj.get("pdduid"):
                items.append(obj)
        except Exception:
            continue
    # active first, then ready, then others
    order = {STATUS_ACTIVE: 0, STATUS_READY: 1, STATUS_COOLDOWN: 2, STATUS_HEATED: 3}
    items.sort(key=lambda a: (order.get(a.get("status"), 9), str(a.get("pdduid"))))
    return items


def save_account(obj: dict[str, Any]) -> Path:
    ensure_accounts_dir()
    uid = str(obj["pdduid"])
    obj = deepcopy(obj)
    obj["saved_at"] = int(time.time())
    path = account_path(uid)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def delete_account(uid: str) -> None:
    path = account_path(uid)
    if path.is_file():
        path.unlink()


def write_session_from_account(acc: dict[str, Any], goods_id: str = "") -> None:
    gid = goods_id or acc.get("goods_id") or ""
    payload = {
        "cookie": acc["cookie"],
        "cookies": acc.get("cookies") or cookie_dict_from_str(acc["cookie"]),
        "vat": acc.get("vat") or "",
        "goods_id": str(gid),
        "pdduid": str(acc["pdduid"]),
        "saved_at": int(time.time()),
    }
    with SESSION_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def set_active_account(uid: str, goods_id: str = "") -> dict[str, Any]:
    target = None
    for acc in list_accounts():
        if str(acc.get("pdduid")) == str(uid):
            target = acc
            break
    if not target:
        raise ValueError(f"账号不存在: {uid}")
    if target.get("status") == STATUS_HEATED:
        raise ValueError("该账号已加热(54001)，请换号或手动恢复")

    for acc in list_accounts():
        st = acc.get("status")
        if str(acc.get("pdduid")) == str(uid):
            acc["status"] = STATUS_ACTIVE
            if goods_id:
                acc["goods_id"] = goods_id
            save_account(acc)
            target = acc
        elif st == STATUS_ACTIVE:
            acc["status"] = STATUS_READY
            save_account(acc)

    write_session_from_account(target, goods_id=goods_id or target.get("goods_id") or "")
    return target


def mark_account_status(uid: str, status: str) -> None:
    acc = load_account(uid)
    if not acc:
        return
    acc["status"] = status
    if status == STATUS_HEATED:
        acc["heated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif status in (STATUS_READY, STATUS_ACTIVE):
        acc.pop("heated_at", None)
    save_account(acc)


def upsert_account_from_parsed(
    parsed: dict[str, Any], note: str = "", activate: bool = False, goods_id: str = ""
) -> dict[str, Any]:
    uid = parsed["pdduid"]
    existing = load_account(uid) or {}
    acc = {
        "pdduid": uid,
        "cookie": parsed["cookie"],
        "cookies": parsed["cookies"],
        "vat": parsed.get("vat") or existing.get("vat") or "",
        "goods_id": goods_id or parsed.get("goods_id") or existing.get("goods_id") or "",
        "note": (note or parsed.get("note") or existing.get("note") or "").strip(),
        "status": existing.get("status") or STATUS_READY,
        "heated_at": existing.get("heated_at"),
    }
    if acc["status"] == STATUS_HEATED and not activate:
        pass
    elif activate:
        acc["status"] = STATUS_READY  # set_active will promote
    save_account(acc)
    if activate:
        return set_active_account(uid, goods_id=acc["goods_id"])
    return acc


def migrate_session_if_needed() -> None:
    ensure_accounts_dir()
    if list_accounts():
        return
    if not SESSION_FILE.is_file():
        return
    try:
        with SESSION_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        parsed = parse_cookie_input(json.dumps(data, ensure_ascii=False))
        upsert_account_from_parsed(
            parsed,
            note="从 session_offline 导入",
            activate=True,
            goods_id=str(data.get("goods_id") or ""),
        )
    except Exception:
        pass


def backend_ok(timeout: float = 2.5) -> tuple[bool, str]:
    """兼容旧名：改为检查本地 sdenv（Node + runner），不再探活 27183。"""
    try:
        import pdd_comments_local_tls as tls

        return tls.check_sdenv_local()
    except Exception as e:
        return False, str(e)


def next_ready_account(exclude_uid: str = "") -> Optional[dict[str, Any]]:
    for acc in list_accounts():
        if str(acc.get("pdduid")) == str(exclude_uid):
            continue
        if acc.get("status") == STATUS_READY:
            return acc
    return None


# ── crawl worker ─────────────────────────────────────────────────────


class CrawlResult:
    def __init__(self) -> None:
        self.ok_pages: list[int] = []
        self.fail_page: Optional[int] = None
        self.heated: bool = False
        self.empty_fuse: bool = False
        self.exit_code: int = -1
        self.saved_path: str = ""
        self.last_ok_page: Optional[int] = None


def parse_crawl_line(line: str, result: CrawlResult) -> None:
    m = PAGE_OK_RE.search(line)
    if m:
        page = int(m.group(1))
        result.ok_pages.append(page)
        result.last_ok_page = page
        return
    m = PAGE_FAIL_RE.search(line)
    if m:
        page = int(m.group(1))
        result.fail_page = page
        err = m.group(2)
        verify = m.group(3)
        if "54001" in err or verify.lower() in ("true", "1"):
            result.heated = True
        return
    if HEATED_RE.search(line):
        result.heated = True
    if EMPTY_FUSE_RE.search(line):
        result.empty_fuse = True
    m = SAVED_RE.search(line)
    if m:
        result.saved_path = m.group(1).strip()


def run_cli_once(
    *,
    goods_id: str,
    pdduid: str,
    start_page: int,
    pages: int,
    size: int,
    interval: float,
    empty_fuse: int,
    log: Callable[[str], None],
    stop_event: threading.Event,
) -> CrawlResult:
    result = CrawlResult()
    cmd = [
        sys.executable,
        "-u",
        str(CLI_SCRIPT),
        "--confirm-local",
        "--offline",
        "--goods_id",
        str(goods_id),
        "--pdduid",
        str(pdduid),
        "--start_page",
        str(start_page),
        "--pages",
        str(pages),
        "--size",
        str(size),
        "--interval",
        str(interval),
        "--empty-fuse",
        str(empty_fuse),
        "--cookie-file",
        str(SESSION_FILE),
        "--bundle-file",
        str(BUNDLE_FILE),
        "--token-source",
        "sdenv",
    ]
    log("$ " + " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
    except Exception as e:
        log(f"[gui] 启动 CLI 失败: {e}")
        result.exit_code = 127
        return result

    assert proc.stdout is not None
    while True:
        if stop_event.is_set():
            try:
                proc.terminate()
            except Exception:
                pass
            log("[gui] 用户停止，已 terminate 子进程")
            break
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            line = line.rstrip("\n")
            log(line)
            parse_crawl_line(line, result)

    result.exit_code = proc.wait() if proc.poll() is None else proc.returncode
    log(f"[gui] 子进程结束 code={result.exit_code}")
    return result


# ── GUI ──────────────────────────────────────────────────────────────


class PddCommentsGui(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("PDD 评论本地爬取 · 多账号")
        self.geometry("1100x720")
        self.minsize(960, 640)

        self._log_q: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._selected_uid = ""

        migrate_session_if_needed()
        self._build()
        self.refresh_accounts()
        self.refresh_backend()
        self.after(200, self._drain_log)
        self.after(5000, self._poll_backend)

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, width=280)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_propagate(False)
        left.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(left, text="账号", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 2)
        )
        self.backend_label = ctk.CTkLabel(
            left,
            text="出票服务 …",
            text_color="gray70",
            wraplength=250,
            justify="left",
            anchor="w",
        )
        self.backend_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        self.acc_list = ctk.CTkScrollableFrame(left)
        self.acc_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=8, pady=(8, 12))
        ctk.CTkButton(btn_row, text="选用", width=80, command=self.activate_selected).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            btn_row, text="恢复", width=80, command=lambda: self._mark_sel(STATUS_READY)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_row,
            text="删除",
            width=80,
            fg_color="#8B3A3A",
            hover_color="#6E2E2E",
            command=self.delete_selected,
        ).pack(side="left", padx=2)

        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        # import
        imp = ctk.CTkFrame(right)
        imp.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        imp.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(imp, text="粘贴 Cookie（字符串或 JSON）→ 保存并激活", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 2)
        )
        self.cookie_box = ctk.CTkTextbox(imp, height=88)
        self.cookie_box.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        note_row = ctk.CTkFrame(imp, fg_color="transparent")
        note_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.note_entry = ctk.CTkEntry(note_row, width=160, placeholder_text="备注（可选）")
        self.note_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            note_row, text="保存并激活", width=120, command=lambda: self.save_cookie(True)
        ).pack(side="left")

        # task — 间隔不暴露，随机 13–45s
        task = ctk.CTkFrame(right)
        task.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        for i in range(3):
            task.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(task, text="goods_id").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 0))
        self.goods_entry = ctk.CTkEntry(task, placeholder_text="商品 ID")
        self.goods_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        ctk.CTkLabel(task, text="起始页").grid(row=0, column=1, sticky="w", padx=8, pady=(8, 0))
        self.start_entry = ctk.CTkEntry(task)
        self.start_entry.insert(0, "1")
        self.start_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        ctk.CTkLabel(task, text="页数").grid(row=0, column=2, sticky="w", padx=8, pady=(8, 0))
        self.pages_entry = ctk.CTkEntry(task)
        self.pages_entry.insert(0, "5")
        self.pages_entry.grid(row=1, column=2, sticky="ew", padx=8, pady=4)

        opts = ctk.CTkFrame(task, fg_color="transparent")
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=(2, 4))
        self.auto_switch = ctk.CTkCheckBox(opts, text="54001 自动换号")
        self.auto_switch.pack(side="left")
        self.until_empty = ctk.CTkCheckBox(opts, text="翻到没数据为止")
        self.until_empty.pack(side="left", padx=16)
        ctk.CTkLabel(
            opts,
            text=f"翻页间隔随机 {int(INTERVAL_MIN)}–{int(INTERVAL_MAX)} 秒",
            text_color="gray60",
        ).pack(side="left", padx=8)

        act = ctk.CTkFrame(right, fg_color="transparent")
        act.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        self.start_btn = ctk.CTkButton(
            act, text="开始", width=100, command=self.start_crawl, height=36
        )
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ctk.CTkButton(
            act,
            text="停止",
            width=80,
            fg_color="#8B3A3A",
            hover_color="#6E2E2E",
            command=self.stop_crawl,
            state="disabled",
            height=36,
        )
        self.stop_btn.pack(side="left", padx=4)
        self.status_label = ctk.CTkLabel(act, text="就绪", anchor="w")
        self.status_label.pack(side="left", padx=12)

        logf = ctk.CTkFrame(right)
        logf.grid(row=3, column=0, sticky="nsew", padx=10, pady=(6, 10))
        logf.grid_columnconfigure(0, weight=1)
        logf.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(logf, text="日志", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 2)
        )
        self.log_box = ctk.CTkTextbox(logf, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        if SESSION_FILE.is_file():
            try:
                with SESSION_FILE.open(encoding="utf-8") as f:
                    sess = json.load(f)
                gid = str(sess.get("goods_id") or "")
                if gid:
                    self.goods_entry.delete(0, "end")
                    self.goods_entry.insert(0, gid)
            except Exception:
                pass

    # ── UI helpers ──

    def log(self, msg: str) -> None:
        self._log_q.put(msg)

    def _drain_log(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
        except queue.Empty:
            pass
        self.after(200, self._drain_log)

    def clear_log(self) -> None:
        self.log_box.delete("1.0", "end")

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def refresh_backend(self) -> None:
        ok, detail = backend_ok()
        if ok:
            self.backend_label.configure(
                text="出票(sdenv) ✓ 本地 Node\n无需 27183 后端",
                text_color="#6BCB77",
            )
        else:
            self.backend_label.configure(
                text="出票(sdenv) ✗\n需 Node + server/sdenv_runner.js",
                text_color="#E35D5D",
            )
            self.log(f"[gui] 本地 sdenv 不可用: {detail}")
        self._update_start_enabled()

    def _poll_backend(self) -> None:
        if not self._running:
            ok, _ = backend_ok()
            if ok:
                self.backend_label.configure(
                    text="出票(sdenv) ✓ 本地 Node\n无需 27183 后端",
                    text_color="#6BCB77",
                )
            else:
                self.backend_label.configure(
                    text="出票(sdenv) ✗\n需 Node + server/sdenv_runner.js",
                    text_color="#E35D5D",
                )
            self._update_start_enabled()
        self.after(5000, self._poll_backend)

    def _update_start_enabled(self) -> None:
        if self._running:
            self.start_btn.configure(state="disabled")
            return
        ok, _ = backend_ok()
        if not ok or not BUNDLE_FILE.is_file():
            self.start_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal")

    def refresh_accounts(self) -> None:
        for w in self.acc_list.winfo_children():
            w.destroy()
        accounts = list_accounts()
        if not accounts:
            ctk.CTkLabel(self.acc_list, text="暂无账号，请上方导入 Cookie").pack(
                anchor="w", padx=6, pady=8
            )
            return
        for acc in accounts:
            uid = str(acc.get("pdduid"))
            st = acc.get("status") or STATUS_READY
            note = acc.get("note") or ""
            heated = acc.get("heated_at") or ""
            title = note or f"…{uid[-6:]}"
            color = {
                STATUS_ACTIVE: "#3B82F6",
                STATUS_READY: "#6BCB77",
                STATUS_HEATED: "#E35D5D",
                STATUS_COOLDOWN: "#E5A84B",
            }.get(st, "gray70")
            line = f"[{st}] {title}\n{uid}"
            if heated:
                line += f"\nheated {heated}"
            btn = ctk.CTkButton(
                self.acc_list,
                text=line,
                anchor="w",
                fg_color=("gray25", "gray25"),
                hover_color=("gray30", "gray30"),
                border_width=2 if uid == self._selected_uid or st == STATUS_ACTIVE else 0,
                border_color=color,
                text_color=color,
                command=lambda u=uid: self._select_account(u),
                height=54,
            )
            btn.pack(fill="x", padx=4, pady=3)

    def _select_account(self, uid: str) -> None:
        self._selected_uid = uid
        acc = load_account(uid)
        if acc and acc.get("goods_id") and not self.goods_entry.get().strip():
            self.goods_entry.delete(0, "end")
            self.goods_entry.insert(0, str(acc["goods_id"]))
        self.refresh_accounts()

    def activate_selected(self) -> None:
        if not self._selected_uid:
            messagebox.showwarning("提示", "先点选左侧账号")
            return
        try:
            set_active_account(self._selected_uid, goods_id=self.goods_entry.get().strip())
            self.log(f"[gui] 已激活 {self._selected_uid} → session_offline.json")
            self.refresh_accounts()
        except Exception as e:
            messagebox.showerror("激活失败", str(e))

    def delete_selected(self) -> None:
        if not self._selected_uid:
            return
        if not messagebox.askyesno("确认", f"删除账号 {self._selected_uid}？"):
            return
        delete_account(self._selected_uid)
        self._selected_uid = ""
        self.refresh_accounts()
        self.log("[gui] 已删除账号")

    def _mark_sel(self, status: str) -> None:
        if not self._selected_uid:
            messagebox.showwarning("提示", "先点选左侧账号")
            return
        mark_account_status(self._selected_uid, status)
        # if demoting active, keep session as-is but status changes
        if status == STATUS_READY:
            # if was only heated recovery
            pass
        self.refresh_accounts()
        self.log(f"[gui] {self._selected_uid} → {status}")

    def save_cookie(self, activate: bool = False) -> None:
        raw = self.cookie_box.get("1.0", "end").strip()
        note = self.note_entry.get().strip()
        goods = self.goods_entry.get().strip()
        try:
            parsed = parse_cookie_input(raw)
            acc = upsert_account_from_parsed(
                parsed, note=note, activate=activate, goods_id=goods
            )
            self._selected_uid = str(acc["pdduid"])
            if not goods and acc.get("goods_id"):
                self.goods_entry.delete(0, "end")
                self.goods_entry.insert(0, str(acc["goods_id"]))
            self.refresh_accounts()
            self.cookie_box.delete("1.0", "end")
            msg = "保存并激活" if activate else "已保存"
            self.log(f"[gui] {msg} uid={acc['pdduid']}")
            messagebox.showinfo("OK", f"{msg}\nuid={acc['pdduid']}")
        except Exception as e:
            messagebox.showerror("Cookie 无效", str(e))

    # ── crawl control ──

    def stop_crawl(self) -> None:
        self._stop.set()
        self.set_status("正在停止…")

    def start_crawl(self) -> None:
        if self._running:
            return
        ok, detail = backend_ok()
        if not ok:
            messagebox.showerror(
                "本地 sdenv 不可用",
                "出票改为直调 Node + server/sdenv_runner.js，不再依赖 27183。\n\n"
                f"{detail}\n\n请确认已安装 Node.js，且仓库含 server/sdenv_runner.js / sdenv-main。",
            )
            self.refresh_backend()
            return
        if not BUNDLE_FILE.is_file():
            messagebox.showerror(
                "缺少 bundle",
                f"未找到 {BUNDLE_FILE.name}\n请先 CLI: python pdd_comments_local_tls.py --dump-assets",
            )
            return
        if not CLI_SCRIPT.is_file():
            messagebox.showerror("缺少脚本", str(CLI_SCRIPT))
            return

        goods = self.goods_entry.get().strip()
        if not goods:
            messagebox.showwarning("提示", "请填写 goods_id")
            return
        try:
            start_page = int(self.start_entry.get().strip())
            pages = int(self.pages_entry.get().strip())
        except ValueError:
            messagebox.showerror("参数错误", "起始页 / 页数须为数字")
            return
        if start_page < 1 or pages < 1:
            messagebox.showerror("参数错误", "起始页 / 页数须 ≥ 1")
            return

        active = next((a for a in list_accounts() if a.get("status") == STATUS_ACTIVE), None)
        if not active:
            if self._selected_uid:
                try:
                    active = set_active_account(self._selected_uid, goods_id=goods)
                except Exception as e:
                    messagebox.showerror("无可用账号", str(e))
                    return
            else:
                ready = next_ready_account()
                if not ready:
                    messagebox.showerror("无可用账号", "请先导入并激活一个 ready 账号")
                    return
                try:
                    active = set_active_account(str(ready["pdduid"]), goods_id=goods)
                except Exception as e:
                    messagebox.showerror("无可用账号", str(e))
                    return
        else:
            write_session_from_account(active, goods_id=goods)
            active["goods_id"] = goods
            save_account(active)

        self._stop.clear()
        self._running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.set_status("爬取中…")
        self.refresh_accounts()

        auto_sw = bool(self.auto_switch.get())
        until_empty = bool(self.until_empty.get())

        def worker() -> None:
            try:
                self._crawl_loop(
                    goods_id=goods,
                    start_page=start_page,
                    pages=pages,
                    auto_switch=auto_sw,
                    until_empty=until_empty,
                    first_uid=str(active["pdduid"]),
                )
            finally:
                self.after(0, self._on_crawl_done)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _on_crawl_done(self) -> None:
        self._running = False
        self.stop_btn.configure(state="disabled")
        self._update_start_enabled()
        self.set_status("完成")
        self.refresh_accounts()

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep; return False if stop requested."""
        end = time.time() + seconds
        while time.time() < end:
            if self._stop.is_set():
                return False
            time.sleep(min(0.4, end - time.time()))
        return not self._stop.is_set()

    def _crawl_loop(
        self,
        *,
        goods_id: str,
        start_page: int,
        pages: int,
        auto_switch: bool,
        until_empty: bool,
        first_uid: str,
    ) -> None:
        """逐页调用 CLI；页间随机等待 13–45 秒。"""
        cur_uid = first_uid
        page_cursor = start_page
        end_page = start_page + pages - 1
        total_ok = 0
        first_batch = True

        while not self._stop.is_set():
            if not until_empty and page_cursor > end_page:
                break

            if not first_batch:
                wait = random.uniform(INTERVAL_MIN, INTERVAL_MAX)
                self.log(f"[gui] 随机等待 {wait:.1f}s 后再翻下一页…")
                self.after(0, lambda w=wait: self.set_status(f"等待 {w:.0f}s…"))
                if not self._sleep_interruptible(wait):
                    break
            first_batch = False

            self.after(0, lambda: self.set_status(f"爬取 page={page_cursor}"))
            self.log(f"[gui] 账号={cur_uid} goods={goods_id} page={page_cursor}")
            result = run_cli_once(
                goods_id=goods_id,
                pdduid=cur_uid,
                start_page=page_cursor,
                pages=1,
                size=DEFAULT_SIZE,
                interval=INTERVAL_MIN,  # pages=1 时 CLI 内部无间隔
                empty_fuse=DEFAULT_EMPTY_FUSE,
                log=self.log,
                stop_event=self._stop,
            )
            total_ok += len(result.ok_pages)

            if self._stop.is_set():
                break

            if result.heated:
                mark_account_status(cur_uid, STATUS_HEATED)
                self.log(f"[gui] 账号 {cur_uid} 标记 heated (54001)")
                fail_at = result.fail_page or page_cursor
                if not auto_switch:
                    self.log("[gui] 未勾选自动换号 → 停止")
                    break
                nxt = next_ready_account(exclude_uid=cur_uid)
                if not nxt:
                    self.log("[gui] 无更多 ready 账号 → 停止")
                    break
                try:
                    set_active_account(str(nxt["pdduid"]), goods_id=goods_id)
                except Exception as e:
                    self.log(f"[gui] 换号失败: {e}")
                    break
                cur_uid = str(nxt["pdduid"])
                page_cursor = fail_at
                self.log(f"[gui] 换号 → {cur_uid}，从 page={page_cursor} 续爬")
                self.after(0, self.refresh_accounts)
                first_batch = True  # 换号后立刻打，不再额外干等一轮
                continue

            if result.empty_fuse or not result.ok_pages:
                self.log("[gui] 本页无数据 / 空列表熔断，结束")
                break

            page_cursor = (result.last_ok_page or page_cursor) + 1

        self.log(f"[gui] 任务结束，成功页累计 {total_ok}")


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ensure_accounts_dir()
    app = PddCommentsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
