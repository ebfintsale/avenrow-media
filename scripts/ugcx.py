"""Continuity-first UGC tools: probe (inspect a generated video), cutout (real product layer from an Etsy photo)."""
import json, pathlib, shutil, subprocess, sys, tempfile
import cv2, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R


def run_probe(job, out):
    jid = job["id"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="probe_"))
    v = R.fetch(job["url"], tmp, 0)
    info = R.ffprobe_json(v, "-show_entries", "format=duration:stream=width,height,r_frame_rate,nb_frames")
    dur = float(info["format"]["duration"])
    n = int(job.get("frames", 12))
    stamps = [min(dur - 0.05, (k + 0.5) * dur / n) for k in range(n)]
    for k, t in enumerate(stamps, 1):
        R.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", v, "-frames:v", "1", tmp / f"f{k:02d}.png"], quiet=True)
    R.run(["ffmpeg", "-y", "-v", "error", "-i", tmp / "f%02d.png", "-vf", f"scale=270:-1,tile=6x{(n+5)//6}",
           "-frames:v", "1", "-q:v", "3", out / f"{jid}-contact.jpg"], quiet=True)
    R.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.12", "-i", v, "-frames:v", "1", out / f"{jid}-last.png"], quiet=True)
    R.run(["ffmpeg", "-y", "-v", "error", "-i", v, "-frames:v", "1", out / f"{jid}-first.png"], quiet=True)
    for t in job.get("at", []):
        R.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t}", "-i", v, "-frames:v", "1", out / f"{jid}-at{t}.jpg"], quiet=True)
    meta = {"id": jid, "ok": True, "duration": dur, "info": info}
    shutil.rmtree(tmp, ignore_errors=True)
    return meta


