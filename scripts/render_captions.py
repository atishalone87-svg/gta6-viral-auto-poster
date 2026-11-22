"""
Phase 2 (Upgraded): Multilingual Karaoke Captions & 5-SFX Mixing Engine (scripts/render_captions.py)
Features:
  1. Multilingual Support (English, Hindi, Marathi):
     - Native Devanagari font (Nirmala UI / NirmalaB.ttf) for Hindi & Marathi
     - Bold Latin font (Arial Black) for English
     - Contextual native-language center hook banner
  2. Animated Karaoke Word-by-Word Subtitles:
     - Active-word highlight: #FFD700 bright gold (&H0000D7FF)
     - Kinetic pop-in scale animation: \\t(0,120,\\fscx120\\fscy120)\\t(120,240,\\fscx100\\fscy100)
     - Safe zone: MarginV=220 (lower-middle, above platform UI icons)
  3. Expanded 5-SFX Dynamic Audio Mixing:
     - boom.wav (0.3s hook impact)
     - whoosh.wav (0.05s opening transition swoosh)
     - pop.wav (action keyword pops)
     - vine_boom.wav (dramatic climax / shock fail)
     - riser.wav (suspense buildup)
     - Balanced audio mix at -14dB relative to speech
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

import pysubs2
from pysubs2 import SSAFile, SSAStyle, SSAEvent, Color
from PIL import Image, ImageDraw, ImageFont

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
FINAL_CLIPS_DIR = WORKSPACE_DIR / "final_clips"
ASSETS_SFX_DIR = WORKSPACE_DIR / "assets" / "sfx"
TEMP_WORK_DIR = WORKSPACE_DIR / "temp_work"


def get_font_for_language(language: str, bold: bool = True) -> str:
    """Returns absolute path to verified system font for language."""
    if language in ["hi", "mr"]:
        font_path = r"C:\Windows\Fonts\NirmalaB.ttf" if bold else r"C:\Windows\Fonts\Nirmala.ttf"
        if os.path.exists(font_path):
            return font_path
    # Default Latin font
    font_path = r"C:\Windows\Fonts\ariblk.ttf" if bold else r"C:\Windows\Fonts\arialbd.ttf"
    if os.path.exists(font_path):
        return font_path
    return r"C:\Windows\Fonts\arial.ttf"


def generate_center_banner_image(
    headline: str,
    output_path: Path,
    language: str = "en",
    width: int = 1080,
    height: int = 260
) -> Path:
    """
    Renders a solid dark-gradient / glowing center banner image (1080x260):
      - Dark gradient background (#0B0F19 to #161D2B)
      - Glowing gold borders (#FFD700) at top and bottom
      - Mini tag in detected language
      - Bold, high-curiosity viral hook headline in native script with thick black stroke
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    # 1. Dark gradient background
    for y in range(height):
        r = int(11 + (y / height) * 12)
        g = int(15 + (y / height) * 15)
        b = int(25 + (y / height) * 20)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # 2. Glowing gold borders (top and bottom)
    gold = (255, 215, 0)
    gold_dim = (180, 150, 0)
    draw.rectangle([(0, 0), (width, 5)], fill=gold)
    draw.rectangle([(0, 6), (width, 8)], fill=gold_dim)
    draw.rectangle([(0, height - 8), (width, height - 6)], fill=gold_dim)
    draw.rectangle([(0, height - 5), (width, height)], fill=gold)

    # 3. Mini header tag in detected language
    if language == "mr":
        tag_text = "★ व्हायरल हायलाइट्स ★"
        tag_font_path = get_font_for_language("mr", bold=True)
    elif language == "hi":
        tag_text = "★ वायरल हाइलाइट्स ★"
        tag_font_path = get_font_for_language("hi", bold=True)
    else:
        tag_text = "★ GTA VI VIRAL HIGHLIGHT ★"
        tag_font_path = get_font_for_language("en", bold=True)

    try:
        tag_font = ImageFont.truetype(tag_font_path, 28)
    except Exception:
        tag_font = ImageFont.load_default()
    
    tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.text(((width - tag_w) // 2, 26), tag_text, font=tag_font, fill=gold)

    # 4. Main Hook Headline in native script
    main_font_path = get_font_for_language(language, bold=True)
    clean_headline = headline.strip()
    if language == "en":
        clean_headline = clean_headline.upper()

    font_size = 50 if len(clean_headline) <= 24 else (44 if len(clean_headline) <= 30 else 36)
    try:
        main_font = ImageFont.truetype(main_font_path, font_size)
    except Exception:
        main_font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), clean_headline, font=main_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (width - tw) // 2
    ty = 85 + (height - 85 - th) // 2 - 4

    # Thick black stroke / outline
    for ox in range(-4, 5):
        for oy in range(-4, 5):
            if ox != 0 or oy != 0:
                draw.text((tx + ox, ty + oy), clean_headline, font=main_font, fill=(0, 0, 0))

    # Main text fill: Bright gold/yellow
    draw.text((tx, ty), clean_headline, font=main_font, fill=(255, 230, 0))

    img.save(str(output_path), format="PNG")
    return output_path


def create_karaoke_ass(
    segment_info: Dict[str, Any],
    ass_path: Path,
    language: str = "en"
):
    """
    Creates an ASS subtitle file with animated pop-in karaoke style active-word highlighting:
      - Font: 'Nirmala UI' for Marathi/Hindi, 'Arial Black' for English
      - Active word: #FFD700 (&H0000D7FF) with dynamic ASS pop-in scale:
        \\t(0,120,\\fscx120\\fscy120)\\t(120,240,\\fscx100\\fscy100)
      - Lower-middle safe zone: MarginV=220
    """
    clip_start = segment_info.get("start", 0.0)
    clip_dur = segment_info["duration"]
    words = segment_info.get("words", [])

    subs = SSAFile()
    subs.info["PlayResX"] = 1080
    subs.info["PlayResY"] = 1920
    subs.info["WrapStyle"] = 0

    # Subtitle Style per language
    style_caption = SSAStyle()
    if language in ["hi", "mr"]:
        style_caption.fontname = "Nirmala UI"
        style_caption.fontsize = 58
    else:
        style_caption.fontname = "Arial Black"
        style_caption.fontsize = 62

    style_caption.primarycolor = Color(255, 255, 255, 0)      # White
    style_caption.secondarycolor = Color(255, 215, 0, 0)     # Gold #FFD700
    style_caption.outlinecolor = Color(0, 0, 0, 0)           # Black
    style_caption.backcolor = Color(0, 0, 0, 128)
    style_caption.bold = True
    style_caption.outline = 5.5
    style_caption.shadow = 2.0
    style_caption.alignment = 2  # Bottom-Center
    style_caption.marginv = 220  # Safe zone: above platform icons, below center banner
    subs.styles["ViralDefault"] = style_caption

    time_offset = 0.0
    if words and words[0]["start"] >= clip_start and clip_start > 0:
        time_offset = clip_start

    rel_words = []
    for w in words:
        w_s = w["start"] - time_offset
        w_e = w["end"] - time_offset
        if 0.0 <= w_s < clip_dur:
            display_word = w["word"].strip().replace("{", "").replace("}", "")
            if language == "en":
                display_word = display_word.upper()
            rel_words.append({
                "word": display_word,
                "start_ms": int(max(0.0, w_s) * 1000),
                "end_ms": int(min(clip_dur, w_e) * 1000),
                "clean": w.get("clean", "")
            })

    # Group into 2 to 4 word phrases
    chunk_size = 3
    for i in range(0, len(rel_words), chunk_size):
        chunk = rel_words[i:i + chunk_size]
        if not chunk:
            continue

        c_start_ms = chunk[0]["start_ms"]
        c_end_ms = max(chunk[-1]["end_ms"], c_start_ms + 600)

        for active_idx, target_word in enumerate(chunk):
            w_start = target_word["start_ms"]
            w_end = max(target_word["end_ms"], w_start + 250)

            line_tokens = []
            for j, w in enumerate(chunk):
                if j == active_idx:
                    # Animated Pop-In Scale Effect: 100% -> 120% -> 100% in 240ms with #FFD700 bright gold
                    anim_tag = (
                        "{\\t(0,120,\\fscx120\\fscy120)"
                        "\\t(120,240,\\fscx100\\fscy100)"
                        "\\c&H0000D7FF&\\3c&H00000000&\\b1}"
                    )
                    line_tokens.append(f"{anim_tag}{w['word']}{{\\rViralDefault}}")
                else:
                    line_tokens.append(f"{{\\c&H00FFFFFF&\\3c&H00000000&\\b1}}{w['word']}")

            caption_text = " ".join(line_tokens)
            subs.events.append(SSAEvent(
                start=w_start,
                end=w_end,
                style="ViralDefault",
                text=caption_text
            ))

    subs.save(str(ass_path))
    print(f"[render_captions] Saved animated ASS subtitles ({language}): {ass_path}")


def render_final_clip(
    cropped_video: Path,
    segment_info: Dict[str, Any],
    output_path: Path,
    language: str = "en"
) -> Path:
    """
    Burns .ass subtitles into the cropped video and mixes the full 5-SFX pack at -14dB:
      - boom.wav (0.3s hook impact)
      - whoosh.wav (0.05s transition)
      - pop.wav (action keywords)
      - vine_boom.wav (mid-clip shock/fail trigger)
      - riser.wav (suspense buildup before climax)
    Renders 1080x1920 60 FPS CFR MP4.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = TEMP_WORK_DIR / f"_clip_{segment_info.get('id', 1)}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ass_file = temp_dir / "captions.ass"

    create_karaoke_ass(segment_info, ass_file, language=language)

    boom_sfx = ASSETS_SFX_DIR / "boom.wav"
    whoosh_sfx = ASSETS_SFX_DIR / "whoosh.wav"
    pop_sfx = ASSETS_SFX_DIR / "pop.wav"
    vine_boom_sfx = ASSETS_SFX_DIR / "vine_boom.wav"
    riser_sfx = ASSETS_SFX_DIR / "riser.wav"

    clip_start = segment_info.get("start", 0.0)
    clip_dur = segment_info["duration"]
    words = segment_info.get("words", [])

    time_offset = 0.0
    if words and words[0]["start"] >= clip_start and clip_start > 0:
        time_offset = clip_start

    pop_delays = []
    for w in words:
        w_s = w["start"] - time_offset
        if 0.8 < w_s < clip_dur - 0.8:
            if w.get("clean") in [
                "cops", "rpg", "crash", "bhai", "clutch", "headshot", "mara", "blew", "wasted",
                "rada", "bhava", "zala", "mela", "fat gaya", "khatam", "bapre"
            ]:
                pop_delays.append(int(w_s * 1000))
                if len(pop_delays) >= 2:
                    break

    # Riser and Vine Boom timings
    # Riser builds up leading to climax (e.g. 5 seconds before end)
    riser_delay = max(500, int((clip_dur - 4.5) * 1000)) if clip_dur > 8.0 else 1000
    # Vine boom on a dramatic twist around 65% of the clip
    vine_delay = int(clip_dur * 0.65 * 1000)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(cropped_video.resolve()),
        "-i", str(boom_sfx.resolve()),
        "-i", str(whoosh_sfx.resolve()),
        "-i", str(pop_sfx.resolve()),
        "-i", str(vine_boom_sfx.resolve()),
        "-i", str(riser_sfx.resolve())
    ]

    v_filter = f"ass={ass_file.name}"

    # Balanced SFX levels at -14dB relative to speech (speech vol=1.0, SFX vol=0.20-0.28)
    audio_inputs = (
        "[0:a]volume=1.0[a0];"
        "[1:a]adelay=300|300,volume=0.28[aboom];"
        "[2:a]adelay=50|50,volume=0.20[awhoosh];"
        f"[4:a]adelay={vine_delay}|{vine_delay},volume=0.26[avine];"
        f"[5:a]adelay={riser_delay}|{riser_delay},volume=0.22[ariser]"
    )
    mix_sources = "[a0][aboom][awhoosh][avine][ariser]"
    mix_count = 5

    if pop_delays:
        first_pop = pop_delays[0]
        audio_inputs += f";[3:a]adelay={first_pop}|{first_pop},volume=0.25[apop]"
        mix_sources += "[apop]"
        mix_count += 1

    a_filter = f"{audio_inputs};{mix_sources}amix=inputs={mix_count}:duration=first:dropout_transition=2[aout]"

    cmd += [
        "-filter_complex", f"[0:v]{v_filter}[vout];{a_filter}",
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

    print(f"[render_captions] Burning subtitles & mixing 5 SFX into: {output_path.name}...")
    proc = subprocess.run(cmd, cwd=str(temp_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg caption rendering failed:\n{proc.stderr[-1000:]}")

    print(f"[render_captions] Successfully generated final clip: {output_path} ({output_path.stat().st_size / (1024*1024):.2f} MB)")
    return output_path.resolve()


def main():
    parser = argparse.ArgumentParser(description="Multilingual Karaoke Subtitle & 5-SFX Video Renderer")
    parser.add_argument("video", help="Input cropped 1080x1920 video path")
    parser.add_argument("--segment-json", required=True, help="Path to segment JSON description")
    parser.add_argument("--language", default="en", help="Spoken language code (en, hi, mr)")
    parser.add_argument("--output", default=str(FINAL_CLIPS_DIR / "clip_01.mp4"), help="Output video path")
    args = parser.parse_args()

    with open(args.segment_json, "r", encoding="utf-8") as f:
        seg_data = json.load(f)

    render_final_clip(
        cropped_video=Path(args.video),
        segment_info=seg_data,
        output_path=Path(args.output),
        language=args.language
    )


if __name__ == "__main__":
    main()
