import os, re, time, json, threading, hashlib
import requests
from flask import Flask, jsonify, request, abort
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timezone

app = Flask(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 900  # 15 min

def cache_get(key):
    e = _cache.get(key)
    if e and time.time() - e[0] < CACHE_TTL:
        return e[1]
    return None

def cache_set(key, data):
    _cache[key] = (time.time(), data)

# ── Self-ping (Render free tier) ──────────────────────────────────────────────
def self_ping():
    while True:
        time.sleep(600)
        try:
            own_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:10000")
            requests.get(f"{own_url}/health", timeout=10)
            print("[PING] ok")
        except Exception as e:
            print(f"[PING] erro: {e}")

threading.Thread(target=self_ping, daemon=True).start()

# ── Fontes RSS — 100% internacionais ─────────────────────────────────────────
SOURCES = {
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",           # BBC World
        "https://www.aljazeera.com/xml/rss/all.xml",             # Al Jazeera
        "https://feeds.skynews.com/feeds/rss/world.xml",         # Sky News World
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",# NYT World
        "https://www.theguardian.com/world/rss",                  # The Guardian World
        "http://rss.cnn.com/rss/edition_world.rss",              # CNN World
        "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en&gl=US&ceid=US:en", # Reuters via GNews
        "https://feeds.washingtonpost.com/rss/world",            # WashPost World
        "https://www.independent.co.uk/news/world/rss",          # The Independent World
        "https://feeds.bbci.co.uk/news/rss.xml",                 # BBC Top Stories
    ],
    "technology": [
        "https://www.theverge.com/rss/index.xml",                # The Verge
        "https://techcrunch.com/feed/",                          # TechCrunch
        "https://www.wired.com/feed/rss",                        # Wired
        "https://feeds.arstechnica.com/arstechnica/index/",      # Ars Technica
        "https://www.engadget.com/rss.xml",                      # Engadget
        "https://www.cnet.com/rss/all/",                         # CNET
        "https://feeds.bbci.co.uk/news/technology/rss.xml",      # BBC Tech
        "https://venturebeat.com/feed/",                         # VentureBeat
        "https://www.theregister.com/headlines.atom",            # The Register
        "https://feeds.skynews.com/feeds/rss/technology.xml",    # Sky News Tech
    ],
    "science": [
        "https://www.sciencedaily.com/rss/all.xml",              # ScienceDaily
        "https://www.nasa.gov/news-release/feed/",               # NASA
        "https://www.newscientist.com/feed/home/",               # New Scientist
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", # BBC Science
        "https://feeds.arstechnica.com/arstechnica/science/",    # Ars Technica Science
        "https://www.space.com/feeds.xml",                       # Space.com
        "https://www.wired.com/category/science/feed",           # Wired Science
        "https://www.theguardian.com/science/rss",               # Guardian Science
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", # NYT Science
        "https://universetoday.com/feed",                        # Universe Today
    ],
    "health": [
        "https://feeds.bbci.co.uk/news/health/rss.xml",          # BBC Health
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",# NYT Health
        "https://www.theguardian.com/society/health/rss",        # Guardian Health
        "https://feeds.skynews.com/feeds/rss/health.xml",        # Sky News Health
        "https://www.who.int/feeds/entity/news/en/rss.xml",      # WHO
        "https://www.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",# WebMD
        "https://newsinhealth.nih.gov/syndication/rss",          # NIH
        "https://www.medicalnewstoday.com/rss/medicalnewstoday", # Medical News Today
        "https://feeds.arstechnica.com/arstechnica/health/",     # Ars Technica Health
        "https://www.sciencedaily.com/rss/health_medicine/",     # ScienceDaily Health
    ],
    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",                # BBC Sport
        "https://www.espn.com/espn/rss/news.xml",                # ESPN
        "https://www.skysports.com/rss/12040",                   # Sky Sports
        "https://www.theguardian.com/sport/rss",                 # Guardian Sport
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",# NYT Sports
        "https://feeds.skynews.com/feeds/rss/sports.xml",        # Sky News Sport
        "https://www.marca.com/rss/portada.xml",                 # Marca (football global)
        "https://www.eurosport.com/rss/news/",                   # Eurosport
        "https://www.cbssports.com/rss/headlines/",              # CBS Sports
        "https://feeds.bbci.co.uk/sport/football/rss.xml",       # BBC Football
    ],
    "entertainment": [
        "https://feeds.skynews.com/feeds/rss/entertainment.xml", # Sky News Entertainment
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", # BBC Entertainment
        "https://variety.com/feed/",                             # Variety
        "https://www.hollywoodreporter.com/t/news/feed/",        # Hollywood Reporter
        "https://deadline.com/feed/",                            # Deadline
        "https://pitchfork.com/rss/news/feed/r.xml",             # Pitchfork (music)
        "https://www.rollingstone.com/music/music-news/feed/",   # Rolling Stone
        "https://ew.com/feed/",                                  # Entertainment Weekly
        "https://www.theguardian.com/culture/rss",               # Guardian Culture
        "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml", # NYT Arts
    ],
    "business": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",        # BBC Business
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", # NYT Business
        "https://feeds.skynews.com/feeds/rss/business.xml",      # Sky News Business
        "https://www.theguardian.com/business/rss",              # Guardian Business
        "https://feeds.marketwatch.com/marketwatch/topstories/", # MarketWatch
        "https://www.cnbc.com/id/100003114/device/rss/rss.html", # CNBC World
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",           # WSJ World
        "https://www.ft.com/?format=rss",                        # Financial Times
        "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com&hl=en&gl=US&ceid=US:en", # Bloomberg via GNews
        "https://feeds.washingtonpost.com/rss/business",         # WashPost Business
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 9) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").strip()
    except:
        return ""

