import os, re, time, json, threading, hashlib, sqlite3
import requests
from flask import Flask, jsonify, request, abort
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

app = Flask(__name__)

# ── Cache de traduções persistente (SQLite) ───────────────────────────────────
DB_PATH = "/tmp/globenews.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            hash TEXT PRIMARY KEY,
            translated TEXT,
            created_at REAL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT,
            category TEXT,
            data TEXT,
            fetched_at REAL,
            PRIMARY KEY (id, category)
        )
    """)
    con.commit()
    con.close()

init_db()

def db_get_translation(text_hash: str):
    try:
        con = sqlite3.connect(DB_PATH)
        row = con.execute("SELECT translated FROM translations WHERE hash=?", (text_hash,)).fetchone()
        con.close()
        return row[0] if row else None
    except:
        return None

def db_set_translation(text_hash: str, translated: str):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT OR REPLACE INTO translations VALUES (?,?,?)",
                    (text_hash, translated, time.time()))
        con.commit()
        con.close()
    except:
        pass

def db_save_articles(category: str, articles: list):
    """Guarda artigos no DB — acumulativo, mantém os antigos."""
    try:
        con = sqlite3.connect(DB_PATH)
        for a in articles:
            con.execute("INSERT OR REPLACE INTO articles VALUES (?,?,?,?)",
                        (a["id"], category, json.dumps(a, ensure_ascii=False), time.time()))
        con.commit()
        con.close()
    except Exception as e:
        print(f"[DB SAVE] {e}")

def db_load_articles(category: str, limit: int = 200) -> list:
    """Carrega artigos do DB ordenados por data de fetch (mais novos primeiro)."""
    try:
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT data FROM articles WHERE category=? ORDER BY fetched_at DESC LIMIT ?",
            (category, limit)
        ).fetchall()
        con.close()
        return [json.loads(r[0]) for r in rows]
    except:
        return []

# ── Cache em memória (rápido, para pedidos frequentes) ───────────────────────
_mem_cache: dict = {}
MEM_TTL = 300  # 5 min — serve do memória; após isso refetch mas mantém DB

def mem_get(key):
    e = _mem_cache.get(key)
    if e and time.time() - e[0] < MEM_TTL:
        return e[1]
    return None

def mem_set(key, data):
    _mem_cache[key] = (time.time(), data)

# ── Self-ping ─────────────────────────────────────────────────────────────────
def self_ping():
    while True:
        time.sleep(600)
        try:
            own_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:10000")
            requests.get(f"{own_url}/health", timeout=10)
        except:
            pass

# ── Tradução para PT com cache ────────────────────────────────────────────────
_trans_lock = threading.Lock()

def translate_to_pt(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return text
    # Se já é PT (heurística: >60% palavras comuns PT), não traduz
    pt_markers = ["que", "de", "e", "o", "a", "em", "com", "para", "uma", "um",
                  "por", "se", "do", "da", "os", "as", "ao", "na", "no", "foi"]
    words = text.lower().split()[:30]
    pt_count = sum(1 for w in words if w in pt_markers)
    if len(words) > 5 and pt_count / len(words) > 0.25:
        return text  # já é português

    text_hash = hashlib.md5(text.encode()).hexdigest()
    cached = db_get_translation(text_hash)
    if cached:
        return cached

    # Limita a 4500 chars por pedido (limite seguro do Google Translate)
    chunk = text[:4500]
    try:
        with _trans_lock:
            result = GoogleTranslator(source="auto", target="pt").translate(chunk)
        if result:
            # Se o texto original era maior, adiciona o resto sem traduzir
            if len(text) > 4500:
                result = result + " " + text[4500:]
            db_set_translation(text_hash, result)
            return result
    except Exception as e:
        print(f"[TRANSLATE] {e}")
    return text  # fallback: texto original

def translate_article(article: dict) -> dict:
    """Traduz título, descrição e body de um artigo em paralelo."""
    fields = ["title", "description", "body"]
    results = {}

    def trans_field(f):
        results[f] = translate_to_pt(article.get(f, ""))

    threads = [threading.Thread(target=trans_field, args=(f,), daemon=True) for f in fields]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)

    a = dict(article)
    for f in fields:
        if f in results:
            a[f] = results[f]
    return a

# ── SOURCES — 250+ feeds, sem BBC ────────────────────────────────────────────
SOURCES = {
    "world": [
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://www.theguardian.com/world/rss",
        "http://rss.cnn.com/rss/edition_world.rss",
        "https://feeds.washingtonpost.com/rss/world",
        "https://www.independent.co.uk/news/world/rss",
        "https://abcnews.go.com/abcnews/internationalheadlines",
        "https://www.vox.com/rss/world-politics/index.xml",
        "https://thehill.com/homenews/feed/",
        "https://hongkongfp.com/feed/",
        "https://www.pbs.org/newshour/feeds/rss/world",
        "https://nypost.com/feed/",
        "https://www.rferl.org/api/",
        "https://theconversation.com/global/articles.atom",
        "https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf",
        "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en&gl=US&ceid=US:en",
        "https://rss.dw.com/rdf/rss-en-all",
        "https://www.france24.com/en/rss",
        "https://www.euronews.com/rss?level=theme&name=news",
        "https://feeds.npr.org/1001/rss.xml",
        "https://time.com/feed/",
        "https://www.usatoday.com/rss/news/",
        "https://feeds.nbcnews.com/nbcnews/public/news",
        "https://www.cbsnews.com/latest/rss/main",
        "https://feeds.foxnews.com/foxnews/world",
        "https://www.newsweek.com/rss",
        "https://rss.politico.com/politics-news.xml",
        "https://www.axios.com/feeds/feed.rss",
        "https://apnews.com/apf-topnews",
    ],
    "technology": [
        # Internacional Tier 1
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://www.wired.com/feed/rss",
        "http://feeds.arstechnica.com/arstechnica/index/",
        "https://www.engadget.com/rss.xml",
        "https://www.cnet.com/rss/all/",
        "https://venturebeat.com/feed/",
        "https://www.theregister.com/headlines.atom",
        "https://feeds.skynews.com/feeds/rss/technology.xml",
        # Internacional Tier 2
        "https://gizmodo.com/rss",
        "https://mashable.com/feed/",
        "https://www.zdnet.com/news/rss.xml",
        "https://www.digitaltrends.com/feed/",
        "https://www.techradar.com/rss",
        "https://thenextweb.com/feed/",
        "https://www.pcmag.com/rss/news",
        "https://www.pcworld.com/index.rss",
        "https://www.tomshardware.com/feeds/all",
        "https://www.androidpolice.com/feed/",
        "https://9to5mac.com/feed/",
        "https://9to5google.com/feed/",
        "https://appleinsider.com/rss/news/",
        "https://www.macrumors.com/macrumors.xml",
        "https://news.ycombinator.com/rss",
        "https://www.producthunt.com/feed",
        "http://news.mit.edu/rss/topic/artificial-intelligence2",
        "https://www.technologyreview.com/feed/",
        "https://deepmind.com/blog/feed/basic/",
        "https://openai.com/news/rss.xml",
        "https://www.anandtech.com/rss/",
        "https://arstechnica.com/gadgets/feed/",
        "https://www.notebookcheck.net/News.8.0.html?feed=rss",
        "https://www.gsmarena.com/rss-news-reviews.php3",
        "https://www.xda-developers.com/feed/",
        "https://www.slashgear.com/feed/",
        "https://www.techspot.com/backend.xml",
        "https://www.bleepingcomputer.com/feed/",
        "https://feeds.feedburner.com/TheHackersNews",
        "https://www.darkreading.com/rss.xml",
        # PT/BR mantidos
        "https://feeds.feedburner.com/TecMundo",
        "https://www.tecnoblog.net/feed/",
        "https://olhardigital.com.br/feed/",
        "https://canaltech.com.br/rss/",
    ],
    "science": [
        "https://www.sciencedaily.com/rss/all.xml",
        "https://www.nasa.gov/news-release/feed/",
        "https://www.newscientist.com/feed/home/",
        "http://feeds.arstechnica.com/arstechnica/science/",
        "https://www.space.com/feeds.xml",
        "https://www.wired.com/category/science/feed",
        "https://www.theguardian.com/science/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://universetoday.com/feed",
        "https://www.nature.com/nature.rss",
        "https://www.scientificamerican.com/platform/syndication/rss/",
        "https://phys.org/rss-feed/",
        "https://gizmodo.com/science/rss",
        "https://futurism.com/feed",
        "https://www.livescience.com/feeds/all",
        "https://www.discovermagazine.com/rss",
        "https://earthsky.org/feed/",
        "https://www.sciencenews.org/feed",
        "https://rss.nytimes.com/services/xml/rss/nyt/Environment.xml",
        "https://www.theguardian.com/environment/rss",
        "https://www.smithsonianmag.com/rss/latest_articles/",
        "https://www.popsci.com/feed/",
        "https://feeds.feedburner.com/IeeeSpectrumFullText",
        "https://www.sciencemag.org/rss/news_current.xml",
        "https://www.chemistryworld.com/rss-feeds",
        "https://www.nationalgeographic.com/latest-stories/_jcr_content/minified/data.xml",
        "https://feeds.skynews.com/feeds/rss/science.xml",
        "https://www.inverse.com/rss",
        "https://bigthink.com/feed/",
        "https://www.eurekalert.org/rss.xml",
    ],
    "health": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://www.theguardian.com/society/health/rss",
        "https://feeds.skynews.com/feeds/rss/health.xml",
        "https://www.who.int/feeds/entity/news/en/rss.xml",
        "https://newsinhealth.nih.gov/syndication/rss",
        "https://www.sciencedaily.com/rss/health_medicine/",
        "http://feeds.arstechnica.com/arstechnica/health/",
        "https://www.medicalnewstoday.com/rss/medicalnewstoday",
        "https://www.healthline.com/rss/health-news",
        "https://www.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",
        "https://www.statnews.com/feed/",
        "https://www.livescience.com/feeds/health",
        "https://futurism.com/health/feed",
        "https://www.prevention.com/rss/all/",
        "https://rss.nytimes.com/services/xml/rss/nyt/Well.xml",
        "https://www.theguardian.com/society/mentalhealth/rss",
        "https://www.sciencenews.org/topic/health-medicine/feed",
        "https://www.cnn.com/services/rss/health.rss",
        "https://feeds.feedburner.com/medscape/fnks",
        "https://www.fiercehealthcare.com/rss/xml",
        "https://feeds.skynews.com/feeds/rss/health.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://www.bbc.co.uk/news/health/rss.xml",
        "https://www.reuters.com/rssFeed/healthNews",
        "https://www.hhs.gov/rss/news.xml",
        "https://publichealthinsider.com/feed/",
        "https://www.health.com/rss",
        "https://www.everydayhealth.com/rss/all-articles.aspx",
        "https://medlineplus.gov/rss/medlineplus_whatsnew.xml",
        "https://www.mediglobal.org/feed/",
    ],
    "sports": [
        "https://www.espn.com/espn/rss/news",
        "https://www.skysports.com/rss/12040",
        "https://www.theguardian.com/sport/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
        "https://feeds.skynews.com/feeds/rss/sports.xml",
        "https://www.cbssports.com/rss/headlines/",
        "https://www.marca.com/rss/portada.xml",
        "https://www.eurosport.com/rss/news/",
        "https://www.latimes.com/sports.rss",
        "https://www.washingtontimes.com/rss/headlines/sports/",
        "https://www.smh.com.au/rss/sport.xml",
        "https://boxingnewsonline.net/feed/",
        "https://www.essentiallysports.com/feed/",
        "https://www.goal.com/feeds/en/news",
        "https://www.formula1.com/content/fom-website/en/latest/all.xml",
        "https://www.autosport.com/rss/motorsport/news/",
        "https://api.foxsports.com/v2/content/optimized-rss?partnerKey=MB0Wehpmuj2lUhuRhQaafhBjAJqaPU244mlTDK1i&size=30",
        "https://theathletic.com/rss/news/",
        "https://www.bleacherreport.com/articles/feed",
        "https://www.sportingnews.com/rss",
        "https://www.nba.com/rss/nba_rss.xml",
        "https://www.nfl.com/rss/rsslanding?contentId=news",
        "https://www.baseball-reference.com/feeds/rss/news.xml",
        "https://www.si.com/rss/si_topstories.rss",
        "https://sportbible.com/feed",
        "https://www.90min.com/feed",
        "https://www.givemesport.com/feed/",
        "https://www.skysports.com/rss/12040",
        "https://www.transfermarkt.com/news/latest/news",
        "https://www.4fourtwofootball.com/rss",
    ],
    "entertainment": [
        "https://feeds.skynews.com/feeds/rss/entertainment.xml",
        "https://variety.com/feed/",
        "https://www.hollywoodreporter.com/t/news/feed/",
        "https://deadline.com/feed/",
        "https://pitchfork.com/rss/news/feed/r.xml",
        "https://www.rollingstone.com/music/music-news/feed/",
        "https://ew.com/feed/",
        "https://www.theguardian.com/culture/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml",
        "https://www.billboard.com/feed/",
        "https://www.nme.com/feed",
        "https://www.ign.com/rss/articles",
        "https://www.gamespot.com/feeds/mashup/",
        "https://kotaku.com/rss",
        "https://io9.com/rss",
        "https://www.vulture.com/rss/all.xml",
        "https://www.empireonline.com/movies/rss/",
        "https://collider.com/feed/",
        "https://screenrant.com/feed/",
        "https://www.indiewire.com/feed/",
        "https://www.polygon.com/rss/index.xml",
        "https://www.pcgamer.com/rss/",
        "https://pagesix.com/feed/",
        "https://feeds.feedburner.com/nymag/vulture",
        "https://www.avclub.com/rss",
        "https://www.cinemablend.com/rss/news",
        "https://www.comingsoon.net/feed",
        "https://www.slashfilm.com/feed/",
        "https://www.digitalspy.com/feeds/rss/",
        "https://www.tvline.com/feed/",
        "https://www.rottentomatoes.com/syndication/rss/reviews.xml",
        "https://www.pastemagazine.com/rss/",
        "https://www.stereogum.com/feed/",
        "https://consequence.net/feed/",
        "https://pitchfork.com/feed/feed-album-reviews/rss",
    ],
    "business": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://feeds.skynews.com/feeds/rss/business.xml",
        "https://www.theguardian.com/business/rss",
        "https://www.marketwatch.com/rss/topstories",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "https://www.ft.com/?format=rss",
        "https://www.economist.com/latest/rss.xml",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://www.forbes.com/business/feed/",
        "https://www.businessinsider.com/rss",
        "https://feeds.washingtonpost.com/rss/business",
        "https://fortune.com/feed",
        "https://hbr.org/resources/rss/editorial/feed",
        "https://www.fastcompany.com/latest/rss",
        "https://www.inc.com/rss",
        "https://www.entrepreneur.com/latest.rss",
        "https://feeds.feedburner.com/entrepreneur/latest",
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
        "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline",
        "https://seekingalpha.com/feed.xml",
        "https://www.thestreet.com/rss/index.xml",
        "https://rss.politico.com/economy.xml",
        "https://feeds.skynews.com/feeds/rss/money.xml",
        "https://www.reuters.com/rssFeed/businessNews",
        "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com&hl=en&gl=US&ceid=US:en",
    ],
    "africa": [
        "https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/angola/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/southafrica/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/nigeria/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/kenya/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/ethiopia/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/ghana/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/egypt/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/tanzania/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/mozambique/headlines.rdf",
        "https://rss.dw.com/rdf/rss-en-africa",
        "https://www.france24.com/en/africa/rss",
        "https://www.voanews.com/api/zy_qoeivei",
        "https://www.dn.pt/rss/mundo.xml",
        "https://www.publico.pt/api/rss/mundo",
        "https://www.rtp.pt/noticias/rss/mundo",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
}

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").strip()
    except:
        return ""

def favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else ""

def clean_text(text: str, max_len: int = 5000) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&(?:[a-zA-Z]+|#\d+);', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

def is_valid_image(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    u = url.lower().split("?")[0]
    bad = ['pixel','tracker','tracking','beacon','1x1','spacer','logo',
           'favicon','icon','avatar','placeholder','blank','transparent',
           'data:image','badge','button','spinner','loading']
    for b in bad:
        if b in u:
            return False
    bad_ext = ['.gif','.ico','.svg','.bmp','.tiff','.webmanifest','.txt','.js','.css']
    for e in bad_ext:
        if u.endswith(e):
            return False
    return True

def extract_image_from_rss_item(item, desc_tag) -> str:
    for tag_name in ["media:content", "media:thumbnail"]:
        tags = item.find_all(tag_name)
        best, best_w = None, 0
        for t in tags:
            t_type = t.get("type","")
            t_url  = t.get("url","")
            if not t_url or (t_type and not t_type.startswith("image")):
                continue
            try:
                w = int(t.get("width", 0))
            except:
                w = 1
            if w >= best_w:
                best_w, best = w, t_url
        if best and is_valid_image(best):
            return best

    enc = item.find("enclosure")
    if enc:
        eu, et = enc.get("url",""), enc.get("type","")
        if eu and (not et or et.startswith("image")) and is_valid_image(eu):
            return eu

    for tag in [item.find("content:encoded"), desc_tag]:
        if not tag:
            continue
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', str(tag))
        if m and is_valid_image(m.group(1)):
            return m.group(1)

    it = item.find("itunes:image")
    if it:
        href = it.get("href","")
        if is_valid_image(href):
            return href
    return ""

def scrape_og_image(url: str, timeout: int = 5) -> str:
    if not url:
        return ""
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.content, "lxml")
        for attr_n, attr_v in [("property","og:image"),("property","og:image:url"),
                                 ("name","twitter:image"),("name","twitter:image:src"),
                                 ("itemprop","image")]:
            tag = soup.find("meta", {attr_n: attr_v})
            if tag:
                c = (tag.get("content") or "").strip()
                if is_valid_image(c):
                    return c
    except:
        pass
    return ""

def scrape_full_body(url: str) -> str:
    """Scraping completo do corpo do artigo para descrição máxima."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.content, "lxml")

        # Remove elementos indesejados
        for bad in soup.find_all(["script","style","nav","aside","figure",
                                   "figcaption","iframe","button","form",
                                   "header","footer","noscript","advertisement"]):
            bad.decompose()

        # Tenta encontrar o corpo principal
        body_candidates = [
            soup.find("article"),
            soup.find(class_=re.compile(
                r'article-body|post-content|entry-content|story-body|article__body|'
                r'content-body|main-content|article-text|story-content|post-body|'
                r'article__content|post__content|body-text|article-content', re.I)),
            soup.find(id=re.compile(r'article|content|story|main-content|body', re.I)),
            soup.find("main"),
        ]
        body_tag = next((b for b in body_candidates if b), None)

        if body_tag:
            paragraphs = body_tag.find_all("p")
            body = " ".join(
                clean_text(p.get_text(), 2000)
                for p in paragraphs
                if len(p.get_text().strip()) > 30
            )
            if len(body) > 200:
                return body[:8000]

        # Fallback: todos os <p> da página com conteúdo relevante
        all_p = soup.find_all("p")
        body = " ".join(
            clean_text(p.get_text(), 2000)
            for p in all_p
            if len(p.get_text().strip()) > 50
        )
        return body[:8000]
    except Exception as e:
        print(f"[BODY SCRAPE] {url}: {e}")
    return ""

