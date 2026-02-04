#!/usr/bin/env python3
"""
Financial News RSS → Discord Bot
Polls financial RSS feeds and posts new articles to Discord via webhook.
"""

import feedparser
import requests
import json
import time
import signal
import sys
import hashlib
import os
import re
from datetime import datetime, timedelta

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

POLL_INTERVAL = 300        # seconds between feed checks (5 min)
MAX_PER_FEED  = 3          # max articles to post per feed per cycle

# Tracking file lives next to the script itself
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE  = os.path.join(SCRIPT_DIR, ".rss_seen_articles.json")

# ─── FEEDS ───────────────────────────────────────────────────────────────────

FEEDS = {
    "CNBC Top News": {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "color": 0x005999,
        "icon": "https://www.cnbc.com/favicon.ico",
    },
    "CNBC Economy": {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
        "color": 0x005999,
        "icon": "https://www.cnbc.com/favicon.ico",
    },
    "MarketWatch Top": {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "color": 0x00AC4E,
        "icon": "https://www.marketwatch.com/favicon.ico",
    },
    "ZeroHedge": {
        "url": "https://cms.zerohedge.com/fullrss2.xml",
        "color": 0xFC6404,
        "icon": "https://www.zerohedge.com/favicon.ico",
    },
    "Investing.com News": {
        "url": "https://www.investing.com/rss/news.rss",
        "color": 0x1A5276,
        "icon": "https://www.investing.com/favicon.ico",
    },
    "Federal Reserve": {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "color": 0x003366,
        "icon": "https://www.federalreserve.gov/favicon.ico",
    },
}

# ─── GLOBALS ─────────────────────────────────────────────────────────────────

seen_articles = {}
running = True

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def article_id(entry):
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def load_seen():
    global seen_articles
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                seen_articles = json.load(f)
            return True
        except (json.JSONDecodeError, IOError):
            seen_articles = {}
            return False
    return False


def save_seen():
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(seen_articles, f)
    except IOError as e:
        print(f"  ⚠️  Could not save tracking file: {e}")


def prune_seen(days=7):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    for feed in list(seen_articles.keys()):
        seen_articles[feed] = {
            k: v for k, v in seen_articles[feed].items()
            if v > cutoff
        }


def upscale_image_url(url):
    """Swap tiny thumbnails for larger versions where possible."""
    # Investing.com: 108x81 → 800x533
    if "i-invdn-com.investing.com" in url:
        url = re.sub(r"_\d+x\d+\.", "_800x533.", url)
    return url


