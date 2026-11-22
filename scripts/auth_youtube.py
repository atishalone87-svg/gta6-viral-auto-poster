"""
YouTube Authentication Helper (scripts/auth_youtube.py)
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRETS_PATH = WORKSPACE_DIR / "client_secrets.json"
TOKEN_PATH = WORKSPACE_DIR / "youtube_token.json"

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def check_or_login():
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), YOUTUBE_SCOPES)
            if creds and creds.valid:
                print("✅ Found existing valid YouTube token!", flush=True)
            elif creds and creds.expired and creds.refresh_token:
                print("🔄 Refreshing existing YouTube token...", flush=True)
                creds.refresh(Request())
                with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                print("✅ Token refreshed successfully!", flush=True)
        except Exception as e:
            print(f"Token refresh failed: {e}", flush=True)
            creds = None

    if not creds or not creds.valid:
        print("\n" + "=" * 65, flush=True)
        print("🌐 OPENING BROWSER FOR GOOGLE / YOUTUBE ACCOUNT LOGIN...", flush=True)
        print("=" * 65, flush=True)
        print("A browser window will open automatically.", flush=True)
        print("Please log in with the Google account that owns your YouTube Channel", flush=True)
        print("and grant permission to upload videos.\n", flush=True)

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_PATH),
            scopes=YOUTUBE_SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=True)

        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"\n✅ YouTube login successful! Token saved to: {TOKEN_PATH.name}\n", flush=True)

    # Verify channel details
    service = build("youtube", "v3", credentials=creds)
    res = service.channels().list(mine=True, part="snippet,statistics").execute()
    items = res.get("items", [])
    if items:
        ch = items[0]
        title = ch["snippet"]["title"]
        ch_id = ch["id"]
        subs = ch["statistics"].get("subscriberCount", "0")
        vids = ch["statistics"].get("videoCount", "0")
        print("=" * 65, flush=True)
        print(f"🎬 YouTube Channel Connected: {title}", flush=True)
        print(f"   Channel ID: {ch_id}", flush=True)
        print(f"   Subscribers: {subs} | Total Videos: {vids}", flush=True)
        print("=" * 65, flush=True)
        return True
    else:
        print("⚠️ Warning: Google account verified, but no active YouTube channel found on this account.", flush=True)
        return False


if __name__ == "__main__":
    check_or_login()
