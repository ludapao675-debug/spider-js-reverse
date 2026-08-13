/**
 * 京东 JCAP 纯 Node.js 离线 WASM + WASM Instance 导出例程深度追踪探针
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { createCanvas } = require('canvas');
const axios = require('axios');

const LOG_FILE = path.join(__dirname, 'repro_node_output.log');
fs.writeFileSync(LOG_FILE, `[START WASM MEMORY HOOK] ${new Date().toISOString()}\n`);

function log(msg) {
    const str = `[${new Date().toISOString().substring(11, 19)}] ${typeof msg === 'object' ? JSON.stringify(msg) : msg}\n`;
    fs.appendFileSync(LOG_FILE, str);
    console.log(msg);
}

function getSavedCookies() {
    try {
        const jsonPath = path.join(__dirname, 'jd_cookies.json');
        if (fs.existsSync(jsonPath)) {
            const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
            return data.cookie_header || "";
        }
    } catch(e) {}
    return "";
}

async function main() {
    const cookieHeader = getSavedCookies();
    const reqHeaders = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
        "Referer": "https://mygiftcard.jd.com/giftcard/myGiftCardInit.action",
        "Origin": "https://mygiftcard.jd.com"
    };
    if (cookieHeader) reqHeaders["Cookie"] = cookieHeader;

    let activeSi = "";
    try {
        const sidResp = await axios.post("https://mygiftcard.jd.com/giftcard/querySid/pc", "", { headers: reqHeaders, timeout: 5000 });
        if (sidResp.data && sidResp.data.code === "success" && sidResp.data.data) {
            activeSi = sidResp.data.data;
            log(`[✓] 动态获取 sid: ${activeSi.substring(0, 30)}...`);
        }
    } catch(e) {}

    const dom = new JSDOM(`<!DOCTYPE html><html><body><div id="captcha"></div></body></html>`, {
        url: "https://mygiftcard.jd.com/giftcard/myGiftCardInit.action",
        referrer: "https://mygiftcard.jd.com/",
        contentType: "text/html",
        runScripts: "dangerously"
    });

    const window = dom.window;
    global.window = window;
    global.document = window.document;
    global.navigator = window.navigator;
    global.location = window.location;
    global.HTMLElement = window.HTMLElement;
    global.Image = window.Image;
    global.WebAssembly = WebAssembly;
    window.WebAssembly = WebAssembly;

    // Hook WebAssembly.instantiate 取到 wasm 实例导出的函数
    const origInstantiate = WebAssembly.instantiate;
    let wasmInstance = null;

    const hookInstantiate = function(buffer, importObject) {
        log("[WASM HOOK] 触发 WebAssembly.instantiate");
        return origInstantiate.call(this, buffer, importObject).then(res => {
            wasmInstance = res.instance || res;
            log(`[WASM HOOK] 成功捕获 Instance! 导出清单: ${Object.keys(wasmInstance.exports).join(', ')}`);
            for (const name in wasmInstance.exports) {
                const origExport = wasmInstance.exports[name];
                if (typeof origExport === 'function') {
                    wasmInstance.exports[name] = function(...args) {
                        const ret = origExport.apply(this, args);
                        log(`  [WASM EXPORT CALL] ${name}(${args.join(', ')}) => ${ret}`);
                        return ret;
                    };
                }
            }
            return res;
        });
    };

    WebAssembly.instantiate = hookInstantiate;
    window.WebAssembly.instantiate = hookInstantiate;

    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', writable: false });
    Object.defineProperty(window.navigator, 'deviceMemory', { value: 8, writable: false });
    Object.defineProperty(window.navigator, 'hardwareConcurrency', { value: 12, writable: false });
    Object.defineProperty(window.navigator, 'vendor', { value: 'Google Inc.', writable: false });
    Object.defineProperty(window.navigator, 'userAgent', { value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0", writable: false });

    window.chrome = { runtime: {}, app: {} };
    window.screen = { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040, colorDepth: 24, pixelDepth: 24, availLeft: 0, availTop: 0 };
    window.outerWidth = 1920; window.outerHeight = 1040; window.innerWidth = 1920; window.innerHeight = 937; window.devicePixelRatio = 1.25;

    const wasmBuffer = fs.readFileSync(path.join(__dirname, 'jcap_fp.wasm'));

    window.fetch = async function(url, opts) {
        const urlStr = String(url);
        if (urlStr.includes('.wasm') || (urlStr.includes('jcap') && urlStr.includes('fp'))) {
            return {
                ok: true, status: 200,
                arrayBuffer: async () => wasmBuffer.buffer.slice(wasmBuffer.byteOffset, wasmBuffer.byteOffset + wasmBuffer.byteLength),
                json: async () => ({}), text: async () => ""
            };
        }
        return { ok: true, status: 200, json: async () => ({}) };
    };

    const sdkPath = path.join(__dirname, 'jcap_ujb96b.js');
    const sdkCode = fs.readFileSync(sdkPath, 'utf8');
    window.eval(sdkCode);

    const options = { id: "captcha", sessionId: activeSi, language: 1, platformOS: "pc" };
    const fn1 = window.jdCAP.captcha(options);
    const promise = fn1(options);

    promise.then(inst => {
        log("[✓] JCAP SDK 实例就绪");
        if (inst && typeof inst.create === 'function') {
            log("[!] 调用 inst.create()...");
            inst.create();
        }
    }).catch(e => log(`[!] 报错: ${e.message}`));

    setTimeout(() => process.exit(0), 3000);
}

main();
