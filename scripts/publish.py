"""
YouTube & Instagram API Verification and Publishing Engine (scripts/publish.py)
"""

import os
import sys
import json
import time
import ast
import re
import subprocess
from pathlib import Path
from dotenv import load_dotenv

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
ENV_PATH = WORKSPACE_DIR / ".env"
CLIENT_SECRETS_PATH = WORKSPACE_DIR / "client_secrets.json"
TOKEN_PATH = WORKSPACE_DIR / "youtube_token.json"

load_dotenv(ENV_PATH)

import requests

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def robust_json_load(raw_input):
    """
    Safely parses JSON, YAML, or loose Python dictionary text even if it was saved with:
    - Single quotes
    - Unquoted keys/values (e.g. {token: ya29..., refresh_token: 1//...})
    - Markdown codeblocks (```json ... ```)
    - UTF-8 BOM
    - Extra wrapping quotes
    Returns a dict or raises ValueError.
    """
    if not raw_input:
        return None
    if isinstance(raw_input, dict):
        return raw_input

    content = str(raw_input).strip()

    # Strip UTF-8 BOM
    if content.startswith("\ufeff"):
        content = content[1:].strip()

    # Strip markdown code blocks (```json ... ``` or ``` ... ```)
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    # Strip outer quotes if the entire JSON is wrapped in single or double quotes
    if (content.startswith("'") and content.endswith("'")) or (content.startswith('"') and content.endswith('"')):
        if "{" in content:
            unquoted = content[1:-1].strip()
            if unquoted.startswith("{"):
                content = unquoted

    # Attempt 1: Standard JSON decoding
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            inner = json.loads(data)
            if isinstance(inner, dict):
                return inner
    except Exception:
        pass

    # Attempt 2: ast.literal_eval for Python dictionary literals
    try:
        data = ast.literal_eval(content)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Attempt 3: YAML safe load (handles unquoted keys and unquoted strings like {token: ya29..., refresh_token: ...})
    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Attempt 4: Regex single quote substitution
    try:
        fixed = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', content)
        fixed = fixed.replace("True", "true").replace("False", "false").replace("None", "null")
        data = json.loads(fixed)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Attempt 5: Pure Python loose dictionary parser (regex extractor for key: value pairs)
    try:
        clean = content.strip()
        if clean.startswith("{") and clean.endswith("}"):
            clean = clean[1:-1].strip()
        result = {}
        pattern = r'(\w+)\s*:\s*(\[[^\]]*\]|[^,\n\r]+)'
        for m in re.finditer(pattern, clean):
            k = m.group(1).strip().strip("\"'")
            v = m.group(2).strip().strip("\"'")
            if v.startswith("[") and v.endswith("]"):
                items = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
                result[k] = items
            elif v.lower() == "true":
                result[k] = True
            elif v.lower() == "false":
                result[k] = False
            elif v.lower() in ["none", "null"]:
                result[k] = None
            else:
                result[k] = v
        if result and any(key in result for key in ["token", "refresh_token", "client_id", "installed"]):
            return result
    except Exception:
        pass

    raise ValueError(f"Could not parse valid JSON or Python dictionary from input (starts with: {content[:80]!r})")


def get_public_video_url(video_path: Path) -> str:
    """
    Determines the public raw URL for a video file hosted in this GitHub repository.
    Meta's Instagram Graph API uses this public URL to ingest Reels directly and reliably.
    """
    env_base = os.getenv("RAW_VIDEO_BASE_URL")
    if env_base:
        return f"{env_base.rstrip('/')}/{video_path.name}"

    gh_repo = os.getenv("GITHUB_REPOSITORY")
    gh_ref = os.getenv("GITHUB_REF_NAME", "main")
    if gh_repo:
        return f"https://raw.githubusercontent.com/{gh_repo}/{gh_ref}/final_clips/{video_path.name}"

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        m = re.search(r"github\.com[/:]([^/]+)/([^/\.]+)", remote)
        if m:
            owner, repo = m.groups()
            return f"https://raw.githubusercontent.com/{owner}/{repo}/main/final_clips/{video_path.name}"
    except Exception:
        pass

    return f"https://raw.githubusercontent.com/atishalone87-svg/gta6-viral-auto-poster/main/final_clips/{video_path.name}"


