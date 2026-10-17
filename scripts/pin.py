"""Pinterest layout tool (job type: pin). Builds 1000x1500 Pins from REAL product photos: the photo is only
cover-cropped / scaled (never repainted); text and flat colors are added around or over it."""
import pathlib, tempfile
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R

W, H = 1000, 1500
CREAM, INK, BURG, OFFW = (243, 235, 221), (52, 38, 30), (88, 30, 44), (250, 245, 236)


def font(sz, bold=True):
    return ImageFont.truetype("fonts/DMSans-Bold.ttf" if bold else "fonts/DMSans-SemiBold.ttf", sz)


def cover(img, w, h, fx=0.5, fy=0.5):
    iw, ih = img.size
    s = max(w / iw, h / ih)
    nw, nh = int(round(iw * s)), int(round(ih * s))
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int((nw - w) * fx); y = int((nh - h) * fy)
    return im.crop((x, y, x + w, y + h))


def rounded(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.size[0], im.size[1]), r, fill=255)
    out = Image.new("RGBA", im.size); out.paste(im, (0, 0)); out.putalpha(m)
    return out


def lines(d, xy, texts, fnt, fill, leading, anchor="la", shadow=False):
    x, y = xy
    for t in texts:
        if shadow:
            d.text((x + 2, y + 3), t, font=fnt, fill=(0, 0, 0, 90), anchor=anchor)
        d.text((x, y), t, font=fnt, fill=fill, anchor=anchor)
        y += leading
    return y


def scrim(im, y0, y1, a0, a1):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    px = np.zeros((im.size[1], im.size[0], 4), np.uint8)
    for y in range(max(0, y0), min(im.size[1], y1)):
        t = (y - y0) / max(1, y1 - y0)
        px[y, :, 3] = int(255 * (a0 + (a1 - a0) * t))
    return Image.alpha_composite(im.convert("RGBA"), Image.fromarray(px, "RGBA"))


def check(d, x, y, s, col):
    d.line([(x, y + s * 0.55), (x + s * 0.35, y + s * 0.9), (x + s, y + s * 0.1)], fill=col, width=max(4, int(s * 0.14)), joint="curve")


def build(it, photo):
    lay = it["layout"]
    fx, fy = it.get("fx", 0.5), it.get("fy", 0.5)
    if lay == "photo_top_text":
        im = cover(photo, W, H, fx, fy).convert("RGBA")
        im = scrim(im, 0, int(it.get("scrim_h", 620)), it.get("scrim_a", 0.55), 0.0)
        d = ImageDraw.Draw(im)
        lines(d, (70, it.get("y", 120)), it["lines"], font(it.get("size", 92)), OFFW + (255,), int(it.get("size", 92) * 1.08), shadow=True)
        if it.get("sub"):
            d.text((72, it.get("y", 120) + int(it.get("size", 92) * 1.08) * len(it["lines"]) + 14), it["sub"], font=font(34, False), fill=OFFW + (255,))
        return im.convert("RGB")
    if lay == "card_bottom":
        im = Image.new("RGB", (W, H), CREAM)
        im.paste(cover(photo, W, 1000, fx, fy), (0, 0))
        d = ImageDraw.Draw(im)
        y = lines(d, (70, 1050), it["lines"], font(it.get("size", 86)), INK, int(it.get("size", 86) * 1.1))
        d.text((72, y + 22), it.get("sub", ""), font=font(36, False), fill=(120, 98, 84))
        return im
    if lay in ("checklist", "numbered"):
        bg = tuple(it.get("bg", CREAM)); fg = tuple(it.get("fg", INK))
        im = Image.new("RGBA", (W, H), bg + (255,))
        ph = rounded(cover(photo, 860, 640, fx, fy).convert("RGB"), 36)
        im.alpha_composite(ph, (70, 70))
        d = ImageDraw.Draw(im)
        d.text((70, 770), it["head"], font=font(it.get("size", 74)), fill=fg + (255,))
        y = 770 + int(it.get("size", 74) * 1.35)
        for k, t in enumerate(it["items"], 1):
            if lay == "checklist":
                d.rounded_rectangle((70, y + 6, 126, y + 62), 12, outline=fg + (255,), width=5)
                check(d, 80, y + 14, 38, fg + (255,))
            else:
                d.text((70, y), f"{k}.", font=font(54), fill=fg + (255,))
            d.text((150, y + 2), t, font=font(54, False), fill=fg + (255,))
            y += 92
        d.text((70, H - 120), it.get("foot", "AVENROW"), font=font(30), fill=fg + (170,))
        return im.convert("RGB")
    if lay == "quote_overlay":
        im = cover(photo, W, H, fx, fy).convert("RGBA")
        im = scrim(im, 0, H, 0.55, 0.55)
        d = ImageDraw.Draw(im)
        sz = it.get("size", 88)
        h_ = len(it["lines"]) * int(sz * 1.12)
        lines(d, (W // 2, (H - h_) // 2 - 40), it["lines"], font(sz), OFFW + (255,), int(sz * 1.12), anchor="ma")
        d.text((W // 2, H - 160), it.get("sub", ""), font=font(34, False), fill=OFFW + (230,), anchor="ma")
        return im.convert("RGB")
    if lay == "slip":
        im = Image.new("RGB", (W, H), (233, 222, 203))
        d = ImageDraw.Draw(im)
        d.rectangle((50, 50, W - 50, H - 50), fill=CREAM, outline=(150, 125, 100), width=4)
        d.text((W // 2, 130), "PERMISSION SLIP", font=font(40), fill=(130, 100, 80), anchor="ma")
        d.line([(120, 200), (W - 120, 200)], fill=(150, 125, 100), width=3)
        lines(d, (W // 2, 260), it["lines"], font(it.get("size", 104)), INK, int(it.get("size", 104) * 1.08), anchor="ma")
        ph = rounded(cover(photo, 700, 520, fx, fy).convert("RGB"), 28)
        base = im.convert("RGBA"); base.alpha_composite(ph, (150, 800))
        d = ImageDraw.Draw(base)
        d.text((W // 2, 1370), it.get("sub", ""), font=font(34, False), fill=(130, 100, 80), anchor="ma")
        return base.convert("RGB")
    raise SystemExit("unknown layout " + lay)


def run_pin(job, out_dir):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="pin_"))
    meta = []
    for n, it in enumerate(job["items"], 1):
        p = R.fetch(it["src"], tmp, n)
        photo = Image.open(p).convert("RGB")
        im = build(it, photo)
        assert im.size == (W, H)
        name = f"{job['id']}-crop-{it['name']}.jpg"
        im.save(out_dir / name, quality=93)
        meta.append({"name": it["name"], "file": name, "layout": it["layout"], "src": it["src"], "size": f"{W}x{H}"})
    return {"id": job["id"], "type": "pin", "items": meta}
