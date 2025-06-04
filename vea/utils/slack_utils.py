import os
import logging
import re
from typing import Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


def markdown_to_mrkdwn(text: str) -> str:
    """Convert a subset of Markdown to Slack's mrkdwn format."""
    lines = text.splitlines()
    converted: list[str] = []

    bullet_pattern = re.compile(r"^(\s*)-\s+")
    ordered_pattern = re.compile(r"^(\s*)(\d+)\.\s+")

    for line in lines:
        m_bullet = bullet_pattern.match(line)
        if m_bullet:
            indent = m_bullet.group(1)
            content = line[m_bullet.end():].lstrip()
            converted.append(f"{indent}• {content}")
            continue

        m = ordered_pattern.match(line)
        if m:
            indent, number = m.groups()
            rest = line[m.end():].lstrip()
            converted.append(f"{indent}{number}. {rest}")
            continue

        converted.append(line)

    return "\n".join(converted)


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
        mrkdwn_message = markdown_to_mrkdwn(message)
        client.chat_postMessage(
            channel=channel_id,
            text=mrkdwn_message,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": mrkdwn_message}}],
        )
        logger.info("Sent Slack DM to user")
    except SlackApiError as e:
        logger.warning(f"Failed to send Slack DM: {e.response['error']}")
