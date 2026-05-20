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

// Avatares usando DiceBear (ilustrações)
function getAvatar(userId) {
  return `https://api.dicebear.com/7.x/adventurer/svg?seed=${userId}`;
}

// Códigos Apna Tunnel pré-definidos
const APNA_CODES = [
  { id: 1, name: 'Unitel Free', code: 'SNI=free.facebook.com\nHOST=free.facebook.com\nPORT=443\nMETHOD=TLS' },
  { id: 2, name: 'Movicel Zero', code: 'SNI=zero.facebook.com\nHOST=zero.facebook.com\nPORT=443\nMETHOD=TLS' },
  { id: 3, name: 'Unitel Wap', code: 'SNI=wap.unitel.ao\nHOST=wap.unitel.ao\nPORT=443\nMETHOD=TLS' },
  { id: 4, name: 'Unitel Internet', code: 'SNI=internet.unitel.ao\nHOST=internet.unitel.ao\nPORT=443\nMETHOD=TLS' },
];

// Perguntas padronizadas do chat de ajuda
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
  const request = {
    id: 'R' + Date.now(),
    userId, phone, message,
    status: 'pendente',
    createdAt: new Date().toISOString(),
  };
  requests.push(request);
  res.json({ success: true, request });
});

app.get('/requests/my/:userId', (req, res) => {
  const myRequests = requests.filter(r => r.userId === req.params.userId);
  res.json({ requests: myRequests });
});

// ── ADM ───────────────────────────────────────────────────────────────────────
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

// ── AJUDA / CHAT ──────────────────────────────────────────────────────────────
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
  const msgs = helpMessages.filter(m => m.userId === req.params.userId);
  res.json({ messages: msgs });
});

// ── CONFIGS / CÓDIGOS ─────────────────────────────────────────────────────────
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
  http.get(`${APP_URL}/health`, () => {
    console.log(`[ping] ${new Date().toISOString()}`);
  }).on('error', (e) => console.error('[ping error]', e.message));
}, 10 * 60 * 1000);

