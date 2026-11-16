#!/usr/bin/env python3
"""Real-time room message listener for netease-listen-together-mcp.

Polls the MCP service for new room messages at a configurable interval.
New messages can be logged to a file, sent to a webhook, or both.

Usage:
    export MCP_URL="http://127.0.0.1:8006/mcp"
    export POLL_INTERVAL=5
    python3 listener.py

Environment variables:
    MCP_URL         MCP service endpoint (default: http://127.0.0.1:8006/mcp)
    POLL_INTERVAL   Seconds between polls (default: 5, minimum: 3)
    WEBHOOK_URL     Optional: POST new messages to this URL
    LOG_FILE        Optional: Append new messages to this file
    AUTH_TOKEN      Optional: Bearer token for MCP auth
"""

import json
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip3 install requests")
    sys.exit(1)

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8006/mcp")
POLL_INTERVAL = max(3, int(os.environ.get("POLL_INTERVAL", "5")))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
LOG_FILE = os.environ.get("LOG_FILE", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")


def mcp_call(method, params=None):
    """Make a JSON-RPC call to the MCP service."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": method,
            "arguments": params or {},
        },
    }

    try:
        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Extract text content from MCP response
        result = data.get("result", {})
        if isinstance(result, dict) and "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except (json.JSONDecodeError, KeyError):
                        return {"raw": item["text"]}
        return result
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def log_message(msg):
    """Log a message to file and/or stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sender = msg.get("sender", "unknown")
    nickname = msg.get("fromNickname", sender)
    content = msg.get("content", "")
    line = f"[{timestamp}] {nickname}: {content}"

    print(line)

    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except IOError as e:
            print(f"Warning: Could not write to {LOG_FILE}: {e}")


def send_webhook(messages):
    """Send new messages to webhook URL."""
    if not WEBHOOK_URL or not messages:
        return
    try:
        requests.post(
            WEBHOOK_URL,
            json={"messages": messages, "count": len(messages)},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        print(f"Warning: Webhook failed: {e}")


def main():
    print(f"Listener started")
    print(f"  MCP URL: {MCP_URL}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  Webhook: {WEBHOOK_URL or '(disabled)'}")
    print(f"  Log file: {LOG_FILE or '(disabled)'}")
    print()

    last_message_id = None
    consecutive_errors = 0

    while True:
        try:
            params = {"limit": 20}
            if last_message_id:
                params["since_id"] = last_message_id

            result = mcp_call("get_room_messages", params)

            if "error" in result:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    print(f"Error polling: {result['error']}")
                elif consecutive_errors == 4:
                    print("Suppressing repeated errors...")
                time.sleep(POLL_INTERVAL * 2)
                continue

            consecutive_errors = 0

            if result.get("hasNew") and result.get("messages"):
                new_msgs = result["messages"]
                for msg in new_msgs:
                    if msg.get("sender") != "me":
                        log_message(msg)

                partner_msgs = [m for m in new_msgs if m.get("sender") != "me"]
                if partner_msgs:
                    send_webhook(partner_msgs)

                last_message_id = result.get("lastMessageId", last_message_id)

            elif result.get("lastMessageId"):
                last_message_id = result["lastMessageId"]

        except KeyboardInterrupt:
            print("\nListener stopped.")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
