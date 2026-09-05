import logging
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from config import config
from db import init_db
from poller import run_poll_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("yc-launch-monitor")

def main():
    init_db()
    run_poll_cycle()
    scheduler = BlockingScheduler()
    scheduler.add_job(run_poll_cycle, "interval", hours=config.POLL_INTERVAL_HOURS)
    log.info(f"Scheduler started — every {config.POLL_INTERVAL_HOURS}h. Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down")

if __name__ == "__main__":
    if "PORT" in os.environ:
        import uvicorn
        port = int(os.environ["PORT"])
        log.info(f"PORT={port} detected (Render web service environment). Starting pond_server on 0.0.0.0:{port}...")
        uvicorn.run("pond_server:app", host="0.0.0.0", port=port)
    else:
        main()

