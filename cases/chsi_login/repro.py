"""
CHSI (学信网/国家大学生就业服务平台) passport 登录协议复现
==========================================================
核心结论：密码为【明文】提交（仅 HTTPS 保护），无客户端加密。
window.doEncrypt/doDecrypt 仅为干扰项（声明未赋值，不参与提交路径）。

登录流程（标准 CAS）：
  1. GET  /passport/login?service=...   -> 服务端在表单里渲染 lt / execution / _eventId
  2. POST /passport/login?service=...   -> form-urlencoded:
        username, password(明文), tp=crpusr, lt, execution, _eventId=submit

注意：
  - lt / execution 每次会话不同，必须从登录页 HTML 解析。
  - JSESSIONID 通过 Set-Cookie 传递，无需拼到 URL。
  - 部分场景可能要求图形验证码（captchaChange-1.0.1.js 已加载），但基础表单无验证码字段；
    验证码通常在多次失败或风控触发后才出现。
"""
import re
import sys
import requests

LOGIN_URL = (
    "https://account.chsi.com.cn/passport/login"
    "?service=https%3A%2F%2Fjy.chsi.com.cn%2Fj_spring_cas_security_check"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_form(session: requests.Session):
    """GET 登录页，解析隐藏字段 lt / execution / _eventId。"""
    r = session.get(LOGIN_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    def _field(name):
        m = re.search(
            r'name=["\']%s["\'][^>]*?value=["\'](.*?)["\']' % re.escape(name), html
        )
        if not m:
            # 兼容 value 在前的情况
            m = re.search(
                r'value=["\'](.*?)["\'][^>]*?name=["\']%s["\']' % re.escape(name), html
            )
        return m.group(1) if m else None

    lt = _field("lt")
    execution = _field("execution")
    event_id = _field("_eventId") or "submit"
    return lt, execution, event_id, r.url


def login(session: requests.Session, username: str, password: str):
    """执行一次登录 POST，返回 (status_code, final_url, snippet)。"""
    lt, execution, event_id, _ = fetch_form(session)
    if not lt or not execution:
        raise RuntimeError(f"无法解析 lt/execution: lt={lt!r} execution={execution!r}")

    data = {
        "username": username,
        "password": password,
        "tp": "crpusr",
        "lt": lt,
        "execution": execution,
        "_eventId": event_id,
    }
    r = session.post(
        LOGIN_URL,
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": LOGIN_URL},
        timeout=30,
        allow_redirects=True,
    )
    snippet = re.sub(r"\s+", " ", r.text)[:300]
    return r.status_code, r.url, snippet, data


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "testuser_example"
    password = sys.argv[2] if len(sys.argv) > 2 else "FakePass123!"

    session = requests.Session()
    print(f"[*] GET 登录页并解析 lt/execution ...")
    lt, execution, event_id, url = fetch_form(session)
    print(f"    lt={lt}")
    print(f"    execution={execution[:48]}...  (len={len(execution) if execution else 0})")
    print(f"    _eventId={event_id}")

    print(f"[*] POST 登录 (账号={username}) ...")
    status, final_url, snippet, posted = login(session, username, password)
    print(f"    HTTP {status}")
    print(f"    final_url={final_url}")
    print(f"    body_snippet={snippet}")
    # 负向判定：错误凭证应被服务端当作合法登录处理（返回登录页+错误提示），
    # 而不是 400/缺参。这证明参数集正确。
    ok = status == 200 and ("登录" in snippet or "error" in snippet.lower()
                            or "密码" in snippet or "用户名" in snippet)
    print(f"[*] 协议复现(负向): {'PASS' if ok else 'CHECK'}")
    print(f"[*] 已发送字段: username, password(明文), tp, lt, execution, _eventId")


if __name__ == "__main__":
    main()
