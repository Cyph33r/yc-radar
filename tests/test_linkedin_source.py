"""
Offline test for sources/linkedin_source.py. The Apify call is mocked with
rows shaped like johnvc~linkedin-post-search-api output, so no token or
network is needed.

Run from the repo root: python -m pytest tests  (or: python -m unittest discover -s tests)
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# config.py requires these at import time.
for _name, _value in {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_CHANNEL_ID": "C123",
    "APIFY_API_TOKEN": "test-token",
    "APIFY_X_ACTOR_ID": "example~x-actor",
    "APIFY_LINKEDIN_ACTOR_ID": "johnvc~linkedin-post-search-api",
    "LINKEDIN_SEARCH_TERMS": "YC S26,Y Combinator",
}.items():
    os.environ.setdefault(_name, _value)

from config import config
from sources import linkedin_source

ACTOR_ROWS = [
    {
        "postId": "7380000000000000001",
        "text": "Excited to share that Acme is part of YC S26!",
        "postUrl": "https://www.linkedin.com/feed/update/urn:li:activity:7380000000000000001/",
        "authorName": "Jane Founder",
        "authorUrl": "https://www.linkedin.com/in/jane-founder",
        "authorHeadline": "Co-founder at Acme",
        "datePosted": "2026-10-22",
        "numLikes": 42,
        "numComments": 7,
    },
    {
        "postId": "7380000000000000002",
        "text": "We just joined the Speedrun batch.",
        "postUrl": "https://www.linkedin.com/feed/update/urn:li:activity:7380000000000000002/",
        "authorName": "Sam Builder",
        "authorUrl": "https://www.linkedin.com/in/sam-builder",
        "authorHeadline": "Founder",
        "datePosted": "2026-10-21",
        "numLikes": 3,
        "numComments": 0,
    },
]


def _apify_response(rows, status=201):
    # run-sync-get-dataset-items answers 201 Created on success.
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(rows).encode("utf-8")
    return resp


class LinkedInSourceTest(unittest.TestCase):
    def test_sends_keywords_and_maps_rows(self):
        with mock.patch.object(
            linkedin_source.requests, "post", return_value=_apify_response(ACTOR_ROWS)
        ) as post:
            items = linkedin_source.get_new_signals(lambda item_id: False)

        url = post.call_args.args[0]
        self.assertEqual(
            url,
            linkedin_source.APIFY_RUN_SYNC_URL.format(actor_id=config.APIFY_LINKEDIN_ACTOR_ID),
        )
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"keywords": config.LINKEDIN_SEARCH_TERMS, "maxPostsPerKeyword": 50},
        )

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["item_id"], "linkedin:7380000000000000001")
        self.assertEqual(first["founder_name"], "Jane Founder")
        self.assertEqual(first["founder_handle"], "https://www.linkedin.com/in/jane-founder")
        self.assertEqual(first["post_text"], "Excited to share that Acme is part of YC S26!")
        self.assertEqual(first["post_link"], ACTOR_ROWS[0]["postUrl"])
        self.assertEqual(first["source"], "LinkedIn")

    def test_skips_seen_posts(self):
        seen = {"linkedin:7380000000000000001"}
        with mock.patch.object(
            linkedin_source.requests, "post", return_value=_apify_response(ACTOR_ROWS)
        ):
            items = linkedin_source.get_new_signals(lambda item_id: item_id in seen)

        self.assertEqual([i["item_id"] for i in items], ["linkedin:7380000000000000002"])


if __name__ == "__main__":
    unittest.main()
