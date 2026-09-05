# YC Radar - YC Launch Monitor Slack Bot

A personal Slack bot that continuously monitors four sources for new Y Combinator and YC Speedrun company launches, and fires a real-time alert into Slack the moment one is detected, including founder self-announcements that land *before* YC's own official post.

Built for GTM, sales, and BD professionals who want to be first in a new YC company's inbox, not the fifth "congrats on launching" email that week.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

## What it monitors

- **YC Directory** (`ycombinator.com/companies`): The source of truth for confirming a real YC/Speedrun company; scraped for newly added companies and batch listings.
- **YC Speedrun page**: Tracked separately from the main directory and tagged accordingly, since it is a distinct subprogram.
- **X (Twitter)**: Detects founder launch posts mentioning YC/Speedrun keywords ("YC S26", "Speedrun batch", "backed by Y Combinator") *before* YC has made it official.
- **LinkedIn**: Detects founder posts and company pages referencing YC or Speedrun.

Every alert is deduplicated against a persistent SQLite store, so the bot never re-alerts on something it has already posted, including across restarts and redeploys.

## Architecture

```
poller.py            : Shared poll-cycle logic (the actual source-checking work)
main.py              : Standalone entrypoint for local testing/dev (auto-detects PORT on Render)
pond_server.py       : Production entrypoint; FastAPI server implementing Pond Protocol V1,
                       health checks, and running the background recurring poll schedule
config.py            : Loads and validates all environment variables
db.py                : SQLite-backed dedup state (seen_items table)
slack_alerts.py      : Formats and posts alerts via slack_sdk WebClient
sources/
  browser.py         : Resilient Playwright Chromium launcher with auto-installation fallback
  yc_directory.py    : YC main directory scraper (Playwright)
  yc_speedrun.py     : YC Speedrun page scraper (Playwright)
  x_source.py        : X/Twitter early signals (Apify)
  linkedin_source.py : LinkedIn early signals (Apify)
```

`main.py` and `pond_server.py` both call the same `poller.run_poll_cycle()`. No logic is duplicated between the local testing path and the production deployment.

## Known limitations (documented, not hidden)

- **YC Directory / Speedrun scrapers** use Playwright against the live, JS-rendered pages. Selectors were written from the site's general structure and may need periodic re-checking against the live DOM if YC changes their markup.
- **Resilient browser handling**: Scrapers use `sources/browser.py` to launch Chromium with flags `--no-sandbox` and `--disable-dev-shm-usage`. If Chromium binaries are absent at runtime (for example, in ephemeral container builds), it triggers an on-demand download and retries automatically.
- **X source** uses the Apify actor `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`, called with a constructed search URL per search term. Company name and batch are extracted from raw tweet text via regex heuristics (`_extract_company_name` / `_extract_batch` in `x_source.py`) because the actor does not return a dedicated company field. This is reliable on typical "Company (YC S26)" phrasing, but not guaranteed on every tweet.
- **LinkedIn source** uses the Apify actor `apimaestro~linkedin-posts-search`. Genuine open-keyword search across all of LinkedIn is much rarer than on X, since most LinkedIn actors only scrape a known profile or company page's posts. This is the closest available option for open search, but coverage may be less complete than X's.
- **Third-party Apify scrapers**: Using Apify scrapers for X and LinkedIn sits outside those platforms' official APIs and terms of service. That is the deliberate tradeoff for real-time coverage without prohibitive official API costs (X's search API alone costs ~$200+/month), which is important to understand upfront.

## Local setup

### 1. Install dependencies

Ensure you are using Python 3.12 (pinned to `3.12.7` in `.python-version`). Python versions 3.14 or newer will encounter build errors with Playwright dependencies.

