# 抖音 webmssdk X-Bogus 离线复现

`byted_acrawler.frontierSign` 生成请求参数 `X-Bogus`（纯 JS，与 `a_bogus` / bdms VM 不是同一套）。

同目录 `webmssdk.es5.js` 为 CDN `1.0.0.53` 原始样本。Node `vm` 加载后调用 `frontierSign`，产出 16 字符签名。签名含随机盐，与浏览器**不逐字节相同**；本案例验证格式与编码结构。

```bash
node cases/douyin_webmssdk_xbogus/repro_offline_xbogus.js
node cases/douyin_webmssdk_xbogus/verify_xbogus_structure.js
```

通过标志：`OFFLINE_XBOGUS_OK`、`STRUCTURE_OK`。
