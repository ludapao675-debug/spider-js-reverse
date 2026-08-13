import json
import requests
import sys

def run_qidian_sdenv_simulation(target_url: str = "https://www.qidian.com/chapter/1046978342/869269049/"):
    """
    使用项目的 sdenv (sdenv-main 引擎) 进行起点中文网离线沙箱补环境与探针校验测试
    """
    backend_url = "http://127.0.0.1:27183/api/sdenv/verify-code"
    
    # 模拟起点 WAF 探针 probe.js 与环境探针逻辑
    js_code = """
    window.buid = "12274899057122305281";
    document.title = "1.狐妖月见 _《太尊！》小说在线阅读 - 起点中文网";
    
    // 模拟起点 WAF 探针生成的校验 Cookie
    document.cookie = "x-waf-captcha-referer=" + encodeURIComponent(location.href) + "; path=/";
    
    var envSnapshot = {
        ua: navigator.userAgent,
        platform: navigator.platform,
        language: navigator.language,
        cookie: document.cookie,
        buid: window.buid,
        screen_width: window.screen ? window.screen.width : 0,
        screen_height: window.screen ? window.screen.height : 0
    };
    
    window.sdenv_output = JSON.stringify(envSnapshot);
    """
    
    payload = {
        "js_code": js_code,
        "url": target_url,
        "eval_expression": "window.sdenv_output",
        "super_env": True,
        "auto_fix": True
    }
    
    print(f"[sdenv] 开始请求起点沙箱模拟测试...")
    try:
        resp = requests.post(backend_url, json=payload, timeout=30)
        data = resp.json()
        
        if data.get("ok"):
            print("\n[sdenv-main 沙箱补环境通过！]")
            print(f"执行引擎: {data.get('runner_mode')}")
            print(f"用时: {data['rounds'][0]['execution_time']}s")
            print("\nsdenv 捕获到的离线 BOM/DOM 环境快照:")
            output_json = json.loads(data.get("output_value", "{}"))
            print(json.dumps(output_json, ensure_ascii=False, indent=2))
            return True
        else:
            print(f"[sdenv] 运行失败: {data.get('error') or data.get('message')}")
            return False
            
    except Exception as e:
        print(f"[sdenv] 请求发生异常: {e}")
        return False

if __name__ == "__main__":
    success = run_qidian_sdenv_simulation()
    sys.exit(0 if success else 1)