def test_instagram_connection() -> dict:
    """Verifies Instagram Business Account and Facebook Page status via Meta Graph API."""
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    fb_page_id = os.getenv("FB_PAGE_ID")

    if not token or not ig_user_id:
        return {"status": "error", "message": "Missing IG_ACCESS_TOKEN or IG_USER_ID in .env"}

    ig_url = f"https://graph.facebook.com/v19.0/{ig_user_id}?fields=id,username,name,profile_picture_url&access_token={token}"
    res_ig = requests.get(ig_url, timeout=15)
    if res_ig.status_code != 200:
        return {"status": "error", "message": f"Instagram Graph API error: {res_ig.text}"}

    data_ig = res_ig.json()

    data_fb = {}
    if fb_page_id:
        fb_url = f"https://graph.facebook.com/v19.0/{fb_page_id}?fields=id,name&access_token={token}"
        res_fb = requests.get(fb_url, timeout=15)
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
    """
    Authenticates or refreshes YouTube Data API v3 service.
    Headless-safe: in GitHub Actions / CI, it relies purely on token refresh and never
    attempts to open a local browser OAuth callback server.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        raise ImportError(f"Required Google API libraries not installed: {e}")

    token_candidates = [
        WORKSPACE_DIR / "youtube_token.json",
        WORKSPACE_DIR / "token.json",
        SCRIPTS_DIR / "youtube_token.json",
        SCRIPTS_DIR / "token.json",
    ]

    creds = None
    token_data = None

    for p in token_candidates:
        if p.exists():
            try:
                raw_text = p.read_text(encoding="utf-8")
                token_data = robust_json_load(raw_text)
                if token_data and isinstance(token_data, dict):
                    # Rewrite as clean standard JSON
                    clean_str = json.dumps(token_data, indent=2)
                    p.write_text(clean_str, encoding="utf-8")
                    # Sync to other paths
                    for other in [WORKSPACE_DIR / "youtube_token.json", WORKSPACE_DIR / "token.json"]:
                        if other != p:
                            try:
                                other.write_text(clean_str, encoding="utf-8")
                            except Exception:
                                pass
                    break
            except Exception as e:
                print(f"[YouTube] Notice reading {p.name}: {e}")

    # Fallback to direct environment variable
    if not token_data:
        env_token = os.getenv("YOUTUBE_TOKEN_JSON") or os.getenv("TOKEN_JSON")
        if env_token:
            try:
                token_data = robust_json_load(env_token)
                if token_data and isinstance(token_data, dict):
                    clean_str = json.dumps(token_data, indent=2)
                    for p in [WORKSPACE_DIR / "youtube_token.json", WORKSPACE_DIR / "token.json"]:
                        try:
                            p.write_text(clean_str, encoding="utf-8")
                        except Exception:
                            pass
            except Exception as e:
                print(f"[YouTube] Notice reading YOUTUBE_TOKEN_JSON env: {e}")

    if token_data and isinstance(token_data, dict):
        try:
            creds = Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)
        except Exception as e:
            print(f"[YouTube] Error creating credentials from token dict: {e}")
            creds = None

    # Handle expired token or refresh
    if not creds or not creds.valid:
        if creds and creds.refresh_token:
            print("[YouTube] Refreshing expired access token via refresh_token...")
            creds.refresh(Request())
            refreshed_json = creds.to_json()
            for p in [WORKSPACE_DIR / "youtube_token.json", WORKSPACE_DIR / "token.json"]:
                try:
                    p.write_text(refreshed_json, encoding="utf-8")
                except Exception:
                    pass
            print("[YouTube] Access token refreshed and saved successfully.")
        else:
            is_headless = bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS") or not sys.stdin.isatty())
            if is_headless:
                raise RuntimeError(
                    "YouTube authentication failed: No valid credentials or refresh_token found, "
                    "and browser OAuth cannot run in headless CI/CD (GitHub Actions). "
                    "Please verify YOUTUBE_TOKEN_JSON secret in GitHub Repository Secrets."
                )

            # Local interactive flow only
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
            except ImportError:
                raise ImportError("google-auth-oauthlib is required for interactive OAuth login.")

            cs_candidates = [
                WORKSPACE_DIR / "client_secrets.json",
                SCRIPTS_DIR / "client_secrets.json"
            ]
            cs_path = next((p for p in cs_candidates if p.exists()), None)
            if not cs_path:
                raise FileNotFoundError("client_secrets.json not found for local OAuth login.")

            cs_data = robust_json_load(cs_path.read_text(encoding="utf-8"))
            cs_path.write_text(json.dumps(cs_data, indent=2), encoding="utf-8")

            print("[YouTube] Starting browser OAuth login flow via client_secrets.json...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(cs_path),
                scopes=YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)

            refreshed_json = creds.to_json()
            for p in [WORKSPACE_DIR / "youtube_token.json", WORKSPACE_DIR / "token.json"]:
                p.write_text(refreshed_json, encoding="utf-8")
            print("[YouTube] New OAuth token saved successfully.")

    service = build("youtube", "v3", credentials=creds)
    return service


def test_youtube_connection() -> dict:
    """Checks authenticated YouTube channel profile."""
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
    from googleapiclient.http import MediaFileUpload

    try:
        service = get_youtube_service()
    except Exception as e:
        return {"status": "error", "message": f"Authentication failed: {e}"}

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

    try:
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
    except Exception as e:
        return {"status": "error", "message": f"Upload failed: {e}"}


def upload_instagram_reel(
    video_path: Path,
    caption: str
) -> dict:
    """
    Uploads a vertical 9:16 video to Instagram Reels.
    Uses public GitHub raw URL if available (Meta recommended for reliability),
    falling back to direct resumable binary upload with proper octet-stream headers.
    """
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    file_size = video_path.stat().st_size

    if not token or not ig_user_id:
        return {"status": "error", "message": "Missing IG_ACCESS_TOKEN or IG_USER_ID in environment"}

    print(f"\n[Instagram] Preparing Reel upload: {video_path.name} ({file_size / (1024*1024):.2f} MB)...")

    # Method 1: Upload via public raw video URL
    public_url = get_public_video_url(video_path)
    url_accessible = False
    try:
        r_chk = requests.head(public_url, timeout=10, allow_redirects=True)
        url_accessible = (r_chk.status_code == 200)
    except Exception:
        url_accessible = False

    container_id = None
    if url_accessible:
        print(f"[Instagram] Using public video URL: {public_url}")
        init_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
        init_params = {
            "media_type": "REELS",
            "video_url": public_url,
            "caption": caption,
            "access_token": token
        }
        try:
            r1 = requests.post(init_url, data=init_params, timeout=30)
            if r1.status_code == 200 and "id" in r1.json():
                container_id = r1.json().get("id")
                print(f"[Instagram] Container created via video_url (ID: {container_id})")
            else:
                err_text = r1.text
                if "5258005" in err_text or "API access blocked" in err_text:
                    print(f"[Instagram] ⚠️ Meta API access blocked (error 5258005). App/portfolio needs review in Meta Business Suite.")
                print(f"[Instagram] video_url init notice ({r1.status_code}): {err_text}. Falling back to binary...")
        except Exception as e:
            print(f"[Instagram] video_url error: {e}. Falling back to binary...")

    # Method 2: Fallback to resumable binary upload
    if not container_id:
        print("[Instagram] Initializing Resumable Binary Upload...")
        init_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
        init_params = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "access_token": token
        }
        r1 = requests.post(init_url, data=init_params, timeout=30)
        if r1.status_code != 200:
            err_text = r1.text
            if "5258005" in err_text or "API access blocked" in err_text:
                return {
                    "status": "error",
                    "message": "Meta API access blocked (error_subcode 5258005). Meta Business Suite me portfolio admin status verify karna hoga."
                }
            return {"status": "error", "message": f"Init failed: {err_text}"}

        container_id = r1.json().get("id")
        upload_url = r1.json().get("uri")

        with open(video_path, "rb") as f:
            video_bytes = f.read()

        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream"
        }
        r2 = requests.post(upload_url, headers=headers, data=video_bytes, timeout=180)
        if r2.status_code not in [200, 204]:
            return {"status": "error", "message": f"Binary upload failed: {r2.text}"}
        print("[Instagram] Binary uploaded successfully!")

    # Step 3: Wait for container to be ready
    print(f"[Instagram] Waiting for media container {container_id} to complete processing...")
    status_url = f"https://graph.facebook.com/v19.0/{container_id}?fields=status_code,status&access_token={token}"
    for attempt in range(45):
        time.sleep(4)
        try:
            r_status = requests.get(status_url, timeout=15).json()
            code = r_status.get("status_code")
            if code == "FINISHED":
                print("[Instagram] Media container processing complete!")
                break
            elif code in ["ERROR", "EXPIRED"]:
                return {"status": "error", "message": f"Instagram container status error: {code} ({r_status})"}
            else:
                if (attempt + 1) % 5 == 0:
                    print(f"[Instagram] Still processing... (check {attempt+1}/45, status: {code})")
        except Exception as e:
            print(f"[Instagram] Status check notice: {e}")
    else:
        return {"status": "error", "message": f"Timeout waiting for Instagram container {container_id} processing"}

    # Step 4: Publish Reel
    pub_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
    r3 = requests.post(pub_url, data={"creation_id": container_id, "access_token": token}, timeout=30)
    if r3.status_code != 200:
        return {"status": "error", "message": f"Publish failed: {r3.text}"}

    media_id = r3.json().get("id")

    # Step 5: Fetch Live Permalink
    permalink = f"https://www.instagram.com/reel/{media_id}/"
    try:
        info_url = f"https://graph.facebook.com/v19.0/{media_id}?fields=permalink&access_token={token}"
        r_info = requests.get(info_url, timeout=15)
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
