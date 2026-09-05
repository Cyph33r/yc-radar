# YC Radar — Slack Bot

A personal Slack bot that keeps you ahead of **every new Y Combinator and YC Speedrun company launch** — so you can reach founders early for pipeline and outreach, before everyone else.

It continuously monitors four sources and posts **real-time alerts to Slack**
whenever a new company is detected. Crucially, it **flags founders who announce
their YC acceptance on X / LinkedIn before YC has officially listed them** — the
highest-value outreach signal.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

---

## Quick start (local, 5 minutes)

```bash
# 1. Clone & set up
git clone https://github.com/Cyph33r/yc-radar.git
cd yc-radar

# 2. Create virtualenv & install
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

# 3. Configure
cp .env.example .env
#    then edit .env — fill in SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, APIFY_API_TOKEN

# 4. Run one poll cycle (prints + sends alerts to Slack)
python main.py

# 5. Run persistently — pick one:
python main.py                    # foreground (polls every 8h by default)
# or deploy to Render (see below) for zero-maintenance hosting
```

Configuration lives in **`.env`** — see
[Configuration reference](#configuration-reference) below.
Secrets are never committed (`.env` is gitignored).

---

## What it does

| Source | Type | Signal |
|---|---|---|
| **YC Directory** (`ycombinator.com/companies`) | Official | Newly added companies & batch listings → ✅ **Confirmed** |
| **YC Speedrun** (separate subprogram page) | Official | Newly added Speedrun companies → ✅ **Confirmed** |
| **X (Twitter)** | Social | Founder posts mentioning YC/Speedrun keywords → ⚡ **Early** (if not yet officially listed) |
| **LinkedIn** | Social | Founder posts referencing YC/Speedrun → ⚡ **Early** (if not yet officially listed) |

### Two alert types

- **⚡ EARLY YC SIGNAL** — a founder announced their acceptance on X or LinkedIn, but the company is **not yet in the official YC directory**. This is the "get ahead of everyone" signal.
- **✅ NEW YC COMPANY** — the company is now officially listed in YC's directory or the Speedrun subprogram.

Each alert includes: **company name, founder, batch, source, a link to the original post, and a timestamp**. Tap the link, see the announcement yourself, and reach out — that's the entire workflow this bot exists to speed up.

---

## Technologies

| Layer | Tech | Why |
|---|---|---|
| Language | **Python 3.9+** | Batteries included, easy to run & extend |
| Web scraping | **Playwright** | Handles JS-rendered YC/Speedrun pages |
| Social signals | **Apify actors** | X + LinkedIn scraping without official API costs |
| Slack | **`slack_sdk`** via bot OAuth token | Rich, formatted alert messages |
| State & dedup | **SQLite** (stdlib `sqlite3`) | Zero-setup persistent storage, no external DB |
| Config | **python-dotenv** | `.env` for secrets (never committed) |
| Scheduler | **Threaded sleep loop** (8h default) | Built into `main.py`, no external scheduler needed |
| Production server | **FastAPI + Uvicorn** | Hosts the Pond Protocol V1 endpoints on Render |
| Deployment | **Render** (one-click) | Free tier with external cron workaround |

---

## Architecture

```
yc-radar/
├── .github/
│   └── workflows/
│       └── poll.yml              # optional: external cron trigger for Render free tier
├── main.py                       # standalone entrypoint (local / self-hosted)
├── pond_server.py                # Pond Protocol V1 server (Render deployment)
├── poller.py                     # shared poll-cycle logic
├── config.py                     # env var loading + validation
├── db.py                         # SQLite dedup state (seen_items table)
├── slack_alerts.py               # Slack message formatting + posting
├── sources/
│   ├── yc_directory.py           # YC main directory scraper (Playwright)
│   ├── yc_speedrun.py            # YC Speedrun page scraper (Playwright)
│   ├── x_source.py               # X/Twitter early signals (Apify)
│   └── linkedin_source.py        # LinkedIn early signals (Apify)
├── render.yaml                   # Render blueprint (one-click deploy)
├── runtime.txt                   # Python version hint
├── requirements.txt
└── .env.example
```

**Two entrypoints, one brain:** `main.py` (local) and `pond_server.py` (Render)
both call the same `poller.run_poll_cycle()` — nothing is duplicated between
local dev and production.

**State & dedup:** everything is stored in a local SQLite database (`state.db`).
Each event has a stable dedup key, so you **never get duplicate alerts** — even
across restarts and redeploys.

### Data flow

```
                 ┌──────────────────────────────────────────────────────┐
                 │              main.py  /  pond_server.py              │
                 │        calls  poller.run_poll_cycle()                │
                 └───────┬─────────────────────────────┬───────────────┘
                         │                             │
         OFFICIAL sources│                             │SOCIAL sources (Apify)
                         ▼                             ▼
   ┌──────────────────────────┐         ┌───────────────────────────────┐
   │ yc_directory.py          │         │ x_source.py                   │
   │  Playwright scraper      │         │  Apify actor → search tweets  │
   │  → new companies + batch │         │  → raw results + regex extract│
   └───────────┬──────────────┘         └──────────────┬────────────────┘
               │  ✅ CONFIRMED                         │  ⚡ EARLY
               │                                       │
   ┌───────────▼──────────────┐         ┌──────────────▼────────────────┐
   │ yc_speedrun.py           │         │ linkedin_source.py            │
   │  Playwright scraper      │         │  Apify actor → search posts   │
   │  → Speedrun companies    │         │  → raw results + extract      │
   └───────────┬──────────────┘         └──────────────┬────────────────┘
               │  ✅ CONFIRMED                         │  ⚡ EARLY
               └──────────────┬────────────────────────┘
                              ▼
                 ┌────────────────────────────┐
                 │ db.py  (SQLite state.db)   │   dedup via seen_items
                 │  is_seen / mark_seen       │   no duplicate alerts ever
                 └────────────┬───────────────┘
                              ▼
                 ┌────────────────────────────┐
                 │ slack_alerts.py            │   formatted alert message
                 │  chat_postMessage (SDK)    │
                 └────────────┬───────────────┘
                              ▼
                       ┌─────────────┐
                       │  Slack      │   ⚡/✅ company · founder · batch
                       │  channel    │   source · link · timestamp
                       └─────────────┘
```

---

## 1. Create the Slack app (one-time)

1. Go to **[api.slack.com/apps](https://api.slack.com/apps)** → **Create New App** → **From an app manifest**
2. Select your workspace, then paste this YAML:
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
3. Click **Next** → review permissions → **Create**
4. Click **Install to Workspace** → **Allow**
5. Under **OAuth & Permissions**, copy the **Bot User OAuth Token** (starts with `xoxb-`) → this is `SLACK_BOT_TOKEN`
6. In Slack, invite the bot to your channel: `/invite @YC Radar`
7. Right-click the channel → **View channel details** → copy the ID at the bottom (starts with `C`) → this is `SLACK_CHANNEL_ID`

---

## 2. Set up Apify (for X + LinkedIn early signals)

1. Sign up at **[apify.com](https://apify.com)**, grab your **API token** from **Settings → Integrations** → this is `APIFY_API_TOKEN`
2. The project uses two pre-selected actors — no further setup needed beyond the API token

Currently used actors:
| Platform | Actor |
|---|---|
| **X (Twitter)** | `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest` |
| **LinkedIn** | `apimaestro~linkedin-posts-search` |

> **Tip:** If you swap actors, **test each one manually** in the Apify console first — input field names and output shape vary by actor.

---

## 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in real values — see [Configuration reference](#configuration-reference) for the full list:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0123456789
APIFY_API_TOKEN=apify_api_...
```

> **Note:** `POND_ACCESS_KEY` can stay blank for local testing via `main.py` — it's only required for `pond_server.py` (Render deployment).

---

## 4. Test each piece

```bash
# Slack connection (always posts — good for confirming setup)
python3 -c "from slack_alerts import client; from config import config; \
  client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, text='YC Radar connected ✅')"

# YC Directory scraper
python3 -c "from sources.yc_directory import fetch_companies; print(fetch_companies()[:5])"

# X source (bypasses dedup so you always see results)
python3 -c "from sources.x_source import get_new_signals; print(get_new_signals(lambda x: False)[:3])"

# LinkedIn source
python3 -c "from sources.linkedin_source import get_new_signals; print(get_new_signals(lambda x: False)[:3])"
```

> **Tip:** Delete `state.db` between test runs to re-trigger alerts for items already marked seen.

---

## 5. Deploy to Render (production)

### One-click deploy (recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Cyph33r/yc-radar)

Render will fork the repo, create the service, and prompt you for **only three values** — everything else is pre-filled by [`render.yaml`](render.yaml):

| Field | Where to get it |
|---|---|
| `SLACK_BOT_TOKEN` | [api.slack.com/apps](https://api.slack.com/apps) → your app → **OAuth & Permissions** → Bot User OAuth Token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | In Slack, right-click your channel → **View channel details** → copy the ID (`C...`) |
| `APIFY_API_TOKEN` | [apify.com](https://apify.com) → **Settings → Integrations** → API token |

<details>
<summary><strong>Manual deploy (without the button)</strong></summary>

1. Push this repo to GitHub
2. On [render.com](https://render.com): **New → Web Service** → connect this repo
3. **Build Command:**
   ```
   pip install -r requirements.txt && python -m playwright install chromium
   ```
   *(Do **not** add `--with-deps` — it tries to `apt-get install` as root, which Render doesn't allow.)*
4. **Start Command:**
   ```
   uvicorn pond_server:app --host 0.0.0.0 --port $PORT
   ```
5. **Environment** tab → add every variable from `.env.example` with real values, plus:
   ```
   PYTHON_VERSION=3.12.7
   POND_ACCESS_KEY=<generated by Pond when you list the agent>
   ```
6. Deploy.

</details>

### ⚠️ Keeping it alive on Render's free tier

Render's free web services **spin down after ~15 minutes of no HTTP traffic**. Since the polling scheduler runs inside the web process, a spun-down service = silence in Slack.

**Pick one fix:**

1. **Upgrade to Starter plan** (~$7/month) — the service never sleeps.
2. **Free fix — ping it externally on a schedule.** Use [cron-job.org](https://cron-job.org) or the included GitHub Actions workflow to call `POST /runs` every few hours:

   <details>
   <summary>Example GitHub Actions workflow (<code>.github/workflows/poll.yml</code>)</summary>

   ```yaml
   name: Trigger YC Radar poll
   on:
     schedule:
       - cron: "0 */8 * * *"
     workflow_dispatch: {}
   jobs:
     trigger:
       runs-on: ubuntu-latest
       steps:
         - name: Call /runs
           run: |
             curl -i -X POST https://yc-radar.onrender.com/runs \
               -H "Authorization: Bearer ${{ secrets.POND_ACCESS_KEY }}" \
               -H "X-Agent-Protocol-Version: 1.0" \
               -H "Idempotency-Key: gha-${{ github.run_id }}" \
               -H "Content-Type: application/json" \
               -d '{"run_id":"gha-${{ github.run_id }}","agent_id":"gha","conversation_id":"gha","history_truncated":false,"user":{"id":"gha","locale":"en-US","timezone":"UTC"},"messages":[{"id":"m","role":"user","created_at":"2026-08-29T00:00:00Z","parts":[{"type":"text","text":"scheduled poll"}]}],"parameters":{},"execution":{"accepted_output_modes":["text/markdown"],"deadline_ms":300000}}'
   ```
   Add `POND_ACCESS_KEY` as a GitHub Actions secret (repo → **Settings → Secrets and variables → Actions**).

   </details>

### Deployment troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Bot posted after deploy, then went silent | Render free-tier spin-down killed the scheduler | Upgrade to Starter, or add the external cron trigger |
| `failed-wheel-build` / greenlet compile errors | Render defaulted to Python 3.14+ | Set `PYTHON_VERSION=3.12.7` as an env var |
| `su: Authentication failure` | `playwright install --with-deps` tries root access | Use plain `python -m playwright install chromium` |
| `Missing required env var: SLACK_BOT_TOKEN` | Render env vars are separate from local `.env` | Re-add every variable in Render's **Environment** tab |
| `ModuleNotFoundError` at runtime | Wrong start command | Confirm: `uvicorn pond_server:app --host 0.0.0.0 --port $PORT` |
| Apify `404 Client Error` | Actor ID had `/` instead of `~`, or trailing whitespace | `config.py` strips whitespace; sources normalize `/` → `~` |

---

## 6. Run persistently without Render

### Option A — systemd (Linux)

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

```bash
sudo systemctl enable --now yc-radar
```

### Option B — pm2 (any machine)

```bash
npm install -g pm2
pm2 start "venv/bin/python main.py" --name yc-radar
pm2 save
```

> **Note:** These run `main.py` (the standalone poller), not `pond_server.py`, so they won't expose the Pond HTTP endpoints — only the Slack-alerting loop.

---

## 7. Pond Protocol V1 integration

`pond_server.py` implements the three endpoints required by [Pond's Agent spec](https://docs.joinpond.ai/docs/build-and-publish-an-agent-on-pond-full):

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /manifest` | No | Public — describes the agent's capabilities |
| `POST /runs` | Yes | Triggers a poll cycle; returns `202` with a `task_id` |
| `GET /tasks/{task_id}` | Yes | Poll for run status → `queued` → `running` → `completed` |

**Auth:** every `/runs` and `/tasks` request must include:
```
Authorization: Bearer <POND_ACCESS_KEY>
X-Agent-Protocol-Version: 1.0
```

**Idempotency:** Pond sends `Idempotency-Key: <run_id>` and may resend the same
`run_id` on retry. The server rejects mismatches and deduplicates valid retries
automatically.

**Usage reporting:** every completed/failed task includes
`usage: {unit_of_measurement: "result", quantity: <alert count>}`.

<details>
<summary><strong>Test the Pond endpoints directly</strong></summary>

```bash
# Manifest (public, no auth)
curl https://yc-radar.onrender.com/manifest

# Trigger a run
curl -i -X POST https://yc-radar.onrender.com/runs \
  -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" \
  -H "X-Agent-Protocol-Version: 1.0" \
  -H "Idempotency-Key: test123" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"test123","agent_id":"agt_test","conversation_id":"chat_test","history_truncated":false,"user":{"id":"usr_test","locale":"en-US","timezone":"America/Los_Angeles"},"messages":[{"id":"msg_test","role":"user","created_at":"2026-08-29T10:00:00Z","parts":[{"type":"text","text":"Run a poll cycle."}]}],"parameters":{},"execution":{"accepted_output_modes":["text/markdown"],"deadline_ms":300000}}'

# Check status
curl -H "Authorization: Bearer YOUR_POND_ACCESS_KEY" \
  -H "X-Agent-Protocol-Version: 1.0" \
  https://yc-radar.onrender.com/tasks/test123
```

</details>

---

## Configuration reference

| Env var | Required | Purpose |
|---|---|---|
| `SLACK_BOT_TOKEN` | ✅ | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | ✅ | Channel ID to post alerts to (`C...`) |
| `APIFY_API_TOKEN` | ✅ | Apify API token for X + LinkedIn actors |
| `APIFY_X_ACTOR_ID` | — | X actor ID (pre-filled in `render.yaml`) |
| `APIFY_LINKEDIN_ACTOR_ID` | — | LinkedIn actor ID (pre-filled in `render.yaml`) |
| `X_SEARCH_TERMS` | — | Comma-separated X search terms (pre-filled) |
| `LINKEDIN_SEARCH_TERMS` | — | Comma-separated LinkedIn search terms (pre-filled) |
| `POLL_INTERVAL_HOURS` | — | Poll interval in hours (default: `8`) |
| `POND_ACCESS_KEY` | Render only | Pond Protocol auth key (required for `pond_server.py`) |
| `PYTHON_VERSION` | Render only | Pin Python version on Render (recommended: `3.12.7`) |

Secrets live in `.env` or the environment — never commit them.

---

## Known limitations

> These are **documented, not hidden** — understanding them helps you run the bot reliably.

- **Render free-tier spin-down** — the biggest gotcha. The service sleeps after ~15 min of no traffic, killing the scheduler. Fix: Starter plan or external cron trigger.
- **YC / Speedrun scrapers** use Playwright against live JS-rendered pages. Selectors may need updating if YC changes their markup.
- **X source** extracts company name and batch from tweet text via regex heuristics — reliable on typical "Company (YC S26)" phrasing, not guaranteed on every tweet.
- **LinkedIn source** uses an open-search Apify actor. Coverage may be less complete than X's since most LinkedIn actors only scrape known profiles.
- **Apify scrapers** for X and LinkedIn sit outside those platforms' official APIs/ToS — a deliberate tradeoff for coverage without $200+/month API costs.
- **No in-Slack slash command** yet — on-demand checks require calling `/runs` directly (via cron, Pond, or manually).

---

## Future upgradability

The source layer is **pluggable**: add a new platform by dropping a module into
`sources/` that implements a `get_new_*(is_seen_fn) -> list[dict]` function, then
registering it in `poller.py`'s `run_poll_cycle()`. The dedup layer, Slack
formatting, scheduler, and Pond server don't need any changes.

**Ideas for great first PRs:**

- **More social sources** — Reddit, Bluesky, Hacker News, Telegram. Copy `x_source.py` as a template.
- **In-Slack slash command** — `/check-yc` that calls `/runs` directly for on-demand checks.
- **CRM export** — auto-append alerts to a Google Sheet, Airtable, or Notion database.
- **Scoring / prioritisation** — rank alerts by industry fit or keyword relevance to your ICP.
- **Dedup TTL** — expire old `seen_items` rows so re-added companies re-alert after N days.

---

## Built by

**[Cyph33r](https://github.com/Cyph33r)** — building tools for GTM professionals who want to be first in a new YC company's inbox.
