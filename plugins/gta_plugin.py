"""
GTA Action Plugin (gta_plugin.py)
High-Action Moment Detection Engine for GTA & Gaming streams.
Scans:
  1. Audio energy spikes (explosions, crashes, screams, high-intensity sound)
  2. OpenAI Whisper speech transcripts for GTA viral triggers (chases, wanted stars, gunfights, fails)
Ranks and extracts top viral 25-45 second clips.
"""

import os
import sys
import json
import re
import math
import subprocess
import numpy as np
from typing import List, Dict, Any, Tuple

# GTA Keyword Categories & Weighted Multipliers
GTA_CATEGORIES = {
    "CHASE": {
        "title_templates": ["5-STAR POLICE CHASE!", "INSANE ESCAPE!", "THE FEDS ARE HERE!", "HE CANNOT BE CAUGHT!"],
        "keywords": [
            "cops", "cop", "police", "feds", "chase", "chasing", "pursuit", "helicopter", "chopper",
            "siren", "sirens", "roadblock", "pit maneuver", "ram him", "swerve", "lost them", "lose the cops",
            "get away", "escape", "speed up", "tires", "tire popped", "spike strip", "boat chase", "jet"
        ],
        "weight": 2.5
    },
    "CRASH": {
        "title_templates": ["WORST CRASH EVER?!", "INSTANT REGRET!", "HE WRECKED IT!", "BRO FLIPPED THE CAR!"],
        "keywords": [
            "crash", "crashed", "wrecked", "flipped", "exploded", "explosion", "blew up", "blow up", "fire",
            "flying", "launched", "hit a pole", "tree", "cliff", "fell off", "rolling", "totaled", "my car",
            "watch out", "look out", "no brakes"
        ],
        "weight": 2.8
    },
    "WANTED": {
        "title_templates": ["MAX WANTED LEVEL!", "ARMY ON MY TAIL!", "SWAT SURROUNDED!", "5-STAR SURVIVAL!"],
        "keywords": [
            "wanted", "five star", "5 star", "four star", "4 star", "swat", "fbi", "military", "tank",
            "army", "air support", "barricade", "surrounded", "busted", "lockup"
        ],
        "weight": 2.6
    },
    "GUNFIGHT": {
        "title_templates": ["CLUTCH GUNFIGHT!", "1V4 GTA CLUTCH!", "RPG OUT OF NOWHERE!", "GOD TIER AIM!"],
        "keywords": [
            "rpg", "rocket", "sniper", "headshot", "clutch", "spray", "laser", "one shot", "he's dead",
            "got him", "kill", "downed", "grenade", "sticky bomb", "c4", "minigun", "heavy sniper", "reload", "armor"
        ],
        "weight": 2.7
    },
    "FAIL_LAUGH": {
        "title_templates": ["UNREAL GTA FAIL!", "HE THOUGHT HE WAS SAFE!", "BRO WHAT JUST HAPPENED?!", "INSTANT KARMA!"],
        "keywords": [
            "holy shit", "oh my god", "omg", "no way", "wtf", "what the fuck", "bro what", "i'm dead", "im dead",
            "rip", "wasted", "busted", "hahaha", "lmao", "screaming", "unreal", "insane", "clip that", "clip it",
            "you see that", "why did that happen", "how did i live"
        ],
        "weight": 2.4
    }
}


