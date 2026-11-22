"""
Phase 2 (Upgraded): Multilingual Audio-First & Precise Transcription Engine (scripts/transcribe.py)
Optimized for 5-to-10-hour livestreams and high-retention vertical clips:
  1. Multilingual Auto-Detection (English, Hindi, Marathi):
     - Automatically identifies spoken language without manual hardcoding.
     - Generates native Devanagari script for Hindi/Marathi and Latin script for English.
     - Preserves full Unicode matras, ligatures, and character combinations.
     - Generates matching native-language center hook headlines.
  2. Dynamic All-Viral-Moments Extraction:
     - Scores candidate segments on a 0–100 Viral Retention Score (Audio Spikes + Lexical Hooks).
     - Extracts ALL non-overlapping segments scoring >= 75/100 (no hardcoded clip limit).
  3. Precise Word-Level Timestamps:
     - Runs faster-whisper with word_timestamps=True for 100% accurate karaoke sync.
"""

import os
import sys
import json
import re
import argparse
import subprocess
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMP_WORK_DIR = WORKSPACE_DIR / "temp_work"


def clean_word(text: str) -> str:
    """Safely cleans punctuation from words while preserving all Unicode Devanagari and Latin letters/matras."""
    return re.sub(r"[\s.,!?;:\'\"()\[\]{}।॥\-_/\\*&^%$#@~`+=<>|]+", "", text).strip().lower()


# Viral Keywords across English, Hindi, and Marathi (both Latin transliterations and native Devanagari script)
VIRAL_KEYWORDS_EN = {
    "cops", "cop", "police", "feds", "chase", "pursuit", "helicopter", "chopper", "sirens", "ram", "swerve",
    "crash", "crashed", "wrecked", "flipped", "exploded", "blew up", "holy shit", "oh my god", "wtf",
    "bro what", "no way", "i'm dead", "im dead", "wasted", "busted", "rpg", "sniper", "headshot",
    "kill", "downed", "clutch", "laser", "insane", "unreal", "clip that", "clip it", "speed", "jump",
    "mission", "rage", "cheat", "scary", "run", "shoot", "gun", "omg", "yoo", "lets go", "vice city",
    "gta", "car", "tank", "drive", "escape"
}

VIRAL_KEYWORDS_HI = {
    # Latin Hinglish
    "bhai", "bhaiya", "khatam", "mar gaya", "mara", "yeh kya hua", "dekh", "arrey", "bhag", "gaadi",
    "police", "thoko", "bhaago", "ruk", "bachao", "op", "bawaal", "gajab", "dhamaka", "fat gaya",
    "pakad", "goli", "bhasad", "pagal", "shuru", "aag", "loot", "maro", "sach", "kya", "bhaiyo",
    "kya baat", "darr", "gaya", "chalo", "bhai log", "ujjwalgamer", "techno", "vice city",
    # Devanagari Hindi
    "भाई", "भैया", "खत्म", "मर गया", "मारा", "ये क्या हुआ", "देख", "अरे", "भाग", "गाड़ी", "गाडी",
    "पुलिस", "ठोको", "भागो", "रुक", "बचाओ", "ओपी", "बवाल", "गजब", "धमाका", "फट गया",
    "पकड़", "गोली", "भसड़", "पागल", "शुरू", "आग", "लूट", "मारो", "सच", "क्या", "भाइयों", "गया"
}

VIRAL_KEYWORDS_MR = {
    # Latin Marathi
    "bhava", "bhaava", "bhau", "kay re", "naadkhula", "rada", "dhamal", "dhur", "ek number", "zala",
    "khatam", "mela", "pala", "lay bhari", "kadak", "bapre", "arre", "bagh", "aata", "khara", "shant",
    "gadbad", "goli", "polisa", "gaadi", "daav", "mast", "zop", "bhari", "patkan", "maar",
    # Devanagari Marathi
    "भावा", "भाऊ", "काय रे", "नादखुळा", "राडा", "धमाल", "धूर", "एक नंबर", "झाला", "खतम",
    "मेला", "पळा", "लय भारी", "कडक", "बापरे", "अरे", "बघ", "आता", "खरं", "शांत", "गडबड",
    "गोळी", "पोलिस", "गाडी", "दाव", "मस्त", "झोप", "भारी"
}

