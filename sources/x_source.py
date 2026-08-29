"""
Searches X/Twitter for founder posts that mention YC/Speedrun keywords,
via a third-party scraping actor hosted on Apify.

This calls Apify's generic "run an actor synchronously and get its
dataset items" endpoint. Which JSON fields to send as `run_input` and
which fields come back depend entirely on the specific actor you pick
from the Apify Store (search "twitter scraper" / "X search scraper").
APIFY_X_ACTOR_ID in .env defaults to a placeholder — swap in the actor
you've tested and adjust `run_input` / the result parsing below to match
its documented schema.
"""
from datetime import datetime, timezone

import requests

from config import config
import re

def _extract_company_name(text: str) -> str:
    if not text:
        return "Unknown"
    m = re.search(r'@(\w+)\s*\(\s*yc\b', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'([A-Z][\w&.\-]{1,30})\s*\(\s*yc\b', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return "Unknown"


def _extract_batch(text: str) -> str:
    if not text:
        return ""
    m = re.search(r'\b(yc\s*[sw]\d{2}|speedrun)\b', text, re.IGNORECASE)
    return m.group(1).upper() if m else ""

APIFY_RUN_SYNC_URL = (
    "https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
)


def fetch_recent_posts() -> list[dict]:
    """
    Returns raw items from the chosen actor. Adjust `run_input` to match
    that actor's documented input schema (most X/search actors accept
    something like `searchTerms` and a result-count cap).
    """
    actor_id = config.APIFY_X_ACTOR_ID.strip().replace("/", "~")
    url = APIFY_RUN_SYNC_URL.format(actor_id=actor_id)

    run_input = {
        "searchTerms": config.X_SEARCH_TERMS,
        "maxItems": 100,
        "sort": "Latest",
    }
    resp = requests.post(
        url,
        params={"token": config.APIFY_API_TOKEN},
        json=run_input,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_new_signals(is_seen_fn) -> list[dict]:
    """
    is_seen_fn: callable(item_id) -> bool

    NOTE: the field names below (tweet id, author handle, text, url) are
    written for a typical tweet-scraper actor's output shape. Check your
    chosen actor's sample output in the Apify console and rename the
    `raw.get(...)` keys to match.
    """
    new_items = []
    for raw in fetch_recent_posts():
        tweet_id = str(raw.get("id") or raw.get("tweetId") or "")
        if not tweet_id:
            continue
        item_id = f"x:{tweet_id}"
        if is_seen_fn(item_id):
            continue

        new_items.append(
            {
                "item_id": item_id,
            "company_name": _extract_company_name(raw.get("text", "")),
                "founder_name": raw.get("author", {}).get("name", "")
                if isinstance(raw.get("author"), dict)
                else raw.get("authorName", ""),
                "founder_handle": "@" + str(
                    raw.get("author", {}).get("userName", "")
                    if isinstance(raw.get("author"), dict)
                    else raw.get("authorHandle", "")
                ),
                "batch": _extract_batch(raw.get("text", "")),
                "source": "X",
                "post_text": raw.get("text", ""),
                "post_link": raw.get("url") or raw.get("twitterUrl", ""),
                "company_link": "",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return new_items
