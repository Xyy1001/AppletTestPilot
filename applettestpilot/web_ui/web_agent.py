#!/usr/bin/env python3
"""
WebAgent — start the interactive web UI server.

The server waits for browser interactions.  All test logic is triggered
by the frontend via REST API (/api/analyze, /api/start, /api/next, /api/stop).
This entry point does NOT connect to DevTools or run any Agent on its own.

Usage:
    python -m applettestpilot.web_ui.web_agent --port 9120
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from applettestpilot.web_ui import start_server

PROJECT = Path(__file__).parent.parent.parent


def main():
    parser = argparse.ArgumentParser(description="WebAgent — Interactive Web UI Server")
    parser.add_argument("--port", type=int, default=9120, help="Web UI port (default 9120)")
    args = parser.parse_args()

    url = start_server(port=args.port)
    print(f"\n  {'='*50}")
    print(f"  AppletTestPilot Web UI")
    print(f"  URL: {url}")
    print(f"  {'='*50}")
    print(f"\n  Open your browser and:")
    print(f"  1. Configure source / screenshot / output paths")
    print(f"  2. Click [分析规划] to let LLM analyze the app")
    print(f"  3. Choose execution mode in the popup")
    print(f"  4. Watch the Agent run in real-time")
    print(f"\n  Press Ctrl+C to stop the server.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
