"""AVENROW original sound design v3 - SPARSE (owner decision 2026-10-17).

Permanently REMOVED from AVENROW automated video production: wind, airy ambience, filtered-noise ambience,
continuous room-tone noise, white-noise-like textures, vinyl hiss/crackle beds, low drones, any continuous
atmospheric bed. Between sounds the track is digital silence.

What it makes: a handful of isolated, tiny, individually synthesized candle crackles (only for lit candles),
with clear silence around each. No loops, no samples, no music, no vocals. Events are placed by a seeded RNG.
"""
import pathlib, subprocess, re, shutil, tempfile, wave
import numpy as np

SR = 44100
PEAK_DBFS = -17.0          # loudest single event; everything else is quieter
MIN_GAP = 0.9              # seconds of clear silence between events (onset to onset, minimum)


def _burst(L, rng, lo, hi):
    """Short band-limited noise burst (FFT band-pass on a tiny window), unit peak."""
    x = rng.standard_normal(L)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(L, 1 / SR)
    m = ((f >= lo) & (f <= hi)).astype(float)
    y = np.fft.irfft(X * m, L)
    return y / (np.max(np.abs(y)) + 1e-9)


def crackle(rng, kind):
    """One candle crackle. 'tick' = 1-3 micro-pulses; 'snap' = one slightly larger pop with a faint wooden body."""
    if kind == "snap":
        pulses = [(0.0, 1.0, rng.uniform(0.006, 0.011), rng.uniform(2200, 3600), rng.uniform(5200, 7800))]
        body_f, body_amp = rng.uniform(380, 640), 0.35
    else:
        k = int(rng.integers(1, 4))
        t, pulses = 0.0, []
        for _ in range(k):
            pulses.append((t, rng.uniform(0.35, 0.8), rng.uniform(0.002, 0.005), rng.uniform(2800, 4200), rng.uniform(6000, 9000)))
            t += rng.uniform(0.006, 0.028)
        body_f, body_amp = rng.uniform(500, 900), 0.12
    total = int((pulses[-1][0] + 0.06) * SR)
    y = np.zeros(total)
    for t0, amp, dur, lo, hi in pulses:
        i = int(t0 * SR)
        L = max(32, int(dur * SR * 3))
        env = np.exp(-np.arange(L) / (dur * SR))
        env[:8] *= np.linspace(0.3, 1, 8)      # ~0.2 ms attack, no digital click
        m = min(L, total - i)
        if m > 0:
            y[i:i + m] += (_burst(L, rng, lo, hi) * env * amp)[:m]
    # faint resonant body of the wax/wick for realism
    Lb = int(0.025 * SR)
    tb = np.arange(Lb) / SR
    body = np.sin(2 * np.pi * body_f * tb) * np.exp(-tb / 0.006) * body_amp
    y[:Lb] += body[:total]
    return y / (np.max(np.abs(y)) + 1e-9)


def synth(dur, seed, n_events=None):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    y = np.zeros((n, 2))
    if n_events is None:
        n_events = int(round(rng.uniform(0.45, 0.65) * dur))      # ~4-5 events in 8 s
    # place events with enforced silence between them; keep clear of the first 0.7 s and last 0.8 s
    times, tries = [], 0
    while len(times) < n_events and tries < 400:
        tries += 1
        t = rng.uniform(0.7, dur - 0.8)
        if all(abs(t - u) >= MIN_GAP for u in times):
            times.append(t)
    times.sort()
    snap_at = int(rng.integers(0, len(times))) if times else -1
    for k, t in enumerate(times):
        e = crackle(rng, "snap" if k == snap_at else "tick")
        lvl = 1.0 if k == snap_at else rng.uniform(0.30, 0.62)        # ticks are clearly quieter than the one snap
        pan = rng.uniform(0.38, 0.62)
        i = int(t * SR)
        e = e * lvl
        m = min(len(e), n - i)
        y[i:i + m, 0] += e[:m] * (1 - pan) * 2 * 0.5
        y[i:i + m, 1] += e[:m] * pan * 2 * 0.5
    pk = np.max(np.abs(y)) + 1e-9
    y = y / pk * 10 ** (PEAK_DBFS / 20)
    return y, times


def lufs(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)


def write_wav(path, y):
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def vmd5(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def run_audio(job, out_dir):
    import render as R
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="aud_"))
    src = R.fetch(job["src"], tmp, 1)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True).stdout)
    y, times = synth(dur, int(job.get("seed", 1)), job.get("events"))
    wav = out_dir / f"{job['id']}-sparse.wav"
    write_wav(wav, y)
    i_lufs, peak = lufs(wav)
    sil = float(np.mean(np.max(np.abs(y), axis=1) == 0))
    mp4 = out_dir / f"{job['id']}.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-i", str(wav),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-ac", "2", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(mp4)], check=True)
    meta = {"audio": "sparse candle crackles only (v3); no bed", "seed": job.get("seed", 1),
            "event_times_s": [round(t, 2) for t in times], "n_events": len(times),
            "integrated_lufs": i_lufs, "true_peak_dbfs": peak, "digital_silence_fraction": round(sil, 3),
            "min_gap_s": MIN_GAP,
            "video_stream_md5_source": vmd5(src), "video_stream_md5_final": vmd5(mp4),
            "source_url": job["src"], "caption": job.get("caption")}
    meta["video_stream_identical"] = meta["video_stream_md5_source"] == meta["video_stream_md5_final"]
    shutil.rmtree(tmp, ignore_errors=True)
    return dur, meta
