import os, re, time, json, threading, hashlib
import requests
from flask import Flask, jsonify, request, abort
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from datetime import datetime, timezone

app = Flask(__name__)

# ── Cache em memória ──────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 900  # 15 min

def cache_get(key):
    e = _cache.get(key)
    if e and time.time() - e[0] < CACHE_TTL:
        return e[1]
    return None

def cache_set(key, data):
    _cache[key] = (time.time(), data)

# ── Self-ping para não adormecer (Render free dorme após 15 min) ──────────────
def self_ping():
    while True:
        time.sleep(600)  # a cada 10 minutos
        try:
            own_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:10000")
            requests.get(f"{own_url}/health", timeout=10)
            print("[PING] self-ping ok")
        except Exception as e:
            print(f"[PING] erro: {e}")

threading.Thread(target=self_ping, daemon=True).start()

# ── Fontes RSS por categoria ─────────────────────────────────────────────────

SOURCES = {
    "world": [
        "https://feeds.bbci.co.uk/portuguese/rss.xml",
        "https://rss.dw.com/rdf/rss-port-all",
        "https://www.dn.pt/rss/mundo.xml",
        "https://www.publico.pt/api/rss/mundo",
    ],
    "technology": [
        "https://feeds.feedburner.com/TecMundo",
        "https://www.tecnoblog.net/feed/",
        "https://olhardigital.com.br/feed/",
        "https://canaltech.com.br/rss/",
    ],
    "health": [
        "https://saude.abril.com.br/feed/",
        "https://www.rtp.pt/noticias/rss/saude",
    ],
    "sports": [
        "https://www.record.pt/rss/desporto.xml",
        "https://esportes.estadao.com.br/rss/todos.xml",
        "https://www.ojogo.pt/rss/desporto.xml",
    ],
    "science": [
        "https://super.abril.com.br/feed/",
        "https://www.nationalgeographicbrasil.com/feed",
        "https://revistagalileu.globo.com/rss.xml",
    ],
    "entertainment": [
        "https://rollingstone.uol.com.br/feed/",
        "https://www.omelete.com.br/rss/artigos",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").strip()
    except:
        return ""

def favicon_url(domain: str) -> str:
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

def clean_text(text: str, max_len: int = 2000) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

def scrape_og_image(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
        soup = BeautifulSoup(r.content, "lxml")
        for attr in [("property", "og:image"), ("name", "twitter:image"),
                     ("property", "og:image:url")]:
            tag = soup.find("meta", {attr[0]: attr[1]})
            if tag and tag.get("content"):
                img = tag["content"].strip()
                if img.startswith("http"):
                    return img
    except:
        pass
    return ""

def scrape_full_content(url: str) -> dict:
    """Extrai conteúdo completo de uma notícia: título, descrição, corpo, imagem, autor, data."""
    result = {
        "title": "", "description": "", "body": "",
        "image_url": "", "author": "", "published_at": "",
        "source_name": "", "source_domain": "", "favicon_url": "",
        "url": url
    }
    try:
        r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        soup = BeautifulSoup(r.content, "lxml")
        domain = get_domain(url)
        result["source_domain"] = domain
        result["favicon_url"]   = favicon_url(domain)
        result["source_name"]   = domain.split(".")[0].capitalize()

        # Título
        for sel in [("meta", {"property": "og:title"}),
                    ("meta", {"name": "twitter:title"}),
                    ("h1", {})]:
            tag = soup.find(*sel)
            if tag:
                result["title"] = clean_text(tag.get("content") or tag.get_text(), 300)
                if result["title"]:
                    break

        # Descrição
        for attr in [("property", "og:description"), ("name", "description"),
                     ("name", "twitter:description")]:
            tag = soup.find("meta", {attr[0]: attr[1]})
            if tag and tag.get("content"):
                result["description"] = clean_text(tag["content"], 600)
                break

        # Imagem
        for attr in [("property", "og:image"), ("name", "twitter:image")]:
            tag = soup.find("meta", {attr[0]: attr[1]})
            if tag and tag.get("content") and tag["content"].startswith("http"):
                result["image_url"] = tag["content"].strip()
                break

        # Autor
        for sel in [("meta", {"name": "author"}), ("meta", {"property": "article:author"})]:
            tag = soup.find(*sel)
            if tag and tag.get("content"):
                result["author"] = clean_text(tag["content"], 100)
                break
        if not result["author"]:
            tag = soup.find(class_=re.compile(r'author|byline', re.I))
            if tag:
                result["author"] = clean_text(tag.get_text(), 100)

        # Data
        for sel in [("meta", {"property": "article:published_time"}),
                    ("time", {})]:
            tag = soup.find(*sel)
            if tag:
                val = tag.get("content") or tag.get("datetime") or tag.get_text()
                if val:
                    result["published_at"] = val.strip()[:50]
                    break

        # Corpo do artigo
        body_candidates = [
            soup.find("article"),
            soup.find(class_=re.compile(r'article-body|post-content|entry-content|story-body', re.I)),
            soup.find(id=re.compile(r'article|content|story', re.I)),
            soup.find("main"),
        ]
        body_tag = next((b for b in body_candidates if b), None)
        if body_tag:
            # Remove scripts, ads, nav
            for bad in body_tag.find_all(["script", "style", "nav", "aside",
                                           "figure", "figcaption", "iframe", "button"]):
                bad.decompose()
            paragraphs = body_tag.find_all("p")
            body_text  = " ".join(clean_text(p.get_text(), 1000) for p in paragraphs if len(p.get_text().strip()) > 40)
            result["body"] = body_text[:5000]
        
        # Se não achou corpo, usa meta description
        if not result["body"] and result["description"]:
            result["body"] = result["description"]

    except Exception as e:
        print(f"[SCRAPE ERROR] {url}: {e}")
    return result

def parse_rss_feed(feed_url: str, category: str, limit: int = 10) -> list:
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")[:limit]

        for item in items:
            title = clean_text(item.find("title").get_text() if item.find("title") else "", 300)
            if not title:
                continue

            link_tag = item.find("link")
            url = ""
            if link_tag:
                url = link_tag.get_text().strip()
                if not url:
                    url = link_tag.next_sibling.strip() if link_tag.next_sibling else ""
            if not url:
                guid = item.find("guid")
                if guid:
                    url = guid.get_text().strip()

            desc_tag = item.find("description") or item.find("summary")
            desc = clean_text(desc_tag.get_text() if desc_tag else "", 600)

            # Imagem
            img = ""
            enc = item.find("enclosure")
            if enc and str(enc.get("type", "")).startswith("image"):
                img = enc.get("url", "")
            if not img:
                for tag_name in ["media:content", "media:thumbnail"]:
                    m = item.find(tag_name)
                    if m:
                        img = m.get("url", "")
                        break
            if not img and desc_tag:
                desc_html = str(desc_tag)
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html)
                if m:
                    img = m.group(1)
            if not img and url:
                img = scrape_og_image(url)

            pub_date = ""
            pd = item.find("pubDate") or item.find("dc:date") or item.find("published")
            if pd:
                pub_date = pd.get_text().strip()

            domain = get_domain(url or feed_url)
            source_name = domain.split(".")[0].capitalize() if domain else "Fonte"

            uid = hashlib.md5((title + url).encode()).hexdigest()[:12]

            articles.append({
                "id": uid,
                "title": title,
                "description": desc,
                "image_url": img,
                "url": url,
                "source_name": source_name,
                "source_domain": domain,
                "favicon_url": favicon_url(domain),
                "category": category,
                "published_at": pub_date,
                "author": "",
                "body": "",
            })
    except Exception as e:
        print(f"[RSS ERROR] {feed_url}: {e}")
    return articles

def fetch_perplexity_news(topic: str = "noticias mundo hoje", limit: int = 8) -> list:
    """Scraping básico do Perplexity para notícias recentes."""
    articles = []
    try:
        url = f"https://www.perplexity.ai/search?q={quote(topic)}&focus=news"
        r   = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")

        # Tenta extrair do __NEXT_DATA__ JSON (Next.js)
        nd = soup.find("script", {"id": "__NEXT_DATA__"})
        if nd:
            try:
                data = json.loads(nd.string or "{}")
                articles = _extract_from_next_data(data, limit)
            except:
                pass

        # Fallback: extrai links de notícias do HTML
        if not articles:
            for a_tag in soup.find_all("a", href=True)[:30]:
                href = a_tag["href"]
                if href.startswith("http") and "perplexity" not in href:
                    title = clean_text(a_tag.get_text(), 200)
                    if len(title) > 20:
                        domain = get_domain(href)
                        articles.append({
                            "id": hashlib.md5(href.encode()).hexdigest()[:12],
                            "title": title,
                            "description": "",
                            "image_url": scrape_og_image(href),
                            "url": href,
                            "source_name": domain.split(".")[0].capitalize(),
                            "source_domain": domain,
                            "favicon_url": favicon_url(domain),
                            "category": "world",
                            "published_at": "",
                            "author": "",
                            "body": "",
                        })
                    if len(articles) >= limit:
                        break
    except Exception as e:
        print(f"[PERPLEXITY] {e}")
    return articles[:limit]

def _extract_from_next_data(obj, limit: int, depth: int = 0) -> list:
    if depth > 8:
        return []
    results = []
    if isinstance(obj, dict):
        for key in ("webResults", "sources", "organic_results", "results", "items", "news"):
            if key in obj and isinstance(obj[key], list):
                for item in obj[key][:limit]:
                    if isinstance(item, dict):
                        title = item.get("name") or item.get("title") or ""
                        url   = item.get("url") or item.get("link") or ""
                        desc  = item.get("snippet") or item.get("description") or ""
                        if title and url:
                            domain = get_domain(url)
                            results.append({
                                "id": hashlib.md5(url.encode()).hexdigest()[:12],
                                "title": clean_text(title, 300),
                                "description": clean_text(desc, 600),
                                "image_url": item.get("image") or item.get("thumbnail") or "",
                                "url": url,
                                "source_name": domain.split(".")[0].capitalize(),
                                "source_domain": domain,
                                "favicon_url": favicon_url(domain),
                                "category": "world",
                                "published_at": item.get("date") or "",
                                "author": "",
                                "body": "",
                            })
        for v in obj.values():
            results.extend(_extract_from_next_data(v, limit - len(results), depth + 1))
            if len(results) >= limit:
                break
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_extract_from_next_data(item, limit - len(results), depth + 1))
            if len(results) >= limit:
                break
    return results

# ── Pré-cache ao arrancar ─────────────────────────────────────────────────────

def warm_cache():
    """Pré-carrega todas as categorias em background para resposta imediata."""
    for cat in SOURCES.keys():
        try:
            key = f"news_{cat}_pt_20"
            if not cache_get(key):
                arts = _fetch_category(cat, "pt", 20)
                cache_set(key, arts)
                print(f"[WARM] categoria '{cat}' carregada: {len(arts)} artigos")
        except Exception as e:
            print(f"[WARM ERROR] {cat}: {e}")
        time.sleep(2)  # pausa entre feeds para não sobrecarregar

def _fetch_category(category: str, lang: str, limit: int) -> list:
    feed_urls = SOURCES.get(category, SOURCES["world"])
    articles  = []
    per_feed  = max(5, limit // len(feed_urls) + 3)

    for feed_url in feed_urls:
        articles.extend(parse_rss_feed(feed_url, category, limit=per_feed))
        if len(articles) >= limit:
            break

    # Enriquece com Perplexity se necessário
    if len(articles) < 5:
        topic = f"noticias {category} recentes hoje"
        articles.extend(fetch_perplexity_news(topic, limit=8))

    # Deduplica por título
    seen, unique = set(), []
    for a in articles:
        key = a["title"][:60].lower()
        if key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    return unique[:limit]

# Arrancar warm-up em background
threading.Thread(target=warm_cache, daemon=True).start()

# ── Rotas ─────────────────────────────────────────────────────────────────────

@app.route("/news")
def get_news():
    category = request.args.get("category", "world")
    lang     = request.args.get("lang", "pt")
    limit    = min(int(request.args.get("limit", 20)), 50)
    force    = request.args.get("force", "0") == "1"

    cache_key = f"news_{category}_{lang}_{limit}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

    articles = _fetch_category(category, lang, limit)
    cache_set(cache_key, articles)
    return jsonify(articles)

@app.route("/article")
def get_article():
    """Retorna conteúdo completo de uma notícia dado o URL."""
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        abort(400, "url obrigatório")

    cache_key = f"article_{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    article = scrape_full_content(url)
    cache_set(cache_key, article)
    return jsonify(article)

@app.route("/health")
def health():
    categories_cached = [k for k in _cache.keys() if k.startswith("news_")]
    return jsonify({
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "cached_categories": len(categories_cached),
        "total_cache_keys": len(_cache),
    })

@app.route("/")
def index():
    return jsonify({
        "name": "GlobeNews API",
        "version": "2.0",
        "endpoints": {
            "/news": "?category=world|technology|health|sports|science|entertainment&lang=pt&limit=20",
            "/article": "?url=<url_da_noticia>",
            "/health": "status da API",
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)