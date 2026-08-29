import logging
import re
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from config import config
from db import init_db
from poller import run_poll_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("yc-launch-monitor")

app = FastAPI(title="YC Radar Agent")

AGENT_VERSION = "2026.08.29"
PROTOCOL_VERSION = "1.0"

# run_id -> task record. Keyed by run_id itself (not a separately generated
# ID), so a duplicate /runs call with the same Idempotency-Key naturally
# returns the same task instead of starting a second poll cycle.
_tasks: dict = {}
_tasks_lock = threading.Lock()


def _error(code: str, message: str, status: int):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _check_protocol_version(v):
    if not v:
        return _error("invalid_request", "Missing X-Agent-Protocol-Version header.", 400)
    if not re.fullmatch(r"\d+\.\d+", v):
        return _error("invalid_request", "X-Agent-Protocol-Version must be Major.Minor, e.g. 1.0.", 400)
    if v != PROTOCOL_VERSION:
        return _error("unsupported_protocol_version", f"Unsupported protocol version {v}.", 400)
    return None


def _check_auth(authorization):
    if not config.POND_ACCESS_KEY:
        return None  # not configured yet — allow through for local testing
    if authorization != f"Bearer {config.POND_ACCESS_KEY}":
        return _error("unauthorized", "Missing or invalid Access Key.", 401)
    return None


@app.get("/manifest")
def manifest():
    return {
        "protocol": "marketplace-agent",
        "protocol_version": PROTOCOL_VERSION,
        "agent_version": AGENT_VERSION,
        "metadata": {
            "name": "YC Radar",
            "short_description": "Catches new YC and Speedrun company launches — including founder self-announcements before YC's official post — and pushes real-time alerts to Slack.",
            "description": "<p>Monitors the YC Directory, YC Speedrun, X, and LinkedIn for new company launches, including founder self-announcements before YC's own post, and posts real-time alerts to a Slack channel.</p>",
            "category": "sales",
            "github_url": "https://github.com/Cyph33r/yc-radar",
        },
        "capabilities": {
            "sync": False,
            "streaming": False,
            "async_tasks": True,
            "cancellation": False,
            "attachments": False,
            "feedback": False,
        },
        "input_modes": ["text/plain"],
        "output_modes": ["text/markdown"],
        "limits": {
            "max_request_bytes": 1048576,
            "max_attachment_bytes": 1048576,
            "max_run_seconds": 300,
        },
    }


def _execute_run(run_id: str):
    with _tasks_lock:
        _tasks[run_id]["status"] = "running"
        _tasks[run_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = run_poll_cycle()
        alert_count = result["alert_count"]
        if alert_count:
            lines = "\n".join(f"- **{a['company']}** via {a['source']}" for a in result["alerts_sent"])
            text = f"Poll cycle complete — {alert_count} new alert(s) sent to Slack:\n\n{lines}"
        else:
            text = "Poll cycle complete — no new YC/Speedrun signals detected this cycle."
        with _tasks_lock:
            _tasks[run_id].update(
                status="completed",
                output=[{"type": "text", "text": text}],
                usage={"unit_of_measurement": "result", "quantity": alert_count},
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
    except Exception:
        log.exception("Run failed")
        with _tasks_lock:
            _tasks[run_id].update(
                status="failed",
                error={"code": "internal_error", "message": "The poll cycle failed unexpectedly."},
                usage={"unit_of_measurement": "result", "quantity": 0},
                updated_at=datetime.now(timezone.utc).isoformat(),
            )


@app.post("/runs", status_code=202)
async def create_run(
    request: Request,
    authorization: str = Header(default=None),
    x_agent_protocol_version: str = Header(default=None, alias="X-Agent-Protocol-Version"),
):
    version_error = _check_protocol_version(x_agent_protocol_version)
    if version_error:
        return version_error
    auth_error = _check_auth(authorization)
    if auth_error:
        return auth_error

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return _error("unsupported_content_type", "Content-Type must be application/json.", 415)

    try:
        body = await request.json()
    except Exception:
        return _error("invalid_request", "Malformed JSON body.", 400)

    run_id = body.get("run_id")
    if not run_id:
        return _error("invalid_request", "run_id is required.", 400)

    with _tasks_lock:
        existing = _tasks.get(run_id)
        if existing:
            return JSONResponse(
                status_code=202,
                content={"run_id": run_id, "task_id": run_id, "status": existing["status"], "poll_after_ms": 2000},
            )
        _tasks[run_id] = {"status": "queued", "created_at": datetime.now(timezone.utc).isoformat()}

    threading.Thread(target=_execute_run, args=(run_id,), daemon=True).start()

    return JSONResponse(
        status_code=202,
        content={"run_id": run_id, "task_id": run_id, "status": "queued", "poll_after_ms": 2000},
    )


@app.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    authorization: str = Header(default=None),
    x_agent_protocol_version: str = Header(default=None, alias="X-Agent-Protocol-Version"),
):
    version_error = _check_protocol_version(x_agent_protocol_version)
    if version_error:
        return version_error
    auth_error = _check_auth(authorization)
    if auth_error:
        return auth_error

    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        return _error("task_not_found", "Unknown task_id.", 404)

    response = {"run_id": task_id, "task_id": task_id, "status": task["status"]}
    if task["status"] == "completed":
        response.update(output=task["output"], usage=task["usage"], updated_at=task["updated_at"])
    elif task["status"] == "failed":
        response.update(error=task["error"], usage=task["usage"], updated_at=task["updated_at"])
    elif task["status"] == "running":
        response["updated_at"] = task.get("updated_at", task["created_at"])
    return response


@app.on_event("startup")
def _startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_poll_cycle, "interval", hours=config.POLL_INTERVAL_HOURS)
    scheduler.start()
    log.info("Background scheduler started")
