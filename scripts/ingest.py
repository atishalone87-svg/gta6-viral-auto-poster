"""
Phase 2 (Upgraded): Streamlined Ultra-Long Video Ingestion Engine (scripts/ingest.py)
Optimized for 5-to-10 hour livestreams/VODs:
  1. Audio-First Mode: If video duration > 45 minutes (2700s), downloads ONLY lightweight
     audio (temp_work/full_audio.m4a) avoiding 20GB-50GB full video downloads.
  2. Targeted Section Download: Downloads ONLY selected 1080p video clips via
     `yt-dlp --download-sections "*START-END"` with 5-second padding.
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
from typing import Optional

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMP_WORK_DIR = WORKSPACE_DIR / "temp_work"
LONG_VIDEO_THRESHOLD_SEC = 2700.0  # 45 minutes


def format_seconds_to_hms(seconds: float) -> str:
    """Converts seconds float to HH:MM:SS format."""
    sec = max(0.0, seconds)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_media_duration(source: str) -> float:
    """
    Returns duration in seconds. Uses ffprobe for local files,
    yt-dlp --print duration for remote URLs without downloading.
    """
    local_p = Path(source)
    if local_p.exists() and local_p.is_file():
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(local_p.resolve())
        ]
        try:
            res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            return float(res.strip())
        except Exception:
            return 0.0

    print(f"[ingest] Checking duration of remote video: {source}...")
    cmd = [
        "yt-dlp",
        "--print", "duration",
        "--no-playlist",
        source
    ]
    try:
        res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        dur = float(res.strip().split("\n")[0])
        print(f"[ingest] Remote duration: {dur:.1f}s ({dur/3600:.2f} hours)")
        return dur
    except Exception as e:
        print(f"[ingest] Warning: Could not pre-fetch remote duration ({e}). Assuming long video.")
        return LONG_VIDEO_THRESHOLD_SEC + 1.0


def download_audio_only(source: str, output_path: Path, retries: int = 3) -> Path:
    """
    Fast audio-only extraction for long streams (5-10 hours).
    Downloads into lightweight m4a file (usually 50MB - 180MB vs 40GB).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 1024:
        print(f"[ingest] Audio already present: {output_path} ({output_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_path.resolve()

    print(f"[ingest] Downloading AUDIO-ONLY track ({source}) -> {output_path.name}...")
    cmd = [
        "yt-dlp",
        "-f", "139/140/bestaudio",
        "--no-playlist",
        "--retries", "10",
        "--fragment-retries", "10",
        "-o", str(output_path.resolve()),
        source
    ]

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            print(f"[ingest] Audio download attempt {attempt}/{retries}...")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            break
        except subprocess.CalledProcessError as e:
            last_error = e
            print(f"[ingest] Audio download attempt {attempt} failed: {e.stderr[-300:] if e.stderr else str(e)}")
            time.sleep(attempt * 3)
    else:
        raise RuntimeError(f"[ingest] Failed to download audio after {retries} retries: {last_error}")

    print(f"[ingest] Audio download complete: {output_path} ({output_path.stat().st_size / (1024*1024):.2f} MB)")
    return output_path.resolve()


def download_video_section(
    source: str,
    start_sec: float,
    end_sec: float,
    output_path: Path,
    padding_sec: float = 5.0,
    retries: int = 3
) -> Path:
    """
    Downloads ONLY the specific short section in best 1080p quality with 5-second padding.
    Guarantees resolving the exact downloaded file even if yt-dlp appends container extensions.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pad_start = max(0.0, start_sec - padding_sec)
    pad_end = end_sec + padding_sec
    hms_start = format_seconds_to_hms(pad_start)
    hms_end = format_seconds_to_hms(pad_end)
    section_arg = f"*{hms_start}-{hms_end}"

    stem = output_path.stem

    # Check if section was already downloaded
    existing = list(output_path.parent.glob(f"{stem}*"))
    for e in existing:
        if e.is_file() and not e.name.endswith(".part") and e.stat().st_size > 100000:
            print(f"[ingest] Section already present: {e.name} ({e.stat().st_size / (1024*1024):.2f} MB)")
            return e.resolve()

    print(f"[ingest] Downloading 1080p section {section_arg} ({pad_end - pad_start:.1f}s) -> {output_path.name}...")

    cmd = [
        "yt-dlp",
        "--download-sections", section_arg,
        "--format", "299+140/bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", str(output_path.resolve()),
        source
    ]

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            break
        except subprocess.CalledProcessError as e:
            last_error = e
            print(f"[ingest] Section download attempt {attempt} failed: {e.stderr[-300:] if e.stderr else str(e)}")
            time.sleep(attempt * 2)
    else:
        raise RuntimeError(f"[ingest] Failed to download section {section_arg}: {last_error}")

    # Resolve actual output file
    if output_path.exists():
        return output_path.resolve()

    matches = list(output_path.parent.glob(f"{stem}*"))
    for m in matches:
        if m.is_file() and not m.name.endswith(".part"):
            print(f"[ingest] Section ready: {m.name} ({m.stat().st_size / (1024*1024):.2f} MB)")
            return m.resolve()

    raise FileNotFoundError(f"[ingest] Could not find downloaded section file for {stem}")


def download_or_ingest(source: str, output_dir: Path = None, retries: int = 3) -> Path:
    target_dir = output_dir or TEMP_WORK_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    local_path = Path(source)
    if local_path.exists() and local_path.is_file():
        dest = target_dir / local_path.name
        if dest.resolve() != local_path.resolve():
            import shutil
            shutil.copy2(local_path, dest)
            return dest.resolve()
        return local_path.resolve()

    output_template = str(target_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--format", "299+140/bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", output_template,
        source
    ]
    subprocess.run(cmd, check=True)
    mp4_files = sorted(target_dir.glob("*.mp4"), key=os.path.getmtime, reverse=True)
    if not mp4_files:
        raise FileNotFoundError(f"[ingest] Download failed: no MP4 in {target_dir}")
    return mp4_files[0].resolve()
