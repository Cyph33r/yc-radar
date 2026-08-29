"""
Entry point. Runs continuously, polling all four sources every
POLL_INTERVAL_HOURS and pushing Slack alerts for anything new.

Run with:  python main.py
Runs forever until stopped — use a process manager (systemd, pm2,
Docker restart policy, etc.) for real persistence. See README.md.
"""
import logging
import time
import traceback

from apscheduler.schedulers.blocking import BlockingScheduler

from config import config
from db import init_db, is_seen, mark_seen
import pond_agent
from slack_alerts import post_confirmed_alert, post_early_signal_alert
from sources import yc_directory, yc_speedrun, x_source, linkedin_source

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("yc-launch-monitor")


def run_poll_cycle() -> None:
    log.info("Starting poll cycle")

    # --- Confirmed YC / Speedrun companies ---
    for get_new, label in (
        (yc_directory.get_new_companies, "YC Directory"),
        (yc_speedrun.get_new_companies, "YC Speedrun"),
    ):
        try:
            for item in get_new(is_seen):
                post_confirmed_alert(item)
                mark_seen(item["item_id"], item["source"], item["company_name"])
                log.info(f"Alerted: {item['source']} / {item['company_name']}")
        except Exception:
            log.error(f"{label} poll failed:\n{traceback.format_exc()}")

    # --- Early signals from X and LinkedIn ---
    for get_new, label in (
        (x_source.get_new_signals, "X"),
        (linkedin_source.get_new_signals, "LinkedIn"),
    ):
        try:
            for item in get_new(is_seen):
                post_early_signal_alert(item)
                mark_seen(item["item_id"], item["source"], item["company_name"])
                log.info(f"Alerted: {item['source']} / {item['company_name']}")
        except Exception:
            log.error(f"{label} poll failed:\n{traceback.format_exc()}")

    pond_agent.send_heartbeat(status="ok", detail="poll cycle complete")
    log.info("Poll cycle complete")


def main() -> None:
    init_db()
    run_poll_cycle()  # run once immediately on startup

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_poll_cycle,
        "interval",
        hours=config.POLL_INTERVAL_HOURS,
        next_run_time=None,  # already ran once above
    )
    log.info(
        f"Scheduler started — polling every {config.POLL_INTERVAL_HOURS}h. Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down")


if __name__ == "__main__":
    main()
