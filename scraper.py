import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

def parse_rss(source, limit=20):
    try:
        feed = feedparser.parse(source["rss"])
        articles = []
        for entry in feed.entries[:limit]:
            articles.append({
                "source_id": source["id"],
                "source_name": source["name"],
                "country": source["country"],
                "lang": source["lang"],
                "title": entry.get("title", ""),
                "description": entry.get("summary", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "author": entry.get("author", ""),
                "tags": [t.get("term", "") for t in entry.get("tags", [])],
                "images": [],
                "videos": [],
                "content": "",
                "scraped_at": datetime.utcnow().isoformat()
            })
        return articles
    except Exception:
        return []

def scrape_full_article(article_dict):
    url = article_dict.get("url", "")
    if not url:
        return article_dict

    try:
        from newspaper import Article
        art = Article(url)
        art.download()
        art.parse()
        article_dict["content"] = art.text
        if art.top_image:
            article_dict["images"].append(art.top_image)
        article_dict["images"] += [img for img in art.images if img not in article_dict["images"]]
        if not article_dict["author"] and art.authors:
            article_dict["author"] = ", ".join(art.authors)
        if not article_dict["published"] and art.publish_date:
            article_dict["published"] = art.publish_date.isoformat()
    except Exception:
        pass

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src.startswith("http") and src not in article_dict["images"]:
                article_dict["images"].append(src)

        for vid in soup.find_all("video"):
            src = vid.get("src") or (vid.find("source") and vid.find("source").get("src"))
            if src and src not in article_dict["videos"]:
                article_dict["videos"].append(src)

        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if any(p in src for p in ["youtube", "vimeo", "dailymotion", "rumble", "twitch"]):
                if src not in article_dict["videos"]:
                    article_dict["videos"].append(src)

        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            if og_img["content"] not in article_dict["images"]:
                article_dict["images"].insert(0, og_img["content"])

        og_vid = soup.find("meta", property="og:video")
        if og_vid and og_vid.get("content"):
            if og_vid["content"] not in article_dict["videos"]:
                article_dict["videos"].insert(0, og_vid["content"])

    except Exception:
        pass

    article_dict["images"] = article_dict["images"][:10]
    article_dict["videos"] = article_dict["videos"][:5]
    return article_dict