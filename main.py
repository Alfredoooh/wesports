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

# ── Cache em memória ──────────────────────────────────────────────────────────
_mem_cache: dict = {}
MEM_TTL = 300

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

# ── Tradução para PT ──────────────────────────────────────────────────────────
_trans_lock = threading.Lock()

def translate_to_pt(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return text
    pt_markers = ["que", "de", "e", "o", "a", "em", "com", "para", "uma", "um",
                  "por", "se", "do", "da", "os", "as", "ao", "na", "no", "foi"]
    words = text.lower().split()[:30]
    pt_count = sum(1 for w in words if w in pt_markers)
    if len(words) > 5 and pt_count / len(words) > 0.25:
        return text

    text_hash = hashlib.md5(text.encode()).hexdigest()
    cached = db_get_translation(text_hash)
    if cached:
        return cached

    chunk = text[:4500]
    try:
        with _trans_lock:
            result = GoogleTranslator(source="auto", target="pt").translate(chunk)
        if result:
            if len(text) > 4500:
                result = result + " " + text[4500:]
            db_set_translation(text_hash, result)
            return result
    except Exception as e:
        print(f"[TRANSLATE] {e}")
    return text

def translate_article(article: dict) -> dict:
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

# ── SOURCES ───────────────────────────────────────────────────────────────────
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
        "https://www.theatlantic.com/feed/all/",
        "https://foreignpolicy.com/feed/",
        "https://www.foreignaffairs.com/rss.xml",
        "https://www.middleeasteye.net/rss",
        "https://www.dw.com/rss/ept/s-9097",
        "https://www.scmp.com/rss/91/feed",
        "https://www.straitstimes.com/news/world/rss.xml",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
        "https://www.thenationalnews.com/rss",
        "https://feeds.feedburner.com/crooksandliars/fHTE",
        "https://www.globaltimes.cn/rss/outbrain.xml",
        "https://english.alarabiya.net/tools/rss",
        "https://www.hindustantimes.com/rss/topnews/rssfeed.xml",
        "https://www.thehindu.com/news/international/?service=rss",
        "https://feeds.feedburner.com/Antiwar-Antiwar",
        "https://www.trtworld.com/rss",
        "https://www.presstv.ir/homefeed.aspx",
        "https://www.dawn.com/feeds/home",
        "https://www.baltictimes.com/rss/news/",
        "https://feeds.feedburner.com/RealClearWorld",
    ],
    "technology": [
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://www.wired.com/feed/rss",
        "http://feeds.arstechnica.com/arstechnica/index/",
        "https://www.engadget.com/rss.xml",
        "https://www.cnet.com/rss/all/",
        "https://venturebeat.com/feed/",
        "https://www.theregister.com/headlines.atom",
        "https://feeds.skynews.com/feeds/rss/technology.xml",
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
        "https://feeds.feedburner.com/TecMundo",
        "https://www.tecnoblog.net/feed/",
        "https://olhardigital.com.br/feed/",
        "https://canaltech.com.br/rss/",
        "https://www.androidauthority.com/feed/",
        "https://www.phonearena.com/news/feed",
        "https://www.ifixit.com/News/rss",
        "https://www.techdirt.com/feed/",
        "https://www.computerworld.com/index.rss",
        "https://www.infoworld.com/index.rss",
        "https://www.networkworld.com/index.rss",
        "https://www.csoonline.com/index.rss",
        "https://www.itpro.com/rss",
        "https://www.infoq.com/feed/",
        "https://feeds.feedburner.com/Slashdot/slashdot",
        "https://lobste.rs/rss",
        "https://simonwillison.net/atom/everything/",
        "https://www.artificialintelligence-news.com/feed/",
        "https://towardsdatascience.com/feed",
        "https://machinelearningmastery.com/feed/",
        "https://spectrum.ieee.org/feeds/feed.rss",
        "https://www.embedded.com/rss/",
        "https://www.semianalysis.com/feed",
        "https://stratechery.com/feed/",
        "https://www.ben-evans.com/benedictevans?format=rss",
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
        "https://www.quantamagazine.org/feed/",
        "https://www.iflscience.com/rss.xml",
        "https://www.zmescience.com/feed/",
        "https://www.sciencealert.com/feed",
        "https://www.popularmechanics.com/rss/all.xml/",
        "https://www.skyandtelescope.com/feed/",
        "https://www.astronomy.com/feed/",
        "https://www.planetary.org/news/rss",
        "https://www.esa.int/rssfeed/ESA_Top_News",
        "https://blogs.nasa.gov/hubble/feed/",
        "https://www.cell.com/current-biology/current.rss",
        "https://feeds.plos.org/plosone/NewArticles",
        "https://www.the-scientist.com/rss",
        "https://www.biochemist.org/news/rss",
        "https://www.psychologytoday.com/intl/articles/feed",
        "https://neurosciencenews.com/feed/",
        "https://www.anthropocenemagazine.org/feed/",
        "https://www.geologyin.com/feeds/posts/default",
        "https://www.oceansciencenews.org/feed/",
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
        "https://www.reuters.com/rssFeed/healthNews",
        "https://www.hhs.gov/rss/news.xml",
        "https://publichealthinsider.com/feed/",
        "https://www.health.com/rss",
        "https://www.everydayhealth.com/rss/all-articles.aspx",
        "https://medlineplus.gov/rss/medlineplus_whatsnew.xml",
        "https://www.mediglobal.org/feed/",
        "https://www.biospace.com/rss/",
        "https://www.healio.com/rss",
        "https://www.fiercepharma.com/rss/xml",
        "https://www.fierce biotech.com/rss/xml",
        "https://www.drugdiscoverytoday.com/rss/news",
        "https://www.medpagetoday.com/rss/headlines.xml",
        "https://www.psychiatrictimes.com/rss/content/rss",
        "https://www.nutritionaction.com/rss",
        "https://www.eatright.org/rss",
        "https://www.hsph.harvard.edu/news/hsph-in-the-news/feed/",
        "https://www.mayoclinic.org/rss/all-health-information-topics",
        "https://www.clevelandclinic.org/health/rss/",
        "https://www.heart.org/en/news/rss",
        "https://www.cancer.gov/news-events/cancer-currents-blog/feed",
        "https://www.diabetes.org/newsroom/rss",
        "https://www.alzheimers.net/feed/",
        "https://www.mentalhealth.org.uk/rss.xml",
        "https://psychcentral.com/feed/",
        "https://www.verywellmind.com/feed",
        "https://www.verywellhealth.com/feed",
        "https://www.sleepfoundation.org/feed",
        "https://examine.com/feed.xml",
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
        "https://www.si.com/rss/si_topstories.rss",
        "https://sportbible.com/feed",
        "https://www.90min.com/feed",
        "https://www.givemesport.com/feed/",
        "https://www.4fourtwofootball.com/rss",
        "https://www.transfermarkt.com/news/latest/news",
        "https://www.fanatiz.com/rss",
        "https://www.mundodeportivo.com/rss/home.xml",
        "https://www.sport.es/rss/portada.xml",
        "https://www.as.com/rss/tags/ultimas_noticias.xml",
        "https://www.record.pt/rss/",
        "https://www.abola.pt/rss/",
        "https://www.zerozero.pt/rss.php",
        "https://www.maisfutebol.iol.pt/rss",
        "https://www.mlb.com/feeds/news/rss.xml",
        "https://www.nhl.com/rss/news.xml",
        "https://www.atptour.com/en/media/rss-feed/xml-feed",
        "https://www.wtatennis.com/feed.rss",
        "https://www.ufc.com/rss.xml",
        "https://www.mmamania.com/rss/current",
        "https://www.cycling weekly.co.uk/feed",
        "https://www.velonews.com/feed/",
        "https://www.insidethegames.biz/rss",
        "https://www.olympics.com/en/news/rss.xml",
        "https://www.worldrugby.org/rss",
        "https://www.rugbypass.com/feed/",
        "https://www.cricket.com.au/news/rss",
        "https://www.espncricinfo.com/rss/content/story/feeds/0.xml",
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
        "https://www.spin.com/feed/",
        "https://www.loudwire.com/feed/",
        "https://www.kerrang.com/feed",
        "https://www.metalinjection.net/feed",
        "https://www.blabbermouth.net/feed/",
        "https://www.alternativepress.com/feed/",
        "https://www.animenewsnetwork.com/news/rss.xml",
        "https://www.crunchyroll.com/newsrss?lang=enUS",
        "https://www.cbr.com/feed/",
        "https://www.comicbookmovie.com/rss/news.xml",
        "https://www.denofgeek.com/feed/",
        "https://www.syfy.com/syfy-wire/rss",
        "https://www.gamesradar.com/feeds/rss",
        "https://www.eurogamer.net/feed",
        "https://www.rockpapershotgun.com/feed/rss",
        "https://www.vg247.com/feed/rss",
        "https://www.pushsquare.com/feeds/latest",
        "https://www.nintendolife.com/feeds/latest",
        "https://www.purexbox.com/feeds/latest",
        "https://www.thescene.com/rss",
        "https://www.instyle.com/rss/all.xml",
        "https://people.com/rss/all/",
        "https://us.hellomagazine.com/rss/",
        "https://www.tmz.com/rss.xml",
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
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
        "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline",
        "https://seekingalpha.com/feed.xml",
        "https://www.thestreet.com/rss/index.xml",
        "https://rss.politico.com/economy.xml",
        "https://feeds.skynews.com/feeds/rss/money.xml",
        "https://www.reuters.com/rssFeed/businessNews",
        "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com&hl=en&gl=US&ceid=US:en",
        "https://www.morningstar.com/rss/",
        "https://feeds.feedburner.com/RealClearMarkets",
        "https://www.barrons.com/feed",
        "https://www.kiplinger.com/feed/rss",
        "https://www.moneycontrol.com/rss/MCrecentnews.xml",
        "https://www.livemint.com/rss/news",
        "https://feeds.feedburner.com/zerohedge/feed",
        "https://www.pragcap.com/feed/",
        "https://www.calculatedriskblog.com/feeds/posts/default",
        "https://www.visualcapitalist.com/feed/",
        "https://www.businesstimes.com.sg/rss/home",
        "https://www.arabianbusiness.com/rss",
        "https://africa.businessinsider.com/rss",
        "https://www.howmuch.net/feed",
        "https://www.efinancialnews.com/rss/frontpage",
        "https://www.accountingtoday.com/feed",
        "https://www.supplychaindive.com/feeds/news/",
        "https://www.retaildive.com/feeds/news/",
        "https://www.logisticsmgmt.com/rss/",
        "https://www.industryweek.com/rss/all",
        "https://www.manufacturingdive.com/feeds/news/",
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
        "https://allafrica.com/tools/headlines/rdf/senegal/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/zimbabwe/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/cameroon/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/uganda/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/rwanda/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/zambia/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/mali/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/niger/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/liberia/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/sierra_leone/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/botswana/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/namibia/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/malawi/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/mauritius/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/lesotho/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/swaziland/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/madagascar/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/somalia/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/sudan/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/drc/headlines.rdf",
        "https://allafrica.com/tools/headlines/rdf/cote_d_ivoire/headlines.rdf",
        "https://www.theafricareport.com/feed/",
        "https://www.africanews.com/feed/rss",
        "https://mg.co.za/feed/",
        "https://www.dailymaverick.co.za/feed/",
        "https://www.businessdayonline.com/feed/",
        "https://punchng.com/feed/",
        "https://www.premiumtimesng.com/feed/",
        "https://www.dailytrust.com/feed",
        "https://www.thenationonlineng.net/feed/",
        "https://www.monitor.co.ug/Uganda/rss",
        "https://www.thedailystar.net/frontpage/rss.xml",
        "https://www.nation.co.ke/rss/",
        "https://www.standardmedia.co.ke/rss/articles.php",
        "https://www.myjoyonline.com/feed/",
        "https://www.graphic.com.gh/feed/",
        "https://www.moroccoworld news.com/feed/",
        "https://www.egyptindependent.com/feed/",
        "https://www.ethiopia-herald.com/?feed=rss2",
        "https://angop.ao/angola/pt_pt/noticias/rss_noticias.xml",
        "https://www.jornaldeangola.ao/ao/noticias/rss",
        "https://www.voaportugues.com/api/zmoqmmveii",
        "https://rr.sapo.pt/rss/ultimas",
        "https://sicnoticias.pt/rss",
        "https://www.cmjornal.pt/rss",
    ],
    "politics": [
        "https://rss.politico.com/politics-news.xml",
        "https://thehill.com/homenews/feed/",
        "https://www.vox.com/rss/politics/index.xml",
        "https://feeds.washingtonpost.com/rss/politics",
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        "https://www.axios.com/feeds/feed.rss",
        "https://www.rollcall.com/feed/",
        "https://www.realclearpolitics.com/index.xml",
        "https://feeds.feedburner.com/thedailybeast/politics",
        "https://www.npr.org/rss/rss.php?id=1014",
        "https://feeds.feedburner.com/huffingtonpost/raw_feed",
        "https://slate.com/feeds/all.rss",
        "https://www.salon.com/topic/politics/index.rss",
        "https://www.motherjones.com/politics/feed/",
        "https://talkingpointsmemo.com/feed",
        "https://www.nationalreview.com/feed/",
        "https://www.weeklystandard.com/rss",
        "https://www.redstate.com/feed/",
        "https://www.breitbart.com/feed/",
        "https://feeds.foxnews.com/foxnews/politics",
        "https://www.dailywire.com/feeds/rss.xml",
        "https://www.thefederalist.com/feed/",
        "https://reason.com/feed/",
        "https://www.cato.org/rss.xml",
        "https://foreignpolicy.com/feed/",
        "https://www.foreignaffairs.com/rss.xml",
        "https://carnegieendowment.org/publications/rss",
        "https://www.brookings.edu/feed/",
        "https://www.cfr.org/rss/publications",
        "https://www.pewresearch.org/feed/",
        "https://www.opensecrets.org/news/feed",
        "https://rss.politico.com/congress.xml",
        "https://rss.politico.com/whitehouse.xml",
        "https://rss.politico.com/economy.xml",
        "https://apnews.com/apf-politics",
        "https://www.c-span.org/podcasts/rss/podcast.rss",
        "https://www.theguardian.com/us-news/us-politics/rss",
        "https://www.independent.co.uk/news/uk/politics/rss",
        "https://www.euractiv.com/sections/politics/feed/",
        "https://www.politico.eu/feed/",
        "https://www.dw.com/en/top-stories/politics/s-51822/rss",
        "https://www.france24.com/en/europe/rss",
        "https://www.publico.pt/api/rss/politica",
        "https://www.dn.pt/rss/politica.xml",
        "https://feeds.feedburner.com/obsei-pt/noticias",
        "https://www.expresso.pt/rss",
        "https://www.rtp.pt/noticias/rss/politica",
    ],
    "gaming": [
        "https://www.ign.com/rss/articles",
        "https://www.gamespot.com/feeds/mashup/",
        "https://kotaku.com/rss",
        "https://www.polygon.com/rss/index.xml",
        "https://www.pcgamer.com/rss/",
        "https://www.eurogamer.net/feed",
        "https://www.rockpapershotgun.com/feed/rss",
        "https://www.vg247.com/feed/rss",
        "https://www.gamesradar.com/feeds/rss",
        "https://www.pushsquare.com/feeds/latest",
        "https://www.nintendolife.com/feeds/latest",
        "https://www.purexbox.com/feeds/latest",
        "https://www.destructoid.com/feed/",
        "https://www.shacknews.com/rss",
        "https://www.gameinformer.com/rss.xml",
        "https://www.dualshockers.com/feed/",
        "https://toucharcade.com/feed/",
        "https://www.pocketgamer.com/feed/",
        "https://www.androidauthority.com/category/apps-games/feed/",
        "https://www.thegamer.com/feed/",
        "https://gamerant.com/feed/",
        "https://www.cbr.com/category/gaming/feed/",
        "https://www.vgchartz.com/rss/rss.php",
        "https://www.gamespark.jp/rss/rss.xml",
        "https://www.pcgamesn.com/mainrss.xml",
        "https://www.windowscentral.com/gaming/rss",
        "https://www.godisageek.com/feed/",
        "https://www.wccftech.com/feed/",
        "https://www.playstationlifestyle.net/feed/",
        "https://www.tweaktown.com/news/index.rss",
        "https://www.hardcoregamer.com/feed/",
        "https://www.twinfinite.net/feed/",
        "https://www.gamingbolt.com/feed",
        "https://www.noisypixel.net/feed/",
        "https://www.fandomspot.com/feed/",
        "https://www.siliconera.com/feed/",
        "https://www.rpgsite.net/rss.xml",
        "https://nichegamer.com/feed/",
        "https://www.operationsports.com/rss/news/",
        "https://massivelyop.com/feed/",
        "https://www.mmorpg.com/rss.cfm",
        "https://dotesports.com/feed",
        "https://www.invenglobal.com/rss",
        "https://www.gosugamers.net/rss",
        "https://www.redbull.com/int-en/tags/gaming/rss",
        "https://esportsinsider.com/feed/",
        "https://www.pcinvasion.com/feed/",
        "https://www.altchar.com/feed/",
    ],
    "finance": [
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.marketwatch.com/rss/topstories",
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "https://www.ft.com/rss/home/us",
        "https://seekingalpha.com/feed.xml",
        "https://www.thestreet.com/rss/index.xml",
        "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline",
        "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
        "https://www.barrons.com/feed",
        "https://www.morningstar.com/rss/",
        "https://feeds.feedburner.com/zerohedge/feed",
        "https://www.kiplinger.com/feed/rss",
        "https://www.fool.com/feeds/index.aspx",
        "https://moneyweek.com/feed",
        "https://www.benzinga.com/feed",
        "https://finance.yahoo.com/rss/topfinstories",
        "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
        "https://feeds.feedburner.com/RealClearMarkets",
        "https://www.businesswire.com/rss/home/?rss=G7",
        "https://prnewswire.com/rss/news-releases-list.rss",
        "https://www.globenewswire.com/RssFeed/subjectcode/23",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://www.cryptonewsz.com/feed/",
        "https://cryptopotato.com/feed/",
        "https://ambcrypto.com/feed/",
        "https://beincrypto.com/feed/",
        "https://www.newsbtc.com/feed/",
        "https://bitcoinmagazine.com/feed",
        "https://www.coingape.com/feed/",
        "https://www.blockchain.news/rss",
        "https://cryptobriefing.com/feed/",
        "https://www.visualcapitalist.com/feed/",
        "https://www.economicpolicyresearch.org/feed",
        "https://www.nber.org/rss/new_releases.rss",
        "https://feeds.feedburner.com/marginalrevolution",
        "https://www.calculatedriskblog.com/feeds/posts/default",
        "https://www.nakedcapitalism.com/feed",
        "https://www.pragcap.com/feed/",
        "https://www.bravenewcoin.com/news-rss",
        "https://www.fxstreet.com/rss?cat=news",
        "https://www.forexfactory.com/rss",
        "https://www.dailyfx.com/feeds/all",
        "https://www.finance.gov.ao/rss",
        "https://www.economia.uol.com.br/rss.xml",
        "https://exame.com/rss/",
        "https://www.infomoney.com.br/feed/",
    ],
    "environment": [
        "https://www.theguardian.com/environment/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Environment.xml",
        "https://www.ecowatch.com/rss",
        "https://e360.yale.edu/feed",
        "https://www.climatecentral.org/feed",
        "https://insideclimatenews.org/feed/",
        "https://www.carbonbrief.org/feed/",
        "https://www.climatenexus.org/feed/",
        "https://www.desmog.com/feed/",
        "https://www.greenbiz.com/feeds/news",
        "https://www.treehugger.com/feeds/all/",
        "https://earthjustice.org/feed",
        "https://www.sierraclub.org/planet/rss.xml",
        "https://www.nrdc.org/rss.xml",
        "https://www.nationalgeographic.com/environment/rss",
        "https://www.earthday.org/feed/",
        "https://www.conservation.org/news/rss",
        "https://www.iucn.org/rss.xml",
        "https://www.wwf.org/rss/",
        "https://www.nature.org/en-us/newsroom/rss/",
        "https://www.panda.org/news/rss",
        "https://rainforestnetwork.org/feed/",
        "https://www.oceans.org/feed/",
        "https://oceanservice.noaa.gov/rss/",
        "https://www.seashepherd.org/news-and-media/rss/",
        "https://www.renewableenergyworld.com/feed/",
        "https://cleantechnica.com/feed/",
        "https://electrek.co/feed/",
        "https://www.solarpowerworldonline.com/feed/",
        "https://www.windpowermonthly.com/rss",
        "https://www.pv-tech.org/feed/",
        "https://www.rechargenews.com/rss",
        "https://www.greentechmedia.com/rss/all",
        "https://www.utilitydive.com/feeds/news/",
        "https://www.enr.com/rss",
        "https://phys.org/rss-feed/earth-climate-news/",
        "https://www.wunderground.com/cat6/feed",
        "https://www.climatechangenews.com/feed/",
        "https://www.anthropocenemagazine.org/feed/",
        "https://www.unenvironment.org/rss.xml",
        "https://www.fao.org/news/rss-feed/en/",
        "https://www.worldwildlife.org/rss",
        "https://news.mongabay.com/feed/",
        "https://www.forestsnews.cifor.org/feed",
        "https://www.globalforestwatch.org/blog/feed.xml",
        "https://www.circularonline.co.uk/feed/",
        "https://sustainablebrands.com/feed",
        "https://www.triplepundit.com/feed/",
        "https://www.csrwire.com/rss",
        "https://www.edie.net/rss/",
    ],
    "travel": [
        "https://www.lonelyplanet.com/news/feed",
        "https://www.travelandleisure.com/rss",
        "https://www.cntraveler.com/feed/rss",
        "https://www.fodors.com/rss",
        "https://www.frommers.com/rss",
        "https://www.nomadicmatt.com/feed/",
        "https://www.thepointsguy.com/feed/",
        "https://onemileatatime.com/feed/",
        "https://viewfromthewing.com/feed/",
        "https://upgradedpoints.com/feed/",
        "https://thriftytravel.com/feed/",
        "https://www.tripsavvy.com/news-4684635",
        "https://www.smartertravel.com/feed/",
        "https://www.travelzoo.com/rss/",
        "https://www.airfarewatchdog.com/feed/",
        "https://www.secretflying.com/posts/feed/",
        "https://headforpoints.com/feed/",
        "https://aboardingpass.com/feed/",
        "https://www.flyertalk.com/forum/external.php?type=RSS",
        "https://wanderlustandlipstick.com/feed/",
        "https://www.adventuretraveler.com/feed/",
        "https://uncorneredmarket.com/feed/",
        "https://www.goatsontheroad.com/feed/",
        "https://expertvagabond.com/feed/",
        "https://www.adventurouskate.com/feed/",
        "https://www.worldnomads.com/explore/rss",
        "https://www.roughguides.com/feed/",
        "https://www.telegraph.co.uk/travel/rss",
        "https://www.independent.co.uk/travel/rss",
        "https://www.theguardian.com/travel/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Travel.xml",
        "https://www.afar.com/feeds/latest",
        "https://www.nationalgeographic.com/travel/rss",
        "https://www.atlasobscura.com/feeds/latest",
        "https://www.culturetrip.com/feed/rss",
        "https://roadsandkingdoms.com/feed/",
        "https://theculturetrip.com/feed/",
        "https://www.timeout.com/travel/rss",
        "https://www.wheretotravel.net/feed/",
        "https://www.tripadvisor.com/rss",
        "https://www.expedia.com/stories/rss",
        "https://blog.booking.com/feed/",
        "https://www.hostelworld.com/blog/feed/",
        "https://www.skyscanner.net/news/feed/",
        "https://www.kayak.com/news/feed/",
        "https://www.cnn.com/travel/rss",
        "https://www.forbes.com/travel/feed/",
        "https://www.businesstraveller.com/feed/",
        "https://www.executivetraveller.com/rss",
    ],
    "food": [
        "https://www.seriouseats.com/atom.xml",
        "https://www.foodnetwork.com/fn-dish/rss",
        "https://www.epicurious.com/feed/news-articles-rss",
        "https://www.bonappetit.com/feed/rss",
        "https://www.tastingtable.com/feed/",
        "https://www.foodandwine.com/syndication/rss/",
        "https://www.saveur.com/feed/",
        "https://www.eater.com/rss/index.xml",
        "https://www.thedailymeal.com/rss.xml",
        "https://www.allrecipes.com/feeds/rss/",
        "https://www.cookinglight.com/rss/all/",
        "https://www.delish.com/rss/all.xml/",
        "https://www.tasteofhome.com/rss/",
        "https://www.myrecipes.com/rss/all/",
        "https://smittenkitchen.com/feed/",
        "https://www.101cookbooks.com/feed",
        "https://www.thekitchn.com/main.rss",
        "https://www.simplyrecipes.com/feed/",
        "https://www.skinnytaste.com/feed/",
        "https://www.halfbakedharvest.com/feed/",
        "https://minimalistbaker.com/feed/",
        "https://cookieandkate.com/feed/",
        "https://www.ambitiouskitchen.com/feed/",
        "https://sallysbakingaddiction.com/feed/",
        "https://www.kingarthurbaking.com/blog/rss",
        "https://www.thepioneerwoman.com/food-cooking/recipes/rss/",
        "https://www.foodrepublic.com/rss/",
        "https://www.grubstreet.com/rss/",
        "https://ny.eater.com/rss/index.xml",
        "https://la.eater.com/rss/index.xml",
        "https://london.eater.com/rss/index.xml",
        "https://www.theguardian.com/lifeandstyle/food-and-drink/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/DiningandWine.xml",
        "https://www.nationalgeographic.com/food/rss",
        "https://www.telegraph.co.uk/food-and-drink/rss",
        "https://www.independent.co.uk/life-style/food-and-drink/rss",
        "https://www.foodmatters.com/rss",
        "https://www.medicalnewstoday.com/rss/nutrition-diet",
        "https://www.healthline.com/rss/nutrition",
        "https://www.bbcgoodfood.com/api/content-service/rss/all",
        "https://www.olivemagazine.com/feeds/all/",
        "https://www.deliciousmagazine.co.uk/feed/",
        "https://www.jamieoliver.com/rss/",
        "https://www.nigellalaw son.com/rss",
        "https://www.thehappyfoodie.co.uk/rss",
        "https://www.greatbritishchefs.com/feed/",
        "https://www.sortedfood.com/rss",
        "https://www.lovefood.com/rss/",
        "https://www.vinepair.com/feed/",
        "https://www.wineenthusiast.com/feed/",
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
    if not url:
        return ""
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.content, "lxml")

        for bad in soup.find_all(["script","style","nav","aside","figure",
                                   "figcaption","iframe","button","form",
                                   "header","footer","noscript","advertisement"]):
            bad.decompose()

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
                "body":          desc,
            })

    except Exception as e:
        print(f"[RSS ERROR] {feed_url}: {e}")
    return articles

# ── Enriquecimento de corpos ───────────────────────────────────────────────────

def enrich_bodies(articles: list, top_n: int = 10) -> list:
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

    seen, unique = set(), []
    for a in articles:
        key = re.sub(r'\W+', '', a["title"][:60].lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    unique.sort(key=lambda x: (0 if x["image_url"] else 1))
    unique = enrich_bodies(unique, top_n=15)

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
    db_save_articles(category, final)
    return final[:limit]

# ── Warm-up ───────────────────────────────────────────────────────────────────

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
        "version":     "5.0",
        "total_feeds": sum(len(v) for v in SOURCES.values()),
        "endpoints": {
            "/news":       "?category=world|technology|science|health|sports|entertainment|business|africa|politics|gaming|finance|environment|travel|food&limit=20&force=0&history=0",
            "/article":    "?url=<url>  — corpo completo + traduzido PT",
            "/categories": "fontes por categoria",
            "/health":     "status",
        },
        "sources_per_category": {cat: len(urls) for cat, urls in SOURCES.items()},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)