```bash
# Create and activate virtual environment
python -m venv venv

# Linux / macOS:
source venv/bin/activate
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows Command Prompt:
venv\Scripts\activate.bat

# Install Python packages and Chromium
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Create the Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) -> **Create New App** -> **From an app manifest**.
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
3. Click **Next**, review permissions, and click **Create**.
4. In the left navigation menu, click **Install App** -> **Install to Workspace** and approve.
5. Under **OAuth & Permissions**, copy the **Bot User OAuth Token** (starts with `xoxb-`). This is `SLACK_BOT_TOKEN`.
6. Invite the bot to your target Slack channel: `/invite @YC Radar` (or if it is a public channel, `chat:write.public` allows direct delivery).
7. Right-click the channel name in Slack -> **View channel details** -> scroll to the bottom and copy the **Channel ID** (starts with `C`). This is `SLACK_CHANNEL_ID`.

### 3. Set up Apify

1. Create a free account at [apify.com](https://apify.com).
2. Go to **Settings -> Integrations** (or visit [console.apify.com/account/integrations](https://console.apify.com/account/integrations)) and copy your **Personal API token**. This is `APIFY_API_TOKEN`.
3. Pre-configured actors: This project includes tested default actors in `.env.example`:
   - X (Twitter): `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`
   - LinkedIn: `apimaestro~linkedin-posts-search`
   You do not need to manually configure actors unless you wish to customize search queries or swap in alternatives.

### 4. Configure environment variables

Copy the example environment file:
```bash
cp .env.example .env
```

Open `.env` and fill in your **3 required credentials**:
```ini
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL_ID=C0123456789
APIFY_API_TOKEN=apify_api_your_token_here
```

All other variables are pre-configured with working defaults:
- `APIFY_X_ACTOR_ID`: Default actor for X search.
- `APIFY_LINKEDIN_ACTOR_ID`: Default actor for LinkedIn search.
- `X_SEARCH_TERMS`: Keywords to track on X (`"YC S26,backed by Y Combinator,Speedrun batch"`).
- `LINKEDIN_SEARCH_TERMS`: Keywords to track on LinkedIn (`"YC S26,Y Combinator,Speedrun batch"`).
- `POLL_INTERVAL_HOURS`: Polling interval in hours (default: `8`).
- `DB_PATH`: SQLite deduplication database path (default: `state.db`).
- `PLAYWRIGHT_BROWSERS_PATH`: Defaults to `0` (installs and looks up Chromium inside `.venv`).
- `POND_ACCESS_KEY`: Pre-set to `6PVf9vWPkBDT7nSZJSrsjt7m88EAu6Vt` for Pond Protocol V1 testing (can remain blank if running only the standalone poller).

### 5. Run the application

You can run YC Radar in either of two modes:

#### Option A: Standalone background worker (`main.py`)
Runs an immediate poll cycle on launch, then keeps polling every 8 hours in a background scheduler. Best for local background monitoring or headless servers:
```bash
python main.py
```

#### Option B: Pond Protocol V1 API server (`pond_server.py`)
Runs the FastAPI web server implementing Pond Protocol V1 (`GET /manifest`, `POST /runs`, `GET /tasks/{task_id}`) and health check endpoints (`GET /health`, `GET /`). An initial poll cycle is triggered immediately in a background thread on startup:
```bash
uvicorn pond_server:app --host 0.0.0.0 --port 8000 --reload
# or:
python pond_server.py
```

### 6. Test each piece individually

You can test each component in isolation using the following one-liners:

```bash
# Test 1: Slack alert delivery (sends a confirmation message to your channel)
python -c "from slack_alerts import client; from config import config; client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, text='YC Radar connected successfully')"

# Test 2: Resilient browser launch (launches Chromium with automatic fallback auto-install)
python -c "from sources.browser import launch_browser; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=launch_browser(p); print('Browser launched successfully'); b.close(); p.stop()"

# Test 3: YC Directory scraper (fetches live companies from YC directory)
python -c "from sources.yc_directory import fetch_companies; print(fetch_companies()[:3])"

# Test 4: YC Speedrun scraper (fetches live companies from Speedrun page)
python -c "from sources.yc_speedrun import fetch_speedrun_companies; print(fetch_speedrun_companies()[:3])"

# Test 5: X early signals (fetches live tweets via Apify, bypassing dedup)
python -c "from sources.x_source import get_new_signals; print(get_new_signals(lambda x: False)[:2])"

# Test 6: LinkedIn early signals (fetches live LinkedIn posts via Apify, bypassing dedup)
python -c "from sources.linkedin_source import get_new_signals; print(get_new_signals(lambda x: False)[:2])"