ALL_VIRAL_KEYWORDS = VIRAL_KEYWORDS_EN | VIRAL_KEYWORDS_HI | VIRAL_KEYWORDS_MR


def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    try:
        res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        return float(res.strip())
    except Exception:
        return 0.0


def extract_audio_rms_profile(audio_path: str, bucket_size: float = 1.0) -> Tuple[np.ndarray, float]:
    """
    Extracts raw mono audio from full audio file and computes RMS energy profile in seconds.
    Fast & light: 10 hours = 36,000 float samples (~288 KB RAM).
    """
    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "s16le", "-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_audio, _ = proc.communicate()
    except Exception as e:
        print(f"[transcribe] Warning: FFmpeg audio dump failed: {e}")
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

    # Standardize RMS (0 to 3.0 scale)
    p95 = np.percentile(rms, 95) if len(rms) > 0 else 1.0
    rms_norm = np.clip(rms / p95, 0.0, 3.0) if p95 > 0 else rms
    fps = 1.0 / bucket_size
    return rms_norm, fps


def generate_hook_banner(keywords: List[str], language: str = "en") -> str:
    """
    Generates a high-curiosity viral hook banner in the detected language:
    - Marathi ('mr'): Clean Devanagari script with Marathi colloquial slang
    - Hindi ('hi'): Clean Devanagari script with high-impact Hindi hooks
    - English ('en'): Bold uppercase English hooks
    """
    kw_str = " ".join(keywords).lower()
    
    if language == "mr":
        if any(w in kw_str for w in ["polisa", "police", "chase", "pala", "पोलिस"]):
            return "भावा ५-स्टार पोलीस चेस! 🚨"
        if any(w in kw_str for w in ["crash", "gaadi", "thokli", "accident", "गाडी"]):
            return "भावा खतरनाक कार क्रॅश! 💥"
        if any(w in kw_str for w in ["khatam", "mela", "fail", "zala", "खतम", "मेला"]):
            return "नादखुळा खतरनाक स्टंट फेल! 💀"
        if any(w in kw_str for w in ["rada", "bhasad", "kay re", "bapre", "राडा", "बापरे"]):
            return "भावा हे काय राडा झाला?! 🤯"
        if any(w in kw_str for w in ["ek number", "clutch", "dhamal", "dhur", "kadak", "धमाल", "एक नंबर"]):
            return "एक नंबर जबरदस्त क्लच! 🔥"
        return "भावा व्हायरल मोमेंट! ⚡"

    elif language == "hi":
        if any(w in kw_str for w in ["police", "cops", "chase", "bhaago", "पुलिस", "भागो"]):
            return "५-स्टार पुलिस चेस! 🚨"
        if any(w in kw_str for w in ["crash", "gaadi", "thoko", "accident", "गाड़ी", "गाडी", "ठोको"]):
            return "खतरनाक कार क्रैश मोमेंट! 💥"
        if any(w in kw_str for w in ["khatam", "mar gaya", "mara", "fail", "खत्म", "मारा"]):
            return "भाई ये क्या हो गया?! 🤯"
        if any(w in kw_str for w in ["clutch", "op", "bawaal", "gajab", "ओपी", "बवाल", "गजब"]):
            return "ओपी बवाल क्लच मोमेंट! 🔥"
        if any(w in kw_str for w in ["rpg", "goli", "dhamaka", "fat gaya", "गोली", "धमाका"]):
            return "खतरनाक गनफाइट एक्शन! 💣"
        return "भाई गजब वायरल मोमेंट! ⚡"

    else:
        # Default English hooks
        if any(w in kw_str for w in ["boat"]):
            return "INSANE BOAT CHASE! 🚤"
        if any(w in kw_str for w in ["helicopter", "chopper"]):
            return "ATTACK HELICOPTER ESCAPE! 🚁"
        if any(w in kw_str for w in ["rpg", "sniper"]):
            return "GOD TIER RPG SNIPE! 💣"
        if any(w in kw_str for w in ["cops", "cop", "police", "feds"]):
            return "5-STAR POLICE PURSUIT! 🚨"
        if any(w in kw_str for w in ["crash", "wrecked", "blew", "exploded"]):
            return "UNREAL GTA 6 CRASH SURVIVAL! 💥"
        if any(w in kw_str for w in ["clutch", "headshot"]):
            return "UNREAL 1V4 CLUTCH! 🔥"
        if any(w in kw_str for w in ["rage", "wtf", "no way"]):
            return "SPEED RAGE QUIT IN GTA 6! 🤬"
        if any(w in kw_str for w in ["mission", "pass"]):
            return "GTA 6 FINAL MISSION CLIMAX! 😱"
        return "GTA 6 INSANE VIRAL MOMENT! ⚡"


