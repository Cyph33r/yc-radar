# YC Radar — YC Launch Monitor Slack Bot

A personal Slack bot that continuously monitors four sources for new
Y Combinator and YC Speedrun company launches, and fires a real-time
alert into Slack the moment one is detected — including founder
self-announcements that land *before* YC's own official post.

Built for GTM, sales, and BD professionals who want to be first in a
new YC company's inbox, not the fifth "congrats on launching" email
that week.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

## What it monitors

- **YC Directory** (`ycombinator.com/companies`) — the source of truth for confirming a real YC/Speedrun company; scraped for newly added companies and batch listings
- **YC Speedrun page** — tracked separately from the main directory and tagged accordingly, since it's a distinct subprogram
- **X (Twitter)** — detects founder launch posts mentioning YC/Speedrun keywords ("YC S26", "Speedrun batch", "backed by Y Combinator") *before* YC has made it official
- **LinkedIn** — detects founder posts and company pages referencing YC or Speedrun

Every alert is deduplicated against a persistent SQLite store, so the
bot never re-alerts on something it's already posted — including across
restarts and redeploys.

## Architecture

```
poller.py          — shared poll-cycle logic (the actual source-checking work)
main.py             — standalone entrypoint for local testing/dev
pond_server.py      — production entrypoint; FastAPI server implementing
                      Pond Protocol V1, which also runs the same recurring
                      poll schedule in the background
config.py           — loads and validates all environment variables
db.py               — SQLite-backed dedup state (seen_items table)
slack_alerts.py     — formats and posts both alert shapes via slack_sdk
sources/
  yc_directory.py    — YC main directory scraper (Playwright)
  yc_speedrun.py      — YC Speedrun page scraper (Playwright)
  x_source.py          — X/Twitter early signals (Apify)
  linkedin_source.py   — LinkedIn early signals (Apify)
```

`main.py` and `pond_server.py` both call the same `poller.run_poll_cycle()`
— nothing is duplicated between the local-testing path and the production
deployment.

## Known limitations (documented, not hidden)

- **YC Directory / Speedrun scrapers** use Playwright against the live,
  JS-rendered pages. Selectors were written from the site's general
  structure and may need periodic re-checking against the live DOM if
  YC changes their markup.
- **X source** uses the Apify actor
  `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`,
  called with a constructed search URL per search term. Company name and
  batch are extracted from raw tweet text via regex heuristics
  (`_extract_company_name` / `_extract_batch` in `x_source.py`) since the
  actor doesn't return a dedicated company field — reliable on typical
  "Company (YC S26)" phrasing, not guaranteed on every tweet.
- **LinkedIn source** uses the Apify actor `apimaestro~linkedin-posts-search`.
  Genuine open-keyword search across all of LinkedIn is much rarer than on
  X — most LinkedIn actors only scrape a *known* profile or company page's
  posts. This is the closest available option for open search, but
  coverage may be less complete than X's.
- Using third-party Apify scrapers for X and LinkedIn sits outside those
  platforms' official APIs and terms of service. That's the deliberate
  tradeoff for real-time coverage without official API costs (X's search
  API alone runs ~$200+/month) — worth being upfront about.

## Local setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Create the Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From an app manifest**
2. Select your target workspace, then paste this YAML:
   ```yaml
   display_information:
     name: YC Launch Monitor
     description: Real-time alerts for early YC and Speedrun launches
   features:
     bot_user:
       display_name: YC Radar
       always_online: true
   oauth_config:
     scopes:
       bot:
         - chat:write
         - chat:write.public
   ```
3. Click **Next**, review permissions, click **Create**
4. Click **Install to Workspace**, approve
5. Under **OAuth & Permissions**, copy the **Bot User OAuth Token** (starts with `xoxb-`) → this is `SLACK_BOT_TOKEN`
6. In Slack, invite the bot to your target channel: `/invite @YC Radar`
7. Right-click the channel → **View channel details** → copy the ID at the bottom (starts with `C`) → this is `SLACK_CHANNEL_ID`

### 3. Set up Apify

