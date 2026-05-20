const https = require('https');
const http = require('http');
const express = require('express');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

app.use(cors());

const domains = [
  'free.facebook.com',
  'zero.facebook.com',
  'www.facebook.com',
  'graph.facebook.com',
  'b-api.facebook.com',
  'z-p3-upload.facebook.com',
  'www.unitel.ao',
  'unitel.ao',
  'internet.unitel.ao',
  'wap.unitel.ao',
  'www.movicel.ao',
  'movicel.ao',
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

app.get('/servers', (req, res) => {
  const url = 'https://www.vpngate.net/api/iphone/';
  https.get(url, (response) => {
    let data = '';
    response.on('data', chunk => data += chunk);
    response.on('end', () => {
      const lines = data.split('\n').filter(l => l && !l.startsWith('*'));
      const servers = lines.slice(1).map(line => {
        const cols = line.split(',');
        return {
          ip: cols[1],
          country: cols[6],
          speed: cols[4],
          ping: cols[3],
          ovpn: cols[14],
        };
      }).filter(s => s.ip);
      res.json({ total: servers.length, servers: servers.slice(0, 20) });
    });
  }).on('error', () => res.status(500).json({ error: 'Falha ao buscar servidores' }));
});

app.get('/health', (req, res) => res.send('OK'));

setInterval(() => {
  http.get(`${APP_URL}/health`, (res) => {
    console.log(`[ping] ${new Date().toISOString()}`);
  }).on('error', (e) => console.error('[ping error]', e.message));
}, 10 * 60 * 1000);

app.listen(PORT, () => console.log(`Porta ${PORT}`));