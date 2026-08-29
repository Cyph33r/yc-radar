"""
Polls YC's Speedrun program directory separately from the main directory,
so alerts can be tagged distinctly per the task requirements.

Same caveat as yc_directory.py: confirm selectors against the live page
before relying on this, and update SPEEDRUN_URL if YC moves the page.
"""
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

SPEEDRUN_URL = "https://www.ycombinator.com/speedrun"


def fetch_speedrun_companies(max_scroll_rounds: int = 8) -> list[dict]:
    companies = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SPEEDRUN_URL, wait_until="networkidle")

        for _ in range(max_scroll_rounds):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(800)

        # Speedrun cards may link to /companies/<slug> or a speedrun-specific
        # path — check the live DOM and adjust this selector if needed.
        cards = page.query_selector_all("a[href*='speedrun'], a[href^='/companies/']")
        seen_slugs = set()
        for card in cards:
            href = card.get_attribute("href") or ""
            slug = href.rstrip("/").split("/")[-1]
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            name = (card.inner_text() or "").split("\n")[0].strip()
            companies.append(
                {
                    "slug": slug,
                    "name": name or slug,
                    "description": "",
                    "link": f"https://www.ycombinator.com{href}",
                }
            )

        browser.close()

    return companies


def get_new_companies(is_seen_fn) -> list[dict]:
    new_items = []
    for c in fetch_speedrun_companies():
        item_id = f"speedrun:{c['slug']}"
        if not is_seen_fn(item_id):
            new_items.append(
                {
                    "item_id": item_id,
                    "company_name": c["name"],
                    "batch": "Speedrun",
                    "source": "YC Speedrun",
                    "description": c["description"],
                    "link": c["link"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return new_items
