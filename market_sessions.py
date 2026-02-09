#!/usr/bin/env python3
"""
Market Session Discord Bot
Posts notifications when major market sessions open and close.
Includes 30-minute warnings before opens.
Responds to /whatsession slash command with current active sessions.

Requires:
  - DISCORD_BOT_TOKEN (bot token from Discord Developer Portal)
  - DISCORD_WEBHOOK_SESSIONS (webhook URL for session notifications)
  - DISCORD_GUILD_ID (your server ID, for instant slash command sync)
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
import requests
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_SESSIONS", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

# ─── SESSIONS ────────────────────────────────────────────────────────────────
# All times in ET (America/New_York)
# Format: (hour, minute)

SESSIONS = {
    "Sydney": {
        "open": (17, 0),      # 5:00 PM ET
        "close": (2, 0),      # 2:00 AM ET (next day)
        "color": 0x00CED1,    # Dark turquoise
        "emoji": "🇦🇺",
        "weekend": True,
    },
    "Tokyo": {
        "open": (19, 0),      # 7:00 PM ET
        "close": (4, 0),      # 4:00 AM ET (next day)
        "color": 0xDC143C,    # Crimson
        "emoji": "🇯🇵",
        "weekend": True,
    },
    "London": {
        "open": (3, 0),       # 3:00 AM ET
        "close": (12, 0),     # 12:00 PM ET
        "color": 0x1E90FF,    # Dodger blue
        "emoji": "🇬🇧",
        "weekend": False,
    },
    "New York": {
        "open": (9, 30),      # 9:30 AM ET
        "close": (16, 0),     # 4:00 PM ET
        "color": 0x228B22,    # Forest green
        "emoji": "🇺🇸",
        "weekend": False,
    },
    "CME Futures": {
        "open": (18, 0),      # 6:00 PM ET (Sunday open, daily reopen)
        "close": (17, 0),     # 5:00 PM ET (daily close for maintenance)
        "color": 0xFFD700,    # Gold
        "emoji": "📊",
        "weekend": False,     # Opens Sunday evening (handled specially)
    },
}

WARNING_MINUTES = 30
ET = ZoneInfo("America/New_York")
posted_events = set()

# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def format_time_12h(hour, minute):
    """Format 24h time as 12h with AM/PM."""
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minute:02d} {suffix} ET"


def get_event_key(session_name, event_type, dt):
    return f"{session_name}:{event_type}:{dt.strftime('%Y-%m-%d:%H:%M')}"


def is_weekend(dt):
    return dt.weekday() >= 5


def is_sunday_evening(dt):
    return dt.weekday() == 6 and dt.hour >= 17


def should_post_session(session_name, session_cfg, dt):
    if session_cfg.get("weekend", False):
        return True
    if session_name == "CME Futures" and is_sunday_evening(dt):
        return True
    if is_weekend(dt):
        return False
    return True


def is_session_active(session_name, cfg, now):
    """Check if a session is currently active and return time remaining."""
    open_h, open_m = cfg["open"]
    close_h, close_m = cfg["close"]

    if not should_post_session(session_name, cfg, now):
        return False, None

    open_minutes = open_h * 60 + open_m
    close_minutes = close_h * 60 + close_m
    now_minutes = now.hour * 60 + now.minute

    # Session wraps past midnight (e.g. Sydney 17:00 - 02:00)
    if close_minutes < open_minutes:
        is_active = now_minutes >= open_minutes or now_minutes < close_minutes
    else:
        is_active = open_minutes <= now_minutes < close_minutes

    if not is_active:
        return False, None

    # Calculate time remaining until close
    close_dt = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

    # If close is tomorrow (wraps past midnight)
    if close_minutes < open_minutes and now_minutes >= open_minutes:
        close_dt += timedelta(days=1)

    remaining = close_dt - now
    return True, remaining


def get_next_session(now):
    """Find the next session to open."""
    best_name = None
    best_delta = None

    for name, cfg in SESSIONS.items():
        if not should_post_session(name, cfg, now):
            continue

        open_h, open_m = cfg["open"]
        open_dt = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)

        if open_dt <= now:
            open_dt += timedelta(days=1)

        # Skip if already active
        active, _ = is_session_active(name, cfg, now)
        if active:
            continue

        delta = open_dt - now
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_name = name

    return best_name, best_delta


def format_remaining(td):
    """Format a timedelta as a readable string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "closing now"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ─── WEBHOOK POSTING ─────────────────────────────────────────────────────────

