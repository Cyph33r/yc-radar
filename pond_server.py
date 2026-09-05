import logging
import re
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import config
from db import init_db
from poller import run_poll_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("yc-launch-monitor")

app = FastAPI(title="YC Radar Agent")

_tasks: dict = {}
_tasks_lock = threading.Lock()


# === Core Pond Protocol: public manifest ===

@app.get("/manifest")
def manifest():
    return {
        "protocol": "marketplace-agent",
        "protocol_version": "1.0",
        "agent_version": "2026.09.05",
        "metadata": {
            "name": "YC Radar",
            "short_description": "Catches new YC and Speedrun company launches — including founder self-announcements before YC's official post — and pushes real-time alerts to Slack.",
            "description": "<p>Monitors the YC Directory, YC Speedrun, X, and LinkedIn for new company launches, including founder self-announcements before YC's own post, and posts real-time alerts to a Slack channel.</p>",
            "category": "sales",
            "key_features": "<ul><li>YC Directory monitoring</li><li>YC Speedrun tracking</li><li>X (Twitter) social signal detection</li><li>LinkedIn post monitoring</li><li>Real-time Slack alerts</li></ul>",
            "use_cases": "<p>Stay ahead of the curve by detecting new YC and Speedrun company launches before they're officially announced. Ideal for investors, recruiters, and founders tracking the YC ecosystem.</p>",
            "github_url": "https://github.com/Cyph33r/yc-radar",
        },
        "actions": [
            {
                "id": "run_poll_cycle",
                "name": "Run Poll Cycle",
                "description": "Use when the user wants to trigger a poll cycle to check for new YC and Speedrun company launches across all monitored sources (YC Directory, YC Speedrun, X, LinkedIn) and send Slack alerts for any new findings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "An optional instruction or note for the poll cycle.",
                            "minLength": 1,
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ],
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
            "max_request_bytes": 1_048_576,
            "max_attachment_bytes": 1_048_576,
            "max_run_seconds": 300,
        },
    }


# === Core Pond Protocol: run request model ===

class RunRequest(BaseModel):
    run_id: str
    agent_id: str
    conversation_id: str
    history_truncated: bool
    action_id: str | None = None
    user: dict
    messages: list[dict]
    parameters: dict
    execution: dict


# === Supporting function: runtime authentication ===

def authenticate_pond(
    authorization: str | None = Header(default=None),
    pond_version: str | None = Header(default=None, alias="X-Agent-Protocol-Version"),
):
    if authorization != f"Bearer {config.POND_ACCESS_KEY}":
        fail(401, "unauthorized", "The Access Key is missing or invalid.")
    if pond_version is None or re.fullmatch(r"\d+\.\d+", pond_version) is None:
        fail(400, "invalid_request", "The protocol version must be Major.Minor.")
    if pond_version != "1.0":
        fail(400, "unsupported_protocol_version", f"Protocol version {pond_version} is not supported.")


# === Supporting functions: Pond error responses ===

def fail(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def pond_error(_request: Request, error: HTTPException):
    return JSONResponse(status_code=error.status_code, content={"error": error.detail})


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, _error: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": "The request does not match Pond Protocol V1."}},
    )


# === Agent logic: async task execution ===

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


# === Core Pond Protocol: run endpoint ===

@app.post("/runs", status_code=202, dependencies=[Depends(authenticate_pond)])
async def create_run(run: RunRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if idempotency_key != run.run_id:
        fail(400, "invalid_request", "Idempotency-Key must match run_id.")

    # Validate action_id — manifest declares actions, so action_id is required
    if run.action_id != "run_poll_cycle":
        fail(400, "unsupported_operation", "The action is not supported.")

    # Idempotency: return existing task if already created
    with _tasks_lock:
        existing = _tasks.get(run.run_id)
        if existing:
            return JSONResponse(
                status_code=202,
                content={"run_id": run.run_id, "task_id": run.run_id, "status": existing["status"], "poll_after_ms": 2000},
            )
        now = datetime.now(timezone.utc).isoformat()
        _tasks[run.run_id] = {"status": "queued", "created_at": now, "updated_at": now}

    threading.Thread(target=_execute_run, args=(run.run_id,), daemon=True).start()

    return JSONResponse(
        status_code=202,
        content={"run_id": run.run_id, "task_id": run.run_id, "status": "queued", "poll_after_ms": 2000},
    )


# === Core Pond Protocol: task polling endpoint ===

@app.get("/tasks/{task_id}", dependencies=[Depends(authenticate_pond)])
def get_task(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        fail(404, "task_not_found", "Unknown task_id.")

    response = {"run_id": task_id, "task_id": task_id, "status": task["status"], "updated_at": task.get("updated_at", task.get("created_at"))}
    if task["status"] == "completed":
        response["output"] = task["output"]
        response["usage"] = task["usage"]
    elif task["status"] == "failed":
        response["error"] = task["error"]
        response["usage"] = task["usage"]
    return response


# === Application startup ===

@app.on_event("startup")
def _startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_poll_cycle, "interval", hours=config.POLL_INTERVAL_HOURS)
    scheduler.start()
    log.info("Background scheduler started")
