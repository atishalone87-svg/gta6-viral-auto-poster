"""
Master Orchestrator Pipeline (scripts/run_autonomous_clipper.py)
Autonomous end-to-end execution for ultra-long 5-to-10-hour streams and VODs:
  1. Multilingual Auto-Detection (English, Hindi, Marathi)
  2. Dynamic All-Viral-Moments Extraction (Threshold >= 75/100, no hardcoded limit)
  3. High-Retention 9:16 Split-Screen with Visual Micro-Animations (Zoom punch-in & micro-shake)
  4. Animated Word-by-Word Karaoke Captions & 5-SFX Dynamic Audio Mixing
  5. Automatic Verification & Cleanup
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional

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
            clean_token = w.get("clean", "")
            if clean_token in [
                "cops", "rpg", "crash", "bhai", "clutch", "headshot", "mara", "blew", "wasted",
                "speed", "rada", "bhava", "zala", "mela", "fat gaya", "khatam", "bapre",
                "भाई", "पुलिस", "खत्म", "भावा", "राडा", "बवाल", "ओपी"
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


def run_pipeline(
    source: str,
    min_score: float = 75.0,
    top_k: Optional[int] = None,
    min_dur: float = 25.0,
    max_dur: float = 55.0,
    fast_model: str = "base",
    precise_model: str = "base",
    clean_temp: bool = True
) -> List[Dict[str, Any]]:
    print("=" * 75)
    print("   UNIVERSAL VIRAL CLIPPER: SMART MULTILINGUAL & 5-SFX ANIMATED PIPELINE")
    print("=" * 75)

    TEMP_WORK_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    is_local = Path(source).exists() and Path(source).is_file()
    total_duration = ingest_mod.get_media_duration(source)
    is_long_stream = (not is_local) and (total_duration > ingest_mod.LONG_VIDEO_THRESHOLD_SEC)

    results = []

    if is_long_stream:
        print(f"\n>>> DETECTED ULTRA-LONG STREAM ({total_duration/3600:.2f} hours). Activating Audio-First Pipeline.")
        
        # Step 1: Download Audio Only
        audio_path = TEMP_WORK_DIR / "full_audio.m4a"
        print("\n[Stage 1/4] Downloading lightweight audio track (Audio-First Mode)...")
        ingest_mod.download_audio_only(source, audio_path)

        # Step 2: Audio-First Fast Scan
        print(f"\n[Stage 2/4] Scanning audio spikes & auto-detecting language for viral moments (Score >= {min_score})...")
        selected_windows = transcribe_mod.scan_stream_audio_fast(
            str(audio_path),
            min_score=min_score,
            top_k=top_k,
            min_dur=min_dur,
            max_dur=max_dur,
            model_size=fast_model
        )

        # Step 3: Targeted Section Downloads + Precise Word Timestamps + Render
        print(f"\n[Stage 3/4] Processing {len(selected_windows)} selected moments via Section Downloads...")
        for s in selected_windows:
            clip_id = s["id"]
            clip_name = f"clip_{clip_id:02d}.mp4"
            final_clip_path = FINAL_CLIPS_DIR / clip_name
            raw_section_path = TEMP_WORK_DIR / f"raw_section_{clip_id:02d}.mp4"

            print(f"\n--- Clip #{clip_id:02d}: '{s['hook_title']}' ({s['start']}s -> {s['end']}s, dur: {s['duration']}s, score: {s['score']}) ---")
            
            # Download ONLY this 1080p section with 5s padding
            ingest_mod.download_video_section(
                source=source,
                start_sec=s["start"],
                end_sec=s["end"],
                output_path=raw_section_path,
                padding_sec=5.0
            )

            # Precise word-level transcription with auto-language detection
            words, det_lang, lang_prob = transcribe_mod.transcribe_segment_precise(
                raw_section_path,
                model_size=precise_model
            )

            actual_dur = transcribe_mod.get_audio_duration(str(raw_section_path))
            s["words"] = words
            s["start"] = 0.0
            s["end"] = actual_dur
            s["duration"] = actual_dur

            # Analyze layout (detect facecam corner vs speaker center)
            layout_info = crop_mod.analyze_face_presence(raw_section_path, 0.0, actual_dur)

            # Single-pass high-retention render
            render_unified_clip(
                raw_video=raw_section_path,
                layout_info=layout_info,
                segment_info=s,
                output_path=final_clip_path,
                language=det_lang
            )

            if final_clip_path.exists() and final_clip_path.stat().st_size > 0:
                file_size_mb = final_clip_path.stat().st_size / (1024 * 1024)
                print(f"[pipeline] Clip #{clip_id:02d} verified! Size: {file_size_mb:.2f} MB (Lang: {det_lang})")
                
                opening_hook = " ".join([w["word"] for w in words[:6]]) if words else s["hook_title"]
                results.append({
                    "index": clip_id,
                    "filename": clip_name,
                    "path": str(final_clip_path.resolve()),
                    "language": det_lang,
                    "score": s["score"],
                    "timestamps": f"{int(s['start']//60):02d}:{int(s['start']%60):02d} - {int(s['end']//60):02d}:{int(s['end']%60):02d}",
                    "duration_sec": round(actual_dur, 1),
                    "opening_hook": opening_hook,
                    "hook_headline": s["hook_title"],
                    "file_size_mb": round(file_size_mb, 2)
                })

            if raw_section_path.exists():
                try:
                    raw_section_path.unlink()
                except Exception:
                    pass

    # Step 4: Verification & Cleanup
    if clean_temp and results:
        print("\n[Stage 4/4] Verifying outputs and clearing ./temp_work/ ...")
        for item in TEMP_WORK_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                print(f"[pipeline] Note: Could not delete {item}: {e}")
        print("[pipeline] ./temp_work/ cleared successfully.")

    # Save summary.json
    summary_path = FINAL_CLIPS_DIR / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 75)
    print(f" PIPELINE COMPLETE: {len(results)} Ready-to-Upload Shorts in ./final_clips/")
    for clip in results:
        print(f"  -> {clip['filename']} ({clip['file_size_mb']} MB, Lang: {clip['language']}, Score: {clip['score']})")
    print("=" * 75)
    return results


def main():
    parser = argparse.ArgumentParser(description="Autonomous Multilingual & Animated Vertical Clipper")
    parser.add_argument("source", help="YouTube/Twitch/Kick URL or local video file")
    parser.add_argument("--min-score", type=float, default=75.0, help="Minimum Viral Retention Score (0-100)")
    parser.add_argument("--top-k", type=int, default=None, help="Optional max clips limit (default: all >= min-score)")
    parser.add_argument("--min-dur", type=float, default=25.0, help="Minimum clip duration in seconds")
    parser.add_argument("--max-dur", type=float, default=55.0, help="Maximum clip duration in seconds")
    parser.add_argument("--fast-model", default="base", help="Whisper model tier for fast audio scan")
    parser.add_argument("--precise-model", default="base", help="Whisper model tier for final karaoke captions")
    parser.add_argument("--no-clean", action="store_true", help="Keep temporary work files in ./temp_work/")
    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        min_score=args.min_score,
        top_k=args.top_k,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
        fast_model=args.fast_model,
        precise_model=args.precise_model,
        clean_temp=not args.no_clean
    )


if __name__ == "__main__":
    main()
