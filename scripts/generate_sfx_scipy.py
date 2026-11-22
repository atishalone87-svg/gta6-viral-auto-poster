"""
Viral SFX Synthesizer (scripts/generate_sfx_scipy.py)
Uses numpy & scipy.signal to generate broadcast-quality WAV SFX:
  1. boom.wav - Deep 40Hz sub-bass impact with punch transient for 0.3s opening hook
  2. whoosh.wav - Fast 400Hz-2800Hz resonant bandpass transition swoosh
  3. pop.wav - Crisp, snappy frequency-drop pop for active word accents
"""

import os
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy import signal

SAMPLE_RATE = 48000
ASSETS_SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"


def generate_boom() -> np.ndarray:
    """Deep bass sub-impact with punch transient (0.85s)."""
    duration = 0.85
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # Exponential pitch sweep: 160Hz -> 38Hz sub
    pitch = 38.0 + 122.0 * np.exp(-t * 14.0)
    phase = 2.0 * np.pi * np.cumsum(pitch) / SAMPLE_RATE
    sub = np.sin(phase)

    # Initial punch transient (0-50ms)
    punch_env = np.exp(-t * 40.0)
    punch = np.sin(2.0 * np.pi * 90.0 * t) * punch_env

    # Soft tanh saturation
    combined = np.tanh(sub * 1.6 + punch * 0.9)
    # Amplitude envelope
    amp_env = np.exp(-t * 3.8)
    return (combined * amp_env).astype(np.float32)


def generate_whoosh() -> np.ndarray:
    """Fast transition swoosh (0.42s) with resonant bandpass sweep."""
    duration = 0.42
    n_samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)

    # Generate shaped noise
    noise = np.random.normal(0, 1.0, n_samples)
    
    # Resonant center frequency sweep (bell shaped peaking at mid-transition)
    mid = duration / 2.0
    freq_sweep = 400.0 + 2600.0 * np.exp(-((t - mid) ** 2) / (2.0 * (0.09 ** 2)))
    
    # Time-varying Butterworth filter
    # Filter in small chunks to follow center frequency
    chunk_size = 256
    filtered = np.zeros(n_samples, dtype=np.float32)
    for idx in range(0, n_samples, chunk_size):
        chunk = noise[idx:idx + chunk_size]
        cf = freq_sweep[min(idx + chunk_size // 2, n_samples - 1)]
        low = max(60.0, cf * 0.6)
        high = min(cf * 1.5, SAMPLE_RATE * 0.45)
        b, a = signal.butter(2, [low / (SAMPLE_RATE / 2), high / (SAMPLE_RATE / 2)], btype='bandpass')
        filtered[idx:idx + chunk_size] = signal.lfilter(b, a, chunk)

    # Smooth bell envelope
    envelope = np.sin(np.pi * t / duration) ** 2.0
    result = filtered * envelope
    return result.astype(np.float32)


def generate_pop() -> np.ndarray:
    """Crisp keyword pop (0.065s) with sharp exponential decay."""
    duration = 0.065
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # Rapid pitch decay from 1200Hz down to 220Hz
    pitch = 220.0 + 980.0 * np.exp(-t * 90.0)
    phase = 2.0 * np.pi * np.cumsum(pitch) / SAMPLE_RATE
    tone = np.sin(phase)
    
    # 2ms attack, fast 55ms decay
    attack = np.minimum(t / 0.002, 1.0)
    decay = np.exp(-t * 65.0)
    return (tone * attack * decay).astype(np.float32)


def save_wav(path: Path, data: np.ndarray):
    # Normalize peak to 0.95 and convert to 16-bit PCM
    peak = np.max(np.abs(data))
    if peak > 0:
        data = (data / peak) * 0.95
    pcm16 = (data * 32767).astype(np.int16)
    wavfile.write(str(path), SAMPLE_RATE, pcm16)
    print(f"[sfx] Generated: {path.name} ({len(pcm16)/SAMPLE_RATE:.3f}s, {SAMPLE_RATE}Hz)")


def main():
    ASSETS_SFX_DIR.mkdir(parents=True, exist_ok=True)
    save_wav(ASSETS_SFX_DIR / "boom.wav", generate_boom())
    save_wav(ASSETS_SFX_DIR / "whoosh.wav", generate_whoosh())
    save_wav(ASSETS_SFX_DIR / "pop.wav", generate_pop())


if __name__ == "__main__":
    main()
