import os
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS
from sources import SOURCES
from scraper import parse_rss, scrape_full_article

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "sources": len(SOURCES)})

@app.route("/sources", methods=["GET"])
def get_sources():
    country = request.args.get("country")
    lang = request.args.get("lang")
    result = SOURCES
    if country:
        result = [s for s in result if s["country"].upper() == country.upper()]
    if lang:
        result = [s for s in result if s["lang"].lower() == lang.lower()]
    return jsonify({"total": len(result), "sources": result})

@app.route("/news", methods=["GET"])
def get_news():
    source_id = request.args.get("source_id")
    country = request.args.get("country")
    lang = request.args.get("lang")
    limit = int(request.args.get("limit", 10))
    full = request.args.get("full", "false").lower() == "true"

    sources = SOURCES
    if source_id:
        sources = [s for s in sources if s["id"] == source_id]
    if country:
        sources = [s for s in sources if s["country"].upper() == country.upper()]
    if lang:
        sources = [s for s in sources if s["lang"].lower() == lang.lower()]
    if not sources:
        return jsonify({"error": "Nenhuma fonte encontrada"}), 404

    all_articles = []
    lock = threading.Lock()

    def fetch_source(source):
        articles = parse_rss(source, limit)
        if full:
            articles = [scrape_full_article(a) for a in articles]
        with lock:
            all_articles.extend(articles)

    threads = [threading.Thread(target=fetch_source, args=(s,)) for s in sources]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)

    return jsonify({"total": len(all_articles), "full_scrape": full, "articles": all_articles})

@app.route("/article", methods=["GET"])
def get_article():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parâmetro 'url' obrigatório"}), 400
    article = {"url": url, "title": "", "description": "", "content": "", "author": "", "published": "", "tags": [], "images": [], "videos": []}
    return jsonify(scrape_full_article(article))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)