// ── FRONTEND ──────────────────────────────────────────────────────────────────
app.get('/app', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>WeSports VPN</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    html,body{width:100%;height:100%;overflow:hidden;font-family:'Segoe UI',system-ui,sans-serif;background:#fff;color:#111;}

    /* AUTH */
    .auth-screen{position:fixed;inset:0;background:#fff;z-index:30;display:flex;flex-direction:column;padding:48px 28px 32px;transition:opacity 0.3s;}
    .auth-screen.hidden{opacity:0;pointer-events:none;}
    .auth-app-name{font-size:26px;font-weight:800;color:#111;margin-bottom:4px;}
    .auth-tagline{font-size:14px;color:#888;margin-bottom:40px;}
    .auth-heading{font-size:20px;font-weight:700;color:#111;margin-bottom:6px;}
    .auth-sub{font-size:13px;color:#888;margin-bottom:28px;}
    .auth-input-wrap{margin-bottom:14px;}
    .auth-input-label{font-size:12px;font-weight:600;color:#555;margin-bottom:6px;display:block;text-transform:uppercase;letter-spacing:0.04em;}
    .auth-phone-row{display:flex;gap:8px;}
    .auth-prefix{padding:14px 14px;background:#f4f4f4;border:1.5px solid #e8e8e8;border-radius:10px;font-size:15px;font-weight:600;color:#111;white-space:nowrap;}
    .auth-input{width:100%;padding:14px 16px;border:1.5px solid #e8e8e8;border-radius:10px;font-size:15px;color:#111;outline:none;background:#fafafa;transition:border-color 0.2s;}
    .auth-input:focus{border-color:#111;background:#fff;}
    .auth-pin-row{display:flex;gap:10px;justify-content:center;}
    .pin-box{width:52px;height:56px;border:1.5px solid #e8e8e8;border-radius:10px;font-size:22px;text-align:center;background:#fafafa;outline:none;color:#111;transition:border-color 0.2s;}
    .pin-box:focus{border-color:#111;background:#fff;}
    .auth-btn{width:100%;padding:15px;background:#111;color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;margin-top:8px;transition:opacity 0.2s;}
    .auth-btn:active{opacity:0.8;}
    .auth-switch{text-align:center;margin-top:20px;font-size:14px;color:#888;}
    .auth-switch-btn{background:none;border:none;color:#111;font-weight:700;font-size:14px;cursor:pointer;padding:0;}
    .auth-error{font-size:13px;color:#e53e3e;margin-top:6px;display:none;}

    /* DRAWER */
    .drawer{position:fixed;top:0;left:0;width:260px;height:100%;background:#f9f9f9;transform:translateX(-100%);transition:transform 420ms cubic-bezier(0.22,1,0.36,1);will-change:transform;z-index:10;padding:28px 20px;box-shadow:2px 0 14px rgba(0,0,0,0.10);display:flex;flex-direction:column;gap:4px;}
    .drawer.open{transform:translateX(0);}
    .drawer-user{display:flex;align-items:center;gap:12px;padding:0 4px 20px;border-bottom:1px solid #eee;margin-bottom:12px;}
    .drawer-avatar{width:44px;height:44px;border-radius:50%;background:#eee;overflow:hidden;flex-shrink:0;}
    .drawer-avatar img{width:100%;height:100%;}
    .drawer-user-info{flex:1;min-width:0;}
    .drawer-user-id{font-size:11px;font-weight:700;color:#aaa;text-transform:uppercase;}
    .drawer-user-phone{font-size:13px;color:#111;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .drawer-header{font-size:11px;font-weight:700;color:#bbb;text-transform:uppercase;letter-spacing:0.08em;padding-left:12px;margin-bottom:8px;}
    .drawer-item{display:flex;align-items:center;gap:12px;padding:13px 14px;border-radius:10px;color:#111;font-size:15px;cursor:pointer;transition:background 0.15s;-webkit-tap-highlight-color:transparent;}
    .drawer-item:active{background:rgba(0,0,0,0.06);}

    /* OVERLAY */
    .overlay{position:fixed;inset:0;background:rgba(0,0,0,0.18);opacity:0;pointer-events:none;transition:opacity 420ms cubic-bezier(0.22,1,0.36,1);z-index:5;}
    .overlay.show{opacity:1;pointer-events:auto;}

    /* APP */
    .app{position:relative;width:100%;height:100%;background:#fff;transform:translateX(0);transition:transform 420ms cubic-bezier(0.22,1,0.36,1);will-change:transform;z-index:1;display:flex;flex-direction:column;}
    .app.shifted{transform:translateX(110px);}

    /* TOPBAR */
    .topbar{height:60px;display:flex;align-items:center;padding:0 16px;background:#fff;border-bottom:1px solid #f0f0f0;flex-shrink:0;}
    .topbar-title{font-size:17px;font-weight:700;color:#111;margin-left:8px;}
    .menu-btn{width:44px;height:44px;border:none;background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;border-radius:12px;-webkit-tap-highlight-color:transparent;}
    .menu-btn:active{background:rgba(0,0,0,0.06);}
    .icon{width:24px;height:18px;position:relative;}
    .icon span{position:absolute;left:0;width:100%;height:2.5px;background:#111;border-radius:999px;}
    .icon span:nth-child(1){top:0;} .icon span:nth-child(2){top:7.5px;} .icon span:nth-child(3){top:15px;}

    /* SCREENS */
    .screen{display:none;flex:1;overflow-y:auto;padding:24px 16px 90px;flex-direction:column;}
    .screen.active{display:flex;}

    /* HOME */
    .home-greeting{font-size:26px;font-weight:800;color:#111;margin-bottom:4px;}
    .home-sub{font-size:14px;color:#888;margin-bottom:32px;}
    .home-user-card{display:flex;align-items:center;gap:14px;background:#f4f4f4;border-radius:14px;padding:16px;margin-bottom:28px;}
    .home-avatar{width:52px;height:52px;border-radius:50%;overflow:hidden;background:#ddd;flex-shrink:0;}
    .home-avatar img{width:100%;height:100%;}
    .home-user-id{font-size:11px;color:#aaa;font-weight:700;text-transform:uppercase;}
    .home-user-phone{font-size:15px;font-weight:600;color:#111;}
    .new-request-btn{width:100%;padding:18px;background:#111;color:#fff;border:none;border-radius:14px;font-size:16px;font-weight:700;cursor:pointer;transition:opacity 0.2s;}
    .new-request-btn:active{opacity:0.8;}

    /* USO */
    .uso-stat{background:#f4f4f4;border-radius:14px;padding:20px;margin-bottom:16px;text-align:center;}
    .uso-stat-num{font-size:40px;font-weight:800;color:#111;}
    .uso-stat-label{font-size:13px;color:#888;margin-top:4px;}
    .uso-code-card{background:#f9f9f9;border:1px solid #eee;border-radius:14px;padding:16px;margin-bottom:12px;}
    .uso-code-name{font-size:14px;font-weight:700;color:#111;margin-bottom:8px;}
    .uso-code-block{background:#fff;border:1px solid #e8e8e8;border-radius:8px;padding:12px;font-family:monospace;font-size:12px;color:#333;white-space:pre-wrap;margin-bottom:10px;}
    .uso-copy-btn{background:#111;color:#fff;border:none;border-radius:8px;padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer;}
    .uso-copy-btn:active{opacity:0.8;}

    /* AJUDA CHAT */
    .chat-wrap{display:flex;flex-direction:column;height:100%;}
    .chat-faq{padding:0 0 16px;}
    .chat-faq-title{font-size:13px;font-weight:700;color:#888;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.04em;}
    .faq-btn{display:block;width:100%;text-align:left;background:#f4f4f4;border:none;border-radius:10px;padding:12px 14px;font-size:14px;color:#111;cursor:pointer;margin-bottom:8px;transition:background 0.15s;}
    .faq-btn:active{background:#e8e8e8;}
    .chat-messages{flex:1;overflow-y:auto;padding-bottom:12px;display:flex;flex-direction:column;gap:10px;}
    .chat-bubble{max-width:80%;padding:12px 14px;border-radius:14px;font-size:14px;line-height:1.5;}
    .chat-bubble.user{background:#111;color:#fff;align-self:flex-end;border-bottom-right-radius:4px;}
    .chat-bubble.bot{background:#f4f4f4;color:#111;align-self:flex-start;border-bottom-left-radius:4px;}
    .chat-input-row{display:flex;gap:8px;padding-top:12px;border-top:1px solid #f0f0f0;}
    .chat-input{flex:1;padding:12px 14px;border:1.5px solid #e8e8e8;border-radius:10px;font-size:14px;outline:none;background:#fafafa;}
    .chat-input:focus{border-color:#111;}
    .chat-send-btn{padding:12px 18px;background:#111;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;}

    /* CONFIG */
    .config-section-title{font-size:13px;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:12px;}
    .config-danger-btn{width:100%;padding:15px;background:#fff;color:#e53e3e;border:1.5px solid #e53e3e;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;}
    .config-danger-btn:active{background:#fff5f5;}

    /* MODAL */
    .modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:40;display:flex;align-items:flex-end;opacity:0;pointer-events:none;transition:opacity 0.25s;}
    .modal-overlay.show{opacity:1;pointer-events:auto;}
    .modal{background:#fff;border-radius:20px 20px 0 0;padding:28px 24px 40px;width:100%;transform:translateY(100%);transition:transform 0.35s cubic-bezier(0.22,1,0.36,1);}
    .modal-overlay.show .modal{transform:translateY(0);}
    .modal-title{font-size:18px;font-weight:700;color:#111;margin-bottom:8px;}
    .modal-desc{font-size:14px;color:#888;margin-bottom:24px;}
    .modal-btn{width:100%;padding:15px;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:10px;}
    .modal-btn-danger{background:#e53e3e;color:#fff;}
    .modal-btn-cancel{background:#f4f4f4;color:#111;}

    /* ADMIN */
    .admin-tab-row{display:flex;gap:8px;margin-bottom:20px;}
    .admin-tab{flex:1;padding:10px;border:1.5px solid #e8e8e8;border-radius:10px;background:#fff;font-size:14px;font-weight:600;cursor:pointer;color:#888;}
    .admin-tab.active{background:#111;color:#fff;border-color:#111;}
    .admin-card{background:#f9f9f9;border-radius:12px;padding:14px;margin-bottom:10px;}
    .admin-card-id{font-size:11px;color:#aaa;font-weight:700;text-transform:uppercase;margin-bottom:4px;}
    .admin-card-text{font-size:14px;color:#111;margin-bottom:6px;}
    .admin-card-meta{font-size:12px;color:#888;}
    .admin-status{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;}
    .admin-status.pendente{background:#fff3cd;color:#856404;}
    .admin-status.resolvido{background:#d4edda;color:#155724;}

    /* BOTTOM BAR */
    .bottom-bar{position:fixed;bottom:0;left:0;right:0;height:64px;background:#fff;border-top:1px solid #f0f0f0;display:flex;z-index:4;}
    .bottom-item{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;border:none;background:transparent;cursor:pointer;-webkit-tap-highlight-color:transparent;color:#bbb;font-size:11px;font-weight:600;transition:color 0.15s;}
    .bottom-item.active{color:#111;}
    .bottom-icon{width:22px;height:22px;}
  </style>
</head>
<body>

<!-- AUTH -->
<div class="auth-screen" id="authScreen">
  <div id="authLogin">
    <div class="auth-app-name">WeSports</div>
    <div class="auth-tagline">VPN & SNI Scanner</div>
    <div style="height:32px"></div>
    <div class="auth-heading">Entrar</div>
    <div class="auth-sub">Usa o teu número e PIN para entrar</div>
    <div class="auth-input-wrap">
      <label class="auth-input-label">Número de telemóvel</label>
      <div class="auth-phone-row">
        <div class="auth-prefix">+244</div>
        <input class="auth-input" id="loginPhone" type="tel" maxlength="9" placeholder="9XXXXXXXX"/>
      </div>
    </div>
    <div class="auth-input-wrap">
      <label class="auth-input-label">PIN</label>
      <div class="auth-pin-row">
        <input class="pin-box" id="p1" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="p2" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="p3" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="p4" maxlength="1" type="password" inputmode="numeric"/>
      </div>
    </div>
    <div class="auth-error" id="loginError"></div>
    <button class="auth-btn" onclick="doLogin()">Entrar</button>
    <div class="auth-switch">
      Não tens conta?
      <button class="auth-switch-btn" onclick="showRegister()">Registar</button>
    </div>
  </div>

  <div id="authRegister" style="display:none">
    <button class="auth-switch-btn" onclick="showLogin()" style="margin-bottom:28px;font-size:14px;color:#888;font-weight:400;">← Voltar</button>
    <div class="auth-heading">Criar conta</div>
    <div class="auth-sub">Regista-te com o teu número angolano</div>
    <div class="auth-input-wrap">
      <label class="auth-input-label">Número de telemóvel</label>
      <div class="auth-phone-row">
        <div class="auth-prefix">+244</div>
        <input class="auth-input" id="regPhone" type="tel" maxlength="9" placeholder="9XXXXXXXX"/>
      </div>
    </div>
    <div class="auth-input-wrap">
      <label class="auth-input-label">Escolhe um PIN (4 dígitos)</label>
      <div class="auth-pin-row">
        <input class="pin-box" id="r1" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="r2" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="r3" maxlength="1" type="password" inputmode="numeric"/>
        <input class="pin-box" id="r4" maxlength="1" type="password" inputmode="numeric"/>
      </div>
    </div>
    <div class="auth-error" id="regError"></div>
    <button class="auth-btn" onclick="doRegister()">Criar conta</button>
  </div>
</div>

<!-- DRAWER -->
<div class="drawer" id="drawer">
  <div class="drawer-user">
    <div class="drawer-avatar"><img id="drawerAvatar" src="" alt=""/></div>
    <div class="drawer-user-info">
      <div class="drawer-user-id" id="drawerUserId"></div>
      <div class="drawer-user-phone" id="drawerUserPhone"></div>
    </div>
  </div>
  <div class="drawer-header">Menu</div>
  <div class="drawer-item" onclick="drawerGo('config')">
    <svg class="bottom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    Nova configuração
  </div>
  <div class="drawer-item" onclick="drawerGo('ajuda')">
    <svg class="bottom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    Pedido de ajuda
  </div>
</div>

<!-- OVERLAY -->
<div class="overlay" id="overlay"></div>

<!-- APP -->
<div class="app" id="mainApp">
  <div class="topbar">
    <button class="menu-btn" id="menuBtn">
      <div class="icon"><span></span><span></span><span></span></div>
    </button>
    <span class="topbar-title" id="topbarTitle">Início</span>
  </div>

  <!-- HOME -->
  <div class="screen active" id="screenHome">
    <div class="home-greeting">Olá 👋</div>
    <div class="home-sub" id="homeSubtitle">Bem-vindo de volta.</div>
    <div class="home-user-card">
      <div class="home-avatar"><img id="homeAvatar" src="" alt=""/></div>
      <div>
        <div class="home-user-id" id="homeUserId"></div>
        <div class="home-user-phone" id="homeUserPhone"></div>
      </div>
    </div>
    <button class="new-request-btn" onclick="openRequestModal()">Fazer um novo pedido</button>
  </div>

  <!-- USO -->
  <div class="screen" id="screenUso">
    <div class="uso-stat">
      <div class="uso-stat-num" id="configCount">0</div>
      <div class="uso-stat-label">Configurações usadas</div>
    </div>
    <div id="codesContainer"></div>
  </div>

  <!-- AJUDA -->
  <div class="screen" id="screenAjuda" style="padding-bottom:0;">
    <div class="chat-wrap">
      <div class="chat-faq" id="chatFaq">
        <div class="chat-faq-title">Perguntas frequentes</div>
      </div>
      <div class="chat-messages" id="chatMessages"></div>
      <div class="chat-input-row">
        <input class="chat-input" id="chatInput" placeholder="Escreve a tua mensagem..." type="text"/>
        <button class="chat-send-btn" onclick="sendChatMsg()">Enviar</button>
      </div>
    </div>
  </div>

  <!-- CONFIG -->
  <div class="screen" id="screenConfig">
    <div class="config-section-title">Conta</div>
    <button class="config-danger-btn" onclick="openDeleteModal()">Eliminar conta</button>
  </div>

  <!-- ADMIN -->
  <div class="screen" id="screenAdmin">
    <div class="admin-tab-row">
      <button class="admin-tab active" onclick="adminTab('pedidos')">Pedidos</button>
      <button class="admin-tab" onclick="adminTab('users')">Utilizadores</button>
    </div>
    <div id="adminPedidos"></div>
    <div id="adminUsers" style="display:none"></div>
  </div>

  <!-- BOTTOM BAR -->
  <div class="bottom-bar" id="bottomBar">
    <button class="bottom-item active" id="tabHome" onclick="switchScreen('Home')">
      <svg class="bottom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      Início
    </button>
    <button class="bottom-item" id="tabUso" onclick="switchScreen('Uso')">
      <svg class="bottom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      Uso
    </button>
  </div>
</div>

<!-- MODAL PEDIDO -->
<div class="modal-overlay" id="requestModal">
  <div class="modal">
    <div class="modal-title">Novo pedido</div>
    <div class="modal-desc">Descreve o teu pedido. O proprietário será notificado.</div>
    <textarea id="requestText" class="auth-input" rows="4" placeholder="Descreve o teu pedido aqui..." style="resize:none;margin-bottom:16px;"></textarea>
    <button class="modal-btn" style="background:#111;color:#fff;" onclick="submitRequest()">Enviar pedido</button>
    <button class="modal-btn modal-btn-cancel" onclick="closeModal('requestModal')">Cancelar</button>
  </div>
</div>

<!-- MODAL ELIMINAR CONTA -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal">
    <div class="modal-title">Eliminar conta</div>
    <div class="modal-desc">Esta ação é irreversível. Todos os teus dados serão apagados.</div>
    <button class="modal-btn modal-btn-danger" onclick="doDeleteAccount()">Sim, eliminar conta</button>
    <button class="modal-btn modal-btn-cancel" onclick="closeModal('deleteModal')">Cancelar</button>
  </div>
</div>

<script>
  const API = '';
  let currentUser = null;
  let currentScreen = 'Home';

  // ── PIN INPUT AUTO-ADVANCE ──
  function setupPin(ids) {
    ids.forEach((id, i) => {
      const el = document.getElementById(id);
      el.addEventListener('input', () => {
        if (el.value && i < ids.length - 1) document.getElementById(ids[i+1]).focus();
      });
      el.addEventListener('keydown', e => {
        if (e.key === 'Backspace' && !el.value && i > 0) document.getElementById(ids[i-1]).focus();
      });
    });
  }
  setupPin(['p1','p2','p3','p4']);
  setupPin(['r1','r2','r3','r4']);

  function getPin(ids) { return ids.map(id => document.getElementById(id).value).join(''); }
  function clearPin(ids) { ids.map(id => document.getElementById(id).value = ''); }

  // ── AUTH ──
  function showRegister() {
    document.getElementById('authLogin').style.display = 'none';
    document.getElementById('authRegister').style.display = 'block';
  }
  function showLogin() {
    document.getElementById('authRegister').style.display = 'none';
    document.getElementById('authLogin').style.display = 'block';
  }

  async function doLogin() {
    const phone = '+244' + document.getElementById('loginPhone').value.trim();
    const pin = getPin(['p1','p2','p3','p4']);
    const err = document.getElementById('loginError');
    err.style.display = 'none';
    if (pin.length < 4) { err.textContent = 'Introduz o PIN completo'; err.style.display = 'block'; return; }
    try {
      const r = await fetch(API + '/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ phone, pin }) });
      const d = await r.json();
      if (!d.success) { err.textContent = d.error; err.style.display = 'block'; return; }
      currentUser = d.user;
      currentUser.role = d.role;
      enterApp();
    } catch(e) { err.textContent = 'Erro de ligação'; err.style.display = 'block'; }
  }

  async function doRegister() {
    const phone = '+244' + document.getElementById('regPhone').value.trim();
    const pin = getPin(['r1','r2','r3','r4']);
    const err = document.getElementById('regError');
    err.style.display = 'none';
    if (pin.length < 4) { err.textContent = 'Introduz o PIN completo'; err.style.display = 'block'; return; }
    try {
      const r = await fetch(API + '/auth/register', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ phone, pin }) });
      const d = await r.json();
      if (!d.success) { err.textContent = d.error; err.style.display = 'block'; return; }
      currentUser = d.user;
      currentUser.role = 'user';
      enterApp();
    } catch(e) { err.textContent = 'Erro de ligação'; err.style.display = 'block'; }
  }

  function enterApp() {
    const auth = document.getElementById('authScreen');
    auth.style.transition = 'opacity 0.3s';
    auth.style.opacity = '0';
    setTimeout(() => { auth.classList.add('hidden'); auth.style.opacity = ''; }, 300);

    document.getElementById('homeAvatar').src = currentUser.avatar;
    document.getElementById('homeUserId').textContent = currentUser.id;
    document.getElementById('homeUserPhone').textContent = currentUser.phone;
    document.getElementById('drawerAvatar').src = currentUser.avatar;
    document.getElementById('drawerUserId').textContent = currentUser.id;
    document.getElementById('drawerUserPhone').textContent = currentUser.phone;
    document.getElementById('configCount').textContent = currentUser.configs || 0;

    if (currentUser.role === 'admin') {
      document.getElementById('bottomBar').innerHTML += \`
        <button class="bottom-item" id="tabAdmin" onclick="switchScreen('Admin')">
          <svg class="bottom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          ADM
        </button>\`;
    }

    loadCodes();
    loadFAQ();
  }

  // ── DRAWER ──
  const drawerEl = document.getElementById('drawer');
  const overlayEl = document.getElementById('overlay');
  const appEl = document.getElementById('mainApp');

  function toggleDrawer() {
    const open = drawerEl.classList.contains('open');
    drawerEl.classList.toggle('open', !open);
    appEl.classList.toggle('shifted', !open);
    overlayEl.classList.toggle('show', !open);
  }
  function drawerGo(where) {
    toggleDrawer();
    if (where === 'config') switchScreen('Config');
    if (where === 'ajuda') switchScreen('Ajuda');
  }
  document.getElementById('menuBtn').addEventListener('click', toggleDrawer);
  overlayEl.addEventListener('click', toggleDrawer);

  // ── SCREENS ──
  const titles = { Home: 'Início', Uso: 'Uso', Ajuda: 'Ajuda', Config: 'Configurações', Admin: 'Painel ADM' };
  function switchScreen(name) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.bottom-item').forEach(b => b.classList.remove('active'));
    document.getElementById('screen' + name).classList.add('active');
    const tab = document.getElementById('tab' + name);
    if (tab) tab.classList.add('active');
    document.getElementById('topbarTitle').textContent = titles[name] || name;
    currentScreen = name;
    if (name === 'Admin') loadAdmin();
  }

  // ── CÓDIGOS ──
  async function loadCodes() {
    try {
      const r = await fetch(API + '/configs');
      const d = await r.json();
      const container = document.getElementById('codesContainer');
      container.innerHTML = '';
      d.configs.forEach(c => {
        container.innerHTML += \`
          <div class="uso-code-card">
            <div class="uso-code-name">\${c.name}</div>
            <div class="uso-code-block">\${c.code}</div>
            <button class="uso-copy-btn" onclick="copyCode('\${encodeURIComponent(c.code)}', '\${c.id}')">Copiar</button>
          </div>\`;
      });
    } catch(e) {}
  }

  async function copyCode(encodedCode, codeId) {
    const code = decodeURIComponent(encodedCode);
    try { await navigator.clipboard.writeText(code); } catch(e) {}
    if (currentUser) {
      await fetch(API + '/configs/use', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ userId: currentUser.id }) });
      const count = document.getElementById('configCount');
      count.textContent = parseInt(count.textContent) + 1;
    }
  }

  // ── FAQ / CHAT ──
  async function loadFAQ() {
    try {
      const r = await fetch(API + '/help/faq');
      const d = await r.json();
      const faq = document.getElementById('chatFaq');
      d.faq.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'faq-btn';
        btn.textContent = item.question;
        btn.onclick = () => {
          addBubble(item.question, 'user');
          if (item.answer) {
            setTimeout(() => addBubble(item.answer, 'bot'), 400);
          } else {
            setTimeout(() => addBubble('Vou ligar-te com o suporte. Escreve a tua mensagem em baixo.', 'bot'), 400);
          }
        };
        faq.appendChild(btn);
      });
    } catch(e) {}
  }

  function addBubble(text, from) {
    const msgs = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'chat-bubble ' + from;
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  async function sendChatMsg() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    addBubble(msg, 'user');
    input.value = '';
    try {
      await fetch(API + '/help/message', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ userId: currentUser.id, message: msg }) });
      setTimeout(() => addBubble('Mensagem recebida. O suporte irá responder em breve.', 'bot'), 500);
    } catch(e) {}
  }

  document.getElementById('chatInput').addEventListener('keydown', e => { if (e.key === 'Enter') sendChatMsg(); });

  // ── PEDIDO ──
  function openRequestModal() { document.getElementById('requestModal').classList.add('show'); }
  function closeModal(id) { document.getElementById(id).classList.remove('show'); }

  async function submitRequest() {
    const msg = document.getElementById('requestText').value.trim();
    if (!msg) return;
    try {
      await fetch(API + '/requests/new', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ userId: currentUser.id, phone: currentUser.phone, message: msg }) });
      closeModal('requestModal');
      document.getElementById('requestText').value = '';
      addBubble('Pedido enviado com sucesso! O proprietário foi notificado.', 'bot');
      switchScreen('Ajuda');
    } catch(e) {}
  }

  // ── ELIMINAR CONTA ──
  function openDeleteModal() { document.getElementById('deleteModal').classList.add('show'); }

  async function doDeleteAccount() {
    try {
      const r = await fetch(API + '/auth/delete', { method: 'DELETE', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ phone: currentUser.phone, pin: prompt('Confirma o teu PIN') }) });
      const d = await r.json();
      if (d.success) { closeModal('deleteModal'); location.reload(); }
    } catch(e) {}
  }

  // ── ADMIN ──
  async function loadAdmin() {
    try {
      const [rr, ru] = await Promise.all([
        fetch(API + '/admin/requests').then(r => r.json()),
        fetch(API + '/admin/users').then(r => r.json()),
      ]);
      const pedidosEl = document.getElementById('adminPedidos');
      pedidosEl.innerHTML = rr.requests.length === 0 ? '<p style="color:#888;font-size:14px;">Sem pedidos</p>' : '';
      rr.requests.forEach(req => {
        pedidosEl.innerHTML += \`
          <div class="admin-card">
            <div class="admin-card-id">\${req.id} • \${req.phone}</div>
            <div class="admin-card-text">\${req.message}</div>
            <div class="admin-card-meta">
              <span class="admin-status \${req.status}">\${req.status}</span>
              &nbsp;• \${new Date(req.createdAt).toLocaleString('pt')}
            </div>
          </div>\`;
      });
      const usersEl = document.getElementById('adminUsers');
      usersEl.innerHTML = ru.users.length === 0 ? '<p style="color:#888;font-size:14px;">Sem utilizadores</p>' : '';
      ru.users.forEach(u => {
        usersEl.innerHTML += \`
          <div class="admin-card" style="display:flex;align-items:center;gap:12px;">
            <img src="\${u.avatar}" style="width:40px;height:40px;border-radius:50%;background:#eee;"/>
            <div>
              <div class="admin-card-id">\${u.id}</div>
              <div class="admin-card-text">\${u.phone}</div>
              <div class="admin-card-meta">Configs: \${u.configs} • \${new Date(u.createdAt).toLocaleDateString('pt')}</div>
            </div>
          </div>\`;
      });
    } catch(e) {}
  }

  function adminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach((t,i) => t.classList.toggle('active', (tab==='pedidos'&&i===0)||(tab==='users'&&i===1)));
    document.getElementById('adminPedidos').style.display = tab === 'pedidos' ? 'block' : 'none';
    document.getElementById('adminUsers').style.display = tab === 'users' ? 'block' : 'none';
  }
</script>
</body>
</html>`);
});

app.listen(PORT, () => console.log(`Porta ${PORT}`));