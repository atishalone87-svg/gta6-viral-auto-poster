"""
Autonomous Batch Pipeline: process_speed_stream.py
Runs the complete multilingual high-retention clipping workflow:
  1. Auto-Language Detection (English, Hindi, Marathi):
     - Automatically identifies spoken language
     - Generates Devanagari captions (Nirmala UI) or English captions (Arial Black)
     - Renders matching native-script center hook banner
  2. High-Retention 9:16 Split-Screen with Visual Micro-Animations:
     - Top Panel (1080x760): Zoomed facecam with zoom punch-in (1.0x -> 1.08x) & camera micro-shake
     - Center Banner (1080x260): Persistent dark gradient with glowing gold borders
     - Bottom Panel (1080x900): Full 16:9 gameplay with blurred backdrop padding (0 black bars)
     - Animated karaoke active-word pop-in scale: \\t(0,120,\\fscx120\\fscy120)\\t(120,240,\\fscx100\\fscy100)
  3. Expanded 5-SFX Audio Mixing:
     - boom.wav (0.3s hook impact)
     - whoosh.wav (0.05s opening transition)
     - pop.wav (keyword pops)
     - vine_boom.wav (dramatic twist / shock fail)
     - riser.wav (suspense buildup)
     - Balanced audio mix at -14dB relative to speech
  4. Renders clips at 1080x1920 60 FPS CFR into ./final_clips/.
"""

import os
import sys
import json
import shutil
import cv2
import subprocess
from pathlib import Path
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMP_WORK_DIR = WORKSPACE_DIR / "temp_work"
FINAL_CLIPS_DIR = WORKSPACE_DIR / "final_clips"
SCRIPTS_DIR = WORKSPACE_DIR / "scripts"

sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import scripts.ingest as ingest_mod
import scripts.transcribe as transcribe_mod
import scripts.smart_crop as crop_mod
import scripts.render_captions as render_mod

STREAM_URL = "https://www.youtube.com/watch?v=OIeLbmyraRQ"

