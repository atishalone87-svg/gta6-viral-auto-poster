"""
Single-Run Cloud Auto-Poster (scripts/post_one_cloud.py)
Designed for 24/7 autonomous GitHub Actions execution.

Behavior:
1. Reconstructs secret files (.env, client_secrets.json, youtube_token.json, token.json)
   from environment variables and sanitizes any single quotes / dirty JSON formats / datetime objects.
2. Reads status.csv and finds the next clip with status 'SCHEDULED' or 'PENDING'.
3. Uploads that clip to YouTube Shorts and Instagram Reels.
4. Marks clip as POSTED if YouTube (or Instagram) succeeds, advancing the queue.
5. Updates status.csv, final_clips/summary.json, and POSTING_STATUS.md with live URLs.
6. Auto-commits and pushes the updated status files back to the GitHub repository.
7. Exits cleanly with status code 0.
"""

import os
import sys
import json
import csv
import argparse
import subprocess
from pathlib import Path

# Ensure UTF-8 output encoding across Windows / Linux GitHub runners
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
FINAL_CLIPS_DIR = WORKSPACE_DIR / "final_clips"
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
STATUS_CSV = WORKSPACE_DIR / "status.csv"
STATUS_MD = WORKSPACE_DIR / "POSTING_STATUS.md"
SUMMARY_JSON = FINAL_CLIPS_DIR / "summary.json"

sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))


