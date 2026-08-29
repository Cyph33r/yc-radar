# YC Launch Monitor — Slack Bot

Continuously monitors four sources — the YC Directory, the YC Speedrun
page, X/Twitter, and LinkedIn — and posts a Slack alert the moment a new
YC/Speedrun company or an early founder self-announcement is detected.
State is kept in a local SQLite file so restarts never re-alert on
something already seen.

## How it works

- `main.py` runs a poll cycle immediately on startup, then every
  `POLL_INTERVAL_HOURS` (default 8) via APScheduler.
- Each source in `sources/` returns only *new* items — checked against
  `state.db` (see `db.py`) before anything is reported.
- `slack_alerts.py` posts one of two message formats: a confirmed-company
  alert or an early-signal alert (founder posted before YC announced).
- `pond_agent.py` is a no-op until you register the bot with Pond and
  fill in the agent credentials — after that it sends a heartbeat at the
  end of every poll cycle.

**Important — before this is production-ready:**
- **YC Directory / Speedrun** (`sources/yc_directory.py`,
  `sources/yc_speedrun.py`) scrape the live pages with Playwright.
  Their selectors are written from the page's current general structure
  and *will* need a quick check/adjustment against the live DOM — open
  the page, inspect a company card, and confirm the selectors still
  match before your first real run.
- **X and LinkedIn** (`sources/x_source.py`,
  `sources/linkedin_source.py`) call a third-party scraping actor via
  [Apify](https://apify.com). You need to pick specific actors from the
  Apify Store (see step 4 below) and match the field names in those two
  files to that actor's actual output — the ones here are written for a
  typical actor's schema as a starting point, not a guarantee.
- Using third-party scrapers for X and LinkedIn sits outside those
  platforms' official APIs and terms of service — that's the tradeoff of
  getting real-time coverage without official (and in X's case, costly)
  API access. Worth being upfront about this in your task submission.

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Create the Slack app

1. Go to https://api.slack.com/apps → "Create New App" → "From scratch".
2. Under **OAuth & Permissions**, add the `chat:write` Bot Token Scope.
3. Click **Install to Workspace**, approve, then copy the **Bot User
   OAuth Token** (starts with `xoxb-`).
4. Invite the bot to your target channel (`/invite @YourBotName`), or
   note the user ID if you want DMs instead.
5. Get the channel ID: right-click the channel in Slack → **View channel
   details** → copy the ID at the bottom.

### 3. Set up Apify

1. Sign up at https://apify.com and grab your API token from
   **Settings → Integrations**.
2. In the Apify Store, search for an X/Twitter search scraper and a
   LinkedIn posts/company scraper. Test each one manually in the Apify
   console first with a sample search term so you know its exact input
   and output fields.
3. Update `sources/x_source.py` and `sources/linkedin_source.py` so the
   `run_input` dict and the `raw.get(...)` field names match what you
   tested.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Fill in `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `APIFY_API_TOKEN`,
`APIFY_X_ACTOR_ID`, `APIFY_LINKEDIN_ACTOR_ID`, and the search terms.

### 5. Register with Pond's agent infrastructure

Go to https://joinpond.ai/agent/create, register this bot, and copy the
resulting credentials into `POND_AGENT_ID` / `POND_AGENT_API_KEY` in
`.env`. Until this is filled in, the bot runs standalone with no
heartbeat calls — that's fine for local testing.

### 6. Run it

```bash
python main.py
```

This runs a poll cycle immediately, then keeps running and polls every
8 hours (configurable). Leave the terminal open, or see below for
running it persistently.

### 7. Run it persistently (pick one)

**systemd (Linux server):**
```ini
# /etc/systemd/system/yc-monitor.service
[Unit]
Description=YC Launch Monitor
After=network.target

[Service]
WorkingDirectory=/path/to/yc-launch-monitor
ExecStart=/path/to/yc-launch-monitor/venv/bin/python main.py
Restart=always
EnvironmentFile=/path/to/yc-launch-monitor/.env

[Install]
WantedBy=multi-user.target
```
Then: `sudo systemctl enable --now yc-monitor`

**pm2 (simplest, cross-platform):**
```bash
npm install -g pm2
pm2 start "venv/bin/python main.py" --name yc-monitor
pm2 save
```

**Docker:** wrap the same `python main.py` command in a container with a
`restart: always` policy if you'd rather containerize it.

## Testing before your first real submission

- Temporarily lower `POLL_INTERVAL_HOURS` to a small value and confirm a
  test alert lands in Slack.
- Delete `state.db` between test runs if you want to re-trigger alerts
  for items already seen.
- Record your screen (or take screenshots) showing a real alert posting
  in Slack — this is a required deliverable.

## Project structure

```
yc-launch-monitor/
├── main.py                 # orchestrator / scheduler
├── config.py                # env var loading
├── db.py                     # SQLite dedup state
├── slack_alerts.py           # Slack message formatting + posting
├── pond_agent.py             # Pond heartbeat integration
├── sources/
│   ├── yc_directory.py       # YC main directory scraper (Playwright)
│   ├── yc_speedrun.py        # YC Speedrun page scraper (Playwright)
│   ├── x_source.py           # X/Twitter early signals (Apify)
│   └── linkedin_source.py    # LinkedIn early signals (Apify)
├── requirements.txt
└── .env.example
```

## Future upgradability

Adding a new source is a matter of adding one more `sources/*.py` module
that implements a `get_new_*(is_seen_fn) -> list[dict]` function, then
registering it in the loop in `main.py` — the dedup, Slack formatting,
and scheduling layers don't need to change.