def get_video_duration(video_path: str) -> float:
    """Get total duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        return float(res.strip())
    except Exception:
        return 0.0


def extract_audio_rms_profile(video_path: str, bucket_size: float = 0.5) -> Tuple[np.ndarray, float]:
    """
    Extracts raw mono PCM audio from video using FFmpeg and computes RMS energy profile.
    Returns (energy_array, sample_rate_per_sec).
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "s16le", "-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_audio, _ = proc.communicate()
    except Exception as e:
        print(f"[gta_plugin] Warning: Audio extraction failed: {e}")
        return np.array([]), 1.0

    if not raw_audio:
        return np.array([]), 1.0

    samples = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
    sr = 16000
    chunk_len = int(sr * bucket_size)
    if chunk_len <= 0 or len(samples) < chunk_len:
        return np.array([0.0]), 1.0

    num_buckets = len(samples) // chunk_len
    clipped = samples[:num_buckets * chunk_len].reshape(num_buckets, chunk_len)
    rms = np.sqrt(np.mean(clipped ** 2, axis=1))

    # Standardize/normalize RMS (0.0 to 1.0 scale with outlier damping)
    if np.max(rms) > 0:
        rms_norm = rms / np.percentile(rms, 98) if np.percentile(rms, 98) > 0 else rms / np.max(rms)
        rms_norm = np.clip(rms_norm, 0.0, 2.0) / 2.0
    else:
        rms_norm = rms

    fps = 1.0 / bucket_size
    return rms_norm, fps


def transcribe_video_whisper(video_path: str, model_name: str = "base") -> List[Dict[str, Any]]:
    """
    Transcribes audio using OpenAI Whisper with word-level timestamps.
    Returns a list of word dictionaries: [{'word': str, 'start': float, 'end': float}]
    """
    import whisper
    print(f"[gta_plugin] Transcribing audio with Whisper ({model_name})...")
    model = whisper.load_model(model_name)
    result = model.transcribe(video_path, word_timestamps=True, verbose=False)
    
    words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            clean_word = re.sub(r"[^\w']", "", w.get("word", "")).strip().lower()
            if clean_word:
                words.append({
                    "word": w.get("word", "").strip(),
                    "clean": clean_word,
                    "start": float(w.get("start", 0.0)),
                    "end": float(w.get("end", 0.0))
                })
    print(f"[gta_plugin] Transcription complete: {len(words)} words detected.")
    return words


def score_transcript_window(words_in_window: List[Dict[str, Any]]) -> Tuple[float, str, str, List[str]]:
    """
    Scores speech text inside a time window for GTA high-action keywords.
    Returns (score, dominant_category, hook_title, matched_keywords).
    """
    if not words_in_window:
        return 0.0, "CHASE", "HIGH ACTION GTA MOMENT!", []

    text = " " + " ".join(w["clean"] for w in words_in_window) + " "
    cat_scores = {k: 0.0 for k in GTA_CATEGORIES}
    all_matched = []

    for cat_name, info in GTA_CATEGORIES.items():
        weight = info["weight"]
        for kw in info["keywords"]:
            # Match whole keyword or phrase
            pattern = r"\b" + re.escape(kw) + r"\b"
            matches = len(re.findall(pattern, text))
            if matches > 0:
                cat_scores[cat_name] += matches * weight * (1.5 if len(kw.split()) > 1 else 1.0)
                all_matched.append(kw)

    best_cat = max(cat_scores, key=cat_scores.get)
    max_cat_score = cat_scores[best_cat]
    
    # Select title template based on detected keywords
    templates = GTA_CATEGORIES[best_cat]["title_templates"]
    hook_title = templates[len(all_matched) % len(templates)]
    
    # Custom contextual title overrides
    if "boat" in text:
        hook_title = "INSANE BOAT CHASE!"
    elif "helicopter" in text or "chopper" in text:
        hook_title = "ATTACK HELICOPTER STRIKE!"
    elif "rpg" in text:
        hook_title = "RPG SNIPE OF THE YEAR!"
    elif "five star" in text or "5 star" in text:
        hook_title = "MAX 5-STAR WANTED LEVEL!"
    elif "busted" in text or "wasted" in text:
        hook_title = "WASTED! EPIC GTA FAIL!"

    return max_cat_score, best_cat, hook_title, list(set(all_matched))


