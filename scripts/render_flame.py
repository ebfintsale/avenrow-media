"""Single-scene 'living flame' renderer (job type: flame).

One still image, one continuous slow camera move (push-in / pull-back / pan), and a
local candle-flame flicker confined to a small box around the flame. Everything
outside that box is the untouched source image (only the global camera transform
is applied).

Flame animation (no AI, no generated pixels):
  1. Source is scaled once to a "base" canvas = cover-fit of 2160x3840 (so >= 2160x3840,
     full image kept; a square photo gives 3840x3840 and room to pan).
  2. The flame is located per image: automatic detection (bright, tall, narrow blob inside
     a hint window) or a manual override. A dry_run job writes only a debug sheet.
  3. Per frame, a small region around the flame is re-sampled from the *static* base with a
     smooth displacement field (cv2.remap): tip-weighted lean, mid-height S-bend, vertical
     stretch about the flame base, and a slight width change. A soft mask pins the flame
     base and the rim line and fades to zero around the flame. All sizes scale with the
     detected flame height.
  4. Tiny warm illumination change (gaussian around the flame, cut off just below the rim,
     well above any label) synchronised with the stretch signal.
  5. Parameters are smoothed random signals (two time scales + one gentle gust), seeded but
     non-periodic.
  6. The camera is applied to the finished base frame, so jar/label move only with the
     global camera move.
A proof step renders sample frames with and without the flame effect and reports the
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
WIN_W, WIN_H = W * 2, H * 2  # camera window at z=1, in base px
REF_H = 166.0  # flame height (base px) the reference constants were tuned on


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

    lean, bend, stretch, width, light = chan(2.5, 10), chan(3.5, 14), chan(2.0, 8), chan(3.0, 12), chan(2.5, 9)
    gust = np.exp(-0.5 * ((t - gust_t) / 0.28) ** 2)
    return t, lean, bend, stretch, width, light, gust


def smoothstep(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- base / detection
def build_base(path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    ih, iw = img.shape[:2]
    s = max(WIN_W / iw, WIN_H / ih)
    nw, nh = int(round(iw * s)), int(round(ih * s))
    base = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    return np.ascontiguousarray(base), (iw, ih)


def detect_flame(base, hint=None):
    """Find the flame: bright, tall, narrow blob. Returns dict in base px + candidates."""
    bh, bw = base.shape[:2]
    half = cv2.resize(base, (bw // 2, bh // 2), interpolation=cv2.INTER_AREA)
    lum = (0.114 * half[..., 0] + 0.587 * half[..., 1] + 0.299 * half[..., 2]).astype(np.float32)
    hx0, hy0, hx1, hy1 = hint or (0.0, 0.0, 1.0, 1.0)
    X0, X1, Y0, Y1 = int(hx0 * lum.shape[1]), int(hx1 * lum.shape[1]), int(hy0 * lum.shape[0]), int(hy1 * lum.shape[0])
    mask = np.zeros(lum.shape, np.uint8)
    mask[Y0:Y1, X0:X1] = (lum[Y0:Y1, X0:X1] >= 228).astype(np.uint8)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cands = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 120 or a > 40000 or h < 1.25 * w:
            continue
        score = min(h / max(w, 1), 4.0) * np.sqrt(a) * (1.0 + 0.3 * float(lum[lab == i].mean() > 240))
        cands.append((score, i, x, y, w, h, a))
    if not cands:
        raise SystemExit("no lit flame detected in hint window - refusing to animate (never animate an unlit candle)")
    cands.sort(reverse=True)
    score, i, x, y, w, h, a = cands[0]
    ys, xs = np.nonzero(lab == i)
    upper = ys <= ys.min() + 0.6 * (ys.max() - ys.min() + 1)
    cx = float(xs[upper].mean())
    # tip: climb above the core while the column stays reasonably bright
    col = lum[:, int(round(cx))]
    t = int(ys.min())
    while t > 1 and col[t - 1] > 150:
        t -= 1
    bottom = int(ys.max())
    out = {"cx": cx * 2, "tip": float(t * 2), "base": float(bottom * 2 + 2),
           "core_w": float(w * 2), "n_candidates": len(cands)}
    out["height"] = out["base"] - out["tip"]
    return out


def debug_sheet(base, fl, path):
    cx, tip, by = fl["cx"], fl["tip"], fl["base"]
    hgt = by - tip
    x0, x1 = int(cx - 2.2 * hgt), int(cx + 2.2 * hgt)
    y0, y1 = int(tip - 0.9 * hgt), int(by + 1.6 * hgt)
    x0, y0 = max(0, x0), max(0, y0)
    crop = base[y0:y1, x0:x1].copy()
    cv2.line(crop, (0, int(tip - y0)), (crop.shape[1], int(tip - y0)), (0, 255, 0), 2)
    cv2.line(crop, (0, int(by - y0)), (crop.shape[1], int(by - y0)), (0, 0, 255), 2)
    cv2.line(crop, (int(cx - x0), 0), (int(cx - x0), crop.shape[0]), (255, 255, 0), 1)
    crop = cv2.resize(crop, (700, int(700 * crop.shape[0] / crop.shape[1])), interpolation=cv2.INTER_AREA)
    ov = base.copy()
    cv2.rectangle(ov, (int(cx - 2.2 * hgt), int(tip - 0.9 * hgt)), (int(cx + 2.2 * hgt), int(by + 1.6 * hgt)), (0, 255, 0), max(4, base.shape[1] // 300))
    sc = 700 / base.shape[1]
    ov = cv2.resize(ov, (700, int(base.shape[0] * sc)), interpolation=cv2.INTER_AREA)
    hmax = max(ov.shape[0], crop.shape[0])
    ov = cv2.copyMakeBorder(ov, 0, hmax - ov.shape[0], 0, 0, cv2.BORDER_CONSTANT)
    crop = cv2.copyMakeBorder(crop, 0, hmax - crop.shape[0], 0, 0, cv2.BORDER_CONSTANT)
    cv2.imwrite(str(path), np.hstack([ov, crop]), [cv2.IMWRITE_JPEG_QUALITY, 90])


# ---------------------------------------------------------------- flame effect
class Flame:
    def __init__(self, base, loc, cfg):
        self.base = base
        self.cx, self.tip, self.by = float(loc["cx"]), float(loc["tip"]), float(loc["base"])
        hgt = self.by - self.tip
        s = hgt / REF_H
        self.s = s
        self.amp = float(cfg.get("lean", 0.018)) * hgt
        self.str_amp = float(cfg.get("stretch", 0.03))
        self.glow_k = float(cfg.get("glow", 0.03))
        bh, bw = base.shape[:2]
        self.x0, self.x1 = max(0, int(self.cx - 115 * s)), min(bw, int(self.cx + 115 * s))
        self.y0, self.y1 = max(0, int(self.tip - 95 * s)), min(bh, int(self.by + 4))
        yy, xx = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.h = np.clip((self.by - yy) / hgt, 0, 1.4)
        mx = np.exp(-(((xx - self.cx) / (58.0 * s)) ** 4))
        mtop = np.clip((yy - (self.tip - 95 * s)) / (60.0 * s), 0, 1)
        mtop = mtop * mtop * (3 - 2 * mtop)
        mbot = np.clip((self.by - yy) / (14.0 * s), 0, 1)
        self.m = (mx * mtop * mbot).astype(np.float32)
        self.gx0, self.gx1 = max(0, int(self.cx - 330 * s)), min(bw, int(self.cx + 330 * s))
        self.gy0, self.gy1 = max(0, int(self.by - 460 * s)), min(bh, int(self.by + 0.45 * hgt))
        gy, gx = np.mgrid[self.gy0:self.gy1, self.gx0:self.gx1].astype(np.float32)
        G = np.exp(-(((gx - self.cx) / (150.0 * s)) ** 2 + ((gy - (self.by - 70 * s)) / (165.0 * s)) ** 2) / 2)
        cut = np.clip((self.by + 0.40 * hgt - gy) / (0.25 * hgt), 0, 1)  # zero by 0.4H below the rim
        self.G = (G * cut).astype(np.float32)[..., None]

    def frame(self, sig, i):
        t, lean, bend, stretch, width, light, gust = sig
        base = self.base.copy()
        A = self.amp * (lean[i] + 1.8 * gust[i])
        B = 0.9 * self.amp * bend[i]
        s_ = float(np.clip(self.str_amp * (stretch[i] - 0.8 * gust[i]), -0.08, 0.08))
        w = float(np.clip(-0.5 * s_ + 0.012 * width[i], -0.06, 0.06))
        h, m = self.h, self.m
        hs = np.minimum(h, 1.0)
        y_src = self.by - (self.by - self.yy) / (1.0 + s_ * m)
        dx = A * np.power(hs, 1.6) + B * np.sin(np.pi * hs) * hs
        x_src = self.xx - m * dx
        x_src = self.cx + (x_src - self.cx) / (1.0 + w * m * np.sin(np.pi * hs))
        patch = cv2.remap(self.base, x_src.astype(np.float32), y_src.astype(np.float32),
                          cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        base[self.y0:self.y1, self.x0:self.x1] = patch
        b = np.tanh(0.6 * light[i] + 0.4 * (s_ / max(self.str_amp, 1e-6)))
        k = self.glow_k * b
        reg = base[self.gy0:self.gy1, self.gx0:self.gx1].astype(np.float32)
        warm = np.array([0.75, 0.9, 1.0], dtype=np.float32)
        reg = reg * (1.0 + k * self.G * warm)
        base[self.gy0:self.gy1, self.gx0:self.gx1] = np.clip(reg, 0, 255).astype(np.uint8)
        return base, {"lean": float(A), "bend": float(B), "stretch": s_, "width": w, "light": float(k)}


def camera(base, z, fx, fy):
    """Window of size (2160/z x 3840/z) centred at fractional position (fx, fy) of the allowed range."""
    bh, bw = base.shape[:2]
    ww, wh = WIN_W / z, WIN_H / z
    ccx = ww / 2 + fx * max(0.0, bw - ww)
    ccy = wh / 2 + fy * max(0.0, bh - wh)
    sc = WIN_W / z / W  # base px per output px
    M = np.array([[sc, 0, ccx - sc * W / 2], [0, sc, ccy - sc * H / 2]], dtype=np.float64)
    return cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def render_flame(job, out_dir):
    t0 = time.monotonic()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="flame_"))
    shot = job["shots"][0]
    src = R.fetch(shot["src"], tmp, 1)
    base, (iw, ih) = build_base(src)
    fcfg = job["flame"]
    if "base_xy" in fcfg:
        loc = dict(fcfg["base_xy"])
        loc["height"] = loc["base"] - loc["tip"]
        loc["detected"] = False
    else:
        loc = detect_flame(base, fcfg.get("hint"))
        loc["detected"] = True
    fl = Flame(base, loc, fcfg)
    debug_sheet(base, loc, out_dir / f"{job['id']}-sheet1.jpg")
    shots_meta = [{"index": 1, "source_url": shot["src"], "source_sha256": R.sha256(src),
                   "source_size": f"{iw}x{ih}", "base_size": f"{base.shape[1]}x{base.shape[0]}",
                   "duration_s": float(shot["dur"]), "layout": "cover"}]
    if job.get("dry_run"):
        meta = {"dry_run": True, "flame_location_base_px": loc, "shots": shots_meta,
                "render_script_seconds": round(time.monotonic() - t0, 1)}
        shutil.rmtree(tmp, ignore_errors=True)
        return shots_meta, meta
    dur = float(shot["dur"])
    n = int(round(dur * FPS))
    mo = shot["motion"]
    z0, z1 = float(mo["z0"]), float(mo["z1"])
    fx0, fx1 = float(mo.get("fx0", 0.5)), float(mo.get("fx1", mo.get("fx0", 0.5)))
    fy0, fy1 = float(mo.get("fy0", 0.5)), float(mo.get("fy1", mo.get("fy0", 0.5)))
    sig = make_signals(n, int(fcfg.get("seed", 11)), float(fcfg.get("gust_t", 4.6)))
    if job.get("stills"):
        # typography preview: text-free frames at given times, identical image/flame/camera to the video
        names = []
        for ts in job["stills"]:
            i = min(n - 1, int(round(float(ts) * FPS)))
            u = smoothstep(i / (n - 1))
            eff, _ = fl.frame(sig, i)
            fr = camera(eff, z0 + (z1 - z0) * u, fx0 + (fx1 - fx0) * u, fy0 + (fy1 - fy0) * u)
            nm = f"{job['id']}-still-{float(ts):.1f}.png"
            cv2.imwrite(str(out_dir / nm), fr); names.append(nm)
        shutil.rmtree(tmp, ignore_errors=True)
        return shots_meta, {"stills": names, "flame_location_base_px": loc}
    font = R.find_font()
    vf = ""
    if shot.get("text"):
        if shot["text"].get("v1"):
            import typo
            vf = typo.v1_filters(shot["text"], tmp, "hook") + ","
        else:
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
    cxy = []
    for i in range(n):
        u = smoothstep(i / (n - 1))
        z = z0 + (z1 - z0) * u
        fx, fy = fx0 + (fx1 - fx0) * u, fy0 + (fy1 - fy0) * u
        eff, prm = fl.frame(sig, i)
        frame = camera(eff, z, fx, fy)
        params.append(prm)
        if i in (0, n // 3, 2 * n // 3, n - 1):
            ref = camera(base, z, fx, fy)
            d = np.abs(frame.astype(np.int16) - ref.astype(np.int16)).max(axis=2)
            ys, xs = np.nonzero(d > 0)
            proof[f"frame_{i}"] = {
                "changed_pixels": int(len(xs)),
                "bbox_xyxy": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                "max_abs_diff": int(d.max()),
            }
        if i % max(1, n // 10) == 0:
            # flame position in output px for this frame (for the review strip)
            ww = WIN_W / z
            sc = ww / W
            ccx = ww / 2 + fx * max(0.0, base.shape[1] - ww)
            ccy = (WIN_H / z) / 2 + fy * max(0.0, base.shape[0] - WIN_H / z)
            ox = (fl.cx - (ccx - sc * W / 2)) / sc
            oy = (fl.by - (ccy - sc * H / 2)) / sc
            cxy.append((ox, oy))
            r = int(max(110, (loc["height"] / sc) * 1.7))
            x0, y0 = int(ox - r), int(oy - 2 * r)
            x0, y0 = max(0, min(W - 2 * r, x0)), max(0, min(H - 3 * r, y0))
            strip.append(cv2.resize(frame[y0:y0 + 3 * r, x0:x0 + 2 * r], (200, 300), interpolation=cv2.INTER_AREA))
        if i == n - 12:
            cv2.imwrite(str(tmp / "label.png"), frame)
        p.stdin.write(frame.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg failed")
    cv2.imwrite(str(out_dir / f"{job['id']}-contact.jpg"), np.hstack(strip), [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(out_dir / f"{job['id']}-label-frame.jpg"), cv2.imread(str(tmp / "label.png")),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    stats = {k: {"min": round(min(q[k] for q in params), 3), "max": round(max(q[k] for q in params), 3)}
             for k in params[0]}
    shutil.rmtree(tmp, ignore_errors=True)
    meta = {"shots": shots_meta, "flame_location_base_px": loc, "flame_params_range": stats,
            "flame_region_proof": proof, "camera": {"z0": z0, "z1": z1, "fx": [fx0, fx1], "fy": [fy0, fy1],
                                                    "ease": "smoothstep"},
            "render_script_seconds": round(time.monotonic() - t0, 1),
            "caption": job.get("caption"), "audio": job.get("audio", "silent")}
    return shots_meta, meta
