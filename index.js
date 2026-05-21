const https   = require('https');
const http    = require('http');
const net     = require('net');
const express = require('express');
const cors    = require('cors');

const app     = express();
const PORT    = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

app.use(cors());
app.use(express.json());

// ─── Pool de SNIs por operadora ────────────────────────────────────────────
const SNI_MAP = {
  angola_unitel:  ['www.unitel.ao','internet.unitel.ao','wap.unitel.ao','streaming.unitel.ao','m.unitel.ao','free.unitel.ao'],
  angola_movicel: ['www.movicel.ao','movicel.ao','internet.movicel.ao','wap.movicel.ao'],
  angola_africell:['www.africell.ao','africell.ao'],
  angola_free:    ['free.facebook.com','zero.facebook.com','graph.facebook.com','b-api.facebook.com','static.xx.fbcdn.net','edge-mqtt.facebook.com'],
  brasil_claro:   ['www.claro.com.br','zero.claro.com.br','minhaclaro.claro.com.br'],
  brasil_tim:     ['www.tim.com.br','meutim.tim.com.br','api.tim.com.br'],
  brasil_vivo:    ['www.vivo.com.br','meu.vivo.com.br','api.vivo.com.br'],
  brasil_oi:      ['www.oi.com.br','minhaoi.oi.com.br'],
  universal:      ['www.google.com','accounts.google.com','clients1.google.com','www.youtube.com','www.instagram.com','www.whatsapp.com','wss.whatsapp.net','www.tiktok.com','tunnel.spotify.com'],
};

const ALL_SNIS = Object.values(SNI_MAP).flat();

