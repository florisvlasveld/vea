import os
import time
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# === Configurable Constants ===
WORKDAYS_LOOKBACK = 2
API_CALL_DELAY_SECONDS = 1.0
CHANNEL_TYPES = ["public_channel", "private_channel", "im", "mpim"]

def calculate_lookback_start(now: datetime, workdays: int) -> datetime:
    logger.debug(f"Calculating lookback start time from now: {now.isoformat()}")
    workdays_remaining = workdays
    current = now
    while workdays_remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            workdays_remaining -= 1
    if now.weekday() in (0, 1):
        logger.debug("Today is Monday or Tuesday; including the weekend in lookback range.")
        while current.weekday() > 3:
            current -= timedelta(days=1)
    logger.info(f"Fetching messages from: {current.isoformat()} to {now.isoformat()}")
    return current

def safe_slack_call(client_func, **kwargs):
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
    # Replace user mentions
    text = re.sub(r"<@([A-Z0-9]+)>", lambda m: f"@{user_map.get(m.group(1), m.group(1))}", text)
    # Replace channel mentions
    text = re.sub(r"<#([A-Z0-9]+)\|([^>]+)>", r"#\2", text)
    # Replace user group mentions
    text = re.sub(r"<!subteam\^([A-Z0-9]+)\|@([^>]+)>", r"@\2", text)
    # Replace special mentions like <!here>
    text = re.sub(r"<!([^>]+)>", r"@\1", text)
    return text

def load_slack_messages(workdays_lookback: int = WORKDAYS_LOOKBACK) -> Dict[str, List[Dict[str, Any]]]:
    logger.info("Starting Slack message load (user token mode)...")
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        logger.warning("SLACK_TOKEN is not set.")
        return {}

    client = WebClient(token=token)
    now = datetime.now()
    oldest_dt = calculate_lookback_start(now, workdays_lookback)
    oldest_ts = oldest_dt.timestamp()
    latest_ts = now.timestamp()

    user_map: Dict[str, str] = {}
    results: Dict[str, List[Dict[str, Any]]] = {}

    logger.info("Fetching Slack user list...")
    try:
        for user in safe_slack_call(client.users_list)["members"]:
            user_map[user["id"]] = user.get("real_name", user.get("name", "unknown"))
        logger.debug(f"Fetched {len(user_map)} users.")
    except SlackApiError as e:
        logger.warning(f"Failed to fetch users: {e.response['error']}")

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
                channels = response.get("channels", [])
                logger.debug(f"Found {len(channels)} {conv_type} channels.")
            except SlackApiError as e:
                logger.warning(f"Failed to fetch {conv_type} channels: {e.response['error']}")
                break

            for channel in channels:
                is_member = channel.get("is_member", False)
                is_archived = channel.get("is_archived", False)

                if conv_type in ("public_channel", "private_channel"):
                    if not is_member or is_archived:
                        continue

                channel_id = channel["id"]
                latest_ts_str = channel.get("latest", {}).get("ts", None)
                latest_message_ts = float(latest_ts_str) if latest_ts_str else 0.0

                if conv_type == "im":
                    user_id = channel.get("user")
                    channel_name = f"DM with {user_map.get(user_id, user_id)}"
                elif conv_type == "mpim":
                    channel_name = f"Group DM {channel_id}"
                else:
                    channel_name = channel.get("name", channel_id)

                if latest_ts_str and latest_message_ts < oldest_ts:
                    logger.debug(f"Skipping {channel_name} — no recent activity.")
                    continue

                time.sleep(API_CALL_DELAY_SECONDS)
                logger.debug(f"Fetching messages from {channel_name} ({channel_id})")

                messages = []

                try:
                    history = safe_slack_call(
                        client.conversations_history,
                        channel=channel_id,
                        oldest=str(oldest_ts),
                        latest=str(latest_ts),
                        inclusive=True,
                        limit=100
                    )
                    raw_msgs = history.get("messages", [])
                    logger.debug(f"[{channel_name}] history returned {len(raw_msgs)} messages")

                    for msg in raw_msgs:
                        if msg.get("subtype"):
                            continue

                        ts = datetime.fromtimestamp(float(msg["ts"])).isoformat()
                        user_id = msg.get("user", "unknown")
                        user_name = user_map.get(user_id, user_id)
                        text = replace_slack_mentions(msg.get("text", "").strip(), user_map)

                        message_data = {
                            "user": user_name,
                            "timestamp": ts,
                            "text": text,
                        }

                        if "thread_ts" in msg and msg["thread_ts"] == msg["ts"]:
                            logger.debug(f"Fetching replies for thread in {channel_name} at {ts}")
                            time.sleep(API_CALL_DELAY_SECONDS)
                            try:
                                replies_response = safe_slack_call(
                                    client.conversations_replies,
                                    channel=channel_id,
                                    ts=msg["ts"],
                                    inclusive=True,
                                    limit=50
                                )
                                thread_messages = replies_response.get("messages", [])[1:]
                                replies = []
                                for reply in thread_messages:
                                    if reply.get("subtype"):
                                        continue
                                    reply_ts = datetime.fromtimestamp(float(reply["ts"])).isoformat()
                                    reply_user_id = reply.get("user", "unknown")
                                    reply_user = user_map.get(reply_user_id, reply_user_id)
                                    reply_text = replace_slack_mentions(reply.get("text", "").strip(), user_map)
                                    replies.append({
                                        "user": reply_user,
                                        "timestamp": reply_ts,
                                        "text": reply_text
                                    })
                                if replies:
                                    message_data["replies"] = replies
                            except SlackApiError as e:
                                logger.warning(f"Failed to fetch thread replies in {channel_name}: {e.response['error']}")

                        messages.append(message_data)

                except SlackApiError as e:
                    logger.warning(f"Failed to fetch messages from {channel_name}: {e.response['error']}")
                    continue

                if messages:
                    logger.info(f"Collected {len(messages)} messages from {channel_name}")
                    results[channel_name] = messages

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    logger.info(f"Finished loading Slack messages. Found messages in {len(results)} conversations.")
    return results