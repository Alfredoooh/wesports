const https = require('https');
const http  = require('http');
const net   = require('net');
const express = require('express');
const cors    = require('cors');

const app  = express();
const PORT = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

app.use(cors());
app.use(express.json());

// ─── Domínios SNI para teste ───────────────────────────────────────────────
const SNI_DOMAINS = [
  'free.facebook.com',
  'zero.facebook.com',
  'graph.facebook.com',
  'b-api.facebook.com',
  'www.unitel.ao',
  'internet.unitel.ao',
  'wap.unitel.ao',
  'www.movicel.ao',
  'static.xx.fbcdn.net',
  'edge-mqtt.facebook.com',
];

// ─── Pool de servidores ────────────────────────────────────────────────────
const SERVER_POOL = [
  // SSL/TLS 443
  { ip: '103.214.109.138', port: 443, country: 'ID', type: 'SSL' },
  { ip: '103.106.184.100', port: 443, country: 'SG', type: 'SSL' },
  { ip: '172.104.185.99',  port: 443, country: 'SG', type: 'SSL' },
  { ip: '139.59.221.47',   port: 443, country: 'IN', type: 'SSL' },
  { ip: '178.128.54.202',  port: 443, country: 'SG', type: 'SSL' },
  { ip: '103.149.144.196', port: 443, country: 'ID', type: 'SSL' },
  { ip: '45.77.173.108',   port: 443, country: 'JP', type: 'SSL' },
  { ip: '149.28.68.93',    port: 443, country: 'US', type: 'SSL' },
  { ip: '68.183.36.231',   port: 443, country: 'SG', type: 'SSL' },
  { ip: '64.227.18.44',    port: 443, country: 'IN', type: 'SSL' },
  { ip: '159.65.140.194',  port: 443, country: 'IN', type: 'SSL' },
  { ip: '167.71.40.151',   port: 443, country: 'SG', type: 'SSL' },
  // OCSWS 8080
  { ip: '178.128.54.202',  port: 8080, country: 'SG', type: 'OCSWS' },
  { ip: '103.149.144.196', port: 8080, country: 'ID', type: 'OCSWS' },
  { ip: '103.214.109.138', port: 8080, country: 'ID', type: 'OCSWS' },
  // HTTP 80
  { ip: '103.214.109.138', port: 80,  country: 'ID', type: 'HTTP' },
  { ip: '178.128.54.202',  port: 80,  country: 'SG', type: 'HTTP' },
  { ip: '139.59.221.47',   port: 80,  country: 'IN', type: 'HTTP' },
  { ip: '149.28.68.93',    port: 80,  country: 'US', type: 'HTTP' },
];

// ─── Cache de servidores ───────────────────────────────────────────────────
let cachedServers = [];
let lastRefresh   = 0;
const CACHE_TTL   = 5 * 60 * 1000; // 5 minutos

// ─── Testar porta TCP ──────────────────────────────────────────────────────
function testPort(ip, port, timeout = 5000) {
  return new Promise((resolve) => {
    const start  = Date.now();
    const socket = net.createConnection({ host: ip, port, timeout });
    socket.on('connect', () => {
      const ping = Date.now() - start;
      socket.destroy();
      resolve({ alive: true, ping });
    });
    socket.on('error',   () => resolve({ alive: false, ping: 9999 }));
    socket.on('timeout', () => { socket.destroy(); resolve({ alive: false, ping: 9999 }); });
  });
}

// ─── Speed test TCP simples (mede throughput de resposta) ─────────────────
function testSpeed(ip, port, timeout = 6000) {
  return new Promise((resolve) => {
    try {
      const socket = net.createConnection({ host: ip, port, timeout });
      let bytes = 0;
      const start = Date.now();
      const timer = setTimeout(() => {
        const elapsed = (Date.now() - start) / 1000;
        const bps = elapsed > 0 ? Math.round((bytes * 8) / elapsed) : 0;
        socket.destroy();
        resolve(bps);
      }, timeout);

      socket.on('connect', () => {
        // Enviar GET para provocar resposta e medir
        socket.write('GET / HTTP/1.0\r\nHost: ' + ip + '\r\n\r\n');
      });
      socket.on('data', (d) => { bytes += d.length; });
      socket.on('error', () => { clearTimeout(timer); resolve(0); });
      socket.on('close', () => {
        clearTimeout(timer);
        const elapsed = (Date.now() - start) / 1000;
        const bps = elapsed > 0 ? Math.round((bytes * 8) / elapsed) : 0;
        resolve(bps);
      });
    } catch (_) { resolve(0); }
  });
}

// ─── Testar SNI ───────────────────────────────────────────────────────────
function testSNI(domain) {
  return new Promise((resolve) => {
    const req = https.request({
      hostname: domain, port: 443, path: '/', method: 'HEAD',
      timeout: 6000, servername: domain,
      rejectUnauthorized: false,
    }, (res) => resolve({ domain, valid: true, status: res.statusCode }));
    req.on('error',   () => resolve({ domain, valid: false }));
    req.on('timeout', () => { req.destroy(); resolve({ domain, valid: false }); });
    req.end();
  });
}

// ─── Scan completo dos servidores ─────────────────────────────────────────
async function scanServers() {
  console.log('[scan] A escanear servidores…');
  const results = await Promise.all(
    SERVER_POOL.map(async (s) => {
      const { alive, ping } = await testPort(s.ip, s.port);
      if (!alive) return null;
      const speedBps = await testSpeed(s.ip, s.port, 4000);
      return { ...s, alive, ping, speed: speedBps };
    })
  );

  cachedServers = results
    .filter(Boolean)
    .sort((a, b) => a.ping - b.ping);

  lastRefresh = Date.now();
  console.log(`[scan] ${cachedServers.length} servidores vivos`);
  return cachedServers;
}

// ─── Rotas ────────────────────────────────────────────────────────────────
app.get('/', (req, res) => res.json({ status: 'online', servers: cachedServers.length }));

app.get('/health', (req, res) => res.send('OK'));

app.get('/scan', async (req, res) => {
  const results = await Promise.all(SNI_DOMAINS.map(testSNI));
  res.json({
    total: results.length,
    valid: results.filter(r => r.valid),
    invalid: results.filter(r => !r.valid).map(r => r.domain),
  });
});

app.get('/servers', async (req, res) => {
  try {
    const now = Date.now();
    if (now - lastRefresh > CACHE_TTL || cachedServers.length === 0) {
      await scanServers();
    }
    res.json({ total: cachedServers.length, servers: cachedServers });
  } catch (e) {
    console.error('[/servers]', e.message);
    res.status(500).json({ error: 'Falha ao buscar servidores' });
  }
});

app.get('/servers/refresh', async (req, res) => {
  try {
    const servers = await scanServers();
    res.json({ total: servers.length, servers });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ─── Startup ──────────────────────────────────────────────────────────────
app.listen(PORT, async () => {
  console.log(`[server] Porta ${PORT}`);
  await scanServers();
});

// ─── Auto-refresh a cada 5 min ────────────────────────────────────────────
setInterval(scanServers, CACHE_TTL);

// ─── Self-ping para manter Render acordado ────────────────────────────────
setInterval(() => {
  http.get(`${APP_URL}/health`, () => {
    console.log(`[ping] ${new Date().toISOString()}`);
  }).on('error', (e) => console.error('[ping erro]', e.message));
}, 10 * 60 * 1000);