// ─── Pool de servidores ────────────────────────────────────────────────────
const SERVER_POOL = [
  // ── Angola / África ──────────────────────────────────────────────────────
  { ip: '41.63.64.10',     port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Unitel'   },
  { ip: '41.63.64.11',     port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Unitel'   },
  { ip: '41.220.232.5',    port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Unitel'   },
  { ip: '41.220.232.6',    port: 80,   country: 'AO', region: 'Angola',  type: 'HTTP',  operator: 'Unitel'   },
  { ip: '196.46.244.2',    port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Movicel'  },
  { ip: '196.46.244.3',    port: 80,   country: 'AO', region: 'Angola',  type: 'HTTP',  operator: 'Movicel'  },
  { ip: '41.138.64.1',     port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Africell' },
  { ip: '197.156.68.100',  port: 443,  country: 'AO', region: 'Angola',  type: 'SSL',   operator: 'Angola Cables' },
  // ── Brasil ───────────────────────────────────────────────────────────────
  { ip: '177.11.50.30',    port: 443,  country: 'BR', region: 'Brasil',  type: 'SSL',   operator: 'Claro'    },
  { ip: '189.6.8.100',     port: 443,  country: 'BR', region: 'Brasil',  type: 'SSL',   operator: 'Claro'    },
  { ip: '189.6.8.100',     port: 80,   country: 'BR', region: 'Brasil',  type: 'HTTP',  operator: 'Claro'    },
  { ip: '200.161.2.15',    port: 443,  country: 'BR', region: 'Brasil',  type: 'SSL',   operator: 'Vivo'     },
  { ip: '186.224.112.5',   port: 443,  country: 'BR', region: 'Brasil',  type: 'SSL',   operator: 'TIM'      },
  { ip: '186.224.112.5',   port: 8080, country: 'BR', region: 'Brasil',  type: 'OCSWS', operator: 'TIM'      },
  // ── Servidores públicos SSH-over-SSL ──────────────────────────────────────
  { ip: '103.214.109.138', port: 443,  country: 'ID', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '103.214.109.138', port: 8080, country: 'ID', region: 'Asia',    type: 'OCSWS', operator: 'Public'   },
  { ip: '103.214.109.138', port: 80,   country: 'ID', region: 'Asia',    type: 'HTTP',  operator: 'Public'   },
  { ip: '103.106.184.100', port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '172.104.185.99',  port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '139.59.221.47',   port: 443,  country: 'IN', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '139.59.221.47',   port: 80,   country: 'IN', region: 'Asia',    type: 'HTTP',  operator: 'Public'   },
  { ip: '178.128.54.202',  port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '178.128.54.202',  port: 8080, country: 'SG', region: 'Asia',    type: 'OCSWS', operator: 'Public'   },
  { ip: '178.128.54.202',  port: 80,   country: 'SG', region: 'Asia',    type: 'HTTP',  operator: 'Public'   },
  { ip: '103.149.144.196', port: 443,  country: 'ID', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '103.149.144.196', port: 8080, country: 'ID', region: 'Asia',    type: 'OCSWS', operator: 'Public'   },
  { ip: '45.77.173.108',   port: 443,  country: 'JP', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '149.28.68.93',    port: 443,  country: 'US', region: 'USA',     type: 'SSL',   operator: 'Public'   },
  { ip: '149.28.68.93',    port: 80,   country: 'US', region: 'USA',     type: 'HTTP',  operator: 'Public'   },
  { ip: '68.183.36.231',   port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '64.227.18.44',    port: 443,  country: 'IN', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '159.65.140.194',  port: 443,  country: 'IN', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '167.71.40.151',   port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '143.198.42.30',   port: 443,  country: 'US', region: 'USA',     type: 'SSL',   operator: 'Public'   },
  { ip: '165.22.62.10',    port: 443,  country: 'NL', region: 'Europe',  type: 'SSL',   operator: 'Public'   },
  { ip: '165.22.62.10',    port: 80,   country: 'NL', region: 'Europe',  type: 'HTTP',  operator: 'Public'   },
  { ip: '138.68.79.55',    port: 443,  country: 'NL', region: 'Europe',  type: 'SSL',   operator: 'Public'   },
  { ip: '104.236.228.63',  port: 443,  country: 'US', region: 'USA',     type: 'SSL',   operator: 'Public'   },
  { ip: '188.166.116.117', port: 443,  country: 'NL', region: 'Europe',  type: 'SSL',   operator: 'Public'   },
  { ip: '128.199.87.30',   port: 443,  country: 'SG', region: 'Asia',    type: 'SSL',   operator: 'Public'   },
  { ip: '128.199.87.30',   port: 8080, country: 'SG', region: 'Asia',    type: 'OCSWS', operator: 'Public'   },
];

// ─── Cache ─────────────────────────────────────────────────────────────────
let cachedServers = [];
let lastScan      = 0;
const CACHE_TTL   = 5 * 60 * 1000;

// ─── TCP ping ──────────────────────────────────────────────────────────────
function ping(ip, port, timeout = 5000) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const s  = net.createConnection({ host: ip, port, timeout });
    s.on('connect', () => { s.destroy(); resolve({ alive: true, ping: Date.now() - t0 }); });
    s.on('error',   () => resolve({ alive: false, ping: 9999 }));
    s.on('timeout', () => { s.destroy(); resolve({ alive: false, ping: 9999 }); });
  });
}

// ─── Speed (bytes recebidos em 3s) ────────────────────────────────────────
function speedTest(ip, port, ms = 3000) {
  return new Promise((resolve) => {
    let bytes = 0;
    const t0  = Date.now();
    const timer = setTimeout(() => {
      s.destroy();
      const secs = (Date.now() - t0) / 1000;
      resolve(secs > 0 ? Math.round((bytes * 8) / secs / 1000) : 0); // kbps
    }, ms);
    const s = net.createConnection({ host: ip, port, timeout: ms });
    s.on('connect', () => s.write('GET / HTTP/1.0\r\nHost: ' + ip + '\r\n\r\n'));
    s.on('data',  d => { bytes += d.length; });
    s.on('error', () => { clearTimeout(timer); resolve(0); });
    s.on('close', () => {
      clearTimeout(timer);
      const secs = (Date.now() - t0) / 1000;
      resolve(secs > 0 ? Math.round((bytes * 8) / secs / 1000) : 0);
    });
  });
}

// ─── Testar SNI ────────────────────────────────────────────────────────────
function testSNI(domain) {
  return new Promise((resolve) => {
    const r = https.request({
      hostname: domain, port: 443, path: '/', method: 'HEAD',
      timeout: 6000, servername: domain, rejectUnauthorized: false,
    }, res => resolve({ domain, valid: true, status: res.statusCode }));
    r.on('error',   () => resolve({ domain, valid: false }));
    r.on('timeout', () => { r.destroy(); resolve({ domain, valid: false }); });
    r.end();
  });
}

// ─── Scan completo ─────────────────────────────────────────────────────────
async function scan() {
  console.log(`[scan] a escanear ${SERVER_POOL.length} servidores…`);
  const results = await Promise.allSettled(
    SERVER_POOL.map(async s => {
      const { alive, ping: p } = await ping(s.ip, s.port);
      if (!alive) return null;
      const speed = await speedTest(s.ip, s.port, 3000);
      return { ...s, alive, ping: p, speed };
    })
  );
  cachedServers = results
    .filter(r => r.status === 'fulfilled' && r.value !== null)
    .map(r => r.value)
    .sort((a, b) => a.ping - b.ping);
  lastScan = Date.now();
  console.log(`[scan] ${cachedServers.length} vivos`);
  return cachedServers;
}

// ─── Rotas ─────────────────────────────────────────────────────────────────
app.get('/', (_, res) => res.json({
  status: 'online',
  servers: cachedServers.length,
  last_scan: new Date(lastScan).toISOString(),
}));

app.get('/health', (_, res) => res.send('OK'));

app.get('/servers', async (req, res) => {
  try {
    if (Date.now() - lastScan > CACHE_TTL || cachedServers.length === 0) await scan();
    const { type, country, region } = req.query;
    let list = cachedServers;
    if (type)    list = list.filter(s => s.type.toLowerCase()    === type.toLowerCase());
    if (country) list = list.filter(s => s.country.toLowerCase() === country.toLowerCase());
    if (region)  list = list.filter(s => s.region?.toLowerCase() === region.toLowerCase());
    res.json({ total: list.length, servers: list });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/servers/refresh', async (_, res) => {
  try   { const s = await scan(); res.json({ total: s.length, servers: s }); }
  catch (e) { res.status(500).json({ error: e.message }); }
});

app.get('/sni', (_, res) => res.json({ total: ALL_SNIS.length, sni: SNI_MAP }));

app.get('/scan/sni', async (req, res) => {
  const targets = req.query.operator
    ? (SNI_MAP[req.query.operator] || ALL_SNIS)
    : ALL_SNIS;
  const results = await Promise.all(targets.map(testSNI));
  res.json({
    total:   results.length,
    valid:   results.filter(r => r.valid),
    invalid: results.filter(r => !r.valid).map(r => r.domain),
  });
});

// ─── Init ──────────────────────────────────────────────────────────────────
app.listen(PORT, async () => {
  console.log(`[server] porta ${PORT}`);
  await scan();
});

setInterval(scan, CACHE_TTL);

setInterval(() => {
  http.get(`${APP_URL}/health`, () => console.log(`[ping] ${new Date().toISOString()}`))
    .on('error', e => console.error('[ping erro]', e.message));
}, 10 * 60 * 1000);