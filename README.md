# 📰 Financial News RSS → Discord Bot

A lightweight Python bot that monitors financial news RSS feeds and posts new articles to a Discord channel via webhook. Built for futures traders who want real-time headlines without the noise.

## Feeds

| Source | Focus |
|--------|-------|
| CNBC Top News | Breaking market headlines |
| CNBC Economy | Fed, macro, economic data |
| MarketWatch | General market news |
| Investing.com | Commodities, forex, broad markets |
| Federal Reserve | Rate decisions, policy statements |

## How It Works

- Polls all feeds every 5 minutes
- Posts new articles as Discord embeds with source branding
- On first run, silently indexes existing articles — only posts genuinely **new** content
- Tracks seen articles in a local JSON file so restarts don't cause duplicates
- Handles Discord rate limits and retries automatically
- Prunes tracking data older than 7 days

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/rss-discord-bot.git
cd rss-discord-bot
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure your webhook

Create a `.env` file in the project root:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your/webhook/url
```

To get a webhook URL: Discord Server Settings → Integrations → Webhooks → New Webhook

### 4. Run

```bash
source venv/bin/activate
python rss_to_discord.py
```

Stop with `Ctrl+C` — it saves state gracefully.

## Configuration

Edit these values at the top of `rss_to_discord.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | `300` | Seconds between feed checks (5 min) |
| `MAX_PER_FEED` | `3` | Max articles posted per feed per cycle |

## Adding / Removing Feeds

Edit the `FEEDS` dictionary in the script. Each feed needs:

```python
"Feed Name": {
    "url": "https://example.com/rss.xml",
    "color": 0x005999,        # Discord embed color (hex)
    "icon": "https://example.com/favicon.ico",
},
```

## File Structure

```
├── rss_to_discord.py          # Main bot script
├── requirements.txt           # Python dependencies
├── .env                       # Your webhook URL (not tracked by git)
├── .gitignore                 # Keeps secrets and cache out of repo
└── .rss_seen_articles.json    # Article tracking (auto-generated)
```

## Requirements

- Python 3.8+
- A Discord server with webhook permissions

## License

MIT
