#!/usr/bin/env python3
"""AVENROW media renderer.

Usage: render.py jobs/<id>.json

Job types:
  smoke    - generated background + text only. No external assets.
  montage  - hard-cut montage of still images with camera motion + text.
             Source pixels are never regenerated or retouched: each shot is a
             crop/zoom of the original image file, with optional text on top.

Outputs (in ./out): <id>.mp4, <id>.json (spec + provenance report),
<id>-contact.jpg (one frame per shot), <id>-label-frame.jpg (full-res frame).
Exits non-zero if the finished file does not match the expected specs.
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

W, H, FPS, SS = 1080, 1920, 30, 3  # SS = internal supersampling for smooth sub-pixel motion
CREAM = "0xF7F0E4"

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def find_font():
    try:
        r = subprocess.run(
            ["fc-match", "-f", "%{file}|%{family}", "Inter:style=Medium"],
            capture_output=True, text=True, check=True,
        )
        path, family = r.stdout.split("|", 1)
        if "Inter" in family and pathlib.Path(path).exists():
            return path
    except Exception:
        pass
    for p in FALLBACK_FONTS:
        if pathlib.Path(p).exists():
            return p
    raise SystemExit("no usable font found for drawtext")


def run(cmd, quiet=False):
    if not quiet:
        print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def ffprobe_json(path, *extra):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", *extra, str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(r.stdout)


def even(n):
    return int(n) // 2 * 2


# ---------------------------------------------------------------- smoke test
def render_smoke(job, out_path):
    font = find_font()
    dur = float(job.get("duration", 5))
    vf = (
        f"drawtext=fontfile={font}:text='AVENROW':fontcolor={CREAM}:fontsize=120:"
        f"x=(w-text_w)/2:y=720:alpha='min(1,t/0.6)',"
        f"drawtext=fontfile={font}:text='render smoke test':fontcolor={CREAM}:fontsize=56:"
        f"x=(w-text_w)/2:y=880:alpha='min(1,max(0,(t-0.4)/0.6))'"
    )
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        f"gradients=s=1080x1920:r=30:d={dur}:c0=0x3a2a1e:c1=0x8a6a4a:speed=0.03",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(dur), "-vf", vf + ",format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", "-shortest", out_path,
    ])


# ------------------------------------------------------------------ montage
def fetch(src, dest_dir, idx):
    """Download a public URL (or copy a local test path). Returns path."""
    if not src.startswith("http"):
        p = pathlib.Path(src)
        d = dest_dir / f"src{idx}{p.suffix}"
        shutil.copy(p, d)
        return d
    suffix = pathlib.Path(src.split("?")[0]).suffix or ".img"
    d = dest_dir / f"src{idx}{suffix}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; avenrow-media-render/1.0)"}
    if "etsystatic" in src:
        headers["Referer"] = "https://www.etsy.com/"
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(src, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r, open(d, "wb") as f:
                shutil.copyfileobj(r, f)
            if d.stat().st_size < 1000:
                raise RuntimeError("download too small")
            return d
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise SystemExit(f"could not download {src}: {last}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_filters(txt, font, tmp, prefix):
    parts = []
    s, e = float(txt["start"]), float(txt["end"])
    fade = float(txt.get("fade", 0.25))
    a = float(txt.get("alpha", 1.0))
    size = int(txt["size"])
    leading = int(txt.get("leading", size * 1.35))
    alpha = (
        f"if(lt(t,{s}),0,if(lt(t,{s + fade}),(t-{s})/{fade},"
        f"if(lt(t,{e - fade}),1,if(lt(t,{e}),({e}-t)/{fade},0))))*{a}"
    )
    for i, line in enumerate(txt["lines"]):
        f = tmp / f"{prefix}_{i}.txt"
        f.write_text(line, encoding="utf-8")
        parts.append(
            f"drawtext=fontfile='{font}':textfile='{f}':fontsize={size}:fontcolor={CREAM}:"
            f"alpha='{alpha}':x=(w-text_w)/2:y={int(txt['y']) + i * leading}:"
            f"shadowcolor=0x000000@0.55:shadowx=0:shadowy=3"
        )
    return ",".join(parts)


def motion_exprs(m, n_frames, shot_idx):
    """zoompan z/x/y expressions: eased push/pull + pan + very light handheld sway."""
    z0, z1 = float(m["z0"]), float(m["z1"])
    fx0, fx1 = float(m.get("fx0", 0.5)), float(m.get("fx1", 0.5))
    fy0, fy1 = float(m.get("fy0", 0.5)), float(m.get("fy1", 0.5))
    ease_end = float(m.get("ease_end", 1.0))
    sway = float(m.get("sway", 3.0)) * SS  # +/- px at output scale, in supersampled px
    ph = 1.7 * (shot_idx + 1)
    u = f"min(1,on/{n_frames * ease_end:.3f})"
    e = f"({u}*{u}*(3-2*{u}))"
    z = f"{z0}+({z1}-{z0})*{e}"
    shx = f"{sway:.2f}*(sin(on*0.13+{ph:.2f})+0.5*sin(on*0.31+{2 * ph:.2f}))"
    shy = f"{sway * 0.8:.2f}*(sin(on*0.11+{ph + 1:.2f})+0.5*sin(on*0.27+{2 * ph + 1:.2f}))"
    x = f"min(max((iw-iw/zoom)*({fx0}+({fx1}-{fx0})*{e})+{shx},0),iw-iw/zoom)"
    y = f"min(max((ih-ih/zoom)*({fy0}+({fy1}-{fy0})*{e})+{shy},0),ih-ih/zoom)"
    return z, x, y


def cover_crop(iw, ih, cx=0.5, cy=0.5):
    """Largest 9:16 crop window inside the image."""
    if iw / ih > 9 / 16:
        cw, ch = even(ih * 9 / 16), even(ih)
    else:
        cw, ch = even(iw), even(iw * 16 / 9)
    x = int((iw - cw) * cx)
    y = int((ih - ch) * cy)
    return cw, ch, x, y


def render_shot(idx, shot, srcfile, dims, font, tmp, out_clip):
    iw, ih = dims
    n = round(float(shot["dur"]) * FPS)
    m = shot["motion"]
    mode = shot.get("mode", "auto")
    ratio = iw / ih
    if mode == "auto":
        mode = "cover" if ratio <= 0.72 else "contain"
    txt = text_filters(shot["text"], font, tmp, f"s{idx}") if shot.get("text") else ""
    z, x, y = motion_exprs(m, n, idx)
    if mode == "cover":
        cw, ch, cx, cy = cover_crop(iw, ih, float(shot.get("cropx", 0.5)), float(shot.get("cropy", 0.5)))
        vf = (
            f"format=rgb24,crop={cw}:{ch}:{cx}:{cy},scale={W * SS}:{H * SS}:flags=lanczos,setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},setsar=1"
        )
        if txt:
            vf += "," + txt
        graph = ["-vf", vf]
    else:  # contain: whole photo on a soft blurred copy of itself (no cropping of the product)
        hfg = even(round(W * ih / iw))
        yfg = max(220, (1390 - hfg) // 2)
        cw, ch, cx, cy = cover_crop(iw, ih)
        fc = (
            f"[0:v]format=rgb24,split=2[a][b];"
            f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{H}:flags=lanczos,boxblur=34:6,"
            f"eq=brightness=-0.05:saturation=0.9,setsar=1[bg];"
            f"[b]scale={W * SS}:{hfg * SS}:flags=lanczos,setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{hfg}:fps={FPS},setsar=1[fg];"
            f"[bg][fg]overlay=0:{yfg}"
        )
        if txt:
            fc += "," + txt
        graph = ["-filter_complex", fc]
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS:.4f}", "-i", srcfile,
        *graph, "-frames:v", str(n), "-r", str(FPS), "-c:v", "ffv1", "-pix_fmt", "gbrp", out_clip,
    ])
    return {"mode": mode, "frames": n}


def render_montage(job, out_dir):
    t0 = time.monotonic()
    font = find_font()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="montage_"))
    shots_meta, clips = [], []
    for i, shot in enumerate(job["shots"]):
        src = fetch(shot["src"], tmp, i)
        dims_j = ffprobe_json(src, "-select_streams", "v:0", "-show_entries", "stream=width,height")
        iw, ih = dims_j["streams"][0]["width"], dims_j["streams"][0]["height"]
        clip = tmp / f"shot{i}.mkv"
        info = render_shot(i, shot, src, (iw, ih), font, tmp, clip)
        clips.append(clip)
        shots_meta.append({
            "index": i + 1, "source_url": shot["src"], "source_sha256": sha256(src),
            "source_bytes": src.stat().st_size, "source_size": f"{iw}x{ih}",
            "duration_s": round(info["frames"] / FPS, 3), **{"layout": info["mode"]},
        })
    listfile = tmp / "list.txt"
    listfile.write_text("".join(f"file '{c}'\n" for c in clips))
    total = sum(s["duration_s"] for s in shots_meta)
    mp4 = out_dir / f"{job['id']}.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", listfile,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{total:.3f}",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-level", "4.1",
        "-r", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", "-shortest", mp4,
    ])
    # review frames: one per shot + one extra inside the last shot at full resolution
    starts, t = [], 0.0
    for s in shots_meta:
        starts.append(t)
        t += s["duration_s"]
    stamps = [round(st + d["duration_s"] * 0.55, 2) for st, d in zip(starts, shots_meta)]
    stamps.append(round(total - 0.45, 2))
    for k, ts in enumerate(stamps, 1):
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{ts}", "-i", mp4,
             "-frames:v", "1", tmp / f"f_{k}.png"], quiet=True)
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", tmp / "f_%d.png",
         "-vf", f"scale=360:-1,tile={len(stamps)}x1", "-frames:v", "1", "-q:v", "3",
         out_dir / f"{job['id']}-contact.jpg"], quiet=True)
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", tmp / f"f_{len(stamps)}.png",
         "-frames:v", "1", "-q:v", "2", out_dir / f"{job['id']}-label-frame.jpg"], quiet=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return shots_meta, round(time.monotonic() - t0, 1)


# ------------------------------------------------------------------ checking
def check_specs(info, want_dur):
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    num, den = v["avg_frame_rate"].split("/")
    fps = float(num) / float(den)
    dur = float(info["format"]["duration"])
    spec = {
        "width": v["width"], "height": v["height"], "codec": v["codec_name"],
        "profile": v.get("profile"), "pix_fmt": v["pix_fmt"], "fps": round(fps, 3),
        "duration_s": round(dur, 3), "audio_codec": a[0]["codec_name"] if a else None,
        "size_bytes": int(info["format"]["size"]), "bit_rate": int(info["format"]["bit_rate"]),
    }
    problems = []
    if (v["width"], v["height"]) != (W, H):
        problems.append("resolution")
    if v["codec_name"] != "h264":
        problems.append("codec")
    if v["pix_fmt"] != "yuv420p":
        problems.append("pix_fmt")
    if abs(fps - FPS) > 0.01:
        problems.append("fps")
    if abs(dur - want_dur) > 0.25:
        problems.append("duration")
    if not a:
        problems.append("audio_track")
    spec["problems"], spec["ok"] = problems, not problems
    return spec


def main():
    job = json.loads(pathlib.Path(sys.argv[1]).read_text())
    out_dir = pathlib.Path("out")
    out_dir.mkdir(exist_ok=True)
    mp4 = out_dir / f"{job['id']}.mp4"
    extra = {}
    if job.get("type") == "contact":
        import contact
        contact.run_contact(job, out_dir)
        return
    if job.get("type") == "smoke":
        render_smoke(job, mp4)
        want = float(job.get("duration", 5))
    elif job.get("type") == "montage":
        shots, secs = render_montage(job, out_dir)
        want = sum(s["duration_s"] for s in shots)
        extra = {"shots": shots, "render_script_seconds": secs, "caption": job.get("caption"),
                 "audio": job.get("audio", "silent")}
    elif job.get("type") == "flame":
        import render_flame
        shots, meta = render_flame.render_flame(job, out_dir)
        if job.get("dry_run"):
            (out_dir / f"{job['id']}.json").write_text(json.dumps(meta, indent=2))
            print(json.dumps(meta, indent=2))
            return
        want = float(job["shots"][0]["dur"])
        extra = meta
    else:
        raise SystemExit(f"unsupported job type: {job.get('type')}")
    info = ffprobe_json(mp4, "-show_format", "-show_streams")
    spec = check_specs(info, want)
    spec.update(extra)
    (out_dir / f"{job['id']}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    print(json.dumps(spec, indent=2, ensure_ascii=False))
    if not spec["ok"]:
        raise SystemExit(f"spec check failed: {spec['problems']}")


if __name__ == "__main__":
    main()
