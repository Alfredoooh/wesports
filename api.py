from flask import Flask, jsonify, request, abort
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
import requests
import random
import os

app = Flask(__name__)
CORS(app)

BASE = "https://api.sofascore.com/api/v1"
IMG  = "https://api.sofascore.com/api/v1"
SITE = "https://www.sofascore.com"

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

SESSION = requests.Session()

def get(path):
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent":         ua,
        "Referer":            "https://www.sofascore.com/",
        "Origin":             "https://www.sofascore.com",
        "Accept":             "application/json, text/plain, */*",
        "Accept-Language":    "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding":    "gzip, deflate, br",
        "Cache-Control":      "no-cache",
        "Pragma":             "no-cache",
        "Sec-Fetch-Dest":     "empty",
        "Sec-Fetch-Mode":     "cors",
        "Sec-Fetch-Site":     "same-origin",
        "Sec-Ch-Ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile":   "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Connection":         "keep-alive",
    }
    r = SESSION.get(f"{BASE}{path}", headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def get_safe(path, fallback=None):
    try:
        return get(path)
    except Exception:
        return fallback if fallback is not None else {}

def ts(timestamp):
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def agora():
    return datetime.now(timezone.utc)

def equipa(t):
    if not t:
        return None
    tid  = t.get("id")
    slug = t.get("slug", "")
    sp   = (t.get("sport") or {}).get("slug", "football")
    return {
        "id":         tid,
        "nome":       t.get("name"),
        "nome_curto": t.get("shortName"),
        "codigo":     t.get("nameCode"),
        "slug":       slug,
        "genero":     t.get("gender"),
        "nacional":   t.get("national"),
        "pais":       (t.get("country") or {}).get("name"),
        "cores":      t.get("teamColors"),
        "logo_url":   f"{IMG}/team/{tid}/image" if tid else None,
        "pagina_url": f"{SITE}/{sp}/team/{slug}/{tid}" if tid else None,
    }

def torneio_info(trn):
    if not trn:
        return None
    ut  = trn.get("uniqueTournament") or {}
    cat = trn.get("category") or {}
    uid = ut.get("id")
    return {
        "id":          trn.get("id"),
        "nome":        trn.get("name"),
        "slug":        trn.get("slug"),
        "unique_id":   uid,
        "unique_nome": ut.get("name"),
        "unique_slug": ut.get("slug"),
        "logo_url":    f"{IMG}/unique-tournament/{uid}/image" if uid else None,
        "pais":        cat.get("name"),
        "pais_slug":   cat.get("slug"),
        "pais_flag":   cat.get("flag"),
        "alpha2":      cat.get("alpha2"),
        "sport":       (cat.get("sport") or {}).get("slug"),
    }

def montar_jogo(e):
    eid    = e.get("id")
    slug_c = (e.get("homeTeam") or {}).get("slug", "")
    slug_f = (e.get("awayTeam") or {}).get("slug", "")
    custom = e.get("customId", "")
    sport  = ((e.get("homeTeam") or {}).get("sport") or {}).get("slug", "football")
    venue  = e.get("venue") or {}
    stad   = venue.get("stadium") or {}
    city   = venue.get("city") or {}
    ref    = e.get("referee") or {}
    ri     = e.get("roundInfo") or {}
    season = e.get("season") or {}
    status = e.get("status") or {}
    hs     = e.get("homeScore") or {}
    af     = e.get("awayScore") or {}
    return {
        "id":            eid,
        "custom_id":     custom,
        "sport":         sport,
        "url_sofascore": f"{SITE}/{sport}/{slug_c}-{slug_f}/{custom}" if custom else None,
        "torneio":       torneio_info(e.get("tournament")),
        "temporada":     {"id": season.get("id"), "nome": season.get("name"), "ano": season.get("year")},
        "rodada":        {"numero": ri.get("round"), "nome": ri.get("name")},
        "status":        {"codigo": status.get("code"), "descricao": status.get("description"), "tipo": status.get("type")},
        "vencedor":      e.get("winnerCode"),
        "casa":          equipa(e.get("homeTeam")),
        "fora":          equipa(e.get("awayTeam")),
        "placar": {
            "casa": {"atual": hs.get("current"), "intervalo": hs.get("period1"), "parte2": hs.get("period2"), "prolongamento": hs.get("overtime"), "penaltis": hs.get("penalties")},
            "fora": {"atual": af.get("current"), "intervalo": af.get("period1"), "parte2": af.get("period2"), "prolongamento": af.get("overtime"), "penaltis": af.get("penalties")},
        },
        "estadio":  {"nome": stad.get("name"), "capacidade": stad.get("capacity"), "cidade": city.get("name")},
        "arbitro":  {"id": ref.get("id"), "nome": ref.get("name"), "slug": ref.get("slug"), "pais": (ref.get("country") or {}).get("name")},
        "inicio_timestamp": e.get("startTimestamp"),
        "inicio_formatado": ts(e.get("startTimestamp")),
    }

SPORTS = [
    "football","basketball","tennis","ice-hockey","baseball",
    "handball","volleyball","rugby","cricket","mma",
    "american-football","esports","table-tennis","badminton",
    "futsal","beach-volley","waterpolo","cycling","snooker",
    "darts","aussie-rules","bandy","floorball","motorsport",
]

LIGAS = [
    {"id": 7,    "nome": "UEFA Champions League"},
    {"id": 679,  "nome": "UEFA Europa League"},
    {"id": 329,  "nome": "UEFA Conference League"},
    {"id": 17,   "nome": "Premier League (Inglaterra)"},
    {"id": 32,   "nome": "Championship (Inglaterra)"},
    {"id": 36,   "nome": "League One (Inglaterra)"},
    {"id": 1091, "nome": "FA Cup"},
    {"id": 8,    "nome": "La Liga (Espanha)"},
    {"id": 11,   "nome": "Segunda División (Espanha)"},
    {"id": 23,   "nome": "Serie A (Itália)"},
    {"id": 53,   "nome": "Serie B (Itália)"},
    {"id": 560,  "nome": "Coppa Italia"},
    {"id": 35,   "nome": "Bundesliga (Alemanha)"},
    {"id": 44,   "nome": "2. Bundesliga (Alemanha)"},
    {"id": 572,  "nome": "DFB Pokal"},
    {"id": 34,   "nome": "Ligue 1 (França)"},
    {"id": 182,  "nome": "Ligue 2 (França)"},
    {"id": 238,  "nome": "Primeira Liga (Portugal)"},
    {"id": 307,  "nome": "Taça de Portugal"},
    {"id": 37,   "nome": "Eredivisie (Holanda)"},
    {"id": 40,   "nome": "Super Lig (Turquia)"},
    {"id": 203,  "nome": "Premier Liga (Rússia)"},
    {"id": 242,  "nome": "Ekstraklasa (Polónia)"},
    {"id": 116,  "nome": "Superliga (Dinamarca)"},
    {"id": 955,  "nome": "Allsvenskan (Suécia)"},
    {"id": 325,  "nome": "Eliteserien (Noruega)"},
    {"id": 418,  "nome": "Super League (Suíça)"},
    {"id": 406,  "nome": "Bundesliga (Áustria)"},
    {"id": 187,  "nome": "Super League (Grécia)"},
    {"id": 508,  "nome": "Premiership (Escócia)"},
    {"id": 373,  "nome": "Liga Premier (Israel)"},
    {"id": 533,  "nome": "Nemzeti Bajnokság (Hungria)"},
    {"id": 521,  "nome": "Liga MX (México)"},
    {"id": 474,  "nome": "Liga de Expansión MX"},
    {"id": 390,  "nome": "Brasileirão Série B"},
    {"id": 384,  "nome": "Copa Libertadores"},
    {"id": 480,  "nome": "Copa Sudamericana"},
    {"id": 288,  "nome": "Copa do Brasil"},
    {"id": 600,  "nome": "J1 League (Japão)"},
    {"id": 573,  "nome": "K League 1 (Coreia do Sul)"},
    {"id": 481,  "nome": "Chinese Super League"},
    {"id": 188,  "nome": "Indian Super League"},
    {"id": 299,  "nome": "CAF Champions League"},
    {"id": 16,   "nome": "UEFA Nations League"},
]

LIGAS_IDS_CONFIRMADOS = [
    7, 679, 329, 17, 8, 23, 35, 34, 238, 955,
    242, 325, 521, 384, 480, 600, 573, 481, 40,
    37, 508, 203, 116, 418, 188, 299, 16, 288, 32,
]

@app.route("/jogos/ao-vivo")
def jogos_ao_vivo():
    sport = request.args.get("sport", "football")
    data  = get(f"/sport/{sport}/events/live")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogos/hoje")
def jogos_hoje():
    sport = request.args.get("sport", "football")
    hoje  = agora().strftime("%Y-%m-%d")
    data  = get(f"/sport/{sport}/scheduled-events/{hoje}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogos/amanha")
def jogos_amanha():
    sport  = request.args.get("sport", "football")
    amanha = (agora() + timedelta(days=1)).strftime("%Y-%m-%d")
    data   = get(f"/sport/{sport}/scheduled-events/{amanha}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogos/ontem")
def jogos_ontem():
    sport = request.args.get("sport", "football")
    ontem = (agora() - timedelta(days=1)).strftime("%Y-%m-%d")
    data  = get(f"/sport/{sport}/scheduled-events/{ontem}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogos/data/<string:data>")
def jogos_data(data):
    sport = request.args.get("sport", "football")
    d     = get(f"/sport/{sport}/scheduled-events/{data}")
    return jsonify([montar_jogo(e) for e in d.get("events", [])])

@app.route("/jogo/<int:eid>")
def detalhes_jogo(eid):
    data = get(f"/event/{eid}")
    return jsonify(montar_jogo(data["event"]))

@app.route("/jogo/<int:eid>/eventos")
def eventos_jogo(eid):
    data   = get(f"/event/{eid}/incidents")
    result = []
    for inc in data.get("incidents", []):
        pl  = inc.get("player") or {}
        pl2 = inc.get("playerIn") or {}
        pl3 = inc.get("playerOut") or {}
        result.append({
            "tipo":          inc.get("incidentType"),
            "classe":        inc.get("incidentClass"),
            "minuto":        inc.get("time"),
            "minuto_extra":  inc.get("addedTime"),
            "equipa":        "casa" if inc.get("isHome") else "fora",
            "jogador":       {"id": pl.get("id"),  "nome": pl.get("name"),  "slug": pl.get("slug")} if pl  else None,
            "jogador_entra": {"id": pl2.get("id"), "nome": pl2.get("name")}                         if pl2 else None,
            "jogador_sai":   {"id": pl3.get("id"), "nome": pl3.get("name")}                         if pl3 else None,
            "assistencia":   (inc.get("assist1") or {}).get("name"),
            "descricao":     inc.get("description"),
        })
    return jsonify(result)

@app.route("/jogo/<int:eid>/estatisticas")
def estatisticas_jogo(eid):
    data = get(f"/event/{eid}/statistics")
    return jsonify(data.get("statistics", []))

@app.route("/jogo/<int:eid>/escalacoes")
def escalacoes(eid):
    data   = get(f"/event/{eid}/lineups")
    result = {}
    for lado in ["home", "away"]:
        info = data.get(lado) or {}
        jogs = info.get("players", [])
        result[lado] = {
            "formacao": info.get("formation"),
            "jogadores": [{
                "id":            p["player"]["id"],
                "nome":          p["player"]["name"],
                "slug":          p["player"].get("slug"),
                "posicao":       p.get("position"),
                "posicao_abrev": p.get("positionName"),
                "numero":        p.get("shirtNumber"),
                "titular":       not p.get("substitute", True),
                "capitao":       p.get("captain", False),
                "foto_url":      f"{IMG}/player/{p['player']['id']}/image",
                "rating":        (p.get("statistics") or {}).get("rating"),
            } for p in jogs],
        }
    return jsonify(result)

@app.route("/jogo/<int:eid>/h2h")
def h2h(eid):
    data = get(f"/event/{eid}/h2h")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogo/<int:eid>/odds")
def odds(eid):
    data = get_safe(f"/event/{eid}/odds/1/all", {})
    return jsonify(data)

@app.route("/jogo/<int:eid>/media")
def media_jogo(eid):
    data = get_safe(f"/event/{eid}/highlights", {})
    return jsonify(data.get("highlights", []))

@app.route("/jogo/<int:eid>/momentum")
def momentum_jogo(eid):
    return jsonify(get_safe(f"/event/{eid}/graph", {}))

@app.route("/jogo/<int:eid>/votos")
def votos_jogo(eid):
    return jsonify(get_safe(f"/event/{eid}/votes", {}))

def _fmt_torneio(trn):
    tid = trn.get("id")
    cat = trn.get("category") or {}
    return {
        "id":              tid,
        "nome":            trn.get("name"),
        "slug":            trn.get("slug"),
        "logo_url":        f"{IMG}/unique-tournament/{tid}/image",
        "pais":            cat.get("name"),
        "alpha2":          cat.get("alpha2"),
        "flag":            cat.get("flag"),
        "sport":           (cat.get("sport") or {}).get("slug"),
        "temporada_atual": trn.get("currentSeason"),
        "seguidores":      trn.get("userCount"),
    }

@app.route("/ligas/lista")
def ligas_lista():
    return jsonify(LIGAS)

@app.route("/ligas/populares")
def ligas_populares():
    result = []
    seen   = set()
    for tid in LIGAS_IDS_CONFIRMADOS:
        if tid in seen:
            continue
        seen.add(tid)
        d  = get_safe(f"/uniquetournament/{tid}")
        ut = d.get("uniqueTournament") or {}
        if not ut.get("id"):
            continue
        cat = ut.get("category") or {}
        uid = ut.get("id")
        result.append({
            "id":              uid,
            "nome":            ut.get("name"),
            "slug":            ut.get("slug"),
            "logo_url":        f"{IMG}/unique-tournament/{uid}/image",
            "pais":            cat.get("name"),
            "alpha2":          cat.get("alpha2"),
            "sport":           (cat.get("sport") or {}).get("slug"),
            "temporada_atual": ut.get("currentSeason"),
            "seguidores":      ut.get("userCount"),
            "titulo_atual":    (ut.get("titleHolder") or {}).get("name") if ut.get("titleHolder") else None,
        })
    return jsonify(result)

@app.route("/ligas/ativas/<string:sport>")
def ligas_ativas(sport):
    hoje = agora().strftime("%Y-%m-%d")
    data = get(f"/sport/{sport}/tournament/active/{hoje}")
    tns  = sorted(
        data.get("uniqueTournaments", []),
        key=lambda x: x.get("userCount") or 0,
        reverse=True,
    )
    return jsonify([_fmt_torneio(t) for t in tns])

@app.route("/ligas/categorias/<string:sport>")
def ligas_categorias(sport):
    data   = get(f"/sport/{sport}/categories")
    result = []
    for cat in data.get("categories", []):
        cid = cat.get("id")
        result.append({
            "id":     cid,
            "nome":   cat.get("name"),
            "slug":   cat.get("slug"),
            "flag":   cat.get("flag"),
            "alpha2": cat.get("alpha2"),
            "sport":  (cat.get("sport") or {}).get("slug"),
        })
    return jsonify(result)

@app.route("/torneio/<int:tid>/info")
def torneio_info_detalhado(tid):
    data = get(f"/uniquetournament/{tid}")
    ut   = data.get("uniqueTournament") or {}
    cat  = ut.get("category") or {}
    th   = ut.get("titleHolder") or {}
    mt   = ut.get("mostTitles") or {}
    return jsonify({
        "id":                tid,
        "nome":              ut.get("name"),
        "slug":              ut.get("slug"),
        "logo_url":          f"{IMG}/unique-tournament/{tid}/image",
        "pais":              cat.get("name"),
        "sport":             (cat.get("sport") or {}).get("slug"),
        "temporada_atual":   ut.get("currentSeason"),
        "tem_estatisticas":  ut.get("hasEventPlayerStatistics"),
        "tem_grafico":       ut.get("hasPositionGraph"),
        "seguidores":        ut.get("userCount"),
        "titulo_atual":      th.get("name"),
        "titulo_temporadas": ut.get("titleHolderTitles"),
        "mais_titulos":      mt.get("name"),
        "mais_titulos_num":  ut.get("mostTitlesCount"),
    })

@app.route("/torneio/<int:tid>/temporadas")
def temporadas_torneio(tid):
    data = get(f"/uniquetournament/{tid}/seasons")
    return jsonify(data.get("seasons", []))

@app.route("/torneio/<int:tid>/temporada/<int:sid>/tabela")
def tabela(tid, sid):
    tipo = request.args.get("tipo", "total")
    data = get(f"/uniquetournament/{tid}/season/{sid}/standings/{tipo}")
    rows = (data.get("standings") or [{}])[0].get("rows", [])
    return jsonify([{
        "posicao":      row["position"],
        "clube":        row["team"]["name"],
        "clube_id":     row["team"]["id"],
        "clube_slug":   row["team"].get("slug"),
        "codigo":       row["team"].get("nameCode"),
        "logo_url":     f"{IMG}/team/{row['team']['id']}/image",
        "jogos":        row["matches"],
        "vitorias":     row["wins"],
        "empates":      row["draws"],
        "derrotas":     row["losses"],
        "golos_pro":    row["scoresFor"],
        "golos_contra": row["scoresAgainst"],
        "saldo":        row["scoresFor"] - row["scoresAgainst"],
        "pontos":       row["points"],
        "promocao":     (row.get("promotion") or {}).get("text"),
        "descricao":    row.get("descriptions", []),
    } for row in rows])

@app.route("/torneio/<int:tid>/temporada/<int:sid>/jogos")
def jogos_torneio(tid, sid):
    pagina = request.args.get("pagina", "0")
    data   = get(f"/uniquetournament/{tid}/season/{sid}/events/last/{pagina}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/torneio/<int:tid>/temporada/<int:sid>/jogos/proximos")
def jogos_torneio_proximos(tid, sid):
    pagina = request.args.get("pagina", "0")
    data   = get(f"/uniquetournament/{tid}/season/{sid}/events/next/{pagina}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/torneio/<int:tid>/temporada/<int:sid>/jogos/rodada/<int:rodada>")
def jogos_rodada(tid, sid, rodada):
    data = get(f"/uniquetournament/{tid}/season/{sid}/events/round/{rodada}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/torneio/<int:tid>/temporada/<int:sid>/artilheiros")
def artilheiros(tid, sid):
    data   = get(f"/uniquetournament/{tid}/season/{sid}/top-players/goals")
    result = []
    for item in data.get("topPlayers", []):
        pl  = item.get("player") or {}
        t   = item.get("team") or {}
        pid = pl.get("id")
        result.append({
            "jogador_id":   pid,
            "nome":         pl.get("name"),
            "slug":         pl.get("slug"),
            "foto_url":     f"{IMG}/player/{pid}/image" if pid else None,
            "clube":        t.get("name"),
            "clube_logo":   f"{IMG}/team/{t.get('id')}/image" if t.get("id") else None,
            "golos":        (item.get("statistics") or {}).get("goals"),
            "assistencias": (item.get("statistics") or {}).get("goalAssist"),
            "jogos":        (item.get("statistics") or {}).get("appearances"),
        })
    return jsonify(result)

@app.route("/torneio/<int:tid>/temporada/<int:sid>/assistentes")
def assistentes(tid, sid):
    data   = get(f"/uniquetournament/{tid}/season/{sid}/top-players/assists")
    result = []
    for item in data.get("topPlayers", []):
        pl  = item.get("player") or {}
        t   = item.get("team") or {}
        pid = pl.get("id")
        result.append({
            "jogador_id":   pid,
            "nome":         pl.get("name"),
            "foto_url":     f"{IMG}/player/{pid}/image" if pid else None,
            "clube":        t.get("name"),
            "assistencias": (item.get("statistics") or {}).get("goalAssist"),
            "golos":        (item.get("statistics") or {}).get("goals"),
        })
    return jsonify(result)

@app.route("/torneio/<int:tid>/temporada/<int:sid>/melhores-ratings")
def melhores_ratings(tid, sid):
    data   = get_safe(f"/uniquetournament/{tid}/season/{sid}/top-players/rating", {})
    result = []
    for item in data.get("topPlayers", []):
        pl  = item.get("player") or {}
        t   = item.get("team") or {}
        pid = pl.get("id")
        result.append({
            "jogador_id": pid,
            "nome":       pl.get("name"),
            "foto_url":   f"{IMG}/player/{pid}/image" if pid else None,
            "clube":      t.get("name"),
            "rating":     (item.get("statistics") or {}).get("rating"),
            "jogos":      (item.get("statistics") or {}).get("appearances"),
        })
    return jsonify(result)

@app.route("/clube/<int:tid>")
def dados_clube(tid):
    data  = get(f"/team/{tid}")
    t     = data["team"]
    venue = t.get("venue") or {}
    stad  = venue.get("stadium") or {}
    city  = venue.get("city") or {}
    sport = (t.get("sport") or {}).get("slug", "football")
    slug  = t.get("slug", "")
    return jsonify({
        "id":                tid,
        "nome":              t["name"],
        "nome_curto":        t.get("shortName"),
        "codigo":            t.get("nameCode"),
        "slug":              slug,
        "genero":            t.get("gender"),
        "nacional":          t.get("national"),
        "pais":              (t.get("country") or {}).get("name"),
        "alpha2":            (t.get("country") or {}).get("alpha2"),
        "fundado_timestamp": t.get("foundationDateTimestamp"),
        "fundado":           ts(t.get("foundationDateTimestamp")),
        "cores":             t.get("teamColors"),
        "estadio":           {"nome": stad.get("name"), "capacidade": stad.get("capacity"), "cidade": city.get("name")},
        "logo_url":          f"{IMG}/team/{tid}/image",
        "pagina_url":        f"{SITE}/{sport}/team/{slug}/{tid}",
        "seguidores":        t.get("userCount"),
        "manager":           (t.get("manager") or {}).get("name"),
    })

@app.route("/clube/<int:tid>/jogos/proximos")
def jogos_proximos(tid):
    pagina = request.args.get("pagina", "0")
    data   = get(f"/team/{tid}/events/next/{pagina}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/clube/<int:tid>/jogos/passados")
def jogos_passados(tid):
    pagina = request.args.get("pagina", "0")
    data   = get(f"/team/{tid}/events/last/{pagina}")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/clube/<int:tid>/jogadores")
def jogadores_clube(tid):
    data   = get(f"/team/{tid}/players")
    result = []
    for p in data.get("players", []):
        pl  = p["player"]
        pid = pl.get("id")
        result.append({
            "id":              pid,
            "nome":            pl["name"],
            "nome_curto":      pl.get("shortName"),
            "slug":            pl.get("slug"),
            "posicao":         pl.get("position"),
            "numero":          p.get("shirtNumber"),
            "nacionalidade":   (pl.get("country") or {}).get("name"),
            "alpha2":          (pl.get("country") or {}).get("alpha2"),
            "idade":           pl.get("age"),
            "altura":          pl.get("height"),
            "data_nascimento": ts(pl.get("dateOfBirthTimestamp")),
            "foto_url":        f"{IMG}/player/{pid}/image" if pid else None,
        })
    return jsonify(result)

@app.route("/clube/<int:tid>/transferencias")
def transferencias_clube(tid):
    data   = get(f"/team/{tid}/transfers")
    result = {"entradas": [], "saidas": []}
    for tr in data.get("transfersIn", []):
        pl  = tr.get("player") or {}
        pid = pl.get("id")
        result["entradas"].append({
            "jogador_id": pid,
            "nome":       pl.get("name"),
            "foto_url":   f"{IMG}/player/{pid}/image" if pid else None,
            "de":         (tr.get("transferFrom") or {}).get("name"),
            "valor":      tr.get("transferFeeDescription"),
            "data":       ts(tr.get("transferDateTimestamp")),
        })
    for tr in data.get("transfersOut", []):
        pl  = tr.get("player") or {}
        pid = pl.get("id")
        result["saidas"].append({
            "jogador_id": pid,
            "nome":       pl.get("name"),
            "foto_url":   f"{IMG}/player/{pid}/image" if pid else None,
            "para":       (tr.get("transferTo") or {}).get("name"),
            "valor":      tr.get("transferFeeDescription"),
            "data":       ts(tr.get("transferDateTimestamp")),
        })
    return jsonify(result)

@app.route("/clube/<int:tid>/estatisticas/<int:utid>/temporada/<int:sid>")
def estatisticas_clube(tid, utid, sid):
    data = get_safe(f"/team/{tid}/unique-tournament/{utid}/season/{sid}/statistics/overall", {})
    return jsonify(data)

@app.route("/jogador/<int:pid>")
def jogador(pid):
    data = get(f"/player/{pid}")
    pl   = data["player"]
    t    = pl.get("team") or {}
    tid2 = t.get("id")
    return jsonify({
        "id":              pl["id"],
        "nome":            pl["name"],
        "nome_curto":      pl.get("shortName"),
        "slug":            pl.get("slug"),
        "posicao":         pl.get("position"),
        "numero":          pl.get("jerseyNumber"),
        "nacionalidade":   (pl.get("country") or {}).get("name"),
        "idade":           pl.get("age"),
        "altura":          pl.get("height"),
        "pe_preferido":    pl.get("preferredFoot"),
        "data_nascimento": ts(pl.get("dateOfBirthTimestamp")),
        "clube_atual":     {"id": tid2, "nome": t.get("name"), "slug": t.get("slug"), "logo_url": f"{IMG}/team/{tid2}/image" if tid2 else None},
        "foto_url":        f"{IMG}/player/{pl['id']}/image",
        "seguidores":      pl.get("userCount"),
        "aposentado":      pl.get("retired", False),
    })

@app.route("/jogador/<int:pid>/estatisticas/<int:tid>/temporada/<int:sid>")
def estatisticas_jogador(pid, tid, sid):
    data = get(f"/player/{pid}/unique-tournament/{tid}/season/{sid}/statistics/overall")
    return jsonify(data)

@app.route("/jogador/<int:pid>/transferencias")
def transferencias_jogador(pid):
    data = get(f"/player/{pid}/transfer-history")
    return jsonify(data)

@app.route("/jogador/<int:pid>/jogos/recentes")
def jogos_recentes_jogador(pid):
    data = get(f"/player/{pid}/events/last/0")
    return jsonify([montar_jogo(e) for e in data.get("events", [])])

@app.route("/jogador/<int:pid>/heatmap/<int:tid>/temporada/<int:sid>")
def heatmap_jogador(pid, tid, sid):
    return jsonify(get_safe(f"/player/{pid}/unique-tournament/{tid}/season/{sid}/heatmap/overall", {}))

@app.route("/arbitro/<int:rid>")
def arbitro(rid):
    data = get(f"/referee/{rid}")
    r    = data.get("referee") or {}
    return jsonify({
        "id":        r.get("id"),
        "nome":      r.get("name"),
        "slug":      r.get("slug"),
        "pais":      (r.get("country") or {}).get("name"),
        "foto_url":  f"{IMG}/referee/{rid}/image",
        "jogos":     r.get("matches"),
        "amarelos":  r.get("yellowCards"),
        "vermelhos": r.get("redCards"),
    })

@app.route("/pesquisar/<string:query>")
def pesquisar(query):
    data    = get(f"/search/all/?q={query}&page=0")
    img_map = {"team": "team", "player": "player", "uniqueTournament": "unique-tournament"}
    result  = []
    for r in data.get("results", []):
        ent  = r.get("entity") or {}
        tipo = r.get("type")
        eid2 = ent.get("id")
        ikey = img_map.get(tipo, tipo)
        result.append({
            "tipo":     tipo,
            "id":       eid2,
            "nome":     ent.get("name"),
            "slug":     ent.get("slug"),
            "pais":     (ent.get("country") or {}).get("name"),
            "logo_url": f"{IMG}/{ikey}/{eid2}/image" if ikey and eid2 else None,
        })
    return jsonify(result)

@app.route("/sports")
def sports():
    return jsonify(SPORTS)

@app.route("/")
def index():
    rotas = []
    for rule in app.url_map.iter_rules():
        rotas.append({
            "rota":    str(rule),
            "metodos": [m for m in rule.methods if m not in ("HEAD", "OPTIONS")],
        })
    return jsonify(sorted(rotas, key=lambda x: x["rota"]))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)