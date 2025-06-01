import base64
import quopri
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

MAX_INBOX = 25
TOKEN_PATH = Path(".credentials/gmail_token.json")
SNIPPET_SIZE = 500
MAX_BODY_LENGTH = 2000


def load_emails(target_date: datetime.date, token_unused: Optional[str] = None, gmail_labels: Optional[List[str]] = None) -> Dict[str, List[Dict[str, str]]]:
    """
    Load email snippets from Gmail. Returns a dict with 'inbox', 'sent', and any extra labels as keys.
    """
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    service = build("gmail", "v1", credentials=creds)

    seen_ids = set()

    def unique_snippets(msgs):
        snippets = []
        for m in msgs:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                snippets.append(_extract_snippet(service, m))
        return snippets

    inbox_msgs = _list_messages(service, "me", "in:inbox", MAX_INBOX)
    sent_since = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
    sent_msgs = _list_messages(service, "me", f"in:sent after:{sent_since}", MAX_INBOX)

    result = {
        "inbox": unique_snippets(inbox_msgs),
        "sent": unique_snippets(sent_msgs),
    }

    if gmail_labels:
        for label in gmail_labels:
            label_msgs = _list_messages(service, "me", f"label:{label}", MAX_INBOX)
            result[label] = unique_snippets(label_msgs)

    return result


def _list_messages(service, user_id, query, max_results):
    try:
        response = service.users().messages().list(userId=user_id, q=query, maxResults=max_results).execute()
        return response.get("messages", [])
    except Exception as e:
        logger.warning(f"Failed to list messages for query '{query}': {e}")
        return []


def _decode_base64(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8", errors="replace")


def _clean_text(text: str) -> str:
    text = re.sub(r'[\u200c\u200b\u200d\xa0]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_plain_text(payload) -> str:
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        raw = _decode_base64(payload["body"]["data"])
        return _truncate(_clean_text(raw))

    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return _truncate(_clean_text(text))
    return ""


def _truncate(text: str) -> str:
    if len(text) > MAX_BODY_LENGTH:
        return text[:MAX_BODY_LENGTH] + "..."
    return text


def _extract_snippet(service, msg):
    msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
    headers = msg_data.get("payload", {}).get("headers", [])

    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No subject)")
    sender = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown sender)")
    date = next((h["value"] for h in headers if h["name"] == "Date"), "(Unknown date)")

    plain_body = _extract_plain_text(msg_data.get("payload", {}))
    fallback_snippet = msg_data.get("snippet", "")[:SNIPPET_SIZE]

    return {
        "subject": subject,
        "from": sender,
        "date": date,
        "body": plain_body.strip() if plain_body.strip() else fallback_snippet,
    }
