const https = require('https');

function get(u, headers) {
  return new Promise((resolve, reject) => {
    const req = https.get(u, headers || {}, (r) => {
      let d = '';
      r.on('data', (c) => (d += c));
      r.on('end', () => resolve(d));
    });
    req.on('error', reject);
  });
}

(async () => {
  const URL = 'https://account.chsi.com.cn/passport/login;jsessionid=F3AAE209A62746A8A0C4F75BD83FAF70?service=https%3A%2F%2Fjy.chsi.com.cn%2Fj_spring_cas_security_check';
  const html = await get(URL, { 'User-Agent': 'Mozilla/5.0' });
  const srcs = [...html.matchAll(/<script[^>]*src="([^"]+)"/g)].map((m) => m[1]);
  console.log('SCRIPTS(' + srcs.length + '):');
  srcs.forEach((s) => console.log('  ' + s));
  const inl = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  console.log('INLINE scripts: ' + inl.length);
  inl.forEach((s, i) => {
    if (/encrypt|password|doencrypt|submit|fm1/i.test(s)) console.log('  INLINE[' + i + ']: ' + s.slice(0, 400));
  });

  const candidates = ['https://t1.chei.com.cn/common/wap/js/wap.min.js'];
  for (const u of candidates) {
    const t = await get(u, { 'User-Agent': 'Mozilla/5.0' });
    const low = t.toLowerCase();
    console.log('\n' + u.split('/').pop() + ' len=' + t.length +
      ' doEncrypt=' + low.indexOf('doencrypt') +
      ' encrypt=' + low.indexOf('encrypt') +
      ' password=' + low.indexOf('password') +
      ' rsa=' + low.indexOf('rsa'));
  }
})().catch((e) => console.log('ERR', e.message));
