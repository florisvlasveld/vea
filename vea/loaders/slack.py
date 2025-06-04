import os
import time
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# === Logging Setup ===
logger = logging.getLogger(__name__)

# === Configurable Constants ===
WORKDAYS_LOOKBACK = 5
CHANNEL_TYPES = ["public_channel", "private_channel", "im", "mpim"]


def calculate_lookback_start(now: datetime, workdays: int) -> datetime:
    current = now
    workdays_remaining = workdays
    while workdays_remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            workdays_remaining -= 1
    if now.weekday() in (0, 1):
        while current.weekday() > 4:
            current -= timedelta(days=1)
    logger.info(f"Fetching messages from: {current.isoformat()} to {now.isoformat()}")
    return current


def safe_slack_call(client_func, max_retries: int = 5, **kwargs):
    retries = 0
    while True:
        try:
            return client_func(**kwargs)
        except SlackApiError as e:
            if e.response["error"] == "ratelimited" and retries < max_retries:
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(
                    "Rate limited. Retrying after %s seconds...", retry_after
                )
                time.sleep(retry_after)
                retries += 1
            else:
                raise


def replace_slack_mentions(text: str, user_map: Dict[str, str]) -> str:
    text = re.sub(r"<@([A-Z0-9]+)>", lambda m: f"@{user_map.get(m.group(1), m.group(1))}", text)
    text = re.sub(r"<#([A-Z0-9]+)\|([^>]+)>", r"#\2", text)
    text = re.sub(r"<!subteam\^([A-Z0-9]+)\|@([^>]+)>", r"@\2", text)
    text = re.sub(r"<!([^>]+)>", r"@\1", text)
    return text


def build_user_map(client: WebClient) -> Dict[str, str]:
    logger.info("Fetching Slack user list...")
    user_map = {}
    try:
        users = safe_slack_call(client.users_list)["members"]
        for user in users:
            user_map[user["id"]] = user.get("real_name", user.get("name", "unknown"))
    except SlackApiError as e:
        logger.warning(f"Failed to fetch users: {e.response['error']}")
    return user_map


def get_channel_name(channel: Dict[str, Any], conv_type: str, user_map: Dict[str, str]) -> str:
    if conv_type == "im":
        user_id = channel.get("user")
        return f"DM with {user_map.get(user_id, user_id)}"
    elif conv_type == "mpim":
        return f"Group DM {channel['id']}"
    else:
        return channel.get("name", channel["id"])


def fetch_thread_replies(client: WebClient, channel_id: str, thread_ts: str, user_map: Dict[str, str]) -> List[Dict[str, Any]]:
    replies = []
    try:
        thread_data = safe_slack_call(
            client.conversations_replies,
            channel=channel_id,
            ts=thread_ts,
            inclusive=True,
            limit=50
        ).get("messages", [])[1:]
        for reply in thread_data:
            if reply.get("subtype"):
                continue
            replies.append({
                "user": user_map.get(reply.get("user", "unknown"), reply.get("user", "unknown")),
                "timestamp": datetime.fromtimestamp(float(reply["ts"])).isoformat(),
                "text": replace_slack_mentions(reply.get("text", "").strip(), user_map)
            })
    except SlackApiError as e:
        logger.warning(f"Failed to fetch thread replies: {e.response['error']}")
    return replies


def fetch_messages_from_channel(client: WebClient, channel: Dict[str, Any], conv_type: str,
                                oldest_ts: float, latest_ts: float, user_map: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
    channel_id = channel["id"]
    channel_name = get_channel_name(channel, conv_type, user_map)
    try:
        history = safe_slack_call(
            client.conversations_history,
            channel=channel_id,
            oldest=str(oldest_ts),
            latest=str(latest_ts),
            inclusive=True,
            limit=100
        )
    except SlackApiError as e:
        logger.warning(f"Failed to fetch messages from {channel_name}: {e.response['error']}")
        return None

    messages = []
    for msg in history.get("messages", []):
        if msg.get("subtype"):
            continue

        msg_data = {
            "user": user_map.get(msg.get("user", "unknown"), msg.get("user", "unknown")),
            "timestamp": datetime.fromtimestamp(float(msg["ts"])).isoformat(),
            "text": replace_slack_mentions(msg.get("text", "").strip(), user_map),
        }

        if msg.get("thread_ts") == msg.get("ts") and msg.get("reply_count", 0) > 0:
            msg_data["replies"] = fetch_thread_replies(client, channel_id, msg["ts"], user_map)

        messages.append(msg_data)

    return messages if messages else None


def load_slack_messages(workdays_lookback: int = WORKDAYS_LOOKBACK) -> Dict[str, List[Dict[str, Any]]]:
    logger.info("Starting Slack message load...")
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        logger.warning("SLACK_TOKEN is not set.")
        return {}

    client = WebClient(token=token)
    now = datetime.now()
    oldest_ts = calculate_lookback_start(now, workdays_lookback).timestamp()
    latest_ts = now.timestamp()
    user_map = build_user_map(client)
    results = {}

    for conv_type in CHANNEL_TYPES:
        logger.info(f"Fetching conversations of type: {conv_type}")
        cursor = None

        while True:
            try:
                response = safe_slack_call(
                    client.conversations_list,
                    types=conv_type,
                    limit=200,
                    cursor=cursor,
                    exclude_archived=True
                )
            except SlackApiError as e:
                logger.warning(f"Failed to fetch {conv_type} channels: {e.response['error']}")
                break

            for channel in response.get("channels", []):
                if conv_type in ("public_channel", "private_channel"):
                    if not channel.get("is_member", False) or channel.get("is_archived", False):
                        continue
                latest_ts_str = channel.get("latest", {}).get("ts")
                if latest_ts_str and float(latest_ts_str) < oldest_ts:
                    continue
                channel_name = get_channel_name(channel, conv_type, user_map)
                messages = fetch_messages_from_channel(client, channel, conv_type, oldest_ts, latest_ts, user_map)
                if messages:
                    logger.info(f"Collected {len(messages)} messages from {channel_name}")
                    results[channel_name] = messages

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    logger.info(f"Finished loading Slack messages. Found messages in {len(results)} conversations.")
    return results
