"""
Searches LinkedIn for new company pages / launch posts referencing YC or
Speedrun, via a third-party scraping actor on Apify.

Same pattern as x_source.py: LinkedIn has no public API for this, so this
calls whichever LinkedIn scraper actor you pick from the Apify Store
(search "linkedin posts scraper" or "linkedin company scraper"). Field
names in `run_input` and the parsing below are written for a typical
post-search actor and will need to match your chosen actor's actual
schema — check its sample output in the Apify console first.
"""
from datetime import datetime, timezone

import requests

from config import config

APIFY_RUN_SYNC_URL = (
    "https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
)


def fetch_recent_posts() -> list[dict]:
    url = APIFY_RUN_SYNC_URL.format(actor_id=config.APIFY_LINKEDIN_ACTOR_ID)
    run_input = {
        "searchTerms": config.LINKEDIN_SEARCH_TERMS,
        "maxItems": 50,
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
    new_items = []
    for raw in fetch_recent_posts():
        post_id = str(raw.get("id") or raw.get("postId") or raw.get("urn") or "")
        if not post_id:
            continue
        item_id = f"linkedin:{post_id}"
        if is_seen_fn(item_id):
            continue

        new_items.append(
            {
                "item_id": item_id,
                "company_name": raw.get("company_name", "Unknown"),
                "founder_name": raw.get("authorName", ""),
                "founder_handle": raw.get("authorProfileUrl", ""),
                "batch": "",
                "source": "LinkedIn",
                "post_text": raw.get("text", ""),
                "post_link": raw.get("postUrl") or raw.get("url", ""),
                "company_link": raw.get("companyUrl", ""),
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return new_items