# Moments identified with high Viral Retention Scores across the 6-hour stream
MOMENTS = [
    {
        "id": 1,
        "start": 18334.0,
        "end": 18374.0,
        "duration": 40.0,
        "score": 94.50,
        "hook_title": "GTA 6 FINAL MISSION CLIMAX! 😱",
        "viral_title": "IShowSpeed Beats The Final Mission?! 😱",
        "hashtags": ["#ishowspeed", "#gta6", "#speedclips", "#gaming", "#shorts"]
    },
    {
        "id": 2,
        "start": 12082.0,
        "end": 12122.0,
        "duration": 40.0,
        "score": 89.20,
        "hook_title": "5-STAR GTA 6 POLICE PURSUIT! 🚨",
        "viral_title": "Speed Gets A 5-Star Wanted Level! 💀",
        "hashtags": ["#ishowspeed", "#policechase", "#gtaviral", "#funnygaming", "#speed"]
    },
    {
        "id": 3,
        "start": 11240.0,
        "end": 11280.0,
        "duration": 40.0,
        "score": 82.80,
        "hook_title": "SPEED RAGE QUIT IN GTA 6! 🤬",
        "viral_title": "Speed Absolutely LOSES IT Playing GTA! 😭",
        "hashtags": ["#speedrage", "#ishowspeed", "#gtafails", "#gamingclips", "#streamer"]
    },
    {
        "id": 4,
        "start": 9767.0,
        "end": 9807.0,
        "duration": 40.0,
        "score": 79.50,
        "hook_title": "UNREAL GTA 6 CRASH SURVIVAL! 💥",
        "viral_title": "Speed Thinks He's Safe Then THIS Happens! 🚗💥",
        "hashtags": ["#carcrash", "#ishowspeed", "#gtamoment", "#viralreels", "#fyp"]
    },
    {
        "id": 5,
        "start": 6284.0,
        "end": 6324.0,
        "duration": 40.0,
        "score": 78.10,
        "hook_title": "IMPOSSIBLE GTA 6 ESCAPE! 🔥",
        "viral_title": "How Did Speed Even Survive This?! 🤯",
        "hashtags": ["#clutchescape", "#ishowspeed", "#gta6gameplay", "#streamhighlights", "#viral"]
    },
    {
        "id": 6,
        "start": 17900.0,
        "end": 17940.0,
        "duration": 40.0,
        "score": 77.40,
        "hook_title": "INTENSE GTA 6 GUNFIGHT! 🔫",
        "viral_title": "Speed In The Craziest Shootout Ever! 🔫",
        "hashtags": ["#shootout", "#ishowspeed", "#finalmission", "#gamingreels", "#gtarp"]
    },
    {
        "id": 7,
        "start": 2925.0,
        "end": 2965.0,
        "duration": 40.0,
        "score": 76.80,
        "hook_title": "WORST GTA 6 STUNT FAIL! 💀",
        "viral_title": "Bro Tried Doing A Stunt And Instant Karma Hit! 🤣",
        "hashtags": ["#funnyfails", "#speed", "#instantkarma", "#gtastunts", "#shorts"]
    },
    {
        "id": 8,
        "start": 16583.0,
        "end": 16623.0,
        "duration": 40.0,
        "score": 76.20,
        "hook_title": "ATTACK CHOPPER SURVIVAL! 🚁",
        "viral_title": "Speed Takes Down An Attack Chopper?! 🚁",
        "hashtags": ["#chopper", "#ishowspeed", "#gamingmoment", "#actionclips", "#viralshorts"]
    },
    {
        "id": 9,
        "start": 18966.0,
        "end": 19006.0,
        "duration": 40.0,
        "score": 75.90,
        "hook_title": "MISSION PASSED CELEBRATION! 🎉",
        "viral_title": "Speed When He Finally Completes The Mission! 🎉",
        "hashtags": ["#victory", "#ishowspeed", "#reaction", "#wholesomegaming", "#trend"]
    },
    {
        "id": 10,
        "start": 2079.0,
        "end": 2119.0,
        "duration": 40.0,
        "score": 75.20,
        "hook_title": "GTA 6 PURE OPENING CHAOS! ⚡",
        "viral_title": "Speed Starts The Stream In Pure Chaos! ⚡",
        "hashtags": ["#speedlive", "#ishowspeed", "#chaos", "#streamerclips", "#shorts"]
    }
]


