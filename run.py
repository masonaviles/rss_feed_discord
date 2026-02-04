#!/usr/bin/env python3
"""Run both bots together."""

import subprocess
import sys
import signal
import os

procs = []

def shutdown(sig, frame):
    print("\n🛑 Stopping all bots...")
    for p in procs:
        p.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

dir = os.path.dirname(os.path.abspath(__file__))

procs.append(subprocess.Popen([sys.executable, f"{dir}/rss_to_discord.py"]))
procs.append(subprocess.Popen([sys.executable, f"{dir}/market_sessions.py"]))

print("🚀 Running: RSS bot + Market Sessions bot")
print("   Press Ctrl+C to stop both\n")

for p in procs:
    p.wait()