import numpy as np
import wave
import struct
import os

SAMPLE_RATE = 44100

def write_wav(filename, samples):
    # Normalize to 0.95 peak and convert to 16-bit PCM
    samples = np.clip(samples, -1.0, 1.0)
    max_val = np.max(np.abs(samples))
    if max_val > 0:
        samples = samples / max_val * 0.95
    int_samples = (samples * 32767).astype(np.int16)
    
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes = 16 bit
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(int_samples.tobytes())
    print(f"Generated: {filename} ({len(int_samples)/SAMPLE_RATE:.2f}s)")

def make_boom():
    """Deep bass impact for opening hook (0.8s)"""
    duration = 0.8
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    # Pitch drop from 180Hz down to 42Hz exponentially
    freq = 42 + (180 - 42) * np.exp(-t * 18)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase)
    
    # Click/punch transient (high punch at t=0)
    punch_freq = 60 + 300 * np.exp(-t * 60)
    punch_phase = 2 * np.pi * np.cumsum(punch_freq) / SAMPLE_RATE
    punch = np.sin(punch_phase) * np.exp(-t * 35)
    
    # Layer with subtle saturated second harmonic
    sub = np.tanh(sub * 1.5 + punch * 1.2)
    
    # Amplitude envelope
    amp_env = np.exp(-t * 4.5)
    return sub * amp_env

def make_whoosh():
    """Fast transition swoosh (0.45s)"""
    duration = 0.45
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    # White noise
    noise = np.random.uniform(-1.0, 1.0, len(t))
    
    # Bandpass filter simulated via modulated resonance
    # Center frequency sweeps from 400Hz up to 2600Hz and back to 500Hz
    mid = duration / 2.0
    sweep = np.exp(-((t - mid) ** 2) / (2 * (0.12 ** 2)))
    fc = 450 + 2200 * sweep
    
    # Filter noise with simple two-pole resonant bandpass
    filtered = np.zeros_like(noise)
    r = 0.92
    y1, y2 = 0.0, 0.0
    for i in range(len(t)):
        theta = 2 * np.pi * fc[i] / SAMPLE_RATE
        a1 = -2 * r * np.cos(theta)
        a2 = r * r
        val = noise[i] * (1.0 - r) - a1 * y1 - a2 * y2
        filtered[i] = val
        y2 = y1
        y1 = val
        
    # Bell curve amplitude envelope
    env = np.sin(np.pi * t / duration) ** 1.8
    return filtered * env

def make_pop():
    """Clean pop for highlighted keywords (0.07s)"""
    duration = 0.07
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    # Fast pitch decay from 1100 Hz down to 200 Hz
    freq = 200 + 900 * np.exp(-t * 80)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    tone = np.sin(phase)
    # Very fast attack (0.002s), snappy exponential decay
    attack = np.minimum(t / 0.002, 1.0)
    decay = np.exp(-t * 60)
    return tone * attack * decay

def make_vine_boom():
    """Vine boom / comedic fail emphasis (1.6s)"""
    duration = 1.6
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    # Heavy pitch sweep 160Hz -> 36Hz
    freq = 36 + 124 * np.exp(-t * 8)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase) + 0.3 * np.sin(2 * phase)
    
    # Add punchy burst of low noise
    noise = np.random.uniform(-0.5, 0.5, len(t)) * np.exp(-t * 30)
    
    # Overdrive distortion (warm analog clipping)
    mixed = np.tanh((sub + noise) * 3.2)
    
    # Decay envelope with lingering low rumble
    env = 0.7 * np.exp(-t * 2.8) + 0.3 * np.exp(-t * 1.5)
    return mixed * env

def main():
    sfx_dir = r"C:\Users\Dell\.gemini\antigravity\scratch\Viral_Clip_Studio\assets\sfx"
    os.makedirs(sfx_dir, exist_ok=True)
    
    write_wav(os.path.join(sfx_dir, "boom.wav"), make_boom())
    write_wav(os.path.join(sfx_dir, "whoosh.wav"), make_whoosh())
    write_wav(os.path.join(sfx_dir, "pop.wav"), make_pop())
    write_wav(os.path.join(sfx_dir, "vine_boom.wav"), make_vine_boom())

if __name__ == "__main__":
    main()