def scrape_full_content(url: str) -> dict:
    result = {
        "title":"","description":"","body":"",
        "image_url":"","author":"","published_at":"",
        "source_name":"","source_domain":"","favicon_url":"","url":url,
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

        for sel, attr in [(("meta",{"property":"og:title"}),"content"),
                          (("meta",{"name":"twitter:title"}),"content")]:
            tag = soup.find(*sel)
            if tag and tag.get(attr):
                result["title"] = clean_text(tag[attr], 300); break
        if not result["title"]:
            h1 = soup.find("h1")
            if h1:
                result["title"] = clean_text(h1.get_text(), 300)

        for an, av in [("property","og:description"),("name","description"),("name","twitter:description")]:
            tag = soup.find("meta",{an:av})
            if tag and tag.get("content"):
                result["description"] = clean_text(tag["content"], 1000); break

        for an, av in [("property","og:image"),("property","og:image:url"),
                       ("name","twitter:image"),("name","twitter:image:src")]:
            tag = soup.find("meta",{an:av})
            if tag and tag.get("content") and is_valid_image(tag["content"].strip()):
                result["image_url"] = tag["content"].strip(); break

        for sel, attr in [(("meta",{"name":"author"}),"content"),
                          (("meta",{"property":"article:author"}),"content"),
                          (("meta",{"name":"dc.creator"}),"content")]:
            tag = soup.find(*sel)
            if tag and tag.get(attr):
                result["author"] = clean_text(tag[attr], 100); break
        if not result["author"]:
            for cls in [r'author',r'byline',r'article-author']:
                tag = soup.find(class_=re.compile(cls, re.I))
                if tag:
                    result["author"] = clean_text(tag.get_text(), 100); break

        for sel, attr in [(("meta",{"property":"article:published_time"}),"content"),
                          (("time",{}),"datetime")]:
            tag = soup.find(*sel)
            if tag:
                val = tag.get(attr) or tag.get_text()
                if val:
                    result["published_at"] = val.strip()[:50]; break

        result["body"] = scrape_full_body(url)
        if not result["body"]:
            result["body"] = result["description"]

    except Exception as e:
        print(f"[SCRAPE ERROR] {url}: {e}")
    return result

# ── Parser RSS ────────────────────────────────────────────────────────────────

def parse_rss_feed(feed_url: str, category: str, limit: int = 15) -> list:
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []

        try:
            soup = BeautifulSoup(r.content, "xml")
        except:
            soup = BeautifulSoup(r.content, "lxml")

        items = soup.find_all("item") or soup.find_all("entry")
        items = items[:limit]

        for item in items:
            title_tag = item.find("title")
            title = clean_text(title_tag.get_text() if title_tag else "", 300)
            if not title or len(title) < 5:
                continue

            url = ""
            link_tag = item.find("link")
            if link_tag:
                url = link_tag.get("href") or link_tag.get_text(strip=True)
                if not url and link_tag.next_sibling:
                    url = str(link_tag.next_sibling).strip()
            if not url:
                guid = item.find("guid")
                if guid and guid.get_text().startswith("http"):
                    url = guid.get_text().strip()
            if not url:
                continue

            desc_tag = (item.find("description") or item.find("summary")
                        or item.find("content:encoded") or item.find("content"))
            desc = clean_text(desc_tag.get_text() if desc_tag else "", 1500)

            img = extract_image_from_rss_item(item, desc_tag)
            if not img and url:
                img = scrape_og_image(url, timeout=4)

            pub_date = ""
            for dname in ["pubDate","dc:date","published","updated"]:
                pd = item.find(dname)
                if pd and pd.get_text(strip=True):
                    pub_date = pd.get_text(strip=True); break

            author = ""
            for aname in ["dc:creator","author","dc:author"]:
                at = item.find(aname)
                if at and at.get_text(strip=True):
                    author = clean_text(at.get_text(), 100); break

            domain      = get_domain(url or feed_url)
            source_name = domain.split(".")[0].capitalize() if domain else "Source"
            uid         = hashlib.md5((title + url).encode()).hexdigest()[:12]

            # Corpo completo: scraping em background depois
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
                "body":          desc,  # Mínimo: desc do RSS
            })

    except Exception as e:
        print(f"[RSS ERROR] {feed_url}: {e}")
    return articles

