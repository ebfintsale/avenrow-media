"""AVENROW TikTok Typography V1: DM Sans SemiBold, off-white, soft layered shadow, minimal motion.
Spec (job text object):
  lines [str], align left|right|center, margin px (side margin for left/right), y, size, leading,
  weight semibold|bold, start, end, fade_in, fade_out, rise (px, subtle upward reveal), stagger (s)
"""
import pathlib

OFFWHITE = "0xFAF5EC"
FONTS = {"semibold": "fonts/DMSans-SemiBold.ttf", "bold": "fonts/DMSans-Bold.ttf"}
# soft shadow: stacked low-alpha copies (approximates a blur; no outline, no box)
SHADOW = [(0, 3, 0.20), (-2, 5, 0.12), (2, 5, 0.12), (0, 9, 0.08)]


def v1_filters(txt, tmp, prefix, still=False):
    font = str(pathlib.Path(FONTS[txt.get("weight", "semibold")]).resolve())
    size = int(txt["size"])
    lead = int(txt.get("leading", round(size * 1.14)))
    align = txt.get("align", "left")
    m = int(txt.get("margin", 84))
    s0, e = float(txt.get("start", 0.6)), float(txt.get("end", 3.4))
    fi, fo = float(txt.get("fade_in", 0.55)), float(txt.get("fade_out", 0.45))
    rise = float(txt.get("rise", 14))
    stag = float(txt.get("stagger", 0.12))
    peak = float(txt.get("alpha", 0.97))
    parts = []
    for i, line in enumerate(txt["lines"]):
        f = pathlib.Path(tmp) / f"{prefix}_{i}.txt"
        f.write_text(line, encoding="utf-8")
        s = s0 + stag * i
        if align == "left":
            x = f"{m}"
        elif align == "right":
            x = f"w-text_w-{m}"
        else:
            x = "(w-text_w)/2"
        y0 = int(txt["y"]) + i * lead
        if still:
            alpha_w, yy = f"{peak}", f"{y0}"
            alpha_s = lambda a: f"{a}"
        else:
            ramp = f"clip((t-{s})/{fi},0,1)"
            out = f"clip(({e}-t)/{fo},0,1)"
            env = f"{ramp}*{out}"
            alpha_w = f"{peak}*{env}"
            alpha_s = lambda a: f"{a}*{env}"
            yy = f"{y0}+{rise}*pow(1-{ramp},2)"
        for dx, dy, a in SHADOW:
            parts.append(
                f"drawtext=fontfile='{font}':textfile='{f}':fontsize={size}:fontcolor=0x000000:"
                f"alpha='{alpha_s(a)}':x={x}+{dx}:y={yy}+{dy}"
            )
        parts.append(
            f"drawtext=fontfile='{font}':textfile='{f}':fontsize={size}:fontcolor={OFFWHITE}:"
            f"alpha='{alpha_w}':x={x}:y={yy}"
        )
    return ",".join(parts)
