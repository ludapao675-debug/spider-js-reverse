// shim_abogus_harden.js — 对齐首页长签(176)的环境垫片增强
// 根因：bdms 异步采集 canvas/webgl/audio；假 PNG / 空 extensions → 短签(168/raw124~126)
'use strict';
const fs = require('fs');
const path = require('path');

const HERE = __dirname;

/** 活体采集的合法 canvas toDataURL（PNG magic + 真实像素） */
function loadCanvasDataUrl() {
  const p = path.join(HERE, 'live_canvas_dataurl.txt');
  if (fs.existsSync(p)) {
    try {
      return fs.readFileSync(p, 'utf8').trim();
    } catch (e) {
      /* fallthrough */
    }
  }
  // 兜底：1x1 合法 PNG（仍优于 AAAA 假数据）
  return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
}

/** 活体 WebGL getSupportedExtensions（Chrome150 / ANGLE Basic Render） */
const LIVE_WEBGL_EXTS = [
  'ANGLE_instanced_arrays',
  'EXT_blend_minmax',
  'EXT_clip_control',
  'EXT_color_buffer_half_float',
  'EXT_depth_clamp',
  'EXT_float_blend',
  'EXT_frag_depth',
  'EXT_polygon_offset_clamp',
  'EXT_shader_texture_lod',
  'EXT_texture_compression_bptc',
  'EXT_texture_compression_rgtc',
  'EXT_texture_filter_anisotropic',
  'EXT_texture_mirror_clamp_to_edge',
  'EXT_sRGB',
  'KHR_parallel_shader_compile',
  'OES_element_index_uint',
  'OES_fbo_render_mipmap',
  'OES_standard_derivatives',
  'OES_texture_float',
  'OES_texture_float_linear',
  'OES_texture_half_float',
  'OES_texture_half_float_linear',
  'OES_vertex_array_object',
  'WEBGL_color_buffer_float',
  'WEBGL_compressed_texture_s3tc',
  'WEBGL_compressed_texture_s3tc_srgb',
  'WEBGL_debug_renderer_info',
  'WEBGL_debug_shaders',
  'WEBGL_depth_texture',
  'WEBGL_draw_buffers',
  'WEBGL_lose_context',
  'WEBGL_multi_draw',
  'WEBGL_polygon_mode',
  'WEBGL_provoking_vertex',
];

/**
 * 增强 shim，使 bdms 环境完整性检测走长签分支。
 * @returns {{ canvasDataUrl: string, flags: object }}
 */
