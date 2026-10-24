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
