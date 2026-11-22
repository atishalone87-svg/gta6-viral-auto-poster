"""
Master One-Command Pipeline: run_viral_clips.py
Automates the full viral GTA clipping workflow:
  1. Downloads URL via yt-dlp (YouTube, Twitch, Kick) into /input
  2. Runs gta_plugin.py to detect top viral moments (25-45s)
  3. Formats to vertical 1080x1920 (9:16) with smart center framing
  4. Burns Hormozi-style animated word-by-word captions & top hook banner
  5. Dynamically mixes SFX (boom, whoosh, pop, vine_boom)
  6. Exports to /output/clip_XX.mp4
"""

import os
import sys
import argparse
import subprocess
import json
import re
import math
from pathlib import Path
from typing import List, Dict, Any

# Root Workspace Directories
WORKSPACE_DIR = Path(r"C:\Users\Dell\.gemini\antigravity\scratch\Viral_Clip_Studio").resolve()
INPUT_DIR = WORKSPACE_DIR / "input"
OUTPUT_DIR = WORKSPACE_DIR / "output"
ASSETS_DIR = WORKSPACE_DIR / "assets"
SFX_DIR = ASSETS_DIR / "sfx"
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
PLUGINS_DIR = WORKSPACE_DIR / "plugins"

# Ensure plugins can be imported
sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(PLUGINS_DIR))
sys.path.insert(0, str(WORKSPACE_DIR / "clips-studio"))


