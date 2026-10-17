"""AVENROW original ambient sound design v2 (pure numpy synthesis; no samples, no music, no vocals).
v2 (2026-10-17): wind / airy / leaf-wind / drone sound direction REMOVED. Each profile = warm band-limited room tone + soft cloth rustles + wood ticks + optional vinyl-like crackle + tiny candle crackles.
No loops: everything is generated for the clip's full length from a seeded RNG."""
import json, pathlib, subprocess, re, shutil, tempfile, wave
import numpy as np

SR = 44100
TARGET_LUFS = -27.0   # v2: quiet, clearly secondary to the picture
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


def clicks(n, rng, rate, lo, hi, dec, amp_mu=-1.0, amp_sd=0.7, maxlen=0.02):
    """Poisson-timed tiny transients (band-limited noise with fast decay). Irregular by construction."""
    y = np.zeros(n)
    t = 0.0
    dur = n / SR
    while True:
        t += rng.exponential(1.0 / rate)
        i = int(t * SR)
        L = int(min(maxlen, rng.uniform(0.002, maxlen)) * SR) + 8
        if i + L >= n:
            break
        b = shaped(L, rng, lo, hi) * np.exp(-np.linspace(0, dec * rng.uniform(0.7, 1.4), L))
        y[i:i + L] += b * rng.lognormal(amp_mu, amp_sd)
    return y


def rustle(n, rng, rate):
    """Soft fabric / paper movement: short, gentle, filtered bursts with slow attack. Very sparse."""
    y = np.zeros(n)
    t = 0.0
    dur = n / SR
    while True:
        t += rng.exponential(1.0 / rate)
        i = int(t * SR)
        L = int(rng.uniform(0.08, 0.28) * SR)
        if i + L >= n:
            break
        env = np.sin(np.linspace(0, np.pi, L)) ** 2
        y[i:i + L] += shaped(L, rng, 1200, 4200, 0.8) * env * rng.lognormal(-1.2, 0.4)
    return y


# Production ambience profiles (v2 room-tone system). No wind, no airy swells, no tonal drones, no white-noise bed.
PROFILES = {
    #            room lo,hi,tilt  room_g  vinyl_rate vinyl_g  candle_rate candle_g  rustle_rate  tick_rate
    "roomdusk":  dict(room=(170, 1000, 0.9), rg=1.0, vr=7.0, vg=0.55, cr=0.45, cg=0.55, ru=0.14, tk=0.08),   # warm autumn evening
    "roomnight": dict(room=(160, 900, 1.0), rg=1.0, vr=5.0, vg=0.45, cr=0.40, cg=0.50, ru=0.10, tk=0.06),   # quiet cozy night in
    "roomday":   dict(room=(180, 1150, 0.7), rg=1.0, vr=0.0, vg=0.0,  cr=0.35, cg=0.40, ru=0.18, tk=0.10),  # bright morning / desk, no vinyl
}


def synth(scene, dur, seed):
    if scene not in PROFILES:
        raise SystemExit(f"unknown scene {scene} (v2 profiles: {', '.join(PROFILES)})")
    P = PROFILES[scene]
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    lo, hi, tilt = P["room"]
    # warm room tone: band-limited (no energy below ~150 Hz -> no drone), nearly steady (+/-1 dB drift), mostly-correlated stereo
    shared = shaped(n, rng, lo, hi, tilt)
    drift = 1.0 + 0.10 * (shaped(n, rng, 0.03, 0.25, 0.0) / 3.0)
    L = (0.75 * shared + 0.25 * shaped(n, rng, lo, hi, tilt)) * drift
    R = (0.75 * shared + 0.25 * shaped(n, rng, lo, hi, tilt)) * drift
    room = np.stack([L, R], 1) * P["rg"] * 0.6
    y = room.copy()
    def pan(sig, w):
        return np.stack([sig * (1 - w), sig * w], 1) * 2 * 0.5
    # soft cozy texture: gentle fabric/paper rustles + rare low wood ticks, panned randomly
    for _ in range(1):
        y += pan(rustle(n, rng, P["ru"]), rng.uniform(0.3, 0.7)) * 0.20
    y += pan(clicks(n, rng, P["tk"], 220, 900, 14, -0.4, 0.4, 0.04), rng.uniform(0.3, 0.7)) * 0.22
    # vinyl-like surface texture (original synthesized, no sampled records): sparse crackle + small pops, no hiss bed
    if P["vr"] > 0:
        crack = clicks(n, rng, P["vr"], 2500, 9000, 70, -2.1, 0.8, 0.004)
        pops = clicks(n, rng, P["vr"] * 0.04, 800, 4500, 40, -1.0, 0.5, 0.012)
        y += pan(crack, 0.5) * P["vg"] * 0.5 + pan(pops, rng.uniform(0.35, 0.65)) * P["vg"] * 0.35
    # tiny realistic candle: sparse small crackles + rare slightly larger snap (no airy flutter)
    cand = clicks(n, rng, P["cr"], 1800, 7500, 55, -1.4, 0.7, 0.014)
    snap = clicks(n, rng, P["cr"] * 0.12, 900, 5000, 30, -0.6, 0.4, 0.02)
    y += pan(cand, rng.uniform(0.4, 0.6)) * P["cg"] + pan(snap, rng.uniform(0.4, 0.6)) * P["cg"] * 0.8
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