def favicon_url(domain: str) -> str:
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

def clean_text(text: str, max_len: int = 2000) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&(?:[a-z]+|#\d+);', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

def is_valid_image(url: str) -> bool:
    """Filtra imagens de má qualidade: ícones, pixels de tracking, base64, etc."""
    if not url or not url.startswith("http"):
        return False
    url_lower = url.lower()
    # Rejeita imagens suspeitas
    bad_patterns = [
        'pixel', 'tracker', 'tracking', 'beacon', '1x1', 'spacer',
        'logo', 'favicon', 'icon', 'avatar', 'placeholder',
        'data:image', 'blank', 'transparent',
    ]
    for pat in bad_patterns:
        if pat in url_lower:
            return False
    # Rejeita extensões que não são imagens comuns
    bad_ext = ['.gif', '.ico', '.svg', '.bmp', '.tiff']
    for ext in bad_ext:
        if url_lower.split('?')[0].endswith(ext):
            return False
    return True

def extract_image_from_rss_item(item, desc_tag) -> str:
    """Tenta extrair imagem de alta qualidade do item RSS por múltiplos métodos."""
    img = ""

    # 1. media:content com dimensões
    for tag_name in ["media:content", "media:thumbnail"]:
        tags = item.find_all(tag_name)
        best = None
        best_width = 0
        for t in tags:
            t_type = t.get("type", "")
            t_url  = t.get("url", "")
            if not t_url:
                continue
            if t_type and not t_type.startswith("image"):
                continue
            w = int(t.get("width", 0))
            if w > best_width:
                best_width = w
                best = t_url
        if best and is_valid_image(best):
            return best

    # 2. enclosure
    enc = item.find("enclosure")
    if enc:
        t   = enc.get("type", "")
        url = enc.get("url", "")
        if url and (not t or t.startswith("image")) and is_valid_image(url):
            return url

    # 3. img tag dentro da description/content
    for tag in [item.find("content:encoded"), desc_tag]:
        if not tag:
            continue
        raw = str(tag)
        # Tenta og:image ou src dentro do HTML embutido
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw)
        if m and is_valid_image(m.group(1)):
            img = m.group(1)
            # Prefere imagens maiores: ignora se for muito pequena pelo URL
            if img:
                return img

    # 4. itunes:image
    it = item.find("itunes:image")
    if it:
        href = it.get("href", "")
        if is_valid_image(href):
            return href

    return img

