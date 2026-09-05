"""
Central config loader. Everything the bot needs comes from environment
variables (see .env.example), loaded here via python-dotenv so the rest
of the codebase never touches os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Default PLAYWRIGHT_BROWSERS_PATH to "0" on Render so browser binaries
# are installed and looked up in the persistent virtual environment directory.
if os.environ.get("RENDER") == "true" and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required env var: {name}. Copy .env.example to .env "
            f"and fill it in."
        )
    return value.strip()


def _split_terms(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [t.strip() for t in raw.split(",") if t.strip()]


class Config:
    # Slack
    SLACK_BOT_TOKEN = _require("SLACK_BOT_TOKEN")
    SLACK_CHANNEL_ID = _require("SLACK_CHANNEL_ID")

    # Apify (X + LinkedIn scraping)
    APIFY_API_TOKEN = _require("APIFY_API_TOKEN")
    APIFY_X_ACTOR_ID = _require("APIFY_X_ACTOR_ID")
    X_SEARCH_TERMS = _split_terms("X_SEARCH_TERMS")
    APIFY_LINKEDIN_ACTOR_ID = _require("APIFY_LINKEDIN_ACTOR_ID")
    LINKEDIN_SEARCH_TERMS = _split_terms("LINKEDIN_SEARCH_TERMS")
    
    #pond
    POND_ACCESS_KEY = os.environ.get("POND_ACCESS_KEY", "")

    # Polling
    POLL_INTERVAL_HOURS = float(os.environ.get("POLL_INTERVAL_HOURS", "8"))

    # State
    DB_PATH = os.environ.get("DB_PATH", "state.db")

    # Pond
    POND_AGENT_ID = os.environ.get("POND_AGENT_ID", "")
    POND_AGENT_API_KEY = os.environ.get("POND_AGENT_API_KEY", "")


config = Config()
