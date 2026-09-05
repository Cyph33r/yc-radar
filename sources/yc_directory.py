"""
Polls https://www.ycombinator.com/companies for newly listed companies.

The directory is a client-rendered React app (backed by Algolia), so a
plain `requests.get` returns an empty shell — this uses Playwright to
render the page and read the company cards out of the DOM.

IMPORTANT: YC's markup changes over time. Before your first real run,
open the page in a browser, inspect a company card element, and confirm
the selectors below (`data-*` attributes or class names) still match.
Treat this file as a starting point, not a guarantee.
"""
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from sources.browser import launch_browser

DIRECTORY_URL = "https://www.ycombinator.com/companies"


def fetch_companies(max_scroll_rounds: int = 8) -> list[dict]:
    """
    Returns a list of dicts: {slug, name, description, batch, link}
    Scrolls the results list a few times to load more than the initial page.
    """
    companies = []

    with sync_playwright() as p:
        browser = launch_browser(p, headless=True)
        page = browser.new_page()
        page.goto(DIRECTORY_URL, wait_until="networkidle")

        # Company cards are links to /companies/<slug>. Adjust this selector
        # if YC changes their markup.
        for _ in range(max_scroll_rounds):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(800)

        cards = page.query_selector_all("a[href^='/companies/']")
        seen_slugs = set()
        for card in cards:
            href = card.get_attribute("href") or ""
            slug = href.split("/companies/")[-1].strip("/")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            name = (card.inner_text() or "").split("\n")[0].strip()
            companies.append(
                {
                    "slug": slug,
                    "name": name or slug,
                    "description": "",
                    "batch": "",
                    "link": f"https://www.ycombinator.com/companies/{slug}",
                }
            )

        browser.close()

    return companies


def get_new_companies(is_seen_fn) -> list[dict]:
    """is_seen_fn: callable(item_id) -> bool, injected so this module has
    no direct dependency on the db module (easier to unit test)."""
    new_items = []
    for c in fetch_companies():
        item_id = f"yc:{c['slug']}"
        if not is_seen_fn(item_id):
            new_items.append(
                {
                    "item_id": item_id,
                    "company_name": c["name"],
                    "batch": c["batch"],
                    "source": "YC Directory",
                    "description": c["description"],
                    "link": c["link"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return new_items
