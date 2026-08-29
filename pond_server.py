import logging
import threading
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException

from config import config
from db import init_db
from poller import run_poll_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("yc-launch-monitor")

app = FastAPI(title="YC Launch Monitor Agent")

_tasks: dict = {}
_tasks_lock = threading.Lock()
_cumulative_usage = {"total_alerts_sent": 0, "total_runs": 0}


def _check_access_key(authorization):
    if not config.POND_ACCESS_KEY:
        return  # not generated yet — allow through for local testing
    if authorization != f"Bearer {config.POND_ACCESS_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing Access Key")


@app.get("/manifest")
def manifest():
    return {
        "name": "YC Launch Monitor",
        "description": "Monitors YC Directory, YC Speedrun, X, and LinkedIn for new launches and early founder signals, posting real-time Slack alerts.",
        "actions": [{
            "name": "poll",
            "description": "Runs one poll cycle across all four sources and posts new alerts to Slack.",
            "inputs": {},
            "outputs": {
                "alerts_sent": "list of {source, company} for every alert posted",
                "alert_count": "integer count of alerts posted this cycle",
            },
        }],
    }


def _execute_run(task_id: str):
    with _tasks_lock:
        _tasks[task_id]["status"] = "running"
    try:
        result = run_poll_cycle()
        with _tasks_lock:
            _cumulative_usage["total_alerts_sent"] += result["alert_count"]
            _cumulative_usage["total_runs"] += 1
            _tasks[task_id].update(
                status="completed", result=result,
                cumulative_usage=dict(_cumulative_usage),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
    except Exception as e:
        log.exception("Run failed")
        with _tasks_lock:
            _tasks[task_id].update(status="failed", error=str(e))


@app.post("/runs", status_code=202)
def create_run(authorization: str = Header(default=None)):
    _check_access_key(authorization)
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {"status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}
    threading.Thread(target=_execute_run, args=(task_id,), daemon=True).start()
    return {"task_id": task_id, "status": "pending"}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, authorization: str = Header(default=None)):
    _check_access_key(authorization)
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return {"task_id": task_id, **task}


@app.on_event("startup")
def _startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_poll_cycle, "interval", hours=config.POLL_INTERVAL_HOURS)
    scheduler.start()
    log.info(f"Background scheduler started — every {config.POLL_INTERVAL_HOURS}h")
