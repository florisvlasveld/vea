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
# logging.basicConfig(level=logging.INFO)

# === Configurable Constants ===
WORKDAYS_LOOKBACK = 2  # Number of past workdays to include in message search
API_CALL_DELAY_SECONDS = 1.0  # Delay between Slack API calls to prevent rate limiting
CHANNEL_TYPES = ["public_channel", "private_channel", "im", "mpim"]  # Types of conversations to fetch


def calculate_lookback_start(now: datetime, workdays: int) -> datetime:
    """
    Calculate the datetime that marks the beginning of the lookback period.

    This function subtracts the specified number of workdays (Mon–Fri) from the current time.
    If today is Monday or Tuesday, it also includes the weekend in the lookback period.

    Args:
        now: Current datetime.
        workdays: Number of workdays to look back.

    Returns:
        The datetime representing the start of the lookback window.
    """
    current = now
    workdays_remaining = workdays

    while workdays_remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            workdays_remaining -= 1

    if now.weekday() in (0, 1):  # Monday or Tuesday
        while current.weekday() > 4:  # Include Sat/Sun if necessary
            current -= timedelta(days=1)

    logger.info(f"Fetching messages from: {current.isoformat()} to {now.isoformat()}")
    return current


def safe_slack_call(client_func, **kwargs):
    """
    Call a Slack API function and handle rate limiting by retrying after delay.

    Args:
        client_func: A Slack client method to call.
        **kwargs: Arguments passed to the Slack client method.

    Returns:
        The API response object.
    """
    while True:
        try:
            return client_func(**kwargs)
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                raise


def replace_slack_mentions(text: str, user_map: Dict[str, str]) -> str:
    """
    Convert Slack internal mention formats to readable ones.

    Replaces:
    - User mentions (e.g. <@U12345>)
    - Channel mentions (e.g. <#C12345|channel>)
    - User group mentions (e.g. <!subteam^T123|@team>)
    - Special mentions (e.g. <!here>)

    Args:
        text: The message text containing Slack mentions.
        user_map: Mapping of user IDs to real names.

    Returns:
        A cleaned and human-readable version of the message text.
    """
    text = re.sub(r"<@([A-Z0-9]+)>", lambda m: f"@{user_map.get(m.group(1), m.group(1))}", text)
    text = re.sub(r"<#([A-Z0-9]+)\|([^>]+)>", r"#\2", text)
    text = re.sub(r"<!subteam\^([A-Z0-9]+)\|@([^>]+)>", r"@\2", text)
    text = re.sub(r"<!([^>]+)>", r"@\1", text)
    return text


def build_user_map(client: WebClient) -> Dict[str, str]:
    """
    Build a mapping from Slack user IDs to user names.

    Args:
        client: An authenticated Slack WebClient.

    Returns:
        A dictionary mapping user IDs to real names (or usernames).
    """
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
    """
    Generate a human-readable name for the given Slack channel or DM.

    Args:
        channel: Slack channel or conversation metadata.
        conv_type: Type of the conversation.
        user_map: Mapping of user IDs to names.

    Returns:
        A string representing the channel name.
    """
    if conv_type == "im":
        user_id = channel.get("user")
        return f"DM with {user_map.get(user_id, user_id)}"
    elif conv_type == "mpim":
        return f"Group DM {channel['id']}"
    else:
        return channel.get("name", channel["id"])


def fetch_thread_replies(client: WebClient, channel_id: str, thread_ts: str, user_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Fetch replies to a thread in a Slack conversation.

    Args:
        client: Authenticated Slack WebClient.
        channel_id: ID of the Slack channel.
        thread_ts: Timestamp of the root message.
        user_map: Mapping of user IDs to user names.

    Returns:
        A list of reply messages in dictionary format.
    """
    replies = []
    try:
        thread_data = safe_slack_call(
            client.conversations_replies,
            channel=channel_id,
            ts=thread_ts,
            inclusive=True,
            limit=50
        ).get("messages", [])[1:]  # Skip the root message

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


def fetch_messages_from_channel(
    client: WebClient,
    channel: Dict[str, Any],
    conv_type: str,
    oldest_ts: float,
    latest_ts: float,
    user_map: Dict[str, str]
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch messages from a specific Slack channel.

    Args:
        client: Authenticated Slack WebClient.
        channel: Metadata for the Slack channel.
        conv_type: Type of conversation (e.g. public_channel, im).
        oldest_ts: Oldest timestamp to include.
        latest_ts: Latest timestamp to include.
        user_map: Mapping of user IDs to names.

    Returns:
        A list of messages (including thread replies), or None if no valid messages are found.
    """
    if conv_type in ("public_channel", "private_channel"):
        if not channel.get("is_member", False) or channel.get("is_archived", False):
            return None

    latest_ts_str = channel.get("latest", {}).get("ts")
    if latest_ts_str and float(latest_ts_str) < oldest_ts:
        return None

    channel_id = channel["id"]
    channel_name = get_channel_name(channel, conv_type, user_map)

    logger.debug(f"Fetching messages from {channel_name} ({channel_id})")
    time.sleep(API_CALL_DELAY_SECONDS)

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

        if msg.get("thread_ts") == msg.get("ts"):
            time.sleep(API_CALL_DELAY_SECONDS)
            msg_data["replies"] = fetch_thread_replies(client, channel_id, msg["ts"], user_map)

        messages.append(msg_data)

    return messages if messages else None


def load_slack_messages(workdays_lookback: int = WORKDAYS_LOOKBACK) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load recent messages from Slack based on conversation types and workday lookback.

    Uses a user token from the SLACK_TOKEN environment variable. Gathers messages
    across various conversation types and includes threads, filtering out archived channels
    and non-member channels where appropriate.

    Args:
        workdays_lookback: How many previous workdays to include.

    Returns:
        A dictionary mapping channel names to lists of messages.
    """
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
                channel_name = get_channel_name(channel, conv_type, user_map)
                messages = fetch_messages_from_channel(
                    client, channel, conv_type, oldest_ts, latest_ts, user_map
                )
                if messages:
                    logger.info(f"Collected {len(messages)} messages from {channel_name}")
                    results[channel_name] = messages

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    logger.info(f"Finished loading Slack messages. Found messages in {len(results)} conversations.")
    return results