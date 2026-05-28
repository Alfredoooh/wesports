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

# ── SOURCES — 200+ feeds internacionais + PT/BR em tech ──────────────────────
SOURCES = {
    # ── WORLD ─────────────────────────────────────────────────────────────────
    "world": [
        # Big internationals
        "https://feeds.bbci.co.uk/news/world/rss.xml",            # BBC World
        "https://feeds.bbci.co.uk/news/rss.xml",                  # BBC Top Stories
        "https://www.aljazeera.com/xml/rss/all.xml",              # Al Jazeera
        "https://feeds.skynews.com/feeds/rss/world.xml",          # Sky News World
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", # NYT World
        "https://www.theguardian.com/world/rss",                   # Guardian World
        "http://rss.cnn.com/rss/edition_world.rss",               # CNN World
        "https://feeds.washingtonpost.com/rss/world",             # WashPost World
        "https://www.independent.co.uk/news/world/rss",           # Independent World
        "https://abcnews.go.com/abcnews/internationalheadlines",   # ABC News
        "https://www.vox.com/rss/world-politics/index.xml",       # Vox World
        "https://thehill.com/homenews/feed/",                     # The Hill
        "https://hongkongfp.com/feed/",                           # Hong Kong Free Press
        "https://www.pbs.org/newshour/feeds/rss/world",           # PBS World
        "https://nypost.com/feed/",                               # NY Post
        "https://www.rferl.org/api/",                             # Radio Free Europe
        "https://theconversation.com/global/articles.atom",       # The Conversation
        "https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf", # All Africa
        # Reuters via Google News (RSS direto foi descontinuado)
        "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en&gl=US&ceid=US:en",
        # DW, France 24, euronews
        "https://rss.dw.com/rdf/rss-en-all",                     # Deutsche Welle EN
        "https://www.france24.com/en/rss",                        # France 24 EN
        "https://www.euronews.com/rss?level=theme&name=news",     # Euronews
        "https://feeds.npr.org/1001/rss.xml",                     # NPR News
        "https://time.com/feed/",                                 # TIME Magazine
        "https://www.usatoday.com/rss/news/",                    # USA Today
    ],

    # ── TECHNOLOGY ────────────────────────────────────────────────────────────
    "technology": [
        # Internacional — Tier 1
        "https://www.theverge.com/rss/index.xml",                 # The Verge
        "https://techcrunch.com/feed/",                           # TechCrunch
        "https://www.wired.com/feed/rss",                         # Wired
        "http://feeds.arstechnica.com/arstechnica/index/",        # Ars Technica
        "https://www.engadget.com/rss.xml",                       # Engadget
        "https://www.cnet.com/rss/all/",                          # CNET
        "https://feeds.bbci.co.uk/news/technology/rss.xml",       # BBC Tech
        "https://venturebeat.com/feed/",                          # VentureBeat
        "https://www.theregister.com/headlines.atom",             # The Register
        "https://feeds.skynews.com/feeds/rss/technology.xml",     # Sky News Tech
        # Internacional — Tier 2
        "https://gizmodo.com/rss",                                # Gizmodo
        "https://mashable.com/feed/",                             # Mashable
        "https://www.zdnet.com/news/rss.xml",                     # ZDNet
        "https://www.digitaltrends.com/feed/",                    # Digital Trends
        "https://www.techradar.com/rss",                          # TechRadar
        "https://thenextweb.com/feed/",                           # The Next Web
        "https://www.pcmag.com/rss/news",                         # PCMag
        "https://www.pcworld.com/index.rss",                      # PCWorld
        "https://www.tomshardware.com/feeds/all",                 # Tom's Hardware
        "https://www.androidpolice.com/feed/",                    # Android Police
        "https://9to5mac.com/feed/",                              # 9to5Mac
        "https://9to5google.com/feed/",                           # 9to5Google
        "https://appleinsider.com/rss/news/",                     # AppleInsider
        "https://www.macrumors.com/macrumors.xml",                # MacRumors
        "https://news.ycombinator.com/rss",                       # Hacker News
        "https://www.producthunt.com/feed",                       # Product Hunt
        "http://news.mit.edu/rss/topic/artificial-intelligence2", # MIT AI News
        "https://www.technologyreview.com/feed/",                 # MIT Tech Review
        "https://deepmind.com/blog/feed/basic/",                  # DeepMind
        "https://openai.com/news/rss.xml",                        # OpenAI
        # PT/BR — mantidos como pedido
        "https://feeds.feedburner.com/TecMundo",                  # TecMundo
        "https://www.tecnoblog.net/feed/",                        # Tecnoblog
        "https://olhardigital.com.br/feed/",                      # Olhar Digital
        "https://canaltech.com.br/rss/",                          # Canaltech
    ],

    # ── SCIENCE ───────────────────────────────────────────────────────────────
    "science": [
        "https://www.sciencedaily.com/rss/all.xml",               # ScienceDaily
        "https://www.nasa.gov/news-release/feed/",                # NASA
        "https://www.newscientist.com/feed/home/",                # New Scientist
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", # BBC Science
        "http://feeds.arstechnica.com/arstechnica/science/",      # Ars Technica Science
        "https://www.space.com/feeds.xml",                        # Space.com
        "https://www.wired.com/category/science/feed",            # Wired Science
        "https://www.theguardian.com/science/rss",                # Guardian Science
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", # NYT Science
        "https://universetoday.com/feed",                         # Universe Today
        "https://www.nature.com/nature.rss",                      # Nature
        "https://www.scientificamerican.com/platform/syndication/rss/", # Scientific American
        "https://phys.org/rss-feed/",                             # Phys.org
        "https://gizmodo.com/science/rss",                        # Gizmodo Science
        "https://futurism.com/feed",                              # Futurism
        "https://www.livescience.com/feeds/all",                  # Live Science
        "https://www.discovermagazine.com/rss",                   # Discover Magazine
        "https://earthsky.org/feed/",                             # EarthSky
        "https://www.sciencenews.org/feed",                       # Science News
        "https://rss.nytimes.com/services/xml/rss/nyt/Environment.xml", # NYT Environment
        "https://www.theguardian.com/environment/rss",            # Guardian Environment
        "https://www.smithsonianmag.com/rss/latest_articles/",    # Smithsonian
    ],

    # ── HEALTH ────────────────────────────────────────────────────────────────
    "health": [
        "https://feeds.bbci.co.uk/news/health/rss.xml",           # BBC Health
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",# NYT Health
        "https://www.theguardian.com/society/health/rss",         # Guardian Health
        "https://feeds.skynews.com/feeds/rss/health.xml",         # Sky News Health
        "https://www.who.int/feeds/entity/news/en/rss.xml",       # WHO
        "https://newsinhealth.nih.gov/syndication/rss",           # NIH
        "https://www.sciencedaily.com/rss/health_medicine/",      # ScienceDaily Health
        "http://feeds.arstechnica.com/arstechnica/health/",       # Ars Technica Health
        "https://www.medicalnewstoday.com/rss/medicalnewstoday",  # Medical News Today
        "https://www.healthline.com/rss/health-news",             # Healthline
        "https://www.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",# WebMD
        "https://www.mayoclinic.org/rss/all-health-information-topics.rss", # Mayo Clinic
        "https://www.statnews.com/feed/",                         # STAT News
        "https://www.livescience.com/feeds/health",               # Live Science Health
        "https://futurism.com/health/feed",                       # Futurism Health
        "https://www.prevention.com/rss/all/",                    # Prevention
        "https://www.everydayhealth.com/rss/all-articles.aspx",   # Everyday Health
        "https://rss.nytimes.com/services/xml/rss/nyt/Well.xml",  # NYT Well
        "https://www.theguardian.com/society/mentalhealth/rss",   # Guardian Mental Health
        "https://www.sciencenews.org/topic/health-medicine/feed", # ScienceNews Health
    ],

    # ── SPORTS ────────────────────────────────────────────────────────────────
    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",                 # BBC Sport
        "https://feeds.bbci.co.uk/sport/football/rss.xml",        # BBC Football
        "https://www.espn.com/espn/rss/news",                     # ESPN
        "https://www.skysports.com/rss/12040",                    # Sky Sports
        "https://www.theguardian.com/sport/rss",                  # Guardian Sport
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",# NYT Sports
        "https://feeds.skynews.com/feeds/rss/sports.xml",         # Sky News Sport
        "https://www.cbssports.com/rss/headlines/",               # CBS Sports
        "https://www.marca.com/rss/portada.xml",                  # Marca (football)
        "https://www.eurosport.com/rss/news/",                    # Eurosport
        "https://www.latimes.com/sports.rss",                     # LA Times Sports
        "https://www.washingtontimes.com/rss/headlines/sports/",  # Washington Times Sports
        "https://www.smh.com.au/rss/sport.xml",                   # Sydney Morning Herald Sport
        "https://boxingnewsonline.net/feed/",                     # Boxing News
        "https://www.essentiallysports.com/feed/",                # Essentially Sports
        "https://www.goal.com/feeds/en/news",                     # Goal.com Football
        "https://www.nba.com/rss/nba_rss.xml",                    # NBA
        "https://www.formula1.com/content/fom-website/en/latest/all.xml", # F1
        "https://www.autosport.com/rss/motorsport/news/",         # Autosport
        "https://www.tennis.com/rss/news",                        # Tennis.com
        "https://www.cycling news.com/rss/news/",                 # CyclingNews
        "https://api.foxsports.com/v2/content/optimized-rss?partnerKey=MB0Wehpmuj2lUhuRhQaafhBjAJqaPU244mlTDK1i&size=30", # Fox Sports
        "https://theathletic.com/rss/news/",                      # The Athletic
        "https://www.bleacherreport.com/articles/feed",           # Bleacher Report
        "https://www.sportingnews.com/rss",                       # Sporting News
    ],

    # ── ENTERTAINMENT ─────────────────────────────────────────────────────────
    "entertainment": [
        "https://feeds.skynews.com/feeds/rss/entertainment.xml",  # Sky News Entertainment
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", # BBC Entertainment
        "https://variety.com/feed/",                              # Variety
        "https://www.hollywoodreporter.com/t/news/feed/",         # Hollywood Reporter
        "https://deadline.com/feed/",                             # Deadline
        "https://pitchfork.com/rss/news/feed/r.xml",              # Pitchfork
        "https://www.rollingstone.com/music/music-news/feed/",    # Rolling Stone Music
        "https://ew.com/feed/",                                   # Entertainment Weekly
        "https://www.theguardian.com/culture/rss",                # Guardian Culture
        "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml",  # NYT Arts
        "https://www.billboard.com/feed/",                        # Billboard
        "https://www.nme.com/feed",                               # NME Music
        "https://www.ign.com/rss/articles",                       # IGN
        "https://www.gamespot.com/feeds/mashup/",                 # GameSpot
        "https://kotaku.com/rss",                                 # Kotaku
        "https://io9.com/rss",                                    # io9 (sci-fi/pop culture)
        "https://www.vulture.com/rss/all.xml",                    # Vulture
        "https://www.empireonline.com/movies/rss/",               # Empire (cinema)
        "https://collider.com/feed/",                             # Collider
        "https://screenrant.com/feed/",                           # Screen Rant
        "https://www.indiewire.com/feed/",                        # IndieWire
        "https://www.polygon.com/rss/index.xml",                  # Polygon (games)
        "https://www.pcgamer.com/rss/",                           # PC Gamer
        "https://pagesix.com/feed/",                              # Page Six (celebs)
        "https://feeds.feedburner.com/nymag/vulture",             # NY Mag Vulture
    ],

    # ── BUSINESS ──────────────────────────────────────────────────────────────
    "business": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",         # BBC Business
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", # NYT Business
        "https://feeds.skynews.com/feeds/rss/business.xml",       # Sky News Business
        "https://www.theguardian.com/business/rss",               # Guardian Business
        "https://www.marketwatch.com/rss/topstories",             # MarketWatch
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # CNBC World
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",          # WSJ Markets
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",            # WSJ World
        "https://www.ft.com/?format=rss",                         # Financial Times
        "https://www.economist.com/latest/rss.xml",               # The Economist
        "https://feeds.bloomberg.com/markets/news.rss",           # Bloomberg Markets
        "https://www.forbes.com/business/feed/",                  # Forbes Business
        "https://www.businessinsider.com/rss",                    # Business Insider
        "https://feeds.washingtonpost.com/rss/business",          # WashPost Business
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",   # CNBC Finance
        "https://fortune.com/feed",                               # Fortune
        "https://hbr.org/resources/rss/editorial/feed",           # Harvard Business Review
        "https://www.fastcompany.com/latest/rss",                 # Fast Company
        "https://www.inc.com/rss",                                # Inc. Magazine
        "https://www.entrepreneur.com/latest.rss",                # Entrepreneur
    ],

    # ── AFRICA / ANGOLA / LUSOPHONE ───────────────────────────────────────────
    # Categoria dedicada para contexto africano e lusófono (não BR-centric)
    "africa": [
        "https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf", # All Africa
        "https://allafrica.com/tools/headlines/rdf/angola/headlines.rdf", # All Africa Angola
        "https://allafrica.com/tools/headlines/rdf/southafrica/headlines.rdf", # SA
        "https://allafrica.com/tools/headlines/rdf/nigeria/headlines.rdf", # Nigeria
        "https://allafrica.com/tools/headlines/rdf/kenya/headlines.rdf",   # Kenya
        "https://allafrica.com/tools/headlines/rdf/ethiopia/headlines.rdf",# Ethiopia
        "https://allafrica.com/tools/headlines/rdf/ghana/headlines.rdf",   # Ghana
        "https://www.bbc.co.uk/africa/feeds/rss/",                # BBC Africa
        "https://rss.dw.com/rdf/rss-en-africa",                   # DW Africa
        "https://www.france24.com/en/africa/rss",                 # France24 Africa
        "https://www.voanews.com/api/zy_qoeivei",                  # VOA Africa
        "https://www.dn.pt/rss/mundo.xml",                        # Diário de Notícias PT
        "https://www.publico.pt/api/rss/mundo",                   # Público PT
        "https://www.rtp.pt/noticias/rss/mundo",                  # RTP Notícias
        "https://www.jornaldenegocios.pt/rss/all",                # Jornal de Negócios PT
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
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
    text = re.sub(r'&(?:[a-zA-Z]+|#\d+);', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

def is_valid_image(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    url_lower = url.lower().split("?")[0]
    bad_kw = [
        'pixel', 'tracker', 'tracking', 'beacon', '1x1', 'spacer',
        'logo', 'favicon', 'icon', 'avatar', 'placeholder',
        'blank', 'transparent', 'data:image', 'badge', 'button',
    ]
    for kw in bad_kw:
        if kw in url_lower:
            return False
    bad_ext = ['.gif', '.ico', '.svg', '.bmp', '.tiff', '.webmanifest', '.txt']
    for ext in bad_ext:
        if url_lower.endswith(ext):
            return False
    return True

def extract_image_from_rss_item(item, desc_tag) -> str:
    # 1. media:content / media:thumbnail — prefere maior width
    for tag_name in ["media:content", "media:thumbnail"]:
        tags = item.find_all(tag_name)
        best, best_w = None, 0
        for t in tags:
            t_type = t.get("type", "")
            t_url  = t.get("url", "")
            if not t_url:
                continue
            if t_type and not t_type.startswith("image"):
                continue
            try:
                w = int(t.get("width", 0))
            except:
                w = 1
            if w >= best_w:
                best_w, best = w, t_url
        if best and is_valid_image(best):
            return best

    # 2. enclosure
    enc = item.find("enclosure")
    if enc:
        enc_url  = enc.get("url", "")
        enc_type = enc.get("type", "")
        if enc_url and (not enc_type or enc_type.startswith("image")) and is_valid_image(enc_url):
            return enc_url

    # 3. <img> embutida no HTML da description / content:encoded
    for tag in [item.find("content:encoded"), desc_tag]:
        if not tag:
            continue
        raw = str(tag)
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw)
        if m and is_valid_image(m.group(1)):
            return m.group(1)

    # 4. itunes:image
    it = item.find("itunes:image")
    if it:
        href = it.get("href", "")
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
        for attr_name, attr_val in [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name",     "twitter:image"),
            ("name",     "twitter:image:src"),
            ("itemprop", "image"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag:
                content = (tag.get("content") or "").strip()
                if is_valid_image(content):
                    return content
    except Exception as e:
        print(f"[OG_IMAGE] {url}: {e}")
    return ""

def scrape_full_content(url: str) -> dict:
    result = {
        "title": "", "description": "", "body": "",
        "image_url": "", "author": "", "published_at": "",
        "source_name": "", "source_domain": "", "favicon_url": "",
        "url": url,
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
            (("meta", {"property": "og:title"}),  "content"),
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
        for attr_name, attr_val in [
            ("property", "og:description"),
            ("name",     "description"),
            ("name",     "twitter:description"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag and tag.get("content"):
                result["description"] = clean_text(tag["content"], 800)
                break

        # Imagem
        for attr_name, attr_val in [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name",     "twitter:image"),
            ("name",     "twitter:image:src"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag and tag.get("content") and is_valid_image(tag["content"].strip()):
                result["image_url"] = tag["content"].strip()
                break

        # Autor
        for sel, attr in [
            (("meta", {"name": "author"}),            "content"),
            (("meta", {"property": "article:author"}),"content"),
            (("meta", {"name": "dc.creator"}),        "content"),
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

        # Corpo
        body_candidates = [
            soup.find("article"),
            soup.find(class_=re.compile(
                r'article-body|post-content|entry-content|story-body|article__body|'
                r'content-body|main-content|article-text|story-content|post-body', re.I)),
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
            body_text  = " ".join(
                clean_text(p.get_text(), 1000)
                for p in paragraphs if len(p.get_text().strip()) > 40
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
        r = requests.get(feed_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            print(f"[RSS SKIP] {feed_url} → HTTP {r.status_code}")
            return []

        try:
            soup = BeautifulSoup(r.content, "xml")
        except Exception:
            soup = BeautifulSoup(r.content, "lxml")

        items = soup.find_all("item")
        if not items:
            items = soup.find_all("entry")  # Atom feeds
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
            desc = clean_text(desc_tag.get_text() if desc_tag else "", 800)

            img = extract_image_from_rss_item(item, desc_tag)
            if not img and url:
                img = scrape_og_image(url, timeout=4)

            pub_date = ""
            for dname in ["pubDate", "dc:date", "published", "updated"]:
                pd = item.find(dname)
                if pd and pd.get_text(strip=True):
                    pub_date = pd.get_text(strip=True)
                    break

            author = ""
            for aname in ["dc:creator", "author", "dc:author"]:
                at = item.find(aname)
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

# ── Fetch por categoria com threads paralelas ─────────────────────────────────

def _fetch_category(category: str, limit: int) -> list:
    feed_urls = SOURCES.get(category, SOURCES["world"])
    per_feed  = max(5, (limit // len(feed_urls)) + 3)
    results   = [[] for _ in feed_urls]

    def fetch_one(idx, url):
        results[idx] = parse_rss_feed(url, category, limit=per_feed)

    threads = [
        threading.Thread(target=fetch_one, args=(i, u), daemon=True)
        for i, u in enumerate(feed_urls)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    articles = []
    for r in results:
        articles.extend(r)

    # Deduplicação por título normalizado
    seen, unique = set(), []
    for a in articles:
        key = re.sub(r'\W+', '', a["title"][:60].lower())
        if key and key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    # Artigos com imagem primeiro
    unique.sort(key=lambda x: (0 if x["image_url"] else 1))

    return unique[:limit]

# ── Warm-up atrasado ──────────────────────────────────────────────────────────

def warm_cache():
    time.sleep(5)  # Espera o Flask estar a ouvir antes de fazer qualquer request
    print("[WARM] A iniciar pré-cache em background...")
    for cat in SOURCES.keys():
        try:
            key = f"news_{cat}_20"
            if not cache_get(key):
                arts = _fetch_category(cat, 20)
                cache_set(key, arts)
                print(f"[WARM] '{cat}' → {len(arts)} artigos")
        except Exception as e:
            print(f"[WARM ERROR] {cat}: {e}")
        time.sleep(2)
    print("[WARM] Pré-cache completo.")

# ── Arranque das threads de background ───────────────────────────────────────
threading.Thread(target=self_ping,  daemon=True).start()
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
    return jsonify({cat: len(urls) for cat, urls in SOURCES.items()})

@app.route("/health")
def health():
    cached_cats = [k for k in _cache if k.startswith("news_")]
    return jsonify({
        "status":            "ok",
        "time":              datetime.now(timezone.utc).isoformat(),
        "cached_categories": len(cached_cats),
        "total_cache_keys":  len(_cache),
        "categories":        list(SOURCES.keys()),
        "total_feeds":       sum(len(v) for v in SOURCES.values()),
    })

@app.route("/")
def index():
    return jsonify({
        "name":        "GlobeNews API",
        "version":     "3.2",
        "total_feeds": sum(len(v) for v in SOURCES.values()),
        "endpoints": {
            "/news":       "?category=world|technology|science|health|sports|entertainment|business|africa&limit=20&force=0",
            "/article":    "?url=<article_url>",
            "/categories": "lista de categorias e número de fontes",
            "/health":     "status da API",
        },
        "sources_per_category": {cat: len(urls) for cat, urls in SOURCES.items()},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)