def post_to_discord(title, description, color, emoji):
    """Post an embed to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        return False

    embed = {
        "title": f"{emoji}  {title}",
        "description": description,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
    }

    for attempt in range(3):
        try:
            r = requests.post(
                DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10
            )
            if r.status_code == 204:
                return True
            elif r.status_code == 429:
                retry_after = r.json().get("retry_after", 5)
                print(f"  ⏳ Rate limited, waiting {retry_after}s...")
                import time; time.sleep(retry_after)
            else:
                print(f"  ⚠️  Discord returned {r.status_code}: {r.text[:200]}")
                return False
        except requests.RequestException as e:
            print(f"  ⚠️  Request error: {e}")
            import time; time.sleep(2)
    return False


# ─── SCHEDULED EVENT CHECKS ─────────────────────────────────────────────────

def check_events():
    now = datetime.now(ET)
    current_hour = now.hour
    current_minute = now.minute

    for session_name, cfg in SESSIONS.items():
        open_h, open_m = cfg["open"]
        close_h, close_m = cfg["close"]

        if not should_post_session(session_name, cfg, now):
            continue

        # 30-minute warning
        warn_time = datetime(
            now.year, now.month, now.day, open_h, open_m, tzinfo=ET
        ) - timedelta(minutes=WARNING_MINUTES)
        if warn_time.day != now.day:
            warn_time += timedelta(days=1)

        if current_hour == warn_time.hour and current_minute == warn_time.minute:
            event_key = get_event_key(session_name, "warning", now)
            if event_key not in posted_events:
                title = f"{session_name} — 30 Minutes"
                desc = f"Opens at {format_time_12h(open_h, open_m)}"
                if post_to_discord(title, desc, cfg["color"], "⏰"):
                    print(f"  ⏰ {session_name} 30-min warning")
                    posted_events.add(event_key)

        # Session open
        if current_hour == open_h and current_minute == open_m:
            event_key = get_event_key(session_name, "open", now)
            if event_key not in posted_events:
                title = f"{session_name} Session Open"
                desc = f"Market is now open • Closes at {format_time_12h(close_h, close_m)}"
                if post_to_discord(title, desc, cfg["color"], cfg["emoji"]):
                    print(f"  🟢 {session_name} OPEN")
                    posted_events.add(event_key)

        # Session close
        if current_hour == close_h and current_minute == close_m:
            event_key = get_event_key(session_name, "close", now)
            if event_key not in posted_events:
                title = f"{session_name} Session Close"
                desc = "Market is now closed"
                if post_to_discord(title, desc, cfg["color"], cfg["emoji"]):
                    print(f"  🔴 {session_name} CLOSE")
                    posted_events.add(event_key)


def cleanup_old_events():
    now = datetime.now(ET)
    if now.hour == 0 and now.minute == 0:
        posted_events.clear()
        print("  🧹 Cleared posted events cache")


# ─── DISCORD BOT ─────────────────────────────────────────────────────────────

class SessionBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"  ⚡ Slash commands synced to guild {DISCORD_GUILD_ID}")
        else:
            await self.tree.sync()
            print("  🌐 Slash commands synced globally (may take up to 1 hour)")


bot = SessionBot()


@bot.tree.command(
    name="whatsession",
    description="Show current active market sessions and time remaining",
)
async def whatsession(interaction: discord.Interaction):
    now = datetime.now(ET)
    active_sessions = []

    for name, cfg in SESSIONS.items():
        active, remaining = is_session_active(name, cfg, now)
        if active:
            close_h, close_m = cfg["close"]
            active_sessions.append({
                "name": name,
                "emoji": cfg["emoji"],
                "color": cfg["color"],
                "remaining": remaining,
                "close_time": format_time_12h(close_h, close_m),
            })

    embed = discord.Embed(title="🕐  Market Sessions", timestamp=now)

    if active_sessions:
        embed.color = active_sessions[0]["color"]
        lines = []
        for s in active_sessions:
            lines.append(
                f"{s['emoji']} **{s['name']}** — "
                f"`{format_remaining(s['remaining'])}` remaining\n"
                f"　　Closes at {s['close_time']}"
            )
        embed.add_field(
            name="🟢  Active Sessions",
            value="\n\n".join(lines),
            inline=False,
        )
    else:
        embed.color = 0x808080
        embed.add_field(
            name="🔴  No Active Sessions",
            value="All markets are currently closed.",
            inline=False,
        )

    # Next session to open
    next_name, next_delta = get_next_session(now)
    if next_name:
        next_cfg = SESSIONS[next_name]
        open_h, open_m = next_cfg["open"]
        embed.add_field(
            name="⏭️  Next Up",
            value=(
                f"{next_cfg['emoji']} **{next_name}** opens in "
                f"`{format_remaining(next_delta)}`\n"
                f"　　Opens at {format_time_12h(open_h, open_m)}"
            ),
            inline=False,
        )

    embed.set_footer(text=f"{now.strftime('%I:%M %p ET  •  %A, %B %d')}")

    await interaction.response.send_message(embed=embed)


@bot.event
async def on_ready():
    print(f"  🤖 Bot logged in as {bot.user}")
    bot.loop.create_task(notification_loop())


async def notification_loop():
    """Background loop for webhook session notifications."""
    print("  🔄 Notification loop started")
    while True:
        now = datetime.now(ET)
        if now.second < 30:
            check_events()
            cleanup_old_events()
        await asyncio.sleep(30)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN not set!")
        print()
        print("   How to set up the bot:")
        print("   1. Go to https://discord.com/developers/applications")
        print("   2. Click 'New Application' → name it → 'Bot' tab")
        print("   3. Click 'Reset Token' → copy it into your .env file")
        print("   4. Go to 'OAuth2' → 'URL Generator'")
        print("   5. Check 'bot' and 'applications.commands'")
        print("   6. Under Bot Permissions: 'Send Messages' + 'Use Slash Commands'")
        print("   7. Copy the URL → open it → invite bot to your server")
        print()
        print("   .env needs:")
        print("     DISCORD_BOT_TOKEN=your_token_here")
        print("     DISCORD_GUILD_ID=your_server_id")
        sys.exit(1)

    if not DISCORD_WEBHOOK_URL:
        print("⚠️  WARNING: DISCORD_WEBHOOK_SESSIONS not set")
        print("   Session open/close notifications won't post")
        print("   /whatsession command will still work\n")

    print("=" * 60)
    print("🕐 Market Session Bot")
    print(f"   Tracking {len(SESSIONS)} sessions")
    print(f"   Warning: {WARNING_MINUTES} minutes before open")
    if DISCORD_GUILD_ID:
        print(f"   Guild: {DISCORD_GUILD_ID}")
    print("=" * 60)

    now = datetime.now(ET)
    print(f"\n   Current time: {now.strftime('%I:%M %p ET')} ({now.strftime('%A')})")
    print("\n   Sessions tracked:")
    for name, cfg in SESSIONS.items():
        open_t = format_time_12h(*cfg["open"])
        close_t = format_time_12h(*cfg["close"])
        weekend = "✓" if cfg.get("weekend") else "✗"
        print(f"     • {name}: {open_t} - {close_t} (weekend: {weekend})")
    print()

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