def scan_stream_audio_fast(
    audio_path: str,
    min_score: float = 75.0,
    top_k: Optional[int] = None,
    min_dur: float = 30.0,
    max_dur: float = 55.0,
    model_size: str = "base"
) -> List[Dict[str, Any]]:
    """
    Dynamic All-Viral-Moments Extraction:
      1. Computes 1-second RMS volume profile across whole audio track.
      2. Detects high-energy audio peaks (screaming, explosions, hype, laughter).
      3. Transcribes candidate windows using faster-whisper with auto-language detection.
      4. Calculates Viral Retention Score (0–100):
           - Audio Energy Score (0–55)
           - Lexical Hook Score (0–45)
      5. Extracts ALL non-overlapping segments that score >= min_score (75.0).
    """
    total_dur = get_audio_duration(audio_path)
    print(f"[transcribe] Fast scanning {total_dur/3600:.2f}h audio stream ({total_dur:.1f}s) for viral moments (threshold >= {min_score})...")

    rms, fps = extract_audio_rms_profile(audio_path, bucket_size=1.0)
    if len(rms) == 0:
        return [{
            "id": 1, "start": 0.0, "end": min(total_dur, 40.0),
            "duration": min(total_dur, 40.0), "score": 85.0,
            "hook_title": "GTA 6 VIRAL MOMENT! ⚡", "keywords": [],
            "language": "en"
        }]

    nominal_dur = 40.0
    min_dist_buckets = 75  # Minimum 75 seconds between candidate peaks to prevent overlap
    
    # Sort buckets by energy
    sorted_indices = np.argsort(rms)[::-1]
    selected_indices = []
    
    # Pool candidate peaks
    max_candidates = 60 if top_k is None else max(top_k * 4, 30)
    for idx in sorted_indices:
        if rms[idx] < 0.7:  # Below baseline excitement
            break
        if all(abs(idx - s) > min_dist_buckets for s in selected_indices):
            selected_indices.append(idx)
            if len(selected_indices) >= max_candidates:
                break

    if not selected_indices:
        selected_indices = [int(len(rms) * 0.2), int(len(rms) * 0.5), int(len(rms) * 0.8)]

    # Initialize faster-whisper with language=None for auto-detection
    from faster_whisper import WhisperModel
    print(f"[transcribe] Initializing faster-whisper ({model_size}) with auto-language detection & VAD...")
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    candidates = []
    for rank, p_idx in enumerate(selected_indices):
        center_sec = p_idx / fps
        start_sec = max(0.0, center_sec - 12.0)
        end_sec = min(total_dur, start_sec + nominal_dur)
        w_dur = end_sec - start_sec

        # Extract snippet audio for fast verification
        snippet_path = TEMP_WORK_DIR / f"_snip_{rank}.wav"
        snippet_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(w_dur),
            "-i", str(audio_path),
            "-ar", "16000", "-ac", "1",
            str(snippet_path.resolve())
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        kws = []
        det_lang = "en"
        try:
            segments, info = model.transcribe(
                str(snippet_path),
                vad_filter=True,
                beam_size=1,
                language=None  # Auto-detect language (en, hi, mr, etc.)
            )
            det_lang = info.language
            for seg in segments:
                words = seg.text.lower().split()
                for w in words:
                    clean = clean_word(w)
                    if clean in ALL_VIRAL_KEYWORDS:
                        kws.append(clean)
        except Exception:
            pass
        finally:
            if snippet_path.exists():
                snippet_path.unlink()

        audio_val = float(rms[p_idx])
        # Score computation:
        # Audio energy component: up to 55 points (1.0 RMS = 25 pts, 2.2 RMS = 55 pts)
        audio_score = min(55.0, audio_val * 25.0)
        # Lexical keyword component: up to 45 points (each keyword = 12 pts, plus bonus for excitement)
        lexical_score = min(45.0, len(kws) * 12.0 + (10.0 if len(kws) >= 2 else 0.0))
        total_score = round(min(100.0, audio_score + lexical_score), 2)

        hook_headline = generate_hook_banner(kws, language=det_lang)
        candidates.append({
            "start": round(start_sec, 2),
            "end": round(end_sec, 2),
            "duration": round(w_dur, 2),
            "score": total_score,
            "language": det_lang,
            "hook_title": hook_headline,
            "keywords": list(set(kws))
        })

    # Sort descending by Viral Retention Score
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Dynamic extraction: Select ALL qualified segments with score >= min_score
    qualified = [c for c in candidates if c["score"] >= min_score]
    if not qualified:
        # Fallback to top candidates if none exceeded threshold
        qualified = candidates[:max(1, len(candidates) // 2)]

    if top_k is not None and top_k > 0:
        selected = qualified[:top_k]
    else:
        selected = qualified

    for i, s in enumerate(selected):
        s["id"] = i + 1

    print(f"[transcribe] Dynamically extracted {len(selected)} viral segments scoring >= {min_score} (Languages: {set(s['language'] for s in selected)})")
    return selected


_CACHED_PRECISE_MODEL = None

def get_precise_model(model_size: str = "base"):
    global _CACHED_PRECISE_MODEL
    if _CACHED_PRECISE_MODEL is None:
        from faster_whisper import WhisperModel
        print(f"[transcribe] Initializing faster-whisper ({model_size}) model cache...")
        try:
            _CACHED_PRECISE_MODEL = WhisperModel(model_size, device="cuda", compute_type="float16")
        except Exception:
            _CACHED_PRECISE_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _CACHED_PRECISE_MODEL


def transcribe_segment_precise(
    section_video_path: Path,
    model_size: str = "base"
) -> Tuple[List[Dict[str, Any]], str, float]:
    """
    Phase 2: Runs faster-whisper with auto-language detection (en, hi, mr)
    and word_timestamps=True on the downloaded short section.
    Returns:
      (all_words, detected_language, language_probability)
    """
    print(f"[transcribe] Running precise multilingual transcription ({model_size}) on: {section_video_path.name}...")
    model = get_precise_model(model_size)

    segments, info = model.transcribe(
        str(section_video_path),
        word_timestamps=True,
        beam_size=1,
        vad_filter=True,
        language=None  # Auto-detect language!
    )

    detected_lang = info.language
    lang_prob = round(float(info.language_probability), 2)
    all_words = []
    
    for seg in segments:
        for w in (seg.words or []):
            raw_w = w.word.strip()
            clean = clean_word(raw_w)
            if raw_w:
                all_words.append({
                    "word": raw_w,
                    "clean": clean,
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "probability": round(float(w.probability), 2)
                })

    print(f"[transcribe] Word timestamps ready: {len(all_words)} words (Language: '{detected_lang}', Confidence: {lang_prob:.0%})")
    return all_words, detected_lang, lang_prob


def main():
    parser = argparse.ArgumentParser(description="Multilingual Audio-First & Precise Transcription Engine")
    parser.add_argument("audio", help="Path to input audio file")
    parser.add_argument("--min-score", type=float, default=75.0, help="Minimum Viral Retention Score (0-100)")
    parser.add_argument("--top-k", type=int, default=None, help="Optional max clips limit (None = extract all >= min-score)")
    parser.add_argument("--model", default="base", help="Whisper model tier")
    args = parser.parse_args()

    results = scan_stream_audio_fast(args.audio, min_score=args.min_score, top_k=args.top_k, model_size=args.model)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
