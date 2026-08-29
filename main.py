import logging
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
    main()