# Test 7: Run a complete poll cycle end-to-end
python -c "from poller import run_poll_cycle; print(run_poll_cycle())"
```

To reset seen items during testing, delete the SQLite file:
```bash
rm state.db   # Windows: del state.db
```

## Deployment (Render.com)

### One-click deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

Click the button above and Render will:
1. Fork the repo into your GitHub account.
2. Create the web service with the correct build and start commands already configured.
3. Show you a form with **only the three credentials you need to fill in**; everything else (Python version 3.12.7, actor IDs, search terms, `PLAYWRIGHT_BROWSERS_PATH=0`, `POND_ACCESS_KEY`) is pre-filled by [`render.yaml`](render.yaml).

**You will be prompted for three values:**

| Field | Where to get it |
|---|---|
| `SLACK_BOT_TOKEN` | [api.slack.com/apps](https://api.slack.com/apps) -> your app -> **OAuth & Permissions** -> Bot User OAuth Token (starts with `xoxb-`) |
| `SLACK_CHANNEL_ID` | In Slack, right-click your target channel -> **View channel details** -> copy the ID at the bottom (starts with `C`) |
| `APIFY_API_TOKEN` | [apify.com](https://apify.com) -> **Settings -> Integrations** -> API token |

`POND_ACCESS_KEY` is pre-configured in `render.yaml` (`6PVf9vWPkBDT7nSZJSrsjt7m88EAu6Vt`), gating the `/runs` and `/tasks` API endpoints for Pond Protocol V1 marketplace integration.

Once you click **Deploy**, Render gives you a public HTTPS URL like `https://yc-radar.onrender.com` and the bot starts monitoring immediately. On startup, it runs an initial poll cycle right away and schedules subsequent runs every 8 hours.

Render's free tier spins down after inactivity. The first request after idle time may take 30 to 60 seconds while it wakes up. Health checks are served at `/health` to keep deployments stable.

<details>
<summary><strong>Manual deploy (without the button)</strong></summary>

