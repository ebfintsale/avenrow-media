"""Instagram feed crops: cover-fit a source image to 1080x1350 (4:5) with a vertical/horizontal focus.
Job: {"type":"crop","id":..,"items":[{"name":..,"src":url,"fy":0.5,"fx":0.5,"preview":true}]}
Outputs <id>-src-<name>.jpg (source preview) and <id>-crop-<name>.jpg (1080x1350)."""
import cv2, json, pathlib, tempfile, shutil
import numpy as np

W, H = 1080, 1350


def run_crop(job, out_dir):
    import render as R
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="crop_"))
    meta = {"items": []}
    for i, it in enumerate(job["items"]):
        p = R.fetch(it["src"], tmp, i)
        im = cv2.imread(str(p), cv2.IMREAD_COLOR)
        h, w = im.shape[:2]
        meta_i = {"name": it["name"], "src": it["src"], "src_size": f"{w}x{h}", "sha256": R.sha256(p)}
        cv2.imwrite(str(out_dir / f"{job['id']}-src-{it['name']}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not it.get("preview_only"):
            s = max(W / w, H / h)
            nw, nh = int(round(w * s)), int(round(h * s))
            big = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
            fy, fx = float(it.get("fy", 0.5)), float(it.get("fx", 0.5))
            x0 = int(round((nw - W) * fx)); y0 = int(round((nh - H) * fy))
            c = big[y0:y0 + H, x0:x0 + W]
            assert c.shape[:2] == (H, W), c.shape
            cv2.imwrite(str(out_dir / f"{job['id']}-crop-{it['name']}.jpg"), c,
                        [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
            meta_i.update({"scale": round(s, 4), "crop_origin_in_scaled": [x0, y0], "out_size": f"{W}x{H}",
                           "fy": fy, "fx": fx,
                           "source_window_px": [round(x0 / s), round(y0 / s), round((x0 + W) / s), round((y0 + H) / s)]})
        meta["items"].append(meta_i)
    shutil.rmtree(tmp, ignore_errors=True)
    return meta