1. Sign up at [apify.com](https://apify.com), grab your **API token** from **Settings → Integrations** → this is `APIFY_API_TOKEN`
2. This project uses two pre-selected actors (below) — no further setup needed beyond the API token, unless you want to swap in alternatives
3. If you do swap actors, **test each one manually** in the Apify console first — input field names and output shape vary by actor

This project currently uses:
- X: `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`
- LinkedIn: `apimaestro~linkedin-posts-search`

### 4. Configure environment variables

```bash
cp .env.example .env
```

Fill in real values for:
```
SLACK_BOT_TOKEN
SLACK_CHANNEL_ID
APIFY_API_TOKEN
APIFY_X_ACTOR_ID
APIFY_LINKEDIN_ACTOR_ID
X_SEARCH_TERMS
LINKEDIN_SEARCH_TERMS
```

`POND_ACCESS_KEY` can stay blank for local testing via `main.py` — it's
only required to run `pond_server.py` (see the Pond integration section
below), since that file now enforces authentication unconditionally.

### 5. Run it locally

```bash
python main.py
```

Runs one poll cycle immediately, then keeps polling every
`POLL_INTERVAL_HOURS` (default 8). It only posts to Slack when it finds
a genuinely new company or signal — if nothing new exists at that exact
moment, no alert fires, which is expected behavior, not a malfunction.

### 6. Test each piece individually

```bash
# Slack connection (posts regardless of live data — good for confirming setup)
python3 -c "from slack_alerts import client; from config import config; client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, text='YC Radar connected successfully')"

# YC Directory scraper
python3 -c "from sources.yc_directory import fetch_companies; print(fetch_companies()[:5])"

# X source (bypasses dedup so you always see results)
python3 -c "from sources.x_source import get_new_signals; print(get_new_signals(lambda x: False)[:3])"

# LinkedIn source
python3 -c "from sources.linkedin_source import get_new_signals; print(get_new_signals(lambda x: False)[:3])"
```

Delete `state.db` between test runs if you want to re-trigger alerts
for items already marked seen.

## Deployment (Render.com)

### One-click deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

Click the button above and Render will:
1. Fork the repo into your GitHub account
2. Create the web service with the correct build/start commands already configured
3. Show you a form with **only the fields you need to fill in** — everything else (Python version, actor IDs, search terms) is pre-filled by [`render.yaml`](render.yaml)

**You'll be prompted for three values:**

| Field | Where to get it |
|---|---|
| `SLACK_BOT_TOKEN` | [api.slack.com/apps](https://api.slack.com/apps) → your app → **OAuth & Permissions** → Bot User OAuth Token (starts with `xoxb-`) |
| `SLACK_CHANNEL_ID` | In Slack, right-click your target channel → **View channel details** → copy the ID at the bottom (starts with `C`) |
| `APIFY_API_TOKEN` | [apify.com](https://apify.com) → **Settings → Integrations** → API token |

`POND_ACCESS_KEY` is also prompted but **optional** — leave it blank and Slack alerts work fine. It's only needed if you're listing the agent on [Pond](https://joinpond.ai), where it gates the `/runs` and `/tasks` API endpoints.

Once you click **Deploy**, Render gives you a public HTTPS URL like `https://yc-radar.onrender.com` and the bot starts monitoring immediately.

Render's free tier spins down after inactivity — the first request
after idle time may take 30–60 seconds while it wakes up.

<details>
<summary><strong>Manual deploy (without the button)</strong></summary>

1. Push this repo to GitHub
2. On [render.com](https://render.com): **New → Web Service** → connect this repo
3. **Build Command:**
   ```
   pip install -r requirements.txt && python -m playwright install chromium
   ```
   *(Do not add `--with-deps` — it tries to `apt-get install` system packages as root via `su`, which Render's build environment doesn't allow and will fail the build.)*
4. **Start Command:**
   ```
   uvicorn pond_server:app --host 0.0.0.0 --port $PORT
   ```
5. **Environment** tab — add every variable from `.env.example` with real values, plus:
   ```
   PYTHON_VERSION=3.12.7
   POND_ACCESS_KEY=<generated by Pond when you list the agent>
   ```
6. Deploy.

</details>

### Deployment troubleshooting (real issues hit building this)

| Symptom | Cause | Fix |
|---|---|---|
| `error: failed-wheel-build-for-install` / greenlet compile errors | Render defaulted to a too-new Python (3.14) that Playwright's `greenlet` dependency can't build against | Set `PYTHON_VERSION=3.12.7` as an environment variable (not `runtime.txt` — Render doesn't reliably read that) |
| `su: Authentication failure` / `Failed to install browsers` | `playwright install --with-deps` tries to install OS packages as root | Drop `--with-deps`, use plain `python -m playwright install chromium` |
| `Missing required env var: SLACK_BOT_TOKEN` at runtime | Render env vars are separate from Codespaces secrets — nothing carries over automatically | Re-add every variable in Render's own **Environment** tab |
| `ModuleNotFoundError` / wrong app fails to start | Start command pointed at the wrong file | Confirm Start Command is exactly `uvicorn pond_server:app --host 0.0.0.0 --port $PORT` |
| `Port scan timeout reached, no open ports detected` | Start command ran `python main.py` (which runs a blocking loop and never opens a port) or uvicorn omitted `--host 0.0.0.0` | In Render service **Settings → Start Command**, set to: `uvicorn pond_server:app --host 0.0.0.0 --port $PORT` |
| Apify calls return `404 Client Error: Not Found` | Actor ID env var had a `/` instead of `~`, and/or a trailing newline from copy-paste | `config.py`'s `_require()` strips whitespace; each source file also normalizes `/` → `~` before building the request URL |

## Pond Protocol V1 integration

`pond_server.py` implements the three endpoints required by
[Pond's Agent spec](https://docs.joinpond.ai/docs/build-and-publish-an-agent-on-pond-full):

| Endpoint | Auth required | Purpose |
|---|---|---|
| `GET /manifest` | No | Public — describes the agent's capabilities, always available without a key |
| `POST /runs` | Yes | Triggers a poll cycle; always returns `202` with a `task_id`, since a real poll cycle (scraping + API calls) is never instant |
| `GET /tasks/{task_id}` | Yes | Poll for a run's status and, once `completed`, its result |

**Auth:** every `/runs` and `/tasks` request must include:
```
Authorization: Bearer <POND_ACCESS_KEY>
X-Agent-Protocol-Version: 1.0
```
`/manifest` requires neither header. `POND_ACCESS_KEY` must be set for
`pond_server.py` to accept any runtime request — there is no bypass.

**Idempotency:** Pond sends `Idempotency-Key: <run_id>` and may resend the
same `run_id` on retry. `pond_server.py` rejects any request where the
header doesn't match the body's `run_id`, and keys its task store by
`run_id` itself — so a valid duplicate naturally returns the same task
instead of starting a second poll cycle.

**Usage reporting:** every completed/failed task response includes
`usage: {unit_of_measurement: "result", quantity: <alert count>}`, matching
the `result`-based pricing plan configured on the Pond listing.

### Testing the Pond endpoints directly

```bash
curl https://yc-radar.onrender.com/manifest

curl -i -X POST https://yc-radar.onrender.com/runs \
  -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" \
  -H "X-Agent-Protocol-Version: 1.0" \
  -H "Idempotency-Key: test123" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"test123","agent_id":"agt_test","conversation_id":"chat_test","history_truncated":false,"user":{"id":"usr_test","locale":"en-US","timezone":"America/Los_Angeles"},"messages":[{"id":"msg_test","role":"user","created_at":"2026-08-29T10:00:00Z","parts":[{"type":"text","text":"Run a poll cycle."}]}],"parameters":{},"execution":{"accepted_output_modes":["text/markdown"],"deadline_ms":300000}}'

curl -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" -H "X-Agent-Protocol-Version: 1.0" \
  https://yc-radar.onrender.com/tasks/test123
```

Expect: `/manifest` returns the capabilities JSON immediately; `/runs`
returns `{"run_id":"test123","task_id":"test123","status":"queued",...}`;
polling `/tasks/test123` a few times moves through `queued` → `running` →
`completed`, with a final `output` and `usage` block.

Note the `Idempotency-Key` header must match `run_id` exactly, or the
request is rejected with `400 invalid_request`.

## Alternative: running persistently without Render

If you'd rather self-host on your own server instead of Render:

**systemd (Linux):**
```ini
[Unit]
Description=YC Radar
After=network.target

[Service]
WorkingDirectory=/path/to/yc-radar
ExecStart=/path/to/yc-radar/venv/bin/python main.py
Restart=always
EnvironmentFile=/path/to/yc-radar/.env

[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now yc-radar`

**pm2:**
```bash
npm install -g pm2
pm2 start "venv/bin/python main.py" --name yc-radar
pm2 save
```

Note: these run `main.py`, the standalone poller — not
`pond_server.py` — so they won't expose the Pond-compatible HTTP
endpoints, only the independent Slack-alerting loop.

## Project structure

```
yc-radar/
├── main.py                   # standalone entrypoint (local/self-hosted)
├── pond_server.py            # Pond Protocol V1 server (Render deployment)
├── poller.py                 # shared poll-cycle logic
├── config.py                 # env var loading + validation
├── db.py                     # SQLite dedup state
├── slack_alerts.py           # Slack message formatting + posting
├── sources/
│   ├── yc_directory.py       # YC main directory scraper (Playwright)
│   ├── yc_speedrun.py        # YC Speedrun page scraper (Playwright)
│   ├── x_source.py           # X/Twitter early signals (Apify)
│   └── linkedin_source.py    # LinkedIn early signals (Apify)
├── runtime.txt                # Python version hint (Render prefers the env var instead)
├── requirements.txt
└── .env.example
```

## Future upgradability

Adding a new source is a matter of adding one more `sources/*.py` module
that implements a `get_new_*(is_seen_fn) -> list[dict]` function, then
registering it inside `poller.py`'s `run_poll_cycle()`. The dedup layer,
Slack formatting, local scheduler, and Pond protocol server don't need
any changes — this is the mechanism the original task's "future
upgradability" requirement (e.g. adding more social platforms later) is
built around.