def fetch_og_image(url):
    """Fallback: fetch the article page and grab the og:image meta tag."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r.text[:50000]
            )
            if not match:
                # Some sites flip the attribute order
                match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    r.text[:50000]
                )
            if match:
                return match.group(1)
    except requests.RequestException:
        pass
    return None


def extract_image(entry):
    """Try to pull an image URL from the RSS entry, fallback to og:image."""
    # media:content or media:thumbnail (most common)
    if "media_content" in entry:
        for media in entry["media_content"]:
            url = media.get("url", "")
            if url and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                return upscale_image_url(url)
    if "media_thumbnail" in entry:
        for thumb in entry["media_thumbnail"]:
            url = thumb.get("url", "")
            if url:
                return upscale_image_url(url)

    # og:image style in <enclosure>
    if "links" in entry:
        for link in entry["links"]:
            if link.get("type", "").startswith("image/"):
                return upscale_image_url(link.get("href", ""))

    # Image tag buried in summary HTML
    summary = entry.get("summary", "")
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if img_match:
        return upscale_image_url(img_match.group(1))

    # Fallback: fetch the article page for og:image
    og = fetch_og_image(entry.get("link", ""))
    if og:
        return upscale_image_url(og)

    return None


def clean_description(entry):
    """Extract a clean text snippet from the entry."""
    desc = entry.get("summary", "") or entry.get("description", "")
    # Strip HTML tags
    desc = re.sub(r"<[^>]+>", "", desc)
    # Collapse whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    # Trim to ~400 chars at a sentence boundary
    if len(desc) > 400:
        cut = desc[:400].rfind(". ")
        if cut > 100:
            desc = desc[:cut + 1]
        else:
            desc = desc[:400] + "…"
    return desc


def post_to_discord(entry, feed_name, feed_cfg):
    title = entry.get("title", "No title")[:256]
    link  = entry.get("link", "")
    desc  = clean_description(entry)
    image = extract_image(entry)

    embed = {
        "title": title,
        "url": link,
        "description": desc,
        "color": feed_cfg["color"],
        "footer": {
            "text": feed_name,
            "icon_url": feed_cfg.get("icon", ""),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    if image:
        embed["image"] = {"url": image}

    payload = {"embeds": [embed]}

    for attempt in range(3):
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if r.status_code == 204:
                return True
            elif r.status_code == 429:
                retry_after = r.json().get("retry_after", 5)
                print(f"  ⏳ Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
            else:
                print(f"  ⚠️  Discord returned {r.status_code}: {r.text[:200]}")
                return False
        except requests.RequestException as e:
            print(f"  ⚠️  Request error: {e}")
            time.sleep(2)
    return False


def check_feed(feed_name, feed_cfg, post=True, limit=None):
    try:
        feed = feedparser.parse(feed_cfg["url"])
    except Exception as e:
        print(f"  ⚠️  Error parsing {feed_name}: {e}")
        return 0

    if not feed.entries:
        print(f"  📋 {feed_name}: 0 articles found")
        return 0

    if feed_name not in seen_articles:
        seen_articles[feed_name] = {}

    new_entries = []
    for entry in feed.entries:
        aid = article_id(entry)
        if aid not in seen_articles[feed_name]:
            new_entries.append((aid, entry))

    to_post = new_entries[:limit or MAX_PER_FEED]
    posted = 0

    for aid, entry in to_post:
        if post:
            title = entry.get("title", "No title")[:60]
            if post_to_discord(entry, feed_name, feed_cfg):
                print(f"  ✅ [{feed_name}] {title}")
                posted += 1
                time.sleep(0.5)
            else:
                print(f"  ❌ [{feed_name}] Failed: {title}")

    # Mark ALL new entries as seen
    for aid, entry in new_entries:
        seen_articles[feed_name][aid] = datetime.utcnow().isoformat()

    return posted


def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutting down gracefully...")
    save_seen()
    running = False
    sys.exit(0)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if not DISCORD_WEBHOOK_URL:
        print("❌ ERROR: DISCORD_WEBHOOK_URL not set!")
        print("   Create a .env file with: DISCORD_WEBHOOK_URL=your_url_here")
        sys.exit(1)

    webhook_preview = DISCORD_WEBHOOK_URL[-30:]

    print("=" * 60)
    print("📰 Financial News RSS → Discord Bot")
    print(f"   Monitoring {len(FEEDS)} feeds every {POLL_INTERVAL // 60} minutes")
    print(f"   Webhook: ...{webhook_preview}")
    print(f"   Tracking: {SEEN_FILE}")
    print("=" * 60)

    had_existing = load_seen()

    if not had_existing:
        print("\n📡 First run — indexing existing articles (no posts)...")
        for name, cfg in FEEDS.items():
            check_feed(name, cfg, post=False)
        save_seen()
        count = sum(len(v) for v in seen_articles.values())
        print(f"   Indexed {count} articles. Only NEW articles will be posted.\n")
    else:
        count = sum(len(v) for v in seen_articles.values())
        print(f"\n📂 Loaded {count} tracked articles, watching for new ones...\n")

    # Main polling loop
    cycle = 1
    while running:
        # Wait first (first-run already posted)
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

        if not running:
            break

        print(f"\n🔄 Cycle #{cycle} — {datetime.now().strftime('%I:%M:%S %p')}")
        total = 0
        for name, cfg in FEEDS.items():
            count = check_feed(name, cfg, post=True)
            total += count

        if total == 0:
            print("  💤 No new articles")
        else:
            print(f"  📬 Posted {total} new articles")

        save_seen()
        cycle += 1

        # Prune weekly
        if cycle % 2016 == 0:
            prune_seen()


if __name__ == "__main__":
    main()