from pathlib import Path
from typing import List

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = {
    "calendar": "https://www.googleapis.com/auth/calendar.readonly",
    "gmail": "https://www.googleapis.com/auth/gmail.readonly",
}

TOKEN_DIR = Path(".credentials")
CLIENT_SECRET = Path("credentials/client_secret.json")


def authorize(scopes: List[str]) -> None:
    TOKEN_DIR.mkdir(exist_ok=True)
    required_scopes = [SCOPES[s] for s in scopes if s in SCOPES]
    if not required_scopes:
        raise ValueError(f"No valid services specified. Choose from: {list(SCOPES.keys())}")

    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f"Client secret file not found at {CLIENT_SECRET}. "
            f"Please download your credentials and place them in this path."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), required_scopes)
    creds = flow.run_local_server(port=0)

    for s in scopes:
        token_file = TOKEN_DIR / f"{s}_token.json"
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        print(f"Saved token to {token_file}")