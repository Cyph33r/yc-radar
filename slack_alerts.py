"""
Posts formatted alerts to Slack via the Bolt SDK's WebClient.
Every alert follows the two shapes from the task's Example Deliverables.
"""
from slack_bolt import App

from config import config

app = App(token=config.SLACK_BOT_TOKEN)
client = app.client


def post_confirmed_alert(item: dict) -> None:
    """item keys: company_name, batch, source, description, link, detected_at"""
    text = (
        f"*NEW YC COMPANY*\n"
        f"*Company:* {item['company_name']}\n"
        f"*Batch:* {item.get('batch', 'n/a')}\n"
        f"*Source:* {item['source']}\n"
        f"*Status:* Confirmed by YC\n"
        f"*Description:* {item.get('description', 'n/a')}\n"
        f"*YC Profile:* {item['link']}\n"
        f"*Detected:* {item['detected_at']}"
    )
    client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, text=text)


def post_early_signal_alert(item: dict) -> None:
    """item keys: company_name, founder_name, founder_handle, batch, source,
    post_text, post_link, company_link, detected_at"""
    text = (
        f"*EARLY YC SIGNAL — Founder Announced Before YC*\n"
        f"*Company:* {item['company_name']}\n"
        f"*Founder:* {item.get('founder_name', 'n/a')} "
        f"({item.get('founder_handle', 'n/a')})\n"
        f"*Batch:* {item.get('batch', 'n/a')}\n"
        f"*Source:* {item['source']}\n"
        f"*Status:* Founder announced / not yet officially announced by YC\n"
        f"*Original post:* {item.get('post_text', 'n/a')}\n"
        f"*Original post link:* {item['post_link']}\n"
        f"*Company:* {item.get('company_link', 'n/a')}\n"
        f"*Detected:* {item['detected_at']}"
    )
    client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, text=text)