# ── Fetch corpo completo em paralelo para os top N artigos ────────────────────

def enrich_bodies(articles: list, top_n: int = 10) -> list:
    """Faz scraping do corpo completo para os primeiros top_n artigos."""
    to_enrich = articles[:top_n]
    rest      = articles[top_n:]
    results   = [None] * len(to_enrich)

    def fetch_body(idx, art):
        body = scrape_full_body(art["url"])
        a = dict(art)
        if body and len(body) > len(a.get("body","") or ""):
            a["body"] = body
        results[idx] = a

    threads = [
        threading.Thread(target=fetch_body, args=(i, a), daemon=True)
        for i, a in enumerate(to_enrich)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    enriched = [r if r else to_enrich[i] for i, r in enumerate(results)]
    return enriched + rest

# ── Fetch e tradução por categoria ────────────────────────────────────────────

def _fetch_category(category: str, limit: int) -> list:
    feed_urls = SOURCES.get(category, SOURCES["world"])
    per_feed  = max(5, (limit // len(feed_urls)) + 3)
    raw       = [[] for _ in feed_urls]

    def fetch_one(idx, url):
        raw[idx] = parse_rss_feed(url, category, limit=per_feed)

    threads = [threading.Thread(target=fetch_one, args=(i, u), daemon=True)
               for i, u in enumerate(feed_urls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    articles = []
    for r in raw:
        articles.extend(r)

    # Deduplicação
    seen, unique = set(), []
    for a in articles:
        key = re.sub(r'\W+', '', a["title"][:60].lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    # Artigos com imagem primeiro
    unique.sort(key=lambda x: (0 if x["image_url"] else 1))

    # Enriquece corpos dos top artigos
    unique = enrich_bodies(unique, top_n=15)

    # Traduz para PT em paralelo
    translated = [None] * len(unique)

    def trans_one(idx, art):
        translated[idx] = translate_article(art)

    t_threads = [threading.Thread(target=trans_one, args=(i, a), daemon=True)
                 for i, a in enumerate(unique)]
    for t in t_threads:
        t.start()
    for t in t_threads:
        t.join(timeout=15)

    final = [t if t else unique[i] for i, t in enumerate(translated)]

    # Salva no DB (acumulativo)
    db_save_articles(category, final)

    return final[:limit]

# ── Warm-up atrasado ──────────────────────────────────────────────────────────

def warm_cache():
    time.sleep(5)
    print("[WARM] A iniciar pré-cache...")
    for cat in SOURCES.keys():
        try:
            key = f"cat_{cat}_20"
            if not mem_get(key):
                arts = _fetch_category(cat, 20)
                mem_set(key, arts)
                print(f"[WARM] '{cat}' → {len(arts)} artigos")
        except Exception as e:
            print(f"[WARM ERROR] {cat}: {e}")
        time.sleep(3)
    print("[WARM] Concluído.")

threading.Thread(target=self_ping,  daemon=True).start()
threading.Thread(target=warm_cache, daemon=True).start()

# ── Rotas ─────────────────────────────────────────────────────────────────────

@app.route("/news")
def get_news():
    category = request.args.get("category", "world")
    limit    = min(int(request.args.get("limit", 20)), 60)
    force    = request.args.get("force", "0") == "1"
    # history=1 devolve artigos acumulados do DB (inclui os antigos)
    history  = request.args.get("history", "0") == "1"

    if category not in SOURCES:
        abort(400, f"category inválida. Disponíveis: {', '.join(SOURCES.keys())}")

    if history:
        return jsonify(db_load_articles(category, limit=min(int(request.args.get("limit",200)),500)))

    cache_key = f"cat_{category}_{limit}"
    if not force:
        cached = mem_get(cache_key)
        if cached:
            return jsonify(cached)

    articles = _fetch_category(category, limit)
    mem_set(cache_key, articles)
    return jsonify(articles)

@app.route("/article")
def get_article():
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        abort(400, "Parâmetro 'url' obrigatório")

    cache_key = f"article_{hashlib.md5(url.encode()).hexdigest()}"
    cached = mem_get(cache_key)
    if cached:
        return jsonify(cached)

    article = scrape_full_content(url)
    article = translate_article(article)
    mem_set(cache_key, article)
    return jsonify(article)

@app.route("/categories")
def get_categories():
    return jsonify({cat: len(urls) for cat, urls in SOURCES.items()})

@app.route("/health")
def health():
    return jsonify({
        "status":       "ok",
        "time":         datetime.now(timezone.utc).isoformat(),
        "total_feeds":  sum(len(v) for v in SOURCES.values()),
        "categories":   list(SOURCES.keys()),
        "mem_keys":     len(_mem_cache),
    })

@app.route("/")
def index():
    return jsonify({
        "name":        "GlobeNews API",
        "version":     "4.0",
        "total_feeds": sum(len(v) for v in SOURCES.values()),
        "endpoints": {
            "/news":       "?category=world|technology|science|health|sports|entertainment|business|africa&limit=20&force=0&history=0",
            "/article":    "?url=<url>  — corpo completo + traduzido PT",
            "/categories": "fontes por categoria",
            "/health":     "status",
        },
        "sources_per_category": {cat: len(urls) for cat, urls in SOURCES.items()},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)