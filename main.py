import os
import re
import time
import hashlib
import requests
from flask import Flask, jsonify, request
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime

app = Flask(__name__)

# ── Cache simples em memória: {cache_key: (timestamp, data)} ──────────────────
_cache: dict = {}
CACHE_TTL = 900  # 15 minutos

def cache_get(key):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None

def cache_set(key, data):
    _cache[key] = (time.time(), data)

# ── Fontes de notícias por categoria ─────────────────────────────────────────

SOURCES = {
    "world": [
        "https://feeds.bbci.co.uk/portuguese/rss.xml",
        "https://rss.dw.com/rdf/rss-port-all",
        "https://www.dn.pt/rss/mundo.xml",
    ],
    "technology": [
        "https://feeds.feedburner.com/TecMundo",
        "https://www.tecnoblog.net/feed/",
        "https://olhardigital.com.br/feed/",
    ],
    "health": [
        "https://saude.abril.com.br/feed/",
        "https://www.uol.com.br/vivabem/rss.xml",
    ],
    "sports": [
        "https://www.record.pt/rss/desporto.xml",
        "https://esportes.estadao.com.br/rss/todos.xml",
    ],
    "science": [
        "https://super.abril.com.br/feed/",
        "https://www.nationalgeographicbrasil.com/feed",
    ],
    "entertainment": [
        "https://rollingstone.uol.com.br/feed/",
        "https://www.ofuxico.com.br/feed",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""

def favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

def clean_text(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def parse_rss(feed_url: str, category: str, limit: int = 10) -> list:
    """Faz parse de um feed RSS e extrai artigos com imagem."""
    articles = []
    try:
        resp = requests.get(feed_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")[:limit]

        for item in items:
            title = clean_text(item.find("title").get_text() if item.find("title") else "")
            if not title:
                continue

            link = item.find("link")
            url  = link.get_text() if link else (item.find("guid") or {}).get_text(default="")
            
            desc_tag = item.find("description") or item.find("summary")
            desc = clean_text(desc_tag.get_text() if desc_tag else "")

            # Tentar extrair imagem: enclosure, media:content, og
            img_url = ""
            enclosure = item.find("enclosure")
            if enclosure and enclosure.get("type", "").startswith("image"):
                img_url = enclosure.get("url", "")
            
            if not img_url:
                media = item.find("media:content") or item.find("media:thumbnail")
                if media:
                    img_url = media.get("url", "")
            
            if not img_url:
                # Tenta extrair img do description HTML
                desc_html = desc_tag.decode_contents() if desc_tag else ""
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html)
                if img_match:
                    img_url = img_match.group(1)

            if not img_url and url:
                img_url = scrape_og_image(url)

            domain = get_domain(url or feed_url)
            source_name = domain.split(".")[0].capitalize() if domain else "Fonte"

            articles.append({
                "title": title,
                "description": desc,
                "image_url": img_url,
                "url": url,
                "source_name": source_name,
                "source_domain": domain,
                "favicon_url": favicon_url(domain),
                "category": category,
                "published_at": item.find("pubDate").get_text() if item.find("pubDate") else ""
            })
    except Exception as e:
        print(f"[RSS ERROR] {feed_url}: {e}")
    return articles

def scrape_og_image(url: str) -> str:
    """Extrai og:image de uma página para enriquecer o artigo."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        soup = BeautifulSoup(resp.content, "html.parser")
        og = soup.find("meta", property="og:image")
        if og:
            return og.get("content", "")
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw:
            return tw.get("content", "")
    except Exception:
        pass
    return ""

def scrape_perplexity_news(query: str = "noticias mundo hoje", limit: int = 10) -> list:
    """Scraping simples do Perplexity para enriquecer com notícias recentes."""
    articles = []
    try:
        search_url = f"https://www.perplexity.ai/search?q={requests.utils.quote(query)}&focus=news"
        resp = requests.get(search_url, headers={
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml",
        }, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")

        # Perplexity renderiza no cliente — tenta extrair do JSON embutido
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                import json
                data = json.loads(script.string or "")
                # Percorre recursivamente à procura de títulos/links de notícias
                results = extract_perplexity_results(data, limit)
                articles.extend(results)
                if len(articles) >= limit:
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"[PERPLEXITY] {e}")
    return articles[:limit]

def extract_perplexity_results(obj, limit: int) -> list:
    """Percorre JSON do Perplexity à procura de webResults/sources."""
    results = []
    if isinstance(obj, dict):
        for key in ("webResults", "sources", "results", "items"):
            if key in obj and isinstance(obj[key], list):
                for item in obj[key][:limit]:
                    if isinstance(item, dict):
                        title = item.get("name") or item.get("title") or ""
                        url   = item.get("url") or item.get("link") or ""
                        desc  = item.get("snippet") or item.get("description") or ""
                        if title and url:
                            domain = get_domain(url)
                            results.append({
                                "title": clean_text(title),
                                "description": clean_text(desc),
                                "image_url": scrape_og_image(url),
                                "url": url,
                                "source_name": domain.split(".")[0].capitalize(),
                                "source_domain": domain,
                                "favicon_url": favicon_url(domain),
                                "category": "world",
                                "published_at": ""
                            })
        for val in obj.values():
            results.extend(extract_perplexity_results(val, limit))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(extract_perplexity_results(item, limit))
    return results

# ── Rotas ─────────────────────────────────────────────────────────────────────

@app.route("/news")
def get_news():
    category = request.args.get("category", "world")
    lang     = request.args.get("lang", "pt")
    limit    = min(int(request.args.get("limit", 20)), 50)

    cache_key = f"{category}_{lang}_{limit}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    feed_urls = SOURCES.get(category, SOURCES["world"])
    articles  = []

    for feed_url in feed_urls:
        articles.extend(parse_rss(feed_url, category, limit=limit // len(feed_urls) + 5))
        if len(articles) >= limit:
            break

    # Enriquece com Perplexity se houver poucas notícias
    if len(articles) < 5:
        perplexity_q = f"noticias {category} hoje"
        articles.extend(scrape_perplexity_news(perplexity_q, limit=10))

    # Deduplica por título
    seen = set()
    unique = []
    for a in articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    result = unique[:limit]
    cache_set(cache_key, result)
    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)