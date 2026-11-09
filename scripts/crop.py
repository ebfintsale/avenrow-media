"""Instagram feed crops: cover-fit a source image to 1080x1350 (4:5) with a vertical/horizontal focus.
Job: {"type":"crop","id":..,"items":[{"name":..,"src":url,"fy":0.5,"fx":0.5,"preview":true}]}
Outputs <id>-src-<name>.jpg (source preview) and <id>-crop-<name>.jpg (1080x1350)."""
import cv2, json, pathlib, tempfile, shutil
import numpy as np

W, H = 1080, 1350


def _style(c, it):
    """Editorial feed layouts on top of the real photo (photo only cropped, never repainted)."""
    from PIL import Image, ImageDraw, ImageFont
    import pin as PN
    st = it["style"]
    img = Image.fromarray(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))
    bg = tuple(it.get("bg", (243, 235, 221))); fg = tuple(it.get("fg", (52, 38, 30)))
    sz = it.get("size", 70); fnt = PN.font(sz); lead = int(sz * 1.14); ls = it["lines"]
    if st == "band":  # photo on top, solid text band below
        bh = it.get("band", 300)
        out = Image.new("RGB", (W, H), bg)
        out.paste(img.crop((0, bh // 2, W, bh // 2 + H - bh)), (0, 0))
        d = ImageDraw.Draw(out)
        y = H - bh + (bh - lead * len(ls)) // 2 - 6
        PN.lines(d, (W // 2, y), ls, fnt, fg, lead, anchor="ma")
        return cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)
    if st == "top":  # text on a soft top scrim
        im = PN.scrim(img.convert("RGBA"), 0, it.get("scrim", 520), 0.55, 0.0)
        d = ImageDraw.Draw(im)
        PN.lines(d, (70, it.get("y", 90)), ls, fnt, (250, 245, 236, 255), lead, shadow=True)
        return cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    if st == "pill":
        im = img.convert("RGBA"); d = ImageDraw.Draw(im)
        tw = max(d.textlength(t, font=fnt) for t in ls); bw, bh = int(tw + 80), int(lead * len(ls) + 48)
        x0 = 54 if it.get("align", "left") == "left" else W - 54 - bw
        y0 = it.get("y", 60) if it.get("pos", "top") == "top" else H - 60 - bh
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(ov).rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 32, fill=bg + (238,))
        im = Image.alpha_composite(im, ov); d = ImageDraw.Draw(im)
        PN.lines(d, (x0 + 40, y0 + 22), ls, fnt, fg + (255,), lead)
        return cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    raise SystemExit("unknown style " + st)


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
            fy, fx = float(it.get("fy", 0.5)), float(it.get("fx", 0.5))
            z = float(it.get("z", 1.0))
            if z > 1.0:  # tighter window of the real photo (never repainted)
                cw, ch = w / z, h / z
                x0z = int(min(max(fx * w - cw / 2, 0), w - cw)); y0z = int(min(max(fy * h - ch / 2, 0), h - ch))
                im = im[y0z:y0z + int(ch), x0z:x0z + int(cw)]
                h, w = im.shape[:2]; fx = fy = 0.5
            s = max(W / w, H / h)
            nw, nh = int(round(w * s)), int(round(h * s))
            big = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
            x0 = int(round((nw - W) * fx)); y0 = int(round((nh - H) * fy))
            c = big[y0:y0 + H, x0:x0 + W]
            assert c.shape[:2] == (H, W), c.shape
            if it.get("style"):
                c = _style(c, it)
            cv2.imwrite(str(out_dir / f"{job['id']}-crop-{it['name']}.jpg"), c,
                        [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
            meta_i.update({"scale": round(s, 4), "crop_origin_in_scaled": [x0, y0], "out_size": f"{W}x{H}",
                           "fy": fy, "fx": fx,
                           "source_window_px": [round(x0 / s), round(y0 / s), round((x0 + W) / s), round((y0 + H) / s)]})
        meta["items"].append(meta_i)
    shutil.rmtree(tmp, ignore_errors=True)
    return meta