function hardenAbogusShim(g, opts = {}) {
  const flags = { canvas_patched: false, webgl_patched: false, audio_patched: false, uach_patched: false, events_patched: false };
  const canvasDataUrl = opts.canvasDataUrl || loadCanvasDataUrl();

  // 事件入队：空 addEventListener 会导致行为指纹永远不涨（活体 168→176 靠 mousemove）
  try {
    const { installEventTargetShim } = require('./shim_event_target');
    const ev = installEventTargetShim(g);
    flags.events_patched = !!(ev && ev.patched && ev.patched.length);
    flags.event_targets = ev && ev.patched;
  } catch (e) {
    flags.events_error = String(e.message || e);
  }

  // ---- canvas：createElement 返回带合法 toDataURL / getImageData 的对象 ----
  const origCreate = g.document.createElement.bind(g.document);
  g.document.createElement = function createElement(tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() !== 'canvas') return el;

    flags.canvas_patched = true;
    const wrapCtx2d = (ctx) => {
      if (!ctx || ctx.__ab_hard) return ctx;
      ctx.__ab_hard = true;
      const _gid = ctx.getImageData;
      ctx.getImageData = function getImageData(x, y, w, h) {
        if (typeof _gid === 'function') return _gid.call(this, x, y, w, h);
        const W = w | 0;
        const H = h | 0;
        const data = new Uint8ClampedArray(W * H * 4);
        for (let yy = 0; yy < H; yy++) {
          for (let xx = 0; xx < W; xx++) {
            const base = 128 + Math.sin(xx * 0.15 + yy * 0.07) * 60 + Math.cos((xx + yy) * 0.05) * 30;
            const noise = (((xx * 73856093) ^ (yy * 19349663)) & 0xff) * 0.3;
            const v = base + noise;
            const o = (yy * W + xx) * 4;
            data[o] = v & 0xff;
            data[o + 1] = (v * 1.1) & 0xff;
            data[o + 2] = (v * 0.9) & 0xff;
            data[o + 3] = 255;
          }
        }
        return { data, width: W, height: H };
      };
      return ctx;
    };

    // 原 shim 的 webgl 是 Proxy，直接赋值无效；外层再包 Proxy 覆盖关键 API
    const wrapGl = (inner) => {
      flags.webgl_patched = true;
      const dbgExt = { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 };
      const shaders = new WeakMap();
      const programs = new WeakMap();
      return new Proxy(inner || {}, {
        get(t, p) {
          if (p === '__ab_hard') return true;
          if (p === 'canvas') return inner && inner.canvas;
          if (p === 'drawingBufferWidth') return 300;
          if (p === 'drawingBufferHeight') return 150;
          if (p === 'getSupportedExtensions') return () => LIVE_WEBGL_EXTS.slice();
          if (p === 'getExtension') {
            return (name) => (name === 'WEBGL_debug_renderer_info' ? dbgExt : {});
          }
          if (p === 'getParameter') {
            return (k) => {
              if (k === 37445) return 'Google Inc. (Microsoft)';
              if (k === 37446) {
                return 'ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)';
              }
              if (k === 7938) return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
              if (k === 7936) return 'WebKit';
              if (k === 7937) return 'WebKit WebGL';
              if (k === 35724) return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)';
              if (k === 3379) return 16384; // MAX_TEXTURE_SIZE
              if (k === 34076) return 16384;
              if (k === 34921) return 16;
              if (k === 36347) return 1024;
              if (k === 36348) return 4096;
              if (k === 36349) return 32;
              return 16384;
            };
          }
          if (p === 'getShaderPrecisionFormat') {
            return () => ({ rangeMin: 127, rangeMax: 127, precision: 23 });
          }
          if (p === 'createShader') return (type) => ({ __shader: true, type });
          if (p === 'shaderSource') return (sh, src) => { shaders.set(sh, src); };
          if (p === 'compileShader') return () => {};
          if (p === 'getShaderParameter') return (sh, pname) => (pname === 35713 /* COMPILE_STATUS */ ? true : 0);
          if (p === 'getShaderInfoLog') return () => '';
          if (p === 'createProgram') return () => ({ __program: true });
          if (p === 'attachShader') return () => {};
          if (p === 'linkProgram') return () => {};
          if (p === 'getProgramParameter') return (prog, pname) => (pname === 35714 /* LINK_STATUS */ ? true : 0);
          if (p === 'getProgramInfoLog') return () => '';
          if (p === 'useProgram') return () => {};
          if (p === 'createBuffer') return () => ({ __buf: true });
          if (p === 'bindBuffer') return () => {};
          if (p === 'bufferData') return () => {};
          if (p === 'createTexture') return () => ({ __tex: true });
          if (p === 'bindTexture') return () => {};
          if (p === 'texImage2D') return () => {};
          if (p === 'texParameteri') return () => {};
          if (p === 'viewport') return () => {};
          if (p === 'clearColor') return () => {};
          if (p === 'clear') return () => {};
          if (p === 'drawArrays') return () => {};
          if (p === 'drawElements') return () => {};
          if (p === 'getAttribLocation') return () => 0;
          if (p === 'getUniformLocation') return () => ({ __uni: true });
          if (p === 'enableVertexAttribArray') return () => {};
          if (p === 'vertexAttribPointer') return () => {};
          if (p === 'uniform1f' || p === 'uniform2f' || p === 'uniform1i') return () => {};
          if (p === 'readPixels') {
            return (x, y, w, h, fmt, typ, buf) => {
              if (buf && buf.length) {
                for (let i = 0; i < buf.length; i++) buf[i] = ((i * 2654435761) >>> 0) & 0xff;
              }
              return buf;
            };
          }
          const v = inner ? inner[p] : undefined;
          if (typeof v === 'function') return v.bind(inner);
          if (v !== undefined) return v;
          // 未识别方法返回空函数，避免 VM 抛错进短签分支
          if (typeof p === 'string') return () => 0;
          return undefined;
        },
      });
    };

    const _getContext = typeof el.getContext === 'function' ? el.getContext.bind(el) : null;
    el.getContext = function getContext(type) {
      const t = String(type || '');
      let ctx = _getContext ? _getContext(t) : null;
      if (t === '2d') ctx = wrapCtx2d(ctx);
      else if (t.indexOf('webgl') >= 0 || t === 'experimental-webgl') ctx = wrapGl(ctx);
      return ctx;
    };
    el.toDataURL = function toDataURL() {
      return canvasDataUrl;
    };
    return el;
  };

  // ---- OfflineAudioContext（bdms 常用音频指纹）----
  function OfflineAudioContext(channels, length, sampleRate) {
    flags.audio_patched = true;
    this.numberOfChannels = channels || 1;
    this.length = length || 44100;
    this.sampleRate = sampleRate || 44100;
    this.destination = {};
    this.currentTime = 0;
    this.state = 'suspended';
  }
  OfflineAudioContext.prototype.createOscillator = function createOscillator() {
    return {
      type: 'triangle',
      frequency: { value: 10000, setValueAtTime() {} },
      connect() {},
      start() {},
      stop() {},
    };
  };
  OfflineAudioContext.prototype.createDynamicsCompressor = function createDynamicsCompressor() {
    return {
      threshold: { value: -50 },
      knee: { value: 40 },
      ratio: { value: 12 },
      reduction: { value: -20 },
      attack: { value: 0 },
      release: { value: 0.25 },
      connect() {},
    };
  };
  OfflineAudioContext.prototype.startRendering = function startRendering() {
    const ch = this.numberOfChannels;
    const len = this.length;
    const buf = {
      numberOfChannels: ch,
      length: len,
      sampleRate: this.sampleRate,
      duration: len / this.sampleRate,
      getChannelData(i) {
        const arr = new Float32Array(len);
        for (let j = 0; j < len; j++) {
          arr[j] = Math.sin(j * 0.01 + (i || 0)) * 0.1 + ((((j * 2654435761) >>> 0) & 0xff) / 2550);
        }
        return arr;
      },
    };
    return Promise.resolve(buf);
  };
  g.OfflineAudioContext = OfflineAudioContext;
  g.webkitOfflineAudioContext = OfflineAudioContext;

  // ---- UA-CH 对齐 Chrome 150（与活体 fingerprint 一致）----
  if (g.navigator) {
    const ua =
      opts.ua ||
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36';
    g.navigator.userAgent = ua;
    g.navigator.appVersion = ua.replace(/^Mozilla\//, '');
    g.navigator.userAgentData = {
      brands: [
        { brand: 'Not;A=Brand', version: '8' },
        { brand: 'Chromium', version: '150' },
        { brand: 'Google Chrome', version: '150' },
      ],
      mobile: false,
      platform: 'Windows',
      getHighEntropyValues: () =>
        Promise.resolve({
          architecture: 'x86',
          bitness: '64',
          model: '',
          platformVersion: '15.0.0',
          uaFullVersion: '150.0.0.0',
          wow64: false,
        }),
    };
    flags.uach_patched = true;
  }

  // ---- 屏幕 / DPR（首页活体）----
  if (g.screen) {
    Object.assign(g.screen, {
      width: 2560,
      height: 1600,
      availWidth: 2560,
      availHeight: 1600,
      colorDepth: 24,
      pixelDepth: 24,
    });
  }
  g.devicePixelRatio = 1;
  g.innerWidth = 1904;
  g.innerHeight = 929;
  g.outerWidth = 1904;
  g.outerHeight = 929;

  if (!g.performance) g.performance = { now: () => Date.now(), timing: { navigationStart: Date.now() } };
  g.performance.memory = {
    usedJSHeapSize: 23898516,
    totalJSHeapSize: 25165916,
    jsHeapSizeLimit: 4395630592,
  };

  return { canvasDataUrl, flags, canvasDataUrlLen: canvasDataUrl.length };
}

/**
 * 等待 bdms 异步环境采集（实测 ~3s 会 create canvas / 读 plugins）
 * @param {number} ms
 */
function waitEnvReady(ms = 3500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = {
  hardenAbogusShim,
  waitEnvReady,
  loadCanvasDataUrl,
  LIVE_WEBGL_EXTS,
};