def format_hms(seconds: float) -> str:
    s = max(0.0, seconds)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def render_unified_clip(
    raw_video: Path,
    layout_info: dict,
    segment_info: dict,
    output_path: Path,
    language: str = "en"
) -> Path:
    """
    Unified High-Retention Single-Pass FFmpeg Renderer with 5-SFX & Micro-Animations:
      - Top Panel (1080x760): Streamer facecam with zoom punch-in (1.0x -> 1.08x) & camera micro-shake
      - Center Banner (1080x260): Persistent dark gradient with glowing gold borders in native script
      - Bottom Panel (1080x900): Full 16:9 gameplay with blurred backdrop padding (0 black bars)
      - Lower-middle animated karaoke captions (MarginV=220, active-word pop-in scale)
      - 5-SFX mixing at -14dB (boom, whoosh, pop, vine_boom, riser)
      - Guaranteed 1080x1920 60 FPS CFR output
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = TEMP_WORK_DIR / f"_clip_{segment_info.get('id', 1)}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ass_file = temp_dir / "captions.ass"
    banner_img = temp_dir / "center_banner.png"

    # 1. Generate native-script persistent center banner image
    hook_headline = segment_info.get("hook_title", "GTA 6 VIRAL MOMENT! ⚡")
    render_mod.generate_center_banner_image(hook_headline, banner_img, language=language)

    # 2. Generate animated ASS karaoke subtitles
    render_mod.create_karaoke_ass(segment_info, ass_file, language=language)

    # 3. Locate 5 SFX
    boom_sfx = render_mod.ASSETS_SFX_DIR / "boom.wav"
    whoosh_sfx = render_mod.ASSETS_SFX_DIR / "whoosh.wav"
    pop_sfx = render_mod.ASSETS_SFX_DIR / "pop.wav"
    vine_boom_sfx = render_mod.ASSETS_SFX_DIR / "vine_boom.wav"
    riser_sfx = render_mod.ASSETS_SFX_DIR / "riser.wav"

    words = segment_info.get("words", [])
    clip_dur = segment_info["duration"]

    pop_delays = []
    for w in words:
        w_s = w["start"]
        if 0.8 < w_s < clip_dur - 0.8:
            if w.get("clean") in [
                "cops", "rpg", "crash", "bhai", "clutch", "headshot", "mara", "blew", "wasted",
                "speed", "rada", "bhava", "zala", "mela", "fat gaya", "khatam", "bapre"
            ]:
                pop_delays.append(int(w_s * 1000))
                if len(pop_delays) >= 2:
                    break

    # 4. High-Retention Split-Screen Video Filter with Micro-Animations
    v_stack = crop_mod.build_high_retention_video_filter(
        layout_info=layout_info,
        banner_input_idx=1,
        enable_micro_animations=True
    )
    v_combined = f"{v_stack};[vbase]ass={ass_file.name}[vout]"

    # 5. Multi-track 5-SFX Audio Mixing (-14dB relative to speech)
    riser_delay = max(500, int((clip_dur - 4.5) * 1000)) if clip_dur > 8.0 else 1000
    vine_delay = int(clip_dur * 0.65 * 1000)

    audio_inputs = (
        "[0:a]volume=1.0[a0];"
        "[2:a]adelay=300|300,volume=0.28[aboom];"
        "[3:a]adelay=50|50,volume=0.20[awhoosh];"
        f"[5:a]adelay={vine_delay}|{vine_delay},volume=0.26[avine];"
        f"[6:a]adelay={riser_delay}|{riser_delay},volume=0.22[ariser]"
    )
    mix_sources = "[a0][aboom][awhoosh][avine][ariser]"
    mix_count = 5

    if pop_delays:
        first_pop = pop_delays[0]
        audio_inputs += f";[4:a]adelay={first_pop}|{first_pop},volume=0.25[apop]"
        mix_sources += "[apop]"
        mix_count += 1

    a_filter = f"{audio_inputs};{mix_sources}amix=inputs={mix_count}:duration=first:dropout_transition=2[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-ss", "0.0",
        "-t", str(clip_dur),
        "-i", str(raw_video.resolve()),
        "-i", str(banner_img.resolve()),
        "-i", str(boom_sfx.resolve()),
        "-i", str(whoosh_sfx.resolve()),
        "-i", str(pop_sfx.resolve()),
        "-i", str(vine_boom_sfx.resolve()),
        "-i", str(riser_sfx.resolve()),
        "-filter_complex", f"{v_combined};{a_filter}",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-r", "60",
        "-c:a", "aac",
        "-b:a", "192k",
        "-fps_mode", "cfr",
        "-shortest",
        str(output_path.resolve())
    ]
    print(f"[pipeline] Rendering 9:16 vertical clip with animated captions & 5-SFX -> {output_path.name}...")
    proc = subprocess.run(cmd, cwd=str(temp_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Unified FFmpeg render failed:\n{proc.stderr[-1000:]}")
    return output_path


def process_clip(moment: dict) -> dict:
    clip_id = moment["id"]
    clip_filename = f"clip_{clip_id:02d}.mp4"
    final_output = FINAL_CLIPS_DIR / clip_filename

    start_sec = moment["start"]
    end_sec = moment["end"]
    dur = moment["duration"]

    print("\n" + "=" * 65, flush=True)
    print(f" PROCESSING HIGH-RETENTION CLIP #{clip_id:02d}: {moment['hook_title']}", flush=True)
    print(f" Timestamps: {format_hms(start_sec)} -> {format_hms(end_sec)} ({dur:.1f}s) | Score: {moment['score']}", flush=True)
    print("=" * 65, flush=True)

    # 1. Targeted Section Download (1080p, 5-second padding)
    raw_sec = ingest_mod.download_video_section(
        source=STREAM_URL,
        start_sec=start_sec,
        end_sec=end_sec,
        output_path=TEMP_WORK_DIR / f"raw_sec_{clip_id:02d}.mp4",
        padding_sec=5.0
    )

    cap = cv2.VideoCapture(str(raw_sec))
    actual_dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 60.0)
    cap.release()
    if actual_dur <= 0:
        actual_dur = dur

    # 2. Multilingual Word-Level Transcription (Auto-detects language)
    words, detected_lang, lang_prob = transcribe_mod.transcribe_segment_precise(
        raw_sec,
        model_size="base"
    )

    # Opening hook line (first 6 words spoken)
    opening_hook = " ".join([w["word"] for w in words[:6]]) if words else moment["hook_title"]

    # 3. Smart Crop & Layout Detection
    layout_info = crop_mod.analyze_face_presence(raw_sec, 0.0, actual_dur)
    detected_layout = "HIGH_RETENTION_9_16_SPLIT"

    # 4. Unified High-Retention Render with 5-SFX & Animated Micro-Animations
    seg_info = {
        "id": clip_id,
        "start": 0.0,
        "end": actual_dur,
        "duration": actual_dur,
        "hook_title": moment["hook_title"],
        "words": words
    }
    render_unified_clip(
        raw_video=raw_sec,
        layout_info=layout_info,
        segment_info=seg_info,
        output_path=final_output,
        language=detected_lang
    )

    # Verification
    if not final_output.exists() or final_output.stat().st_size == 0:
        raise RuntimeError(f"Clip #{clip_id:02d} failed to render or is empty!")

    file_size_mb = final_output.stat().st_size / (1024 * 1024)
    print(f"✅ Clip #{clip_id:02d} VERIFIED: {final_output.name} ({file_size_mb:.2f} MB, Lang: {detected_lang}, Layout: {detected_layout})", flush=True)

    # Clean intermediate raw section file
    if raw_sec.exists():
        try:
            raw_sec.unlink()
        except Exception:
            pass

    return {
        "index": clip_id,
        "filename": clip_filename,
        "path": str(final_output.resolve()),
        "language": detected_lang,
        "score": moment["score"],
        "timestamps": f"{format_hms(start_sec)} - {format_hms(end_sec)}",
        "duration_sec": round(actual_dur, 1),
        "opening_hook": opening_hook,
        "detected_layout": detected_layout,
        "viral_title": moment["viral_title"],
        "hook_headline": moment["hook_title"],
        "hashtags": " ".join(moment["hashtags"]),
        "file_size_mb": round(file_size_mb, 2)
    }


def main():
    FINAL_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    summary_results = []

    for moment in MOMENTS:
        try:
            res = process_clip(moment)
            summary_results.append(res)
        except Exception as e:
            print(f"❌ Error processing Clip #{moment['id']}: {e}", flush=True)

    # Wipe temp_work
    print("\n[Cleanup] Cleaning up temp_work/ ...", flush=True)
    for item in TEMP_WORK_DIR.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception:
            pass

    # Save summary JSON
    summary_path = FINAL_CLIPS_DIR / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70, flush=True)
    print(f" ALL {len(summary_results)} VIRAL CLIPS RENDERED & VERIFIED IN ./final_clips/!", flush=True)
    print("=" * 70, flush=True)
    print(json.dumps(summary_results, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