def ensure_secret_files():
    """Reconstructs and sanitizes credentials from environment variables and disk."""
    from scripts.publish import robust_json_load

    env_content = os.getenv("ENV_FILE") or os.getenv("ENV_FILE_CONTENT")
    if env_content and not (WORKSPACE_DIR / ".env").exists():
        (WORKSPACE_DIR / ".env").write_text(env_content.strip() + "\n", encoding="utf-8")
        print("🔐 Reconstructed .env from GitHub Secret.")

    client_secrets_content = os.getenv("CLIENT_SECRETS_JSON") or os.getenv("CLIENT_SECRETS_CONTENT")
    if client_secrets_content:
        try:
            cs_data = robust_json_load(client_secrets_content)
            clean_cs = json.dumps(cs_data, indent=2)
            (WORKSPACE_DIR / "client_secrets.json").write_text(clean_cs, encoding="utf-8")
            (SCRIPTS_DIR / "client_secrets.json").write_text(clean_cs, encoding="utf-8")
            print("🔐 Reconstructed & sanitized client_secrets.json from GitHub Secret.")
        except Exception as e:
            print(f"⚠️ Warning reconstructing client_secrets.json: {e}")
    elif (WORKSPACE_DIR / "client_secrets.json").exists():
        try:
            raw_cs = (WORKSPACE_DIR / "client_secrets.json").read_text(encoding="utf-8")
            cs_data = robust_json_load(raw_cs)
            (WORKSPACE_DIR / "client_secrets.json").write_text(json.dumps(cs_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    youtube_token_content = os.getenv("YOUTUBE_TOKEN_JSON") or os.getenv("TOKEN_JSON")
    if youtube_token_content:
        try:
            tok_data = robust_json_load(youtube_token_content)
            clean_tok = json.dumps(tok_data, indent=2)
            (WORKSPACE_DIR / "youtube_token.json").write_text(clean_tok, encoding="utf-8")
            (WORKSPACE_DIR / "token.json").write_text(clean_tok, encoding="utf-8")
            print("🔐 Reconstructed & sanitized youtube_token.json and token.json from GitHub Secret.")
        except Exception as e:
            print(f"⚠️ Warning reconstructing youtube_token.json from env: {e}")
    else:
        # Sanitize any existing token file on disk (e.g. written by CI printf)
        for p in [WORKSPACE_DIR / "youtube_token.json", WORKSPACE_DIR / "token.json"]:
            if p.exists():
                try:
                    raw_tok = p.read_text(encoding="utf-8")
                    tok_data = robust_json_load(raw_tok)
                    clean_tok = json.dumps(tok_data, indent=2)
                    (WORKSPACE_DIR / "youtube_token.json").write_text(clean_tok, encoding="utf-8")
                    (WORKSPACE_DIR / "token.json").write_text(clean_tok, encoding="utf-8")
                    print(f"🔐 Sanitized {p.name} on disk and synced to token.json & youtube_token.json.")
                    break
                except Exception as e:
                    print(f"⚠️ Warning parsing {p.name} on disk: {e}")


def load_status_csv() -> list:
    if not STATUS_CSV.exists():
        print(f"❌ Error: {STATUS_CSV} not found!")
        return []
    with open(STATUS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_status_csv(rows: list):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(STATUS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_summary_json() -> list:
    if not SUMMARY_JSON.exists():
        return []
    try:
        return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_summary_json(items: list):
    if not items:
        return
    SUMMARY_JSON.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def update_status_md(rows: list, summary_items: list = None):
    headlines_map = {}
    if summary_items:
        for it in summary_items:
            headlines_map[it.get("index")] = it.get("hook_headline") or it.get("viral_title")

    lines = [
        "# Viral Clip Studio - Posting Status Tracker\n",
        "| Clip | Filename | Viral Hook Headline | YouTube Status | Instagram Status | Published Links | Status |",
        "|:---:|:---:|---|:---:|:---:|---|:---:|"
    ]
    for r in rows:
        idx = int(r["index"])
        fn = r["filename"]
        title = headlines_map.get(idx) or r.get("title", "")
        yt_st = r.get("youtube_status", "PENDING")
        ig_st = r.get("instagram_status", "PENDING")
        yt_link = r.get("youtube_link", "")
        ig_link = r.get("instagram_link", "")
        ov_st = r.get("overall_status", "PENDING")

        links = []
        if yt_link and yt_link != "MANUAL":
            links.append(f"[YouTube Short]({yt_link})")
        if ig_link and ig_link != "MANUAL":
            links.append(f"[Instagram Reel]({ig_link})")

        if yt_link == "MANUAL" or ig_link == "MANUAL":
            link_str = "Manually Posted by User"
        elif links:
            link_str = " \\| ".join(links)
        elif ov_st == "SCHEDULED":
            link_str = "Auto-Scheduler Queue"
        else:
            link_str = "Pending"

        badge = "✅" if ov_st == "POSTED" else ("🕒" if ov_st == "SCHEDULED" else ("⚠️" if ov_st == "PARTIAL" else "⏳"))
        lines.append(f"| **#{idx:02d}** | `{fn}` | `{title}` | {yt_st} | {ig_st} | {link_str} | **{ov_st}** {badge} |")

    with open(STATUS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def git_commit_and_push(idx: int, filename: str):
    """Commits and pushes updated status files back to the repository."""
    try:
        check_repo = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True
        )
        if check_repo.returncode != 0:
            print("[Git] Notice: Not a git repository or git not initialized. Skipping commit & push.")
            return

        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)

        # Stage the updated metadata files
        files_to_stage = ["status.csv", "POSTING_STATUS.md"]
        if SUMMARY_JSON.exists():
            files_to_stage.append("final_clips/summary.json")

        subprocess.run(["git", "add"] + files_to_stage, check=False)

        # Check if changes exist
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff.returncode != 0:
            commit_msg = f"Auto-post clip #{idx:02d} ({filename}) [skip ci]"
            print(f"[Git] Committing changes: '{commit_msg}'")
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)

            print("[Git] Pulling with rebase...")
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)

            print("[Git] Pushing to remote branch...")
            push_res = subprocess.run(["git", "push", "origin", "HEAD"], capture_output=True, text=True)
            if push_res.returncode == 0:
                print("✅ [Git] Successfully pushed status updates to GitHub!")
            else:
                print(f"⚠️ [Git] Push failed or warnings: {push_res.stderr or push_res.stdout}")
        else:
            print("[Git] No file changes to commit.")
    except Exception as e:
        print(f"⚠️ [Git] Error during auto-commit/push: {e}")


def post_next_single_clip(dry_run: bool = False) -> bool:
    ensure_secret_files()

    import scripts.auto_post as post_mod

    rows = load_status_csv()
    summary_items = load_summary_json()

    # Find the first pending or scheduled clip
    target_row = None
    target_idx = None

    for row in rows:
        if row.get("overall_status") in ["SCHEDULED", "PENDING"]:
            target_row = row
            target_idx = int(row["index"])
            break

    if not target_row:
        print("🎉 [Auto-Poster] All clips (clip_01 to clip_10) have already been published!")
        print("Nothing left to post. Cloud workflow finished.")
        return True

    filename = target_row["filename"]
    video_path = FINAL_CLIPS_DIR / filename
    if not video_path.exists():
        print(f"❌ Error: Video file not found: {video_path}")
        return False

    # Retrieve custom metadata from summary.json if available
    summary_entry = next((item for item in summary_items if item.get("index") == target_idx), {})
    title = target_row.get("title") or summary_entry.get("viral_title") or f"GTA 6 Highlight #{target_idx:02d}"
    headline = summary_entry.get("hook_headline") or title
    hashtags = summary_entry.get("hashtags") or "#ishowspeed #gta6 #viral #shorts #gaming #reels"

    caption_text = f"{headline}\n\nWatch full GTA 6 viral action highlight #{target_idx:02d}!"

    print("\n" + "=" * 70)
    print(f"🚀 CLOUD RUNNER: Posting Clip #{target_idx:02d}: {filename}")
    print(f"📌 Title: {title}")
    print(f"📢 Headline: {headline}")
    print(f"🏷️ Hashtags: {hashtags}")
    print("=" * 70)

    if dry_run:
        print("[Dry-Run] Skipping real API uploads and git commit.")
        return True

    results = post_mod.post_single_clip(
        video_path=video_path,
        title=title,
        caption=caption_text,
        hashtags=hashtags,
        target="all"
    )

    yt_res = results.get("youtube", {})
    ig_res = results.get("instagram", {})

    yt_success = yt_res.get("status") == "success"
    ig_success = ig_res.get("status") == "success"

    if yt_success:
        target_row["youtube_status"] = "POSTED"
        target_row["youtube_link"] = yt_res.get("url", "")
    else:
        target_row["youtube_status"] = "FAILED"

    if ig_success:
        target_row["instagram_status"] = "POSTED"
        target_row["instagram_link"] = ig_res.get("url", "")
    else:
        target_row["instagram_status"] = "FAILED"

    # If YouTube succeeds (even while Instagram is blocked), mark as POSTED to advance queue!
    if yt_success or ig_success:
        target_row["overall_status"] = "POSTED"
        if summary_entry:
            summary_entry["status"] = "POSTED"
        print(f"\n✅ [Auto-Poster] Clip #{target_idx:02d} successfully posted (YouTube: {target_row['youtube_status']}, Instagram: {target_row['instagram_status']})!")
    else:
        target_row["overall_status"] = "SCHEDULED"
        target_row["youtube_status"] = "SCHEDULED"
        target_row["instagram_status"] = "SCHEDULED"
        if summary_entry:
            summary_entry["status"] = "SCHEDULED"
        print(f"\n⚠️ [Auto-Poster] Both uploads failed for Clip #{target_idx:02d}. Retaining SCHEDULED status.")

    # Save tracking files
    save_status_csv(rows)
    if summary_items:
        save_summary_json(summary_items)
    update_status_md(rows, summary_items)

    print("\n" + "=" * 70)
    print(f"📊 Results for Clip #{target_idx:02d}:")
    print(f"  - YouTube: {target_row['youtube_status']} ({target_row.get('youtube_link', 'N/A')})")
    print(f"  - Instagram: {target_row['instagram_status']} ({target_row.get('instagram_link', 'N/A')})")
    print(f"  - Overall: {target_row['overall_status']}")
    print("=" * 70)

    # Only commit and push if at least one upload succeeded
    if yt_success or ig_success:
        git_commit_and_push(target_idx, filename)

    return (yt_success or ig_success)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post single next pending clip for Cloud Auto-Poster")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without uploading or pushing")
    args = parser.parse_args()

    success = post_next_single_clip(dry_run=args.dry_run)
    sys.exit(0 if success else 1)