def run_cutout(job, out):
    jid = job["id"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cut_"))
    src = R.fetch(job["src"], tmp, 0)
    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = [int(a) for a in (job["keep_box"][0] * w, job["keep_box"][1] * h, job["keep_box"][2] * w, job["keep_box"][3] * h)]
    crop = img[y0:y1, x0:x1]
    try:
        from rembg import remove, new_session
        sess = new_session(job.get("model", "isnet-general-use"))
        from PIL import Image
        rgba = np.array(remove(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), session=sess))
        alpha = rgba[:, :, 3]
        method = "rembg"
    except Exception as e:  # noqa: BLE001
        print("rembg failed", e)
        mask = np.zeros(crop.shape[:2], np.uint8)
        rect = (4, 4, crop.shape[1] - 8, crop.shape[0] - 8)
        bg, fg = np.zeros((1, 65)), np.zeros((1, 65))
        cv2.grabCut(crop, mask, rect, bg, fg, 8, cv2.GC_INIT_WITH_RECT)
        alpha = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
        method = "grabcut"
    # largest connected component only, then light feather
    bin_ = (alpha > 127).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bin_)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        bin_ = (lab == k).astype(np.uint8)
    bin_ = cv2.morphologyEx(bin_, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    # fill holes
    ff = bin_.copy(); m2 = np.zeros((bin_.shape[0] + 2, bin_.shape[1] + 2), np.uint8)
    cv2.floodFill(ff, m2, (0, 0), 2); bin_ = np.where(ff == 2, bin_, 1).astype(np.uint8)
    a = cv2.GaussianBlur(cv2.erode(bin_, np.ones((3, 3), np.uint8)).astype(np.float32) * 255, (0, 0), 1.2)
    ys, xs = np.nonzero(bin_)
    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    rgba = np.dstack([crop, a.astype(np.uint8)])[by0:by1, bx0:bx1]
    cv2.imwrite(str(out / f"{jid}-cutout.png"), rgba)
    prev = np.full((rgba.shape[0], rgba.shape[1], 3), (160, 200, 120), np.uint8)
    al = rgba[:, :, 3:4].astype(np.float32) / 255
    prev = (rgba[:, :, :3] * al + prev * (1 - al)).astype(np.uint8)
    cv2.imwrite(str(out / f"{jid}-cutout-preview.jpg"), prev, [cv2.IMWRITE_JPEG_QUALITY, 92])
    meta = {"id": jid, "ok": True, "method": method, "size": [int(rgba.shape[1]), int(rgba.shape[0])],
            "src_size": [w, h], "offset_in_src": [int(x0 + bx0), int(y0 + by0)]}
    shutil.rmtree(tmp, ignore_errors=True)
    return meta


def _cover(img, W=1080, H=1920):
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    r = cv2.resize(img, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    y0, x0 = (r.shape[0] - H) // 2, (r.shape[1] - W) // 2
    return r[y0:y0 + H, x0:x0 + W]


LABEL_RECT = (36, 195, 508, 655)  # label box inside jar_*.png (585x721), pixels


def run_comp(job, out):
    jid = job["id"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="comp_"))
    bg = _cover(cv2.imread(str(R.fetch(job["bg"], tmp, 0)), cv2.IMREAD_COLOR))
    jar = cv2.imread(f"assets/ucx/{job.get('jar', 'jar_unlit')}.png", cv2.IMREAD_UNCHANGED)
    pl = job["place"]
    s = pl["width"] / jar.shape[1]
    jw, jh = int(round(jar.shape[1] * s)), int(round(jar.shape[0] * s))
    jr = cv2.resize(jar, (jw, jh), interpolation=cv2.INTER_AREA)
    x0 = int(round(pl["cx"] - jw / 2)); y0 = int(round(pl["base_y"] - jh))
    out_img = bg.astype(np.float32)
    # contact + cast shadow (light from the left -> shadow falls right)
    sh = np.zeros(bg.shape[:2], np.float32)
    cv2.ellipse(sh, (int(pl["cx"] + jw * 0.04), int(pl["base_y"] - jh * 0.012)), (int(jw * 0.50), int(jw * 0.085)), 0, 0, 360, 1.0, -1)
    cast = np.zeros_like(sh)
    cv2.ellipse(cast, (int(pl["cx"] + jw * 0.42), int(pl["base_y"] - jh * 0.01)), (int(jw * 0.55), int(jw * 0.07)), 0, 0, 360, 1.0, -1)
    sh = np.clip(cv2.GaussianBlur(sh, (0, 0), jw * 0.025) * 0.55 + cv2.GaussianBlur(cast, (0, 0), jw * 0.05) * 0.35, 0, 0.75)
    out_img *= (1 - sh[:, :, None] * 0.75)
    # paste jar (real pixels, untouched colour)
    ys0, xs0 = max(0, y0), max(0, x0)
    ys1, xs1 = min(bg.shape[0], y0 + jh), min(bg.shape[1], x0 + jw)
    sub = jr[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    al = sub[:, :, 3:4].astype(np.float32) / 255
    out_img[ys0:ys1, xs0:xs1] = sub[:, :, :3].astype(np.float32) * al + out_img[ys0:ys1, xs0:xs1] * (1 - al)
    comp = np.clip(out_img, 0, 255).astype(np.uint8)
    cv2.imwrite(str(out / f"{jid}-comp.png"), comp)
    dbg = comp.copy()
    for g in range(0, 1920, 100):
        cv2.line(dbg, (0, g), (1080, g), (0, 255, 255), 1); cv2.putText(dbg, str(g), (4, g + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    for g in range(0, 1080, 100):
        cv2.line(dbg, (g, 0), (g, 1920), (0, 255, 255), 1); cv2.putText(dbg, str(g), (g + 2, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(str(out / f"{jid}-compdbg.jpg"), cv2.resize(dbg, None, fx=0.5, fy=0.5), [cv2.IMWRITE_JPEG_QUALITY, 88])
    cv2.imwrite(str(out / f"{jid}-bgonly.jpg"), cv2.resize(bg, None, fx=0.5, fy=0.5), [cv2.IMWRITE_JPEG_QUALITY, 88])
    lx0, ly0, lx1, ly1 = LABEL_RECT
    meta = {"id": jid, "ok": True, "jar_box": [x0, y0, x0 + jw, y0 + jh], "scale": s,
            "label_box_out": [int(x0 + lx0 * s), int(y0 + ly0 * s), int(x0 + lx1 * s), int(y0 + ly1 * s)]}
    shutil.rmtree(tmp, ignore_errors=True)
    return meta


def patch_clip(raw, comp_path, label_box, jar_box, dur, ss, out_mp4, dbg_dir, jid, W=1080, H=1920, FPS=30):
    """Re-impose the REAL label pixels (from the composited still) over a generated clip of the same still.
    Per frame: estimate small camera drift, keep generated pixels where something occludes the label (hand/sleeve)."""
    comp = cv2.imread(str(comp_path), cv2.IMREAD_COLOR)
    lx0, ly0, lx1, ly1 = label_box
    jx0, jy0, jx1, jy1 = jar_box
    pad = 70
    px0, py0, px1, py1 = max(0, jx0 - pad), max(0, jy0 - pad), min(W, jx1 + pad), min(H, jy1 + pad)
    ref = cv2.cvtColor(comp[py0:py1, px0:px1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    win = cv2.createHanningWindow((ref.shape[1], ref.shape[0]), cv2.CV_32F)
    # feathered label mask (rounded rect)
    m0 = np.zeros((H, W), np.float32)
    cv2.rectangle(m0, (lx0 + 3, ly0 + 3), (lx1 - 3, ly1 - 3), 1.0, -1)
    m0 = cv2.GaussianBlur(m0, (0, 0), 2.0)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{ss}", "-i", str(raw), "-t", f"{dur}",
                             "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p", str(out_mp4)],
                           stdin=subprocess.PIPE)
    fsz = W * H * 3
    stats, i, keep = [], 0, {}
    while True:
        buf = proc.stdout.read(fsz)
        if len(buf) < fsz:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        g = cv2.cvtColor(fr[py0:py1, px0:px1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        (dx, dy), resp = cv2.phaseCorrelate(ref, g, win)
        if abs(dx) > 25 or abs(dy) > 25 or resp < 0.03:
            dx, dy = 0.0, 0.0
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        cs = cv2.warpAffine(comp, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        ms = cv2.warpAffine(m0, M, (W, H), flags=cv2.INTER_LINEAR)
        # occlusion: large blurred luminance disagreement between generated frame and the real label pixels
        d = np.abs(cv2.GaussianBlur(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (0, 0), 7).astype(np.float32)
                   - cv2.GaussianBlur(cv2.cvtColor(cs, cv2.COLOR_BGR2GRAY), (0, 0), 7).astype(np.float32))
        occ = ((d > 40) & (ms > 0.5)).astype(np.uint8)
        occ = cv2.morphologyEx(occ, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(occ)
        keepocc = np.zeros_like(occ)
        for k in range(1, n):
            if st[k, cv2.CC_STAT_AREA] > 1200:
                keepocc[lab == k] = 1
        keepocc = cv2.dilate(keepocc, np.ones((25, 25), np.uint8))
        keepocc = cv2.GaussianBlur(keepocc.astype(np.float32), (0, 0), 8)
        mk = ms * (1 - np.clip(keepocc * 1.5, 0, 1))
        # exposure follow: scale real pixels by the local light change seen on the table beside the jar
        ring_f = fr[ly0:ly1, max(0, lx0 - 160):max(1, lx0 - 40)].astype(np.float32).mean()
        ring_c = comp[ly0:ly1, max(0, lx0 - 160):max(1, lx0 - 40)].astype(np.float32).mean()
        gain = float(np.clip(ring_f / max(ring_c, 1), 0.92, 1.08))
        cs2 = np.clip(cv2.GaussianBlur(cs, (0, 0), 0.8).astype(np.float32) * gain, 0, 255)
        outf = fr.astype(np.float32) * (1 - mk[:, :, None]) + cs2 * mk[:, :, None]
        outf = np.clip(outf, 0, 255).astype(np.uint8)
        enc.stdin.write(outf.tobytes())
        stats.append({"i": i, "dx": round(float(dx), 2), "dy": round(float(dy), 2), "resp": round(float(resp), 3),
                      "occ_px": int(keepocc.sum() > 1), "mask_mean": round(float(mk.sum() / max(ms.sum(), 1)), 3), "gain": round(gain, 3)})
        if i in (0, 40, 80, 120, 160):
            cv2.imwrite(str(pathlib.Path(dbg_dir) / f"{jid}-dbg{i}.jpg"), outf)
            cv2.imwrite(str(pathlib.Path(dbg_dir) / f"{jid}-dbgraw{i}.jpg"), fr)
        i += 1
    enc.stdin.close(); enc.wait(); proc.wait()
    return stats