def download_or_resolve_video(target: str) -> Path:
    """Downloads video via yt-dlp if it's a URL, or resolves local file path."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if target is a local file
    local_p = Path(target)
    if local_p.exists() and local_p.is_file():
        print(f"[run_viral_clips] Using local video file: {local_p}")
        return local_p.resolve()

    # URL download via yt-dlp
    print(f"[run_viral_clips] Downloading video from: {target} ...")
    output_template = str(INPUT_DIR / "%(title).50s-%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", output_template,
        target
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"yt-dlp failed to download video: {e}")

    # Find the downloaded file
    mp4_files = sorted(INPUT_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
    if not mp4_files:
        raise FileNotFoundError(f"No video file found in {INPUT_DIR} after download.")
    
    downloaded_video = mp4_files[0]
    print(f"[run_viral_clips] Downloaded: {downloaded_video}")
    return downloaded_video.resolve()


def generate_ass_subtitles(
    clip_info: Dict[str, Any],
    ass_path: Path,
    hook_title: str
):
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file.
    Creates:
      1. Top Hook Banner with bold outline and energetic style
      2. Hormozi-style animated word-by-word active highlighting:
         - 2 to 4 words displayed per line in bold uppercase
         - The actively spoken word lights up in bright yellow/green
    """
    clip_start = clip_info["start"]
    clip_end = clip_info["end"]
    clip_dur = clip_info["duration"]
    words = clip_info.get("words", [])

    header = """[Script Info]
Title: Viral GTA Clip Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HookBanner,Arial,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,105,105,2,0,1,7,4,8,40,40,240,1
Style: CaptionNormal,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,7,3,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt_time(sec: float) -> str:
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:01d}:{m:02d}:{s:05.2f}"

    events = []

    # 1. Top Hook Banner (shown during first 4.5 seconds with slight pulse)
    banner_end = min(4.5, clip_dur)
    safe_title = hook_title.upper().replace("{", "").replace("}", "")
    events.append(
        f"Dialogue: 1,{fmt_time(0.0)},{fmt_time(banner_end)},HookBanner,,0,0,0,,"
        f"{{\\fad(150,200)\\an8\\pos(540,260)\\bord8\\3c&H000000&\\c&H0000FFFF\\b1}}💥 {safe_title} 💥"
    )

    # 2. Hormozi-style Word-by-Word Active Captions
    # Adjust word timestamps relative to clip start
    rel_words = []
    for w in words:
        w_start = w["start"] - clip_start
        w_end = w["end"] - clip_start
        if 0 <= w_start < clip_dur:
            rel_words.append({
                "word": w["word"].upper(),
                "start": max(0.0, w_start),
                "end": min(clip_dur, w_end),
                "clean": w.get("clean", "")
            })

    # Group words into 3-word chunks
    chunk_size = 3
    for i in range(0, len(rel_words), chunk_size):
        chunk = rel_words[i:i + chunk_size]
        if not chunk:
            continue
        c_start = chunk[0]["start"]
        c_end = chunk[-1]["end"]
        # Ensure at least minimal readable span
        if c_end - c_start < 0.6:
            c_end = c_start + 0.6

        # For each word in the chunk, display the entire chunk with that word highlighted
        for target_idx, active_w in enumerate(chunk):
            w_s = active_w["start"]
            w_e = active_w["end"]
            if w_e <= w_s:
                w_e = w_s + 0.25

            line_parts = []
            for j, cw in enumerate(chunk):
                clean_text = cw["word"].replace("{", "").replace("}", "")
                if j == target_idx:
                    # Highlighted active word: Bright Yellow / Neon Green with pop scale
                    line_parts.append(f"{{\\c&H0000FFFF\\3c&H000000&\\b1\\fscx115\\fscy115}}{clean_text}{{\\rCaptionNormal}}")
                else:
                    line_parts.append(f"{{\\c&H00FFFFFF\\3c&H000000&\\b1}}{clean_text}")

            full_line = " ".join(line_parts)
            events.append(
                f"Dialogue: 0,{fmt_time(w_s)},{fmt_time(w_e)},CaptionNormal,,0,0,0,,{full_line}"
            )

    ass_content = header + "\n".join(events) + "\n"
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    print(f"[run_viral_clips] ASS Subtitles generated: {ass_path}")


def render_clip_ffmpeg(
    source_video: Path,
    clip_info: Dict[str, Any],
    output_path: Path
):
    """
    Renders 1080x1920 (9:16) vertical video:
      - Background: Stretched and heavily blurred cover fill (scale=1080:1920, boxblur=25:5, darkened)
      - Foreground: Sharp 16:9 gameplay placed centrally (scale=1080:608)
      - Subtitles: Hormozi word-by-word captions burned in
      - Audio: Mixed with SFX (boom at 0.3s hook, whoosh at start, pop on action words)
    """
    clip_start = clip_info["start"]
    clip_dur = clip_info["duration"]
    hook_title = clip_info["hook_title"]
    category = clip_info.get("category", "CHASE")
    
    temp_dir = output_path.parent / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ass_file = temp_dir / f"captions_{clip_info['clip_id']}.ass"
    
    generate_ass_subtitles(clip_info, ass_file, hook_title)

    # Prepare SFX files
    boom_sfx = SFX_DIR / "boom.wav"
    whoosh_sfx = SFX_DIR / "whoosh.wav"
    pop_sfx = SFX_DIR / "pop.wav"
    vine_boom_sfx = SFX_DIR / "vine_boom.wav"

    # Identify action timestamps for pop sound effects
    rel_words = clip_info.get("words", [])
    pop_delays = []
    for w in rel_words:
        w_start = w["start"] - clip_start
        if 1.0 < w_start < clip_dur - 1.0:
            if w.get("clean") in ["cops", "rpg", "crash", "dead", "shoot", "run", "blew", "wasted", "busted", "hit"]:
                pop_delays.append(int(w_start * 1000))
                if len(pop_delays) >= 3:
                    break

    # Construct FFmpeg command
    # Video input: 0
    # SFX inputs: 1 (boom), 2 (whoosh), 3 (pop)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(clip_start),
        "-t", str(clip_dur),
        "-i", str(source_video),
        "-i", str(boom_sfx),
        "-i", str(whoosh_sfx),
        "-i", str(pop_sfx)
    ]

    # Filter graph:
    # 1. Background: split source, scale to fill 1080x1920, boxblur, darken
    # 2. Foreground: scale to 1080:-2, overlay at center (y=656)
    # 3. Subtitles: overlay via ass filter using relative filename to avoid Windows path colon/backslash issue
    bg_filter = "[0:v]split=2[v_bg][v_fg];[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg_blur]"
    fg_filter = "[v_fg]scale=1080:-2:flags=lanczos[fg_sharp]"
    overlay_filter = f"[bg_blur][fg_sharp]overlay=0:(1920-h)/2[v_over]"
    sub_filter = f"[v_over]ass={ass_file.name}[vout]"
    v_filtergraph = f"{bg_filter};{fg_filter};{overlay_filter};{sub_filter}"

    # Audio filter graph:
    # Base stream: 0:a
    # Boom at 300ms (hook): adelay=300|300, volume=0.65
    # Whoosh at 50ms (transition): adelay=50|50, volume=0.40
    # Pop at key word (if any): adelay=T|T, volume=0.35
    audio_inputs = "[0:a]volume=1.0[a0];[1:a]adelay=300|300,volume=0.65[aboom];[2:a]adelay=50|50,volume=0.40[awhoosh]"
    mix_sources = "[a0][aboom][awhoosh]"
    mix_count = 3

    if pop_delays:
        first_pop = pop_delays[0]
        audio_inputs += f";[3:a]adelay={first_pop}|{first_pop},volume=0.35[apop]"
        mix_sources += "[apop]"
        mix_count += 1

    a_filtergraph = f"{audio_inputs};{mix_sources}amix=inputs={mix_count}:duration=first:dropout_transition=2[aout]"

    cmd += [
        "-filter_complex", f"{v_filtergraph};{a_filtergraph}",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "21",
        "-c:a", "aac",
        "-b:a", "192k",
        "-fps_mode", "cfr",
        "-shortest",
        str(output_path.resolve())
    ]

    print(f"[run_viral_clips] Rendering vertical clip #{clip_info['clip_id']} ({clip_dur}s) ...")
    # Execute ffmpeg with working directory inside temp_dir so ass=captions.ass resolves cleanly on Windows
    proc = subprocess.run(cmd, cwd=str(temp_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg render failed for clip #{clip_info['clip_id']}:\n{proc.stderr[-1000:]}")

    print(f"[run_viral_clips] Successfully rendered: {output_path}")


def run_pipeline(
    url_or_path: str,
    max_clips: int = 3,
    min_duration: float = 25.0,
    max_duration: float = 45.0,
    whisper_model: str = "base"
) -> List[Path]:
    """
    End-to-End Orchestrator:
      Downloads -> Analyzes (GTA Engine) -> Vertical Render + Hormozi Captions + SFX
    """
    print("=" * 65)
    print("      VIRAL CLIP STUDIO: MASTER ACTION PIPELINE")
    print("=" * 65)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Acquire video
    video_path = download_or_resolve_video(url_or_path)

    # 2. GTA Plugin Detection
    print("\n[Step 2/3] Scanning audio spikes & speech transcripts via GTA Action Engine...")
    import plugins.gta_plugin as gta_plugin
    clips = gta_plugin.find_viral_moments(
        str(video_path),
        min_duration=min_duration,
        max_duration=max_duration,
        target_clips=max_clips,
        whisper_model=whisper_model
    )

    if not clips:
        print("[run_viral_clips] No action moments found.")
        return []

    # 3. Render Each Clip
    print(f"\n[Step 3/3] Rendering {len(clips)} vertical clips with Hormozi captions & SFX...")
    rendered_files = []
    for i, c in enumerate(clips):
        clip_num = f"{i + 1:02d}"
        output_file = OUTPUT_DIR / f"clip_{clip_num}.mp4"
        print(f"\n>>> Clip #{clip_num}: '{c['hook_title']}' ({c['start']}s -> {c['end']}s, score: {c['score']})")
        render_clip_ffmpeg(video_path, c, output_file)
        rendered_files.append(output_file)

    print("\n" + "=" * 65)
    print(f" ALL CLIPS COMPLETE! {len(rendered_files)} viral shorts exported to:")
    print(f" {OUTPUT_DIR}")
    print("=" * 65)
    return rendered_files


def main():
    parser = argparse.ArgumentParser(description="Master Viral Clip Pipeline for GTA & Action Gaming Streams")
    parser.add_argument("source", help="YouTube/Twitch/Kick URL or path to local video file")
    parser.add_argument("--max-clips", type=int, default=3, help="Maximum number of clips to generate (default: 3)")
    parser.add_argument("--min-duration", type=float, default=25.0, help="Minimum clip duration in seconds (default: 25)")
    parser.add_argument("--max-duration", type=float, default=45.0, help="Maximum clip duration in seconds (default: 45)")
    parser.add_argument("--whisper-model", default="base", help="Whisper model to use (tiny, base, small, medium)")

    args = parser.parse_args()
    run_pipeline(
        url_or_path=args.source,
        max_clips=args.max_clips,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        whisper_model=args.whisper_model
    )


if __name__ == "__main__":
    main()
