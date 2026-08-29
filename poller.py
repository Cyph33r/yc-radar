import logging
import traceback
from datetime import datetime, timezone

from db import is_seen, mark_seen
import pond_agent
from slack_alerts import post_confirmed_alert, post_early_signal_alert
from sources import yc_directory, yc_speedrun, x_source, linkedin_source

log = logging.getLogger("yc-launch-monitor")


def run_poll_cycle() -> dict:
    log.info("Starting poll cycle")
    alerts_sent = []

    for get_new, label in (
        (yc_directory.get_new_companies, "YC Directory"),
        (yc_speedrun.get_new_companies, "YC Speedrun"),
    ):
        try:
            for item in get_new(is_seen):
                post_confirmed_alert(item)
                mark_seen(item["item_id"], item["source"], item["company_name"])
                alerts_sent.append({"source": item["source"], "company": item["company_name"]})
                log.info(f"Alerted: {item['source']} / {item['company_name']}")
        except Exception:
            log.error(f"{label} poll failed:\n{traceback.format_exc()}")

    for get_new, label in (
        (x_source.get_new_signals, "X"),
        (linkedin_source.get_new_signals, "LinkedIn"),
    ):
        try:
            for item in get_new(is_seen):
                post_early_signal_alert(item)
                mark_seen(item["item_id"], item["source"], item["company_name"])
                alerts_sent.append({"source": item["source"], "company": item["company_name"]})
                log.info(f"Alerted: {item['source']} / {item['company_name']}")
        except Exception:
            log.error(f"{label} poll failed:\n{traceback.format_exc()}")

    pond_agent.send_heartbeat(status="ok", detail="poll cycle complete")
    log.info("Poll cycle complete")
    return {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "alerts_sent": alerts_sent,
        "alert_count": len(alerts_sent),
    }
