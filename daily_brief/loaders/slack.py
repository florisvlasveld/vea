"""
Slack integration: fetch recent messages from channels the bot is in.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

DEFAULT_HOURS_LOOKBACK = 48


def load_slack_messages(hours_lookback: int = DEFAULT_HOURS_LOOKBACK) -> Dict[str, List[Dict[str, str]]]:
    """
    Load recent messages from Slack channels that the bot has access to.
    """
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        logger.warning("SLACK_TOKEN is not set.")
        return {}

    client = WebClient(token=token)
    latest_ts = datetime.now().timestamp()
    oldest_ts = (datetime.now() - timedelta(hours=hours_lookback)).timestamp()

    user_map: Dict[str, str] = {}
    results: Dict[str, List[Dict[str, str]]] = {}

    # Fetch all users for name resolution
    try:
        users = client.users_list()["members"]
        for user in users:
            user_map[user["id"]] = user.get("real_name", user.get("name", "unknown"))
    except SlackApiError as e:
        logger.warning(f"Failed to fetch Slack user list: {e.response['error']}")

    # Fetch list of channels
    try:
        channels = client.conversations_list(types="public_channel,private_channel")['channels']
    except SlackApiError as e:
        logger.warning(f"Failed to fetch Slack channel list: {e.response['error']}")
        return {}

    for channel in channels:
        channel_id = channel["id"]
        channel_name = channel.get("name", channel_id)

        try:
            response = client.conversations_history(
                channel=channel_id,
                oldest=str(oldest_ts),
                latest=str(latest_ts),
                inclusive=True,
                limit=100
            )
            messages = []
            for msg in response["messages"]:
                ts = datetime.fromtimestamp(float(msg["ts"])).isoformat()
                user_id = msg.get("user", "unknown")
                user_name = user_map.get(user_id, user_id)
                text = msg.get("text", "").strip()
                messages.append({
                    "user": user_name,
                    "timestamp": ts,
                    "text": text
                })
            results[channel_name] = messages
        except SlackApiError as e:
            logger.warning(f"Failed to fetch messages from Slack channel '{channel_name}': {e.response['error']}")

    return results
