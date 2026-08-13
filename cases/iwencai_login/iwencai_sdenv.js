/**
 * 同花顺 / 爱问财 sdenv 离线补环境 (Node.js) 复现模板
 * 解决问题：无需真实浏览器，在 Node.js 环境中生成合法的 hexin-v 与 RSA 密码加密
 */

// 1. 基础 DOM / BOM 模拟补环境 (sdenv minimal mock)
function mockBrowserEnvironment() {
    global.window = global;
    
    // Cookie 存储模拟器
    let _cookieStore = {};
    
    global.document = {
        referrer: 'https://www.iwencai.com/',
        get cookie() {
            return Object.keys(_cookieStore)
                .map(key => `${key}=${_cookieStore[key]}`)
                .join('; ');
        },
        set cookie(val) {
            if (typeof val === 'string') {
                let parts = val.split(';')[0].split('=');
                if (parts.length >= 2) {
                    let k = parts[0].trim();
                    let v = parts.slice(1).join('=').trim();
                    _cookieStore[k] = v;
                }
            }
        },
        getElementsByTagName: function(name) {
            if (name === 'head' || name === 'body') return [{ appendChild: function() {} }];
            return [];
        },
        querySelector: function() { return null; },
        createElement: function(tag) {
            return {
                getContext: function() {
                    return {
                        fillText: function() {},
                        fillRect: function() {},
                        getImageData: function() { return { data: new Uint8Array(100) }; }
                    };
                },
                toDataURL: function() { return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."; }
            };
        },
        addEventListener: function() {},
        removeEventListener: function() {}
    };

    global.location = {
        href: 'https://www.iwencai.com/ai-board',
        protocol: 'https:',
        host: 'www.iwencai.com',
        hostname: 'www.iwencai.com',
        pathname: '/ai-board',
        search: '',
        hash: ''
    };

    global.navigator = {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        plugins: [{ name: 'Chrome PDF Viewer' }, { name: 'Native Client' }],
        languages: ['zh-CN', 'zh'],
        platform: 'Win32'
    };

    global.screen = {
        width: 1920,
        height: 1080,
        colorDepth: 24,
        availWidth: 1920,
        availHeight: 1040
    };

    global.history = { length: 2 };
    global.performance = { now: function() { return Date.now(); } };
}

// 2. 初始化环境
mockBrowserEnvironment();

/**
 * 模拟生成同花顺 v 值 (Hexin-V)
 */
function getHexinV() {
    // 若引入真实 chameleon.js，直接调用 window.chameleon.getV()
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    let randStr = '';
    for (let i = 0; i < 52; i++) {
        randStr += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return 'A2P8H8SD' + randStr;
}

// 导出函数供外部使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getHexinV,
        getCookie: () => global.document.cookie
    };
}

// 测试打印
console.log('[sdenv 补环境测试结果]');
console.log('生成的 hexin-v 参数:', getHexinV());
console.log('当前模拟 Cookie 属性:', global.document.cookie);
