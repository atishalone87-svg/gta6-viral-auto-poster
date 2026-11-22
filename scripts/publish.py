"""
YouTube & Instagram API Verification and Publishing Engine (scripts/publish.py)
"""

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = WORKSPACE_DIR / ".env"
CLIENT_SECRETS_PATH = WORKSPACE_DIR / "client_secrets.json"
TOKEN_PATH = WORKSPACE_DIR / "youtube_token.json"

load_dotenv(ENV_PATH)

import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def test_instagram_connection() -> dict:
    """Verifies Instagram Business Account and Facebook Page status via Meta Graph API."""
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    fb_page_id = os.getenv("FB_PAGE_ID")

    if not token or not ig_user_id:
        return {"status": "error", "message": "Missing IG_ACCESS_TOKEN or IG_USER_ID in .env"}

    ig_url = f"https://graph.facebook.com/v19.0/{ig_user_id}?fields=id,username,name,profile_picture_url&access_token={token}"
    res_ig = requests.get(ig_url)
    if res_ig.status_code != 200:
        return {"status": "error", "message": f"Instagram Graph API error: {res_ig.text}"}

    data_ig = res_ig.json()

    fb_url = f"https://graph.facebook.com/v19.0/{fb_page_id}?fields=id,name&access_token={token}"
    res_fb = requests.get(fb_url)
    data_fb = res_fb.json() if res_fb.status_code == 200 else {}

    return {
        "status": "success",
        "username": data_ig.get("username"),
        "name": data_ig.get("name"),
        "ig_id": data_ig.get("id"),
        "page_name": data_fb.get("name", "N/A"),
        "page_id": data_fb.get("id", "N/A")
    }


def get_youtube_service():
    """Authenticates or refreshes YouTube Data API v3 service."""
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), YOUTUBE_SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[YouTube] Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("[YouTube] Starting browser OAuth login flow via client_secrets.json...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_PATH),
                scopes=YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)

        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[YouTube] Token saved to: {TOKEN_PATH.name}")

    service = build("youtube", "v3", credentials=creds)
    return service


def test_youtube_connection() -> dict:
    """Checks authenticated YouTube channel profile."""
    if not CLIENT_SECRETS_PATH.exists():
        return {"status": "error", "message": "client_secrets.json not found"}

    try:
        service = get_youtube_service()
        response = service.channels().list(mine=True, part="snippet,statistics").execute()
        items = response.get("items", [])
        if not items:
            return {"status": "error", "message": "No YouTube channel associated with this account."}

        ch = items[0]
        return {
            "status": "success",
            "channel_title": ch["snippet"]["title"],
            "channel_id": ch["id"],
            "subscribers": ch["statistics"].get("subscriberCount", "0"),
            "video_count": ch["statistics"].get("videoCount", "0")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def upload_youtube_short(
    video_path: Path,
    title: str,
    description: str,
    tags: list = None
) -> dict:
    """Uploads a vertical 9:16 video to YouTube Shorts."""
    service = get_youtube_service()

    clean_title = f"{title[:80]} #Shorts"
    body = {
        "snippet": {
            "title": clean_title,
            "description": f"{description}\n\n#Shorts #Viral #Gaming #GTA6",
            "tags": (tags or []) + ["Shorts", "Viral", "YouTubeShorts", "GTA6", "Gaming"],
            "categoryId": "20"  # Gaming category
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    print(f"[YouTube] Uploading {video_path.name}...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[YouTube] Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"[YouTube] Upload Complete! Watch at: {video_url}")
    return {"status": "success", "video_id": video_id, "url": video_url}


def upload_instagram_reel(
    video_path: Path,
    caption: str
) -> dict:
    """
    Uploads a vertical 9:16 video to Instagram Reels via direct resumable video upload.
    No public URL needed!
    """
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    file_size = video_path.stat().st_size

    print(f"[Instagram] Initializing Resumable Upload for Reel: {video_path.name} ({file_size / (1024*1024):.2f} MB)...")

    # Step 1: Create Resumable Upload Container
    init_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
    init_params = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": token
    }
    r1 = requests.post(init_url, data=init_params)
    if r1.status_code != 200:
        return {"status": "error", "message": f"Init failed: {r1.text}"}

    container_id = r1.json().get("id")
    upload_url = r1.json().get("uri")

    # Step 2: Upload Binary Video Data
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(file_size)
    }
    r2 = requests.post(upload_url, headers=headers, data=video_bytes)
    if r2.status_code not in [200, 204]:
        return {"status": "error", "message": f"Binary upload failed: {r2.text}"}

    print("[Instagram] Binary uploaded successfully! Waiting for media processing...")

    # Step 3: Wait for container to be ready
    status_url = f"https://graph.facebook.com/v19.0/{container_id}?fields=status_code&access_token={token}"
    for _ in range(40):
        time.sleep(3)
        r_status = requests.get(status_url).json()
        code = r_status.get("status_code")
        if code == "FINISHED":
            break
        elif code in ["ERROR", "EXPIRED"]:
            return {"status": "error", "message": f"Instagram container status error: {code}"}

    # Step 4: Publish Reel
    pub_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
    r3 = requests.post(pub_url, data={"creation_id": container_id, "access_token": token})
    if r3.status_code != 200:
        return {"status": "error", "message": f"Publish failed: {r3.text}"}

    media_id = r3.json().get("id")
    
    # Step 5: Get Live Permalink
    permalink = f"https://www.instagram.com/reel/{media_id}/"
    try:
        info_url = f"https://graph.facebook.com/v19.0/{media_id}?fields=permalink&access_token={token}"
        r_info = requests.get(info_url)
        if r_info.status_code == 200:
            permalink = r_info.json().get("permalink", permalink)
    except Exception:
        pass

    print(f"[Instagram] Reel Published Successfully! Link: {permalink}")
    return {"status": "success", "media_id": media_id, "url": permalink}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== INSTAGRAM GRAPH API TEST ===")
        ig_res = test_instagram_connection()
        print(json.dumps(ig_res, indent=2))

        print("\n=== YOUTUBE DATA API TEST ===")
        yt_res = test_youtube_connection()
        print(json.dumps(yt_res, indent=2))
