"""
Master Auto-Post Engine (scripts/auto_post.py)
Publishes rendered vertical 9:16 clips to Instagram Reels and YouTube Shorts:
  - Supports uploading a specific clip by index from summary.json (--clip 1)
  - Supports uploading all rendered clips in batch (--all)
  - Supports custom video file input (--file <path> --title <title> --caption <caption>)
  - Targets: --target all | youtube | instagram
"""

import os
import sys
import json
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
FINAL_CLIPS_DIR = WORKSPACE_DIR / "final_clips"
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"

sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import scripts.publish as pub


def post_single_clip(
    video_path: Path,
    title: str,
    caption: str,
    hashtags: str = "",
    target: str = "all"
) -> dict:
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    full_caption = f"{title}\n\n{caption}\n\n{hashtags}".strip()
    results = {}

    print("\n" + "=" * 65, flush=True)
    print(f"🚀 AUTO-POSTING: {video_path.name}", flush=True)
    print(f"📌 Title: {title}", flush=True)
    print(f"🎯 Target: {target.upper()}", flush=True)
    print("=" * 65, flush=True)

    # 1. Instagram Reels Upload
    if target in ["all", "instagram"]:
        print("\n📸 [1/2] Uploading to Instagram Reels...", flush=True)
        try:
            ig_res = pub.upload_instagram_reel(video_path, caption=full_caption)
            results["instagram"] = ig_res
            if ig_res.get("status") == "success":
                print(f"✅ Instagram Reel Published! (Media ID: {ig_res.get('media_id')})", flush=True)
            else:
                print(f"❌ Instagram upload failed: {ig_res.get('message')}", flush=True)
        except Exception as e:
            print(f"❌ Instagram error: {e}", flush=True)
            results["instagram"] = {"status": "error", "message": str(e)}

    # 2. YouTube Shorts Upload
    if target in ["all", "youtube"]:
        print("\n🎬 [2/2] Uploading to YouTube Shorts...", flush=True)
        try:
            tags = [t.replace("#", "") for t in hashtags.split() if t.startswith("#")]
            yt_res = pub.upload_youtube_short(
                video_path=video_path,
                title=title,
                description=full_caption,
                tags=tags
            )
            results["youtube"] = yt_res
            if yt_res.get("status") == "success":
                print(f"✅ YouTube Short Published! Watch: {yt_res.get('url')}", flush=True)
            else:
                print(f"❌ YouTube upload failed: {yt_res.get('message')}", flush=True)
        except Exception as e:
            print(f"❌ YouTube error: {e}", flush=True)
            results["youtube"] = {"status": "error", "message": str(e)}

    return results


def main():
    parser = argparse.ArgumentParser(description="Auto-Post Clips to Instagram Reels & YouTube Shorts")
    parser.add_argument("--clip", type=int, help="Clip index from summary.json (e.g. 1 for clip_01.mp4)")
    parser.add_argument("--all", action="store_true", help="Post all clips listed in summary.json")
    parser.add_argument("--file", help="Custom video file path")
    parser.add_argument("--title", default="", help="Custom post title")
    parser.add_argument("--caption", default="", help="Custom post caption")
    parser.add_argument("--hashtags", default="", help="Custom hashtags string")
    parser.add_argument("--target", default="all", choices=["all", "youtube", "instagram"], help="Publish destination")
    args = parser.parse_args()

    summary_file = FINAL_CLIPS_DIR / "summary.json"
    summary_data = []
    if summary_file.exists():
        try:
            summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception:
            summary_data = []

    if args.file:
        v_path = Path(args.file)
        post_single_clip(
            video_path=v_path,
            title=args.title or v_path.stem,
            caption=args.caption,
            hashtags=args.hashtags,
            target=args.target
        )
    elif args.clip:
        matched = [c for c in summary_data if c.get("index") == args.clip]
        if not matched:
            print(f"❌ Error: Clip #{args.clip} not found in summary.json!")
            sys.exit(1)
        item = matched[0]
        v_path = Path(item["path"])
        post_single_clip(
            video_path=v_path,
            title=item.get("viral_title") or item.get("hook_headline", "GTA 6 Viral Clip"),
            caption=f"{item.get('hook_headline', '')}\nSpoken Hook: \"{item.get('opening_hook', '')}\"",
            hashtags=item.get("hashtags", "#shorts #gaming #gta6"),
            target=args.target
        )
    elif args.all:
        if not summary_data:
            print("❌ Error: No clips found in summary.json!")
            sys.exit(1)
        print(f"🚀 Found {len(summary_data)} clips to auto-post in batch...")
        for item in summary_data:
            v_path = Path(item["path"])
            if v_path.exists():
                post_single_clip(
                    video_path=v_path,
                    title=item.get("viral_title") or item.get("hook_headline", "GTA 6 Viral Clip"),
                    caption=f"{item.get('hook_headline', '')}\nSpoken Hook: \"{item.get('opening_hook', '')}\"",
                    hashtags=item.get("hashtags", "#shorts #gaming #gta6"),
                    target=args.target
                )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
