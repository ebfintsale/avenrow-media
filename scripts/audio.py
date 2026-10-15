"""AVENROW original ambient sound design (pure numpy synthesis; no samples, no music, no vocals).
Each scene = shaped-noise room tone + slow texture layers + very sparse candle micro-ticks.
No loops: everything is generated for the clip's full length from a seeded RNG."""
import json, pathlib, subprocess, re, shutil, tempfile, wave
import numpy as np

SR = 44100
TARGET_LUFS = -23.0
FADE_IN, FADE_OUT = 0.8, 1.3


def shaped(n, rng, lo, hi, tilt=0.0):
    """Band-limited noise (soft edges), optional spectral tilt (f^-tilt/2 amplitude). RMS=1."""
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    edge_lo, edge_hi = max(lo * 0.5, 1.0), hi * 1.5
    m = np.ones_like(f)
    m *= np.clip((f - edge_lo) / max(lo - edge_lo, 1e-6), 0, 1)
    m *= np.clip((edge_hi - f) / max(edge_hi - hi, 1e-6), 0, 1)
    m *= (np.maximum(f, 20.0) / 200.0) ** (-tilt / 2)
    y = np.fft.irfft(X * m, n)
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def slow(n, rng, rate, depth, floor=0.0):
    """Smooth random envelope in [floor, ~1+depth]; `rate` ~ cycles/sec of movement."""
    e = shaped(n, rng, 0.02, rate, 0.0)
    e = e / (np.max(np.abs(e)) + 1e-9)
    return np.clip(1.0 + depth * e, floor, None)


def swells(n, rng, count, lo_s, hi_s):
    """A few long raised-cosine swells at random places."""
    env = np.zeros(n)
    for _ in range(count):
        L = int(rng.uniform(lo_s, hi_s) * SR)
        s = int(rng.uniform(0, max(1, n - L)))
        env[s:s + L] += 0.5 - 0.5 * np.cos(np.linspace(0, 2 * np.pi, L, endpoint=False))[: n - s]
    return np.clip(env, 0, 1)


def sines(n, freqs, rng, trem=0.25, trem_rate=0.07):
    t = np.arange(n) / SR
    y = np.zeros(n)
    for f in freqs:
        ph = rng.uniform(0, 2 * np.pi)
        a = 1 + trem * np.sin(2 * np.pi * trem_rate * rng.uniform(0.6, 1.4) * t + rng.uniform(0, 6.28))
        y += a * np.sin(2 * np.pi * f * t + ph)
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def candle(n, rng, rate=1.1, level=1.0):
    """Very sparse, tiny soft ticks + faint flutter. Never loud, never regular."""
    y = np.zeros(n)
    t = 0.0
    dur = n / SR
    while t < dur:
        t += rng.exponential(1.0 / rate)
        i = int(t * SR)
        L = int(rng.uniform(0.006, 0.03) * SR)
        if i + L >= n:
            break
        b = shaped(L, rng, 1500, 6500) * np.exp(-np.linspace(0, rng.uniform(5, 9), L))
        y[i:i + L] += b * rng.lognormal(-0.6, 0.6)
    flutter = shaped(n, rng, 500, 2600) * 0.06 * slow(n, rng, 1.2, 0.8, 0.0)
    return (y * 0.35 + flutter) * level


def stereo(fn, n, rng):
    return np.stack([fn(rng), fn(rng)], axis=1)


def synth(scene, dur, seed):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)

    def room(lo, hi, tilt, g=1.0):
        return stereo(lambda r: shaped(n, r, lo, hi, tilt) * slow(n, r, 0.15, 0.12, 0.5), n, rng) * g

    def band(lo, hi, g, nsw, ls, hs, tilt=0.0):
        return stereo(lambda r: shaped(n, r, lo, hi, tilt) * swells(n, r, nsw, ls, hs) * slow(n, r, 0.3, 0.3, 0.2), n, rng) * g

    def tones(freqs, g, spread=0.35):
        L = sines(n, freqs, rng)
        R = sines(n, [f * (1 + spread * 0.004) for f in freqs], rng)
        return np.stack([L, R], 1) * g * slow(n, rng, 0.08, 0.35, 0.2)[:, None]

    def cand(level, rate=1.1):
        return np.stack([candle(n, rng, rate, level), candle(n, rng, rate, level)], 1)

    s = scene
    if s == "stay-cozy":      # quiet cozy night room + faint distant city air
        y = room(90, 700, 1.2) + tones([110, 165], 0.14) + band(200, 1100, 0.10, 4, 4, 8, 1.0) + cand(0.10, 0.8)
    elif s == "midnight":     # darker, slightly atmospheric
        y = room(80, 450, 1.4) + tones([147, 196, 294], 0.22) + band(4000, 9000, 0.035, 5, 2, 4) + cand(0.08, 0.7)
    elif s == "spooky":       # warm autumn room + soft wind
        y = room(90, 800, 1.1) + tones([131], 0.10) + band(300, 1300, 0.30, 4, 3, 6, 1.2) + cand(0.12, 1.0)
    elif s == "witching":     # dark room, mysterious not horror
        y = room(70, 350, 1.6) + tones([147, 148.6, 220], 0.20, 0.5) + band(3500, 8000, 0.03, 4, 2, 4) + cand(0.07, 0.6)
    elif s == "pumpkin":      # warm autumn evening, leaf-wind
        y = room(90, 800, 1.1) + band(800, 3500, 0.20, 5, 2, 5, 0.6) + tones([120], 0.06) + cand(0.12, 1.0)
    elif s == "ghostly":      # cozy halloween, airy and playful
        y = room(90, 750, 1.1) + band(500, 2600, 0.26, 3, 1.5, 3, 0.8) + band(2500, 6000, 0.05, 6, 0.4, 1.0) + cand(0.10, 1.0)
    else:
        raise SystemExit(f"unknown scene {s}")
    t = np.arange(n) / SR
    fade = np.minimum(1, t / FADE_IN) * np.minimum(1, (dur - t) / FADE_OUT)
    fade = (0.5 - 0.5 * np.cos(np.pi * np.clip(fade, 0, 1)))
    return y * fade[:, None]


def lufs(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return float(i[-1]), float(p[-1]) if p else None


def write_wav(path, y):
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def make_wav(scene, dur, seed, path):
    y = synth(scene, dur, seed)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.1            # provisional level
    write_wav(path, y)
    cur, _ = lufs(path)
    y = y * 10 ** ((TARGET_LUFS - cur) / 20)
    pk = np.max(np.abs(y))
    if pk > 0.7:                                          # keep true peak safely under -3 dBFS
        y = y * (0.7 / pk)
    write_wav(path, y)
    return lufs(path)


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
    wav = out_dir / f"{job['id']}-ambience.wav"
    i_lufs, peak = make_wav(job["scene"], dur, int(job.get("seed", 1)), wav)
    mp4 = out_dir / f"{job['id']}.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-i", str(wav),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-ac", "2", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(mp4)], check=True)
    meta = {"audio": "original synthesized ambience", "scene": job["scene"], "seed": job.get("seed", 1),
            "integrated_lufs": i_lufs, "true_peak_dbfs": peak, "fade_in_s": FADE_IN, "fade_out_s": FADE_OUT,
            "video_stream_md5_source": vmd5(src), "video_stream_md5_final": vmd5(mp4),
            "source_url": job["src"], "caption": job.get("caption")}
    meta["video_stream_identical"] = meta["video_stream_md5_source"] == meta["video_stream_md5_final"]
    shutil.rmtree(tmp, ignore_errors=True)
    return dur, meta
