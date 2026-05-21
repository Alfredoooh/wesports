const https = require('https');
const http = require('http');
const net = require('net');
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

function testPort(ip, port) {
  return new Promise((resolve) => {
    const start = Date.now();
    const socket = net.createConnection({ host: ip, port, timeout: 4000 });
    socket.on('connect', () => {
      const ping = Date.now() - start;
      socket.destroy();
      resolve({ alive: true, ping });
    });
    socket.on('error', () => resolve({ alive: false, ping: 0 }));
    socket.on('timeout', () => { socket.destroy(); resolve({ alive: false, ping: 0 }); });
  });
}

async function fetchSSHServers() {
  const publicServers = [
    { ip: '103.214.109.138', port: 443, country: 'ID', type: 'SSL' },
    { ip: '103.106.184.100', port: 443, country: 'SG', type: 'SSL' },
    { ip: '172.104.185.99',  port: 443, country: 'SG', type: 'SSL' },
    { ip: '139.59.221.47',   port: 443, country: 'IN', type: 'SSL' },
    { ip: '178.128.54.202',  port: 443, country: 'SG', type: 'SSL' },
    { ip: '103.149.144.196', port: 443, country: 'ID', type: 'SSL' },
    { ip: '45.77.173.108',   port: 443, country: 'JP', type: 'SSL' },
    { ip: '149.28.68.93',    port: 443, country: 'US', type: 'SSL' },
    { ip: '103.214.109.138', port: 80,  country: 'ID', type: 'HTTP' },
    { ip: '178.128.54.202',  port: 80,  country: 'SG', type: 'HTTP' },
    { ip: '139.59.221.47',   port: 80,  country: 'IN', type: 'HTTP' },
  ];

  const results = await Promise.all(
    publicServers.map(async (s) => {
      const { alive, ping } = await testPort(s.ip, s.port);
      return { ...s, alive, ping };
    })
  );

  return results.filter(s => s.alive);
}

app.get('/', (req, res) => res.send('SNI Scanner online'));

app.get('/scan', async (req, res) => {
  const results = await Promise.all(domains.map(testSNI));
  res.json({ valid: results.filter(r => r.valid) });
});

app.get('/servers', async (req, res) => {
  try {
    const servers = await fetchSSHServers();
    res.json({ total: servers.length, servers });
  } catch (e) {
    res.status(500).json({ error: 'Falha ao buscar servidores' });
  }
});

app.get('/health', (req, res) => res.send('OK'));

setInterval(() => {
  http.get(`${APP_URL}/health`, (res) => {
    console.log(`[ping] ${new Date().toISOString()}`);
  }).on('error', (e) => console.error('[ping error]', e.message));
}, 10 * 60 * 1000);

app.listen(PORT, () => console.log(`Porta ${PORT}`));