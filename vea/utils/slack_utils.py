import os
import logging
from typing import Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


def send_slack_dm(message: str, *, token: Optional[str] = None) -> None:
    """Send a direct message to the authenticated user."""
    token = token or os.environ.get("SLACK_TOKEN")
    if not token:
        logger.warning("SLACK_TOKEN not set; cannot send Slack DM")
        return

    client = WebClient(token=token)
    try:
        user_id = client.auth_test()["user_id"]
        channel_id = client.conversations_open(users=user_id)["channel"]["id"]
        client.chat_postMessage(
            channel=channel_id,
            text=message,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": message}}],
        )
        logger.info("Sent Slack DM to user")
    except SlackApiError as e:
        logger.warning(f"Failed to send Slack DM: {e.response['error']}")
