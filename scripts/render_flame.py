"""Single-scene 'living flame' renderer (job type: flame).

One still image, one continuous slow push-in, and a local candle-flame flicker
that is confined to a small box around the flame. Everything outside that box
is the untouched source image (only the global camera transform is applied).

How the flame is animated (no AI, no generated pixels):
  1. The source is scaled once to a 2160x3840 "base" canvas (cover crop of 9:16).
  2. Per frame, a small region around the flame is re-sampled from the *static*
     base with a smooth displacement field (cv2.remap):
       - horizontal lean that grows toward the tip (tip moves most, base is pinned)
       - a mid-height S-bend
       - vertical stretch/compression about the wick end of the flame
       - slight width change, anti-correlated with the stretch (volume-ish)
     The field is multiplied by a soft mask (super-gaussian around the flame,
     fading to zero at the rim line), so only flame + its immediate halo move.
     Because the warped pixels are the flame's own pixels, shape/colour stay real.
  3. A very small warm illumination change (gaussian around the flame, cut off
     well above the label) is synchronised with the stretch/brightness signal.
  4. Per-frame parameters are smoothed random signals (two time scales + a
     single gentle gust), seeded but non-periodic, so there is no obvious loop.
  5. The camera push-in (100% -> 105%, smoothstep) is applied to the finished
     base frame, so jar/label move only with the global zoom.
A proof step renders the same frame with the flame effect off and reports the
bounding box of every output pixel that differs.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R  # noqa: E402

W, H, FPS = R.W, R.H, R.FPS
BW, BH = W * 2, H * 2  # base canvas


def smooth_noise(rng, n, sigma, pad=200):
    x = rng.standard_normal(n + 2 * pad)
    k = int(sigma * 4) * 2 + 1
    g = np.exp(-0.5 * ((np.arange(k) - k // 2) / sigma) ** 2)
    g /= g.sum()
    y = np.convolve(x, g, mode="same")[pad:pad + n]
    return y / (y.std() + 1e-9)


def make_signals(n, seed, gust_t):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FPS

    def chan(fast, slow, wf=0.6, ws=0.8):
        s = wf * smooth_noise(rng, n, fast) + ws * smooth_noise(rng, n, slow)
        return s / (s.std() + 1e-9)

    lean = chan(2.5, 10)
    bend = chan(3.5, 14)
    stretch = chan(2.0, 8)
    width = chan(3.0, 12)
    light = chan(2.5, 9)
    gust = np.exp(-0.5 * ((t - gust_t) / 0.28) ** 2)  # one gentle gust, not periodic
    return t, lean, bend, stretch, width, light, gust


def smoothstep(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


class Flame:
    def __init__(self, base, cfg):
        self.base = base
        c = {"cx": 557, "tip": 817, "base": 900}
        c.update(cfg)
        self.cx, self.tip, self.by = c["cx"] * 2.0, c["tip"] * 2.0, c["base"] * 2.0
        self.amp = float(cfg.get("lean_px", 3.0))      # base px of tip lean (std)
        self.str_amp = float(cfg.get("stretch", 0.035))
        self.glow_k = float(cfg.get("glow", 0.03))
        # warp region (base px)
        self.x0, self.x1 = int(self.cx - 115), int(self.cx + 115)
        self.y0, self.y1 = int(self.tip - 95), int(self.by + 4)
        yy, xx = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.xx, self.yy = xx, yy
        h = np.clip((self.by - yy) / (self.by - self.tip), 0, 1.4)
        self.h = h
        mx = np.exp(-(((xx - self.cx) / 58.0) ** 4))
        mtop = np.clip((yy - (self.tip - 95)) / 60.0, 0, 1)
        mtop = mtop * mtop * (3 - 2 * mtop)
        mbot = np.clip((self.by - yy) / 14.0, 0, 1)
        self.m = (mx * mtop * mbot).astype(np.float32)
        # glow region (base px): hard cut-off above the label (label top ~ y=1980)
        self.gx0, self.gx1 = int(self.cx - 330), int(self.cx + 330)
        self.gy0, self.gy1 = int(self.by - 460), int(self.by + 130)
        gy, gx = np.mgrid[self.gy0:self.gy1, self.gx0:self.gx1].astype(np.float32)
        gcy = self.by - 70
        G = np.exp(-(((gx - self.cx) / 150.0) ** 2 + ((gy - gcy) / 165.0) ** 2) / 2)
        cut = np.clip((self.by + 130 - gy) / 70.0, 0, 1)  # fades out by y = by+130 (< label)
        self.G = (G * cut).astype(np.float32)[..., None]
        self.roi_box = (self.gx0, self.gy0, self.gx1, self.gy1)

    def frame(self, sig, i):
        t, lean, bend, stretch, width, light, gust = sig
        base = self.base.copy()
        A = self.amp * (lean[i] + 1.8 * gust[i])
        B = 0.9 * self.amp * bend[i]
        s = float(np.clip(self.str_amp * (stretch[i] - 0.8 * gust[i]), -0.08, 0.08))
        w = float(np.clip(-0.5 * s + 0.012 * width[i], -0.06, 0.06))
        h, m = self.h, self.m
        hs = np.minimum(h, 1.0)
        y_src = self.by - (self.by - self.yy) / (1.0 + s * m)
        dx = A * np.power(hs, 1.6) + B * np.sin(np.pi * hs) * hs
        x_src = self.xx - m * dx
        x_src = self.cx + (x_src - self.cx) / (1.0 + w * m * np.sin(np.pi * hs))
        patch = cv2.remap(self.base, x_src.astype(np.float32), y_src.astype(np.float32),
                          cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        base[self.y0:self.y1, self.x0:self.x1] = patch
        # local illumination, synchronised with stretch (taller flame = a touch brighter)
        b = np.tanh(0.6 * light[i] + 0.8 * (s / max(self.str_amp, 1e-6)) * 0.5)
        k = self.glow_k * b
        reg = base[self.gy0:self.gy1, self.gx0:self.gx1].astype(np.float32)
        warm = np.array([0.75, 0.9, 1.0], dtype=np.float32)  # BGR gain weights: warmer (R > B)
        reg = reg * (1.0 + k * self.G * warm)
        base[self.gy0:self.gy1, self.gx0:self.gx1] = np.clip(reg, 0, 255).astype(np.uint8)
        return base, {"lean": float(A), "bend": float(B), "stretch": s, "width": w, "light": float(k)}


def camera(base, z):
    sc = 2.0 / z
    M = np.array([[sc, 0, 1080 - 540 * sc], [0, sc, 1920 - 960 * sc]], dtype=np.float64)
    return cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def build_base(path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    ih, iw = img.shape[:2]
    s = max(BW / iw, BH / ih)
    nw, nh = int(round(iw * s)), int(round(ih * s))
    big = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    x0, y0 = (nw - BW) // 2, (nh - BH) // 2
    return np.ascontiguousarray(big[y0:y0 + BH, x0:x0 + BW]), (iw, ih)


def render_flame(job, out_dir):
    t0 = time.monotonic()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="flame_"))
    shot = job["shots"][0]
    src = R.fetch(shot["src"], tmp, 1)
    base, (iw, ih) = build_base(src)
    dur = float(shot["dur"])
    n = int(round(dur * FPS))
    z0, z1 = float(shot["motion"]["z0"]), float(shot["motion"]["z1"])
    fl = Flame(base, job["flame"])
    sig = make_signals(n, int(job["flame"].get("seed", 11)), float(job["flame"].get("gust_t", 4.6)))
    font = R.find_font()
    vf = ""
    if shot.get("text"):
        vf = R.text_filters(shot["text"], font, tmp, "hook") + ","
    vf += ("scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,"
           "format=yuv420p")
    mp4 = out_dir / f"{job['id']}.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur:.3f}",
           "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high",
           "-level", "4.1", "-r", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
           "-movflags", "+faststart", "-shortest", str(mp4)]
    print("+", " ".join(cmd), flush=True)
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    params, proof, strip = [], {}, []
    for i in range(n):
        z = z0 + (z1 - z0) * smoothstep(i / (n - 1))
        eff, prm = fl.frame(sig, i)
        frame = camera(eff, z)
        params.append(prm)
        if i in (0, n // 3, 2 * n // 3, n - 1):
            ref = camera(base, z)
            d = np.abs(frame.astype(np.int16) - ref.astype(np.int16)).max(axis=2)
            ys, xs = np.nonzero(d > 0)
            proof[f"frame_{i}"] = {
                "changed_pixels": int(len(xs)),
                "bbox_xyxy": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                "max_abs_diff": int(d.max()),
            }
        if i % 24 == 0:
            strip.append(frame[760:1000, 440:680].copy())
        if i == n - 12:
            cv2.imwrite(str(tmp / "label.png"), frame)
        p.stdin.write(frame.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg failed")
    # review assets: flame strip (3x nearest) and a full-res late frame
    big = [cv2.resize(s, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC) for s in strip]
    cv2.imwrite(str(out_dir / f"{job['id']}-contact.jpg"), np.hstack(big), [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(out_dir / f"{job['id']}-label-frame.jpg"), cv2.imread(str(tmp / "label.png")),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    stats = {k: {"min": round(min(q[k] for q in params), 3), "max": round(max(q[k] for q in params), 3)}
             for k in params[0]}
    shots_meta = [{"index": 1, "source_url": shot["src"], "source_sha256": R.sha256(src),
                   "source_size": f"{iw}x{ih}", "duration_s": dur, "layout": "cover"}]
    shutil.rmtree(tmp, ignore_errors=True)
    meta = {"shots": shots_meta, "flame_params_range": stats, "flame_region_proof": proof,
            "flame_box_output_px": job["flame"], "camera": {"z0": z0, "z1": z1, "ease": "smoothstep"},
            "render_script_seconds": round(time.monotonic() - t0, 1),
            "caption": job.get("caption"), "audio": job.get("audio", "silent")}
    return shots_meta, meta
