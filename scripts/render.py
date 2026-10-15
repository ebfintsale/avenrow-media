#!/usr/bin/env python3
"""AVENROW media renderer.

Usage: render.py jobs/<id>.json

Job types:
  smoke  - generated background + text only. No external assets.

Outputs (in ./out): <id>.mp4 and <id>.json (ffprobe report + spec check).
Exits non-zero if the finished file does not match the expected specs.
"""
import json
import pathlib
import subprocess
import sys

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def find_font():
    for p in FONT_CANDIDATES:
        if pathlib.Path(p).exists():
            return p
    raise SystemExit("no usable font found for drawtext")


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def render_smoke(job, out_path):
    font = find_font()
    dur = float(job.get("duration", 5))
    # Generated gradient background, two text lines with a short fade-in.
    vf = (
        f"drawtext=fontfile={font}:text='AVENROW':fontcolor=0xF4EBDD:fontsize=120:"
        f"x=(w-text_w)/2:y=720:alpha='min(1,t/0.6)',"
        f"drawtext=fontfile={font}:text='render smoke test':fontcolor=0xF4EBDD:fontsize=56:"
        f"x=(w-text_w)/2:y=880:alpha='min(1,max(0,(t-0.4)/0.6))',"
        f"drawtext=fontfile={font}:text='1080x1920 - 30 fps - H.264':fontcolor=0xD9C7A8:fontsize=44:"
        f"x=(w-text_w)/2:y=980:alpha='min(1,max(0,(t-0.8)/0.6))'"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        f"gradients=s=1080x1920:r=30:d={dur}:c0=0x3a2a1e:c1=0x8a6a4a:speed=0.03",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(dur),
        "-vf", vf + ",format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", "-shortest",
        str(out_path),
    ]
    run(cmd)


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(r.stdout)


def check_specs(info, job):
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    num, den = v["avg_frame_rate"].split("/")
    fps = float(num) / float(den)
    dur = float(info["format"]["duration"])
    want = float(job.get("duration", 5))
    spec = {
        "width": v["width"], "height": v["height"], "codec": v["codec_name"],
        "profile": v.get("profile"), "pix_fmt": v["pix_fmt"], "fps": round(fps, 3),
        "duration_s": round(dur, 3), "audio_codec": a[0]["codec_name"] if a else None,
        "size_bytes": int(info["format"]["size"]),
        "bit_rate": int(info["format"]["bit_rate"]),
    }
    problems = []
    if (v["width"], v["height"]) != (1080, 1920):
        problems.append("resolution")
    if v["codec_name"] != "h264":
        problems.append("codec")
    if v["pix_fmt"] != "yuv420p":
        problems.append("pix_fmt")
    if abs(fps - 30) > 0.01:
        problems.append("fps")
    if abs(dur - want) > 0.25:
        problems.append("duration")
    spec["problems"] = problems
    spec["ok"] = not problems
    return spec


def main():
    job_path = pathlib.Path(sys.argv[1])
    job = json.loads(job_path.read_text())
    job_id = job["id"]
    out_dir = pathlib.Path("out")
    out_dir.mkdir(exist_ok=True)
    mp4 = out_dir / f"{job_id}.mp4"
    if job.get("type") == "smoke":
        render_smoke(job, mp4)
    else:
        raise SystemExit(f"unsupported job type: {job.get('type')}")
    info = probe(mp4)
    spec = check_specs(info, job)
    (out_dir / f"{job_id}.json").write_text(json.dumps(spec, indent=2))
    print(json.dumps(spec, indent=2))
    if not spec["ok"]:
        raise SystemExit(f"spec check failed: {spec['problems']}")


if __name__ == "__main__":
    main()