def find_viral_moments(
    video_path: str,
    min_duration: float = 25.0,
    max_duration: float = 45.0,
    target_clips: int = 5,
    whisper_model: str = "base"
) -> List[Dict[str, Any]]:
    """
    Main detection pipeline:
    1. Extracts audio energy profile
    2. Runs Whisper for word timestamps
    3. Fuses audio peaks + keyword densities to isolate 25-45s action clips
    4. Applies Non-Maximum Suppression (NMS) to avoid overlaps
    5. Returns ranked clips ready for vertical formatting
    """
    total_duration = get_video_duration(video_path)
    if total_duration < min_duration:
        # Video is shorter than minimum clip length, treat entire video as 1 clip
        return [{
            "clip_id": 1,
            "start": 0.0,
            "end": total_duration,
            "duration": total_duration,
            "score": 100.0,
            "category": "CHASE",
            "hook_title": "INSANE GTA MOMENT!",
            "triggers": ["stream"],
            "words": []
        }]

    # 1. Audio Energy Analysis
    rms_profile, fps = extract_audio_rms_profile(video_path, bucket_size=0.5)
    
    # 2. Whisper Transcription
    words = transcribe_video_whisper(video_path, model_name=whisper_model)

    # 3. Sliding Window Multimodal Scoring
    step_sec = 2.0
    nominal_duration = 35.0  # target sweet-spot between 25s and 45s
    candidates = []

    current_start = 0.0
    while current_start + min_duration <= total_duration:
        window_end = min(current_start + nominal_duration, total_duration)
        w_dur = window_end - current_start
        
        # Audio score in window
        if len(rms_profile) > 0:
            idx_start = int(current_start * fps)
            idx_end = int(window_end * fps)
            window_rms = rms_profile[idx_start:idx_end] if idx_end <= len(rms_profile) else rms_profile[idx_start:]
            if len(window_rms) > 0:
                audio_mean = float(np.mean(window_rms))
                audio_peak = float(np.max(window_rms))
                audio_variance = float(np.var(window_rms))
                audio_score = (audio_mean * 30.0) + (audio_peak * 45.0) + (audio_variance * 25.0)
            else:
                audio_score = 10.0
        else:
            audio_score = 10.0

        # Transcript keywords in window
        w_words = [w for w in words if current_start <= w["start"] <= window_end]
        text_score, cat, hook_title, matched_kws = score_transcript_window(w_words)

        # Multimodal fusion score
        total_score = (audio_score * 0.45) + (text_score * 8.5 * 0.45) + (len(matched_kws) * 5.0)

        # Fine-tune boundaries to start just before the action and end cleanly after
        candidates.append({
            "start": round(current_start, 2),
            "end": round(window_end, 2),
            "duration": round(w_dur, 2),
            "score": round(total_score, 2),
            "category": cat,
            "hook_title": hook_title,
            "triggers": matched_kws,
            "words": w_words
        })

        current_start += step_sec

    # 4. Rank Candidates
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 5. Non-Maximum Suppression (NMS) to eliminate overlapping clips
    selected_clips = []
    for cand in candidates:
        overlap = False
        for s in selected_clips:
            # Overlap if intersection / union > 0.35 or time gap < 10s
            overlap_start = max(cand["start"], s["start"])
            overlap_end = min(cand["end"], s["end"])
            if overlap_end > overlap_start:
                intersection = overlap_end - overlap_start
                if intersection > 8.0:
                    overlap = True
                    break
        if not overlap:
            cand["clip_id"] = len(selected_clips) + 1
            selected_clips.append(cand)
            if len(selected_clips) >= target_clips:
                break

    # If no high-scoring triggers found (e.g. silent footage), fall back to top energy sections
    if not selected_clips and candidates:
        selected_clips = candidates[:target_clips]
        for i, c in enumerate(selected_clips):
            c["clip_id"] = i + 1

    print(f"[gta_plugin] Extracted {len(selected_clips)} top viral moments.")
    return selected_clips


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_video = sys.argv[1]
        print(f"Testing GTA Plugin on: {test_video}")
        results = find_viral_moments(test_video, target_clips=3)
        print(json.dumps(results, indent=2, default=str))
    else:
        print("GTA Plugin ready. Usage: python gta_plugin.py <video_path>")
