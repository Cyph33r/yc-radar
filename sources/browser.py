"""
Browser automation utility for Playwright scrapers.
Provides resilient browser launching with automatic on-demand installation fallback
if the browser binary is missing in the runtime environment (common on PaaS like Render).
"""
import logging
import os
import subprocess
import sys
from playwright.sync_api import Browser, Playwright

log = logging.getLogger("yc-launch-monitor")


def launch_browser(p: Playwright, headless: bool = True) -> Browser:
    """
    Launches Chromium with resilient fallback: if the browser binary is missing
    in the runtime container (e.g. Render's ephemeral build cache), it automatically
    runs 'playwright install chromium' and retries.
    """
    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    try:
        return p.chromium.launch(headless=headless, args=launch_args)
    except Exception as e:
        err_msg = str(e)
        if "Executable doesn't exist" in err_msg or "playwright install" in err_msg:
            log.warning(
                "Playwright Chromium binary not found at runtime. "
                "Executing 'playwright install chromium' to download..."
            )
            res = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                log.error(f"Playwright auto-installation failed: {res.stderr}")
                raise
            log.info("Playwright Chromium installed successfully. Launching browser...")
            return p.chromium.launch(headless=headless, args=launch_args)
        raise