1. Push this repo to GitHub.
2. On [render.com](https://render.com): **New -> Web Service** -> connect this repo.
3. **Build Command:**
   ```
   pip install -r requirements.txt && python -m playwright install chromium
   ```
   *(Do not add `--with-deps` because it tries to `apt-get install` system packages as root via `su`, which Render's build environment does not allow and will fail the build.)*
4. **Start Command:**
   ```
   uvicorn pond_server:app --host 0.0.0.0 --port $PORT
   ```
5. **Environment** tab: add variables from `.env.example` with real values, plus:
   ```
   PYTHON_VERSION=3.12.7
   PLAYWRIGHT_BROWSERS_PATH=0
   POND_ACCESS_KEY=6PVf9vWPkBDT7nSZJSrsjt7m88EAu6Vt
   ```
6. Deploy.

</details>

### Deployment troubleshooting (real issues hit building this)

| Symptom | Cause | Fix |
|---|---|---|
| `error: failed-wheel-build-for-install` / greenlet compile errors | Render defaulted to a too-new Python (3.14) that Playwright's `greenlet` dependency cannot build against | Set `PYTHON_VERSION=3.12.7` as an environment variable or use `.python-version` (Render does not reliably read `runtime.txt`) |
| `su: Authentication failure` / `Failed to install browsers` | `playwright install --with-deps` tries to install OS packages as root | Drop `--with-deps`, use plain `python -m playwright install chromium` |
| `BrowserType.launch: Executable doesn't exist at /opt/render/.cache/ms-playwright/...` | Render does not persist `~/.cache` between build and runtime containers | Set `PLAYWRIGHT_BROWSERS_PATH=0` in the Environment tab (and `render.yaml`) so browsers install into `.venv`, which is persisted. `sources/browser.py` also features automatic fallback reinstallation at runtime. |
| `Missing required env var: SLACK_BOT_TOKEN` at runtime | Render env vars are separate from Codespaces secrets; nothing carries over automatically | Re-add every variable in Render's own **Environment** tab |
| `ModuleNotFoundError` / wrong app fails to start | Start command pointed at the wrong file | Confirm Start Command is exactly `uvicorn pond_server:app --host 0.0.0.0 --port $PORT` |
| `Port scan timeout reached, no open ports detected` | Start command ran `python main.py` (when lacking PORT handling) or uvicorn omitted `--host 0.0.0.0` | In Render service **Settings -> Start Command**, set to: `uvicorn pond_server:app --host 0.0.0.0 --port $PORT` (note: `main.py` also forwards to `pond_server` if `PORT` is set) |
| Apify calls return `404 Client Error: Not Found` | Actor ID env var had a `/` instead of `~`, and/or a trailing newline from copy-paste | `config.py`'s `_require()` strips whitespace; each source file also normalizes `/` to `~` before building the request URL |

## Pond Protocol V1 integration

`pond_server.py` implements the endpoints required by
[Pond's Agent spec](https://docs.joinpond.ai/docs/build-and-publish-an-agent-on-pond-full) as well as health check endpoints for cloud hosting:

| Endpoint | Auth required | Purpose |
|---|---|---|
| `GET /health` | No | Health check endpoint returning `{"status": "ok"}` for Render and monitoring |
| `GET /` | No | Root endpoint returning service health status |
| `GET /manifest` | No | Public: describes agent capabilities, metadata, and actions (`run_poll_cycle`) without a key |
| `POST /runs` | Yes | Triggers a poll cycle; returns `202` with `task_id` and validates `action_id: run_poll_cycle` |
| `GET /tasks/{task_id}` | Yes | Poll for a run's status and, once `completed`, its output and usage metrics |

**Auth:** Every `/runs` and `/tasks` request must include:
```
Authorization: Bearer <POND_ACCESS_KEY>
X-Agent-Protocol-Version: 1.0
```
`/manifest` and `/health` require neither header. `POND_ACCESS_KEY` must be set for `pond_server.py` to accept runtime run/task requests; there is no bypass.

**Actions & Validation:** The manifest declares the `run_poll_cycle` action. When a run request arrives at `POST /runs`, `action_id` is validated to be `run_poll_cycle` (returning `400 unsupported_operation` otherwise).

**Idempotency:** Pond sends `Idempotency-Key: <run_id>` and may resend the same `run_id` on retry. `pond_server.py` rejects any request where the header does not match the body's `run_id`, and keys its task store by `run_id` itself, so a valid duplicate naturally returns the existing task instead of starting a redundant poll cycle.

**Usage reporting:** Every completed/failed task response includes `usage: {unit_of_measurement: "result", quantity: <alert count>}`, matching the `result`-based pricing plan configured on the Pond listing.

### Testing the Pond endpoints directly

```bash
# Check health
curl https://yc-radar.onrender.com/health

# Fetch manifest
curl https://yc-radar.onrender.com/manifest

# Trigger a run
curl -i -X POST https://yc-radar.onrender.com/runs \
  -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" \
  -H "X-Agent-Protocol-Version: 1.0" \
  -H "Idempotency-Key: test123" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"test123","agent_id":"agt_test","conversation_id":"chat_test","action_id":"run_poll_cycle","history_truncated":false,"user":{"id":"usr_test","locale":"en-US","timezone":"America/Los_Angeles"},"messages":[{"id":"msg_test","role":"user","created_at":"2026-08-29T10:00:00Z","parts":[{"type":"text","text":"Run a poll cycle."}]}],"parameters":{},"execution":{"accepted_output_modes":["text/markdown"],"deadline_ms":300000}}'

# Poll task status
curl -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" -H "X-Agent-Protocol-Version: 1.0" \
  https://yc-radar.onrender.com/tasks/test123
```

Expect:
- `/manifest` returns the capabilities JSON immediately.
- `/runs` returns `{"run_id":"test123","task_id":"test123","status":"queued",...}`.
- Polling `/tasks/test123` moves through `queued` -> `running` -> `completed`, with final `output` and `usage` blocks.
- The `Idempotency-Key` header must match `run_id` exactly, or the request is rejected with `400 invalid_request`.

## Alternative: running persistently without Render

If you prefer to self-host on your own server instead of Render:

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

Note: These run `main.py` directly in standalone scheduler mode (without `PORT` defined), running the local Slack-alerting loop without exposing external HTTP endpoints.

## Project structure

```
yc-radar/
├── main.py                   # Standalone entrypoint (auto-delegates to pond_server if PORT is set)
├── pond_server.py            # Pond Protocol V1 server + health check endpoints (Render)
├── poller.py                 # Shared poll-cycle logic (YC Directory, Speedrun, X, LinkedIn)
├── config.py                 # Env var loading + validation (defaults PLAYWRIGHT_BROWSERS_PATH on Render)
├── db.py                     # SQLite dedup state (seen_items table)
├── slack_alerts.py           # Slack message formatting + WebClient delivery
├── sources/
│   ├── browser.py            # Resilient Playwright Chromium launcher with auto-installation
│   ├── yc_directory.py       # YC main directory scraper (Playwright)
│   ├── yc_speedrun.py        # YC Speedrun page scraper (Playwright)
│   ├── x_source.py           # X/Twitter early signals (Apify)
│   └── linkedin_source.py    # LinkedIn early signals (Apify)
├── .python-version           # Pinned Python version (3.12.7)
├── runtime.txt               # Python runtime version hint
├── render.yaml               # Render blueprint infrastructure configuration
├── requirements.txt
└── .env.example
```

## Future upgradability

Adding a new source is a matter of adding one more `sources/*.py` module that implements a `get_new_*(is_seen_fn) -> list[dict]` function, then registering it inside `poller.py`'s `run_poll_cycle()`. The dedup layer, Slack formatting, local scheduler, and Pond protocol server do not need any changes. This architecture satisfies future upgradability requirements (such as adding additional social platforms or directories later) with zero refactoring of core pipelines.
