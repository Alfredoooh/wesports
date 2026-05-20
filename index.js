const https = require('https');
const http = require('http');
const express = require('express');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

app.use(cors());

const domains = [
  'www.google.com',
  'www.cloudflare.com',
];

function testSNI(domain) {
  return new Promise((resolve) => {
    const req = https.request({
      hostname: domain, port: 443, path: '/', method: 'GET',
      timeout: 5000, servername: domain,
    }, (res) => resolve({ domain, valid: true, status: res.statusCode }));
    req.on('error', () => resolve({ domain, valid: false }));
    req.on('timeout', () => { req.destroy(); resolve({ domain, valid: false }); });
    req.end();
  });
}

app.get('/', (req, res) => res.send('SNI Scanner online'));
app.get('/scan', async (req, res) => {
  const results = await Promise.all(domains.map(testSNI));
  res.json({ valid: results.filter(r => r.valid) });
});
app.get('/health', (req, res) => res.send('OK'));

setInterval(() => {
  http.get(`${APP_URL}/health`, (res) => {
    console.log(`[ping] ${new Date().toISOString()}`);
  }).on('error', (e) => console.error('[ping error]', e.message));
}, 10 * 60 * 1000);

app.listen(PORT, () => console.log(`Porta ${PORT}`));