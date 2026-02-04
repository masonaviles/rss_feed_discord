#!/usr/bin/env python3
"""
Market Session Discord Bot
Posts notifications when major market sessions open and close.
Includes 30-minute warnings before opens.
"""

import os
import time
import signal
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_SESSIONS", "")

# ─── SESSIONS ────────────────────────────────────────────────────────────────
# All times in ET (America/New_York)
# Format: (hour, minute)

SESSIONS = {
    "Sydney": {
        "open": (17, 0),      # 5:00 PM ET
        "close": (2, 0),      # 2:00 AM ET (next day)
        "color": 0x00CED1,    # Dark turquoise
        "emoji": "🇦🇺",
        "weekend": True,      # Posts on weekends
    },
    "Tokyo": {
        "open": (19, 0),      # 7:00 PM ET
        "close": (4, 0),      # 4:00 AM ET (next day)
        "color": 0xDC143C,    # Crimson
        "emoji": "🇯🇵",
        "weekend": True,      # Posts on weekends
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

WARNING_MINUTES = 30  # Post warning this many minutes before open

# ─── GLOBALS ─────────────────────────────────────────────────────────────────

ET = ZoneInfo("America/New_York")
running = True
posted_events = set()  # Track posted events to avoid duplicates

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def get_event_key(session_name, event_type, dt):
    """Create a unique key for an event to track if we've posted it."""
    return f"{session_name}:{event_type}:{dt.strftime('%Y-%m-%d:%H:%M')}"


def is_weekend(dt):
    """Check if it's Saturday or Sunday."""
    return dt.weekday() >= 5  # Saturday = 5, Sunday = 6


def is_sunday_evening(dt):
    """Check if it's Sunday after 5 PM (CME Futures reopen)."""
    return dt.weekday() == 6 and dt.hour >= 17


def should_post_session(session_name, session_cfg, dt):
    """Determine if we should post for this session at this time."""
    if session_cfg.get("weekend", False):
        return True
    
    # Special case: CME Futures opens Sunday evening
    if session_name == "CME Futures" and is_sunday_evening(dt):
        return True
    
    # Skip weekends for non-weekend sessions
    if is_weekend(dt):
        return False
    
    return True


def post_to_discord(title, description, color, emoji):
    """Post an embed to Discord."""
    if not DISCORD_WEBHOOK_URL:
        print(f"  [NO WEBHOOK] {title}")
        return False

    embed = {
        "title": f"{emoji}  {title}",
        "description": description,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
    }

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


def format_time_12h(hour, minute):
    """Format 24h time as 12h with AM/PM."""
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minute:02d} {suffix} ET"


def check_events():
    """Check if any session events should be posted right now."""
    now = datetime.now(ET)
    current_hour = now.hour
    current_minute = now.minute

    for session_name, cfg in SESSIONS.items():
        open_h, open_m = cfg["open"]
        close_h, close_m = cfg["close"]

        # Check if we should post for this session today
        if not should_post_session(session_name, cfg, now):
            continue

        # ─── 30-MINUTE WARNING ───────────────────────────────────────────
        warn_time = datetime(now.year, now.month, now.day, open_h, open_m, tzinfo=ET) - timedelta(minutes=WARNING_MINUTES)
        # Handle day wraparound for warning
        if warn_time.day != now.day:
            warn_time = warn_time + timedelta(days=1)
        
        if current_hour == warn_time.hour and current_minute == warn_time.minute:
            event_key = get_event_key(session_name, "warning", now)
            if event_key not in posted_events:
                title = f"{session_name} — 30 Minutes"
                desc = f"Opens at {format_time_12h(open_h, open_m)}"
                if post_to_discord(title, desc, cfg["color"], "⏰"):
                    print(f"  ⏰ {session_name} 30-min warning")
                    posted_events.add(event_key)

        # ─── SESSION OPEN ────────────────────────────────────────────────
        if current_hour == open_h and current_minute == open_m:
            event_key = get_event_key(session_name, "open", now)
            if event_key not in posted_events:
                title = f"{session_name} Session Open"
                close_time = format_time_12h(close_h, close_m)
                desc = f"Market is now open • Closes at {close_time}"
                if post_to_discord(title, desc, cfg["color"], cfg["emoji"]):
                    print(f"  🟢 {session_name} OPEN")
                    posted_events.add(event_key)

        # ─── SESSION CLOSE ───────────────────────────────────────────────
        if current_hour == close_h and current_minute == close_m:
            event_key = get_event_key(session_name, "close", now)
            if event_key not in posted_events:
                title = f"{session_name} Session Close"
                desc = "Market is now closed"
                if post_to_discord(title, desc, cfg["color"], cfg["emoji"]):
                    print(f"  🔴 {session_name} CLOSE")
                    posted_events.add(event_key)


def cleanup_old_events():
    """Remove event keys older than 24 hours to prevent memory bloat."""
    # Simple approach: clear everything at midnight
    now = datetime.now(ET)
    if now.hour == 0 and now.minute == 0:
        posted_events.clear()
        print("  🧹 Cleared posted events cache")


def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutting down...")
    running = False
    sys.exit(0)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if not DISCORD_WEBHOOK_URL:
        print("❌ ERROR: DISCORD_WEBHOOK_SESSIONS not set!")
        print("   Add to .env: DISCORD_WEBHOOK_SESSIONS=your_webhook_url")
        sys.exit(1)

    webhook_preview = DISCORD_WEBHOOK_URL[-30:]

    print("=" * 60)
    print("🕐 Market Session Bot")
    print(f"   Tracking {len(SESSIONS)} sessions")
    print(f"   Warning: {WARNING_MINUTES} minutes before open")
    print(f"   Webhook: ...{webhook_preview}")
    print("=" * 60)

    # Show upcoming schedule
    now = datetime.now(ET)
    print(f"\n   Current time: {now.strftime('%I:%M %p ET')} ({now.strftime('%A')})")
    print("\n   Sessions tracked:")
    for name, cfg in SESSIONS.items():
        open_t = format_time_12h(*cfg["open"])
        close_t = format_time_12h(*cfg["close"])
        weekend = "✓" if cfg.get("weekend") else "✗"
        print(f"     • {name}: {open_t} - {close_t} (weekend: {weekend})")
    print()

    # Main loop - check every 30 seconds
    while running:
        now = datetime.now(ET)
        
        # Only check at the start of each minute
        if now.second < 30:
            check_events()
            cleanup_old_events()
        
        # Sleep until next check
        time.sleep(30)


if __name__ == "__main__":
    main()