def scrape_og_image(url: str, timeout: int = 6) -> str:
    """Scraping de og:image com múltiplos fallbacks e validação de qualidade."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout,
                         allow_redirects=True)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.content, "lxml")

        # Tenta por ordem de prioridade
        selectors = [
            ("meta", {"property": "og:image"}),
            ("meta", {"property": "og:image:url"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"name": "twitter:image:src"}),
            ("meta", {"itemprop": "image"}),
        ]
        for tag_name, attrs in selectors:
            tag = soup.find(tag_name, attrs)
            if tag:
                content = tag.get("content") or tag.get("href") or ""
                content = content.strip()
                if is_valid_image(content):
                    return content

        # Fallback: primeira <img> grande no corpo
        for img_tag in soup.find_all("img", src=True)[:10]:
            src = img_tag.get("src", "").strip()
            if not src.startswith("http"):
                continue
            # Tenta pegar dimensões do atributo
            w = img_tag.get("width", "0")
            try:
                if int(w) < 200:
                    continue
            except:
                pass
            if is_valid_image(src):
                return src

    except Exception as e:
        print(f"[OG_IMAGE ERROR] {url}: {e}")
    return ""

def scrape_full_content(url: str) -> dict:
    """Extrai conteúdo completo de uma notícia."""
    result = {
        "title": "", "description": "", "body": "",
        "image_url": "", "author": "", "published_at": "",
        "source_name": "", "source_domain": "", "favicon_url": "",
        "url": url
    }
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return result

        soup = BeautifulSoup(r.content, "lxml")
        domain = get_domain(url)
        result["source_domain"] = domain
        result["favicon_url"]   = favicon_url(domain)
        result["source_name"]   = domain.split(".")[0].capitalize()

        # Título
        for sel, attr in [
            (("meta", {"property": "og:title"}), "content"),
            (("meta", {"name": "twitter:title"}), "content"),
        ]:
            tag = soup.find(*sel)
            if tag and tag.get(attr):
                result["title"] = clean_text(tag[attr], 300)
                break
        if not result["title"]:
            h1 = soup.find("h1")
            if h1:
                result["title"] = clean_text(h1.get_text(), 300)

        # Descrição
        for attr_name, attr_val, content_attr in [
            ("property", "og:description", "content"),
            ("name", "description", "content"),
            ("name", "twitter:description", "content"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag and tag.get(content_attr):
                result["description"] = clean_text(tag[content_attr], 800)
                break

        # Imagem com validação
        for attr_name, attr_val in [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag and tag.get("content"):
                img = tag["content"].strip()
                if is_valid_image(img):
                    result["image_url"] = img
                    break

        # Autor
        for sel, attr in [
            (("meta", {"name": "author"}), "content"),
            (("meta", {"property": "article:author"}), "content"),
            (("meta", {"name": "dc.creator"}), "content"),
        ]:
            tag = soup.find(*sel)
            if tag and tag.get(attr):
                result["author"] = clean_text(tag[attr], 100)
                break
        if not result["author"]:
            for cls in [r'author', r'byline', r'article-author']:
                tag = soup.find(class_=re.compile(cls, re.I))
                if tag:
                    result["author"] = clean_text(tag.get_text(), 100)
                    break

        # Data
        for sel, attr in [
            (("meta", {"property": "article:published_time"}), "content"),
            (("time", {}), "datetime"),
        ]:
            tag = soup.find(*sel)
            if tag:
                val = tag.get(attr) or tag.get_text()
                if val:
                    result["published_at"] = val.strip()[:50]
                    break

        # Corpo do artigo
        body_candidates = [
            soup.find("article"),
            soup.find(class_=re.compile(
                r'article-body|post-content|entry-content|story-body|article__body|'
                r'content-body|main-content|article-text|story-content', re.I)),
            soup.find(id=re.compile(r'article|content|story|main-content', re.I)),
            soup.find("main"),
        ]
        body_tag = next((b for b in body_candidates if b), None)
        if body_tag:
            for bad in body_tag.find_all(
                ["script", "style", "nav", "aside", "figure",
                 "figcaption", "iframe", "button", "form", "header", "footer"]):
                bad.decompose()
            paragraphs = body_tag.find_all("p")
            body_text = " ".join(
                clean_text(p.get_text(), 1000)
                for p in paragraphs
                if len(p.get_text().strip()) > 40
            )
            result["body"] = body_text[:6000]

        if not result["body"] and result["description"]:
            result["body"] = result["description"]

    except Exception as e:
        print(f"[SCRAPE ERROR] {url}: {e}")
    return result

# ── Parser RSS ────────────────────────────────────────────────────────────────

def parse_rss_feed(feed_url: str, category: str, limit: int = 12) -> list:
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"[RSS SKIP] {feed_url} → HTTP {r.status_code}")
            return []

        # Tenta xml primeiro, fallback para html.parser
        try:
            soup = BeautifulSoup(r.content, "xml")
        except Exception:
            soup = BeautifulSoup(r.content, "lxml")

        items = soup.find_all("item")
        if not items:
            items = soup.find_all("entry")  # Atom feeds
        items = items[:limit]

        for item in items:
            # Título
            title_tag = item.find("title")
            title = clean_text(title_tag.get_text() if title_tag else "", 300)
            if not title or len(title) < 5:
                continue

            # URL
            url = ""
            link_tag = item.find("link")
            if link_tag:
                # Atom usa link como tag vazia com href
                url = link_tag.get("href") or link_tag.get_text(strip=True)
                if not url and link_tag.next_sibling:
                    url = str(link_tag.next_sibling).strip()
            if not url:
                guid = item.find("guid")
                if guid and guid.get_text().startswith("http"):
                    url = guid.get_text().strip()
            if not url:
                continue

            # Descrição
            desc_tag = (item.find("description") or item.find("summary")
                        or item.find("content") or item.find("content:encoded"))
            desc = clean_text(desc_tag.get_text() if desc_tag else "", 800)

            # Imagem — método robusto
            img = extract_image_from_rss_item(item, desc_tag)

            # Se não achou imagem no RSS, faz scraping do og:image
            # Mas limita o scraping para não atrasar muito
            if not img and url:
                img = scrape_og_image(url, timeout=5)

            # Data
            pub_date = ""
            for date_tag_name in ["pubDate", "dc:date", "published", "updated"]:
                pd = item.find(date_tag_name)
                if pd and pd.get_text(strip=True):
                    pub_date = pd.get_text(strip=True)
                    break

            # Autor
            author = ""
            for a_tag_name in ["dc:creator", "author", "dc:author"]:
                at = item.find(a_tag_name)
                if at and at.get_text(strip=True):
                    author = clean_text(at.get_text(), 100)
                    break

            domain      = get_domain(url or feed_url)
            source_name = domain.split(".")[0].capitalize() if domain else "Source"
            uid         = hashlib.md5((title + url).encode()).hexdigest()[:12]

            articles.append({
                "id":            uid,
                "title":         title,
                "description":   desc,
                "image_url":     img,
                "url":           url,
                "source_name":   source_name,
                "source_domain": domain,
                "favicon_url":   favicon_url(domain),
                "category":      category,
                "published_at":  pub_date,
                "author":        author,
                "body":          "",
            })

    except Exception as e:
        print(f"[RSS ERROR] {feed_url}: {e}")
    return articles

# ── Fetch por categoria ───────────────────────────────────────────────────────

def _fetch_category(category: str, limit: int) -> list:
    feed_urls = SOURCES.get(category, SOURCES["world"])
    articles: list = []
    # Distribui artigos entre feeds
    per_feed = max(5, (limit // len(feed_urls)) + 3)

    # Fetch paralelo com threads
    results = [[] for _ in feed_urls]

    def fetch_one(idx, url):
        results[idx] = parse_rss_feed(url, category, limit=per_feed)

    threads = [
        threading.Thread(target=fetch_one, args=(i, u))
        for i, u in enumerate(feed_urls)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    for r in results:
        articles.extend(r)

    # Deduplica por título (normalizado)
    seen, unique = set(), []
    for a in articles:
        key = re.sub(r'\W+', '', a["title"][:60].lower())
        if key and key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    # Ordena: artigos com imagem primeiro
    unique.sort(key=lambda x: (0 if x["image_url"] else 1))

    return unique[:limit]

# ── Pré-cache ao arrancar ─────────────────────────────────────────────────────

def warm_cache():
    for cat in SOURCES.keys():
        try:
            key = f"news_{cat}_20"
            if not cache_get(key):
                arts = _fetch_category(cat, 20)
                cache_set(key, arts)
                print(f"[WARM] '{cat}' → {len(arts)} artigos")
        except Exception as e:
            print(f"[WARM ERROR] {cat}: {e}")
        time.sleep(1)

threading.Thread(target=warm_cache, daemon=True).start()

# ── Rotas ─────────────────────────────────────────────────────────────────────

@app.route("/news")
def get_news():
    category = request.args.get("category", "world")
    limit    = min(int(request.args.get("limit", 20)), 60)
    force    = request.args.get("force", "0") == "1"

    if category not in SOURCES:
        abort(400, f"category inválida. Disponíveis: {', '.join(SOURCES.keys())}")

    cache_key = f"news_{category}_{limit}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

    articles = _fetch_category(category, limit)
    cache_set(cache_key, articles)
    return jsonify(articles)

@app.route("/article")
def get_article():
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        abort(400, "Parâmetro 'url' obrigatório e deve começar com http")

    cache_key = f"article_{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    article = scrape_full_content(url)
    cache_set(cache_key, article)
    return jsonify(article)

@app.route("/categories")
def get_categories():
    return jsonify({
        cat: len(urls)
        for cat, urls in SOURCES.items()
    })

@app.route("/health")
def health():
    cached_cats = [k for k in _cache if k.startswith("news_")]
    return jsonify({
        "status":            "ok",
        "time":              datetime.now(timezone.utc).isoformat(),
        "cached_categories": len(cached_cats),
        "total_cache_keys":  len(_cache),
        "categories":        list(SOURCES.keys()),
    })

@app.route("/")
def index():
    return jsonify({
        "name":      "GlobeNews API",
        "version":   "3.0",
        "endpoints": {
            "/news":       "?category=world|technology|science|health|sports|entertainment|business&limit=20&force=0",
            "/article":    "?url=<url_da_noticia>",
            "/categories": "lista de categorias e número de fontes",
            "/health":     "status da API",
        },
        "sources_per_category": {cat: len(urls) for cat, urls in SOURCES.items()},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)