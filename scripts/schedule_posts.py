"""
Autonomous Post Scheduler (scripts/schedule_posts.py)
Iterates through pending clips in status.csv / summary.json:
  - Finds next clip with status == 'SCHEDULED' or 'PENDING'
  - Posts it to both YouTube Shorts and Instagram Reels
  - Updates status.csv and POSTING_STATUS.md with live links
  - Waits for staggered interval (default: 3 hours) before posting the next
"""

import os
import sys
import time
import json
import csv
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
FINAL_CLIPS_DIR = WORKSPACE_DIR / "final_clips"
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
STATUS_CSV = WORKSPACE_DIR / "status.csv"
STATUS_MD = WORKSPACE_DIR / "POSTING_STATUS.md"

sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import scripts.auto_post as post_mod


def load_status_csv() -> list:
    if not STATUS_CSV.exists():
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


def update_status_md(rows: list):
    lines = [
        "# Viral Clip Studio - Posting Status Tracker\n",
        "| Clip | Filename | Viral Hook Headline | YouTube Status | Instagram Status | Published Links | Status |",
        "|:---:|:---:|---|:---:|:---:|---|:---:|"
    ]
    for r in rows:
        idx = int(r["index"])
        fn = r["filename"]
        title = r["title"]
        yt_st = r.get("youtube_status", "PENDING")
        ig_st = r.get("instagram_status", "PENDING")
        yt_link = r.get("youtube_link", "")
        ig_link = r.get("instagram_link", "")
        ov_st = r.get("overall_status", "PENDING")

        links = []
        if yt_link and yt_link != "MANUAL":
            links.append(f"[YouTube]({yt_link})")
        if ig_link and ig_link != "MANUAL":
            links.append(f"[Instagram]({ig_link})")
        
        if yt_link == "MANUAL":
            link_str = "Manually Posted by User"
        elif links:
            link_str = " \\| ".join(links)
        else:
            link_str = "Queued in Auto-Scheduler"

        badge = "✅" if ov_st == "POSTED" else ("🕒" if ov_st == "SCHEDULED" else "⏳")
        lines.append(f"| **#{idx:02d}** | `{fn}` | `{title}` | {yt_st} | {ig_st} | {link_str} | **{ov_st}** {badge} |")

    with open(STATUS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def post_next_scheduled_clip():
    rows = load_status_csv()
    for row in rows:
        if row["overall_status"] in ["SCHEDULED", "PENDING"] and int(row["index"]) > 2:
            idx = int(row["index"])
            v_path = FINAL_CLIPS_DIR / row["filename"]
            title = row["title"]
            hashtags = "#ishowspeed #gta6 #viral #shorts #gaming #reels"

            print(f"\n[Scheduler] Found next scheduled clip: #{idx:02d} ({v_path.name})", flush=True)
            res = post_mod.post_single_clip(
                video_path=v_path,
                title=title,
                caption=f"GTA 6 Viral Highlight #{idx:02d}",
                hashtags=hashtags,
                target="all"
            )

            yt_res = res.get("youtube", {})
            ig_res = res.get("instagram", {})

            if yt_res.get("status") == "success":
                row["youtube_status"] = "POSTED"
                row["youtube_link"] = yt_res.get("url", "")
            else:
                row["youtube_status"] = "FAILED"

            if ig_res.get("status") == "success":
                row["instagram_status"] = "POSTED"
                row["instagram_link"] = ig_res.get("url", "")
            else:
                row["instagram_status"] = "FAILED"

            row["overall_status"] = "POSTED" if (row["youtube_status"] == "POSTED" or row["instagram_status"] == "POSTED") else "FAILED"
            save_status_csv(rows)
            update_status_md(rows)
            return idx, row

    print("[Scheduler] All clips have been posted!", flush=True)
    return None, None


def run_scheduler_daemon(interval_hours: float = 3.0, start_now: bool = False):
    interval_sec = int(interval_hours * 3600)
    print(f"[Scheduler Daemon] Initialized with interval of {interval_hours} hours between uploads.", flush=True)

    if not start_now:
        print(f"[Scheduler Daemon] Clip 2 was just published. Staggering next post by {interval_hours} hours to maximize reach...", flush=True)
        time.sleep(interval_sec)

    while True:
        idx, row = post_next_scheduled_clip()
        if idx is None:
            print("[Scheduler Daemon] No more pending clips. Scheduler completed successfully.", flush=True)
            break
        print(f"[Scheduler Daemon] Clip #{idx:02d} posted. Sleeping for {interval_hours} hours before next post...", flush=True)
        time.sleep(interval_sec)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-Post Scheduler")
    parser.add_argument("--once", action="store_true", help="Post next pending clip once and exit")
    parser.add_argument("--interval", type=float, default=3.0, help="Interval in hours between posts (default: 3.0)")
    parser.add_argument("--start-now", action="store_true", help="Post immediately without initial sleep")
    args = parser.parse_args()

    if args.once:
        post_next_scheduled_clip()
    else:
        run_scheduler_daemon(interval_hours=args.interval, start_now=args.start_now)
