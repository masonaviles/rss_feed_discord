# 📊 Trading Discord Bots

Two bots for your trading Discord server:

1. **RSS News Bot** — Posts financial news from major sources
2. **Market Sessions Bot** — Announces when global markets open and close

## Features

### 📰 RSS News Bot
- Monitors 6 financial news feeds (CNBC, MarketWatch, ZeroHedge, Investing.com, Federal Reserve)
- Posts new articles as rich embeds with images
- Polls every 5 minutes
- Deduplicates articles across restarts

### 🕐 Market Sessions Bot
- Tracks Sydney, Tokyo, London, New York, and CME Futures sessions
- Posts 30-minute warning before each open
- Posts open/close notifications with session times
- Handles weekends correctly (Asian sessions run, Western markets skip)

## Quick Start

```bash
# Clone and enter repo
git clone https://github.com/your-username/trading-discord-bots.git
cd trading-discord-bots

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure webhooks
cp .env.example .env
# Edit .env with your webhook URLs

# Run both bots
python run.py
```

## Configuration

### `.env` file

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
DISCORD_WEBHOOK_SESSIONS=https://discord.com/api/webhooks/aaa/bbb
```

| Variable | Description |
|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Webhook for the news channel |
| `DISCORD_WEBHOOK_SESSIONS` | Webhook for the market sessions channel |

To create a webhook: **Server Settings → Integrations → Webhooks → New Webhook**

### Running Individual Bots

```bash
# Just news
python rss_to_discord.py

# Just sessions
python market_sessions.py

# Both together
python run.py
```

## News Sources

| Source | Coverage |
|--------|----------|
| CNBC Top News | Breaking market headlines |
| CNBC Economy | Fed, macro, economic data |
| MarketWatch | General market news |
| ZeroHedge | Macro & geopolitical |
| Investing.com | Commodities, forex, broad markets |
| Federal Reserve | Rate decisions, policy statements |

## Market Sessions (ET)

| Session | Open | Close | Weekend |
|---------|------|-------|---------|
| 🇦🇺 Sydney | 5:00 PM | 2:00 AM | ✓ |
| 🇯🇵 Tokyo | 7:00 PM | 4:00 AM | ✓ |
| 🇬🇧 London | 3:00 AM | 12:00 PM | ✗ |
| 🇺🇸 New York | 9:30 AM | 4:00 PM | ✗ |
| 📊 CME Futures | 6:00 PM | 5:00 PM | ✗* |

*CME Futures opens Sunday 6 PM ET, closes Friday 5 PM ET, with daily 5-6 PM maintenance breaks.

## File Structure

```
├── run.py                     # Launcher for both bots
├── rss_to_discord.py          # News bot
├── market_sessions.py         # Sessions bot
├── requirements.txt           # Python dependencies
├── .env                       # Your webhook URLs (not in git)
├── .gitignore
└── .rss_seen_articles.json    # Article tracking (auto-generated)
```

## Requirements

- Python 3.9+
- Discord server with webhook permissions

## License

MIT