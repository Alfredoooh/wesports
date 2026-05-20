const https = require('https');
const http = require('http');
const express = require('express');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

app.use(cors());
app.use(express.json());

// ── BASE DE DADOS EM MEMÓRIA ──────────────────────────────────────────────────
let users = [];
let requests = [];
let helpMessages = [];
let userIdCounter = 1000;

const ADMIN_PHONE = '+244900000000';
const ADMIN_PIN = '1234';

function getAvatar(userId) {
  return `https://api.dicebear.com/7.x/adventurer/svg?seed=${userId}`;
}

const APNA_CODES = [
  { id: 1, name: 'Unitel Free', code: 'SNI=free.facebook.com\nHOST=free.facebook.com\nPORT=443\nMETHOD=TLS' },
  { id: 2, name: 'Movicel Zero', code: 'SNI=zero.facebook.com\nHOST=zero.facebook.com\nPORT=443\nMETHOD=TLS' },
  { id: 3, name: 'Unitel Wap', code: 'SNI=wap.unitel.ao\nHOST=wap.unitel.ao\nPORT=443\nMETHOD=TLS' },
  { id: 4, name: 'Unitel Internet', code: 'SNI=internet.unitel.ao\nHOST=internet.unitel.ao\nPORT=443\nMETHOD=TLS' },
];

const FAQ = [
  { id: 1, question: 'Como usar os códigos?', answer: 'Copia o código desejado no separador "Uso" e cola no campo de configuração do app Apna Tunnel.' },
  { id: 2, question: 'Não consigo ligar à VPN', answer: 'Verifica se o teu operador é Unitel ou Movicel e usa o código correspondente. Tenta também mudar o servidor.' },
  { id: 3, question: 'Como mudar de servidor?', answer: 'Vai ao separador SNI Scanner, clica em Escanear e escolhe um servidor da lista.' },
  { id: 4, question: 'A ligação é lenta', answer: 'Tenta um servidor com menor ping. Vai ao separador Servidores e ordena por velocidade.' },
  { id: 5, question: 'Falar com suporte', answer: null },
];

// ── SNI ───────────────────────────────────────────────────────────────────────
const domains = [
  'free.facebook.com','zero.facebook.com','www.facebook.com',
  'graph.facebook.com','b-api.facebook.com','z-p3-upload.facebook.com',
  'www.unitel.ao','unitel.ao','internet.unitel.ao','wap.unitel.ao',
  'www.movicel.ao','movicel.ao',
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

// ── AUTH ──────────────────────────────────────────────────────────────────────
app.post('/auth/register', (req, res) => {
  const { phone, pin } = req.body;
  if (!phone || !pin) return res.status(400).json({ error: 'Telemóvel e PIN obrigatórios' });
  if (!/^\+244\d{9}$/.test(phone)) return res.status(400).json({ error: 'Número inválido. Use +244 seguido de 9 dígitos' });
  if (!/^\d{4,6}$/.test(pin)) return res.status(400).json({ error: 'PIN deve ter 4 a 6 dígitos' });
  if (users.find(u => u.phone === phone)) return res.status(409).json({ error: 'Número já registado' });
  const id = 'U' + (userIdCounter++);
  const user = { id, phone, pin, avatar: getAvatar(id), configs: 0, createdAt: new Date().toISOString() };
  users.push(user);
  res.json({ success: true, user: { id: user.id, phone: user.phone, avatar: user.avatar, configs: user.configs } });
});

app.post('/auth/login', (req, res) => {
  const { phone, pin } = req.body;
  if (phone === ADMIN_PHONE && pin === ADMIN_PIN) {
    return res.json({ success: true, role: 'admin', user: { id: 'ADM', phone: ADMIN_PHONE, avatar: getAvatar('ADM'), configs: 0 } });
  }
  const user = users.find(u => u.phone === phone && u.pin === pin);
  if (!user) return res.status(401).json({ error: 'Número ou PIN incorretos' });
  res.json({ success: true, role: 'user', user: { id: user.id, phone: user.phone, avatar: user.avatar, configs: user.configs } });
});

app.delete('/auth/delete', (req, res) => {
  const { phone, pin } = req.body;
  const idx = users.findIndex(u => u.phone === phone && u.pin === pin);
  if (idx === -1) return res.status(401).json({ error: 'Credenciais inválidas' });
  users.splice(idx, 1);
  res.json({ success: true });
});

// ── PEDIDOS ───────────────────────────────────────────────────────────────────
app.post('/requests/new', (req, res) => {
  const { userId, phone, message } = req.body;
  if (!userId || !message) return res.status(400).json({ error: 'Dados incompletos' });
  const request = { id: 'R' + Date.now(), userId, phone, message, status: 'pendente', createdAt: new Date().toISOString() };
  requests.push(request);
  res.json({ success: true, request });
});

app.get('/requests/my/:userId', (req, res) => {
  res.json({ requests: requests.filter(r => r.userId === req.params.userId) });
});

// ── ADMIN ─────────────────────────────────────────────────────────────────────
app.get('/admin/requests', (req, res) => {
  res.json({ requests: requests.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)) });
});

app.get('/admin/users', (req, res) => {
  res.json({ users: users.map(u => ({ id: u.id, phone: u.phone, avatar: u.avatar, configs: u.configs, createdAt: u.createdAt })) });
});

app.patch('/admin/requests/:id', (req, res) => {
  const r = requests.find(r => r.id === req.params.id);
  if (!r) return res.status(404).json({ error: 'Pedido não encontrado' });
  r.status = req.body.status || r.status;
  r.adminReply = req.body.adminReply || r.adminReply;
  res.json({ success: true, request: r });
});

// ── AJUDA ─────────────────────────────────────────────────────────────────────
app.get('/help/faq', (req, res) => {
  res.json({ faq: FAQ });
});

app.post('/help/message', (req, res) => {
  const { userId, message } = req.body;
  if (!userId || !message) return res.status(400).json({ error: 'Dados incompletos' });
  helpMessages.push({ id: 'M' + Date.now(), userId, message, from: 'user', createdAt: new Date().toISOString() });
  res.json({ success: true });
});

app.get('/help/messages/:userId', (req, res) => {
  res.json({ messages: helpMessages.filter(m => m.userId === req.params.userId) });
});

// ── CONFIGS ───────────────────────────────────────────────────────────────────
app.get('/configs', (req, res) => {
  res.json({ configs: APNA_CODES });
});

app.post('/configs/use', (req, res) => {
  const { userId } = req.body;
  const user = users.find(u => u.id === userId);
  if (user) user.configs++;
  res.json({ success: true });
});

// ── SNI & SERVIDORES ──────────────────────────────────────────────────────────
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
        return { ip: cols[1], country: cols[6], speed: cols[4], ping: cols[3], ovpn: cols[14] };
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