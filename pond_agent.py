"""
Stub for Pond's agent infrastructure integration.

Pond's agent creation flow (https://joinpond.ai/agent/create) is a web UI,
so the actual registration is a manual, one-time step:

  1. Go to https://joinpond.ai/agent/create and register this bot as an
     agent under your Pond account.
  2. Copy the agent ID + API key it gives you into POND_AGENT_ID and
     POND_AGENT_API_KEY in your .env file.
  3. If Pond's docs specify a health-check webhook or heartbeat endpoint
     at registration time, wire it into `send_heartbeat()` below —
     the exact contract depends on what the registration flow returns,
     so check your agent's dashboard for the specifics after step 1.

This module just gives main.py a single place to call once that's set up,
so the heartbeat call is one line to add to the poll loop rather than a
rewrite.
"""
import requests

from config import config

# Placeholder — replace with the real heartbeat/health-check URL from your
# Pond agent dashboard once registered.
POND_HEARTBEAT_URL = "https://joinpond.ai/api/agent/heartbeat"


def send_heartbeat(status: str = "ok", detail: str = "") -> None:
    if not config.POND_AGENT_ID or not config.POND_AGENT_API_KEY:
        # Not registered yet — no-op so the bot still runs standalone.
        return
    try:
        requests.post(
            POND_HEARTBEAT_URL,
            headers={"Authorization": f"Bearer {config.POND_AGENT_API_KEY}"},
            json={
                "agent_id": config.POND_AGENT_ID,
                "status": status,
                "detail": detail,
            },
            timeout=15,
        )
    except requests.RequestException:
        # Heartbeat failures shouldn't crash the monitoring loop.
        pass
