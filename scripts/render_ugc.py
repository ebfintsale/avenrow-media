"""UGC-style Reel assembler (job type: ugc).

Builds a short phone-style Reel from segments, each one of:
  clip  - an AI-generated handheld clip (hands / scene only, NO AVENROW label visible). Cover-cropped to 1080x1920.
  photo - a real Etsy product photo with a light handheld-style move (pixels never regenerated).
  flame - a real Etsy product photo with the existing local flame flicker (render_flame), label untouched.
Any frame where the product label is readable must come from a photo/flame segment.

Then: hard cuts, optional text overlays on the final timeline (AVENROW Typography V1),
original library music (start+dur must fit inside the track), optional voiceover with music ducking.
Raw AI clips and the voiceover are copied into the release for provenance.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R  # noqa: E402

W, H, FPS = R.W, R.H, R.FPS
NORM = ("scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,"
        "setsar=1,format=yuv420p")


def _enc_norm(src, dst, extra_vf=""):
    vf = (extra_vf + "," if extra_vf else "") + NORM
    R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-an", "-vf", vf,
           "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "10", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", dst], quiet=True)


def _dur(path):
    j = R.ffprobe_json(path, "-show_entries", "format=duration")
    return float(j["format"]["duration"])


def render_ugc(job, out_dir):
    t0 = time.monotonic()
    jid = job["id"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ugc_"))
    font = R.find_font()
    norm_files, seg_meta = [], []
    for i, seg in enumerate(job["segments"]):
        kind = seg["kind"]
        dur = float(seg["dur"])
        n_out = tmp / f"seg{i}.mp4"
        if kind == "clip":
            raw = R.fetch(seg["url"], tmp, i)
            shutil.copy(raw, out_dir / f"{jid}-raw{i}.mp4")
            info = R.ffprobe_json(raw, "-select_streams", "v:0", "-show_entries", "stream=width,height,duration")
            ss = float(seg.get("ss", 0))
            speed = float(seg.get("speed", 1.0))
            vf = f"setpts=PTS/{speed}," if speed != 1.0 else ""
            vf += f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS}"
            if seg.get("grade"):
                vf += "," + seg["grade"]
            trimmed = tmp / f"clip{i}.mp4"
            R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{ss}", "-i", raw,
                   "-t", f"{dur}", "-an", "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-crf", "10",
                   "-pix_fmt", "yuv420p", trimmed], quiet=True)
            _enc_norm(trimmed, n_out)
            seg_meta.append({"kind": kind, "url": seg["url"], "sha256": R.sha256(raw),
                             "source": info["streams"][0], "ss": ss, "dur": dur})
        elif kind == "photo":
            src = R.fetch(seg["src"], tmp, i)
            d = R.ffprobe_json(src, "-select_streams", "v:0", "-show_entries", "stream=width,height")["streams"][0]
            shot = {"dur": dur, "mode": seg.get("mode", "cover"), "motion": seg["motion"]}
            for k in ("cropx", "cropy"):
                if k in seg:
                    shot[k] = seg[k]
            mkv = tmp / f"photo{i}.mkv"
            R.render_shot(i, shot, src, (d["width"], d["height"]), font, tmp, mkv)
            _enc_norm(mkv, n_out)
            seg_meta.append({"kind": kind, "src": seg["src"], "sha256": R.sha256(src), "dur": dur})
        elif kind == "flame":
            import render_flame
            sub = {"id": f"{jid}-seg{i}", "type": "flame", "flame": seg["flame"],
                   "shots": [{"src": seg["src"], "dur": dur, "mode": "cover", "motion": seg["motion"]}]}
            sd = tmp / f"flame{i}"
            sd.mkdir()
            render_flame.render_flame(sub, sd)
            _enc_norm(sd / f"{jid}-seg{i}.mp4", n_out)
            shutil.copy(sd / f"{jid}-seg{i}-contact.jpg", out_dir / f"{jid}-seg{i}-flame-contact.jpg")
            seg_meta.append({"kind": kind, "src": seg["src"], "dur": dur})
        else:
            raise SystemExit(f"unknown segment kind {kind}")
        norm_files.append(n_out)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in norm_files))
    joined = tmp / "joined.mp4"
    R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
           "-c", "copy", joined], quiet=True)
    total = _dur(joined)

    # --- text overlays on the final timeline
    vf = []
    import typo
    for k, t in enumerate(job.get("texts", [])):
        vf.append(typo.v1_filters(t, tmp, f"t{k}"))
    vchain = ",".join(vf) if vf else "null"

    # --- audio: library music + optional voiceover with ducking
    mcfg, vcfg = job.get("music"), job.get("vo")
    inputs = ["-i", str(joined)]
    fc = []
    ai = 1
    if mcfg:
        trk = R.fetch(mcfg["url"], tmp, 90)
        start = float(mcfg.get("start", 0))
        inputs += ["-ss", f"{start:.2f}", "-t", f"{total:.3f}", "-i", str(trk)]
        fo = min(1.5, total / 3)
        fc.append(f"[{ai}:a]aresample=44100,aformat=channel_layouts=stereo,afade=t=in:d=0.4,"
                  f"afade=t=out:st={max(0, total - fo):.2f}:d={fo:.2f},volume={float(mcfg.get('gain_db', 0))}dB[mus]")
        ai += 1
    if vcfg:
        vo = R.fetch(vcfg["url"], tmp, 91)
        shutil.copy(vo, out_dir / f"{jid}-vo{vo.suffix}")
        inputs += ["-i", str(vo)]
        delay = int(float(vcfg.get("delay", 0)) * 1000)
        fc.append(f"[{ai}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={delay}|{delay},"
                  f"volume={float(vcfg.get('gain_db', 0))}dB,apad=whole_dur={total:.3f}[vo]")
        if mcfg:
            fc.append("[vo]asplit[vo1][vo2]")
            fc.append("[mus][vo1]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=400[duck]")
            fc.append("[duck][vo2]amix=inputs=2:normalize=0:duration=longest[mix]")
        else:
            fc.append("[vo]anull[mix]")
    elif mcfg:
        fc.append("[mus]anull[mix]")
    mp4 = out_dir / f"{jid}.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs]
    if fc:
        cmd += ["-filter_complex", ";".join(fc), "-map", "0:v:0", "-map", "[mix]"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v:0", "-map", f"{ai}:a"]
    cmd += ["-vf", vchain, "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(mp4)]
    R.run(cmd, quiet=True)

    lu = subprocess.run(["ffmpeg", "-i", str(mp4), "-af", "ebur128", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", lu)
    lufs = float(m[-1]) if m else None

    # --- review frames: 12 evenly spaced + full-res frames at each segment midpoint
    nfr = 12
    stamps = [round((k + 0.5) * total / nfr, 2) for k in range(nfr)]
    for k, ts in enumerate(stamps, 1):
        R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{ts}", "-i", mp4, "-frames:v", "1",
               tmp / f"f_{k:02d}.png"], quiet=True)
    R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", tmp / "f_%02d.png",
           "-vf", "scale=270:-1,tile=6x2", "-frames:v", "1", "-q:v", "3", out_dir / f"{jid}-contact.jpg"], quiet=True)
    t = 0.0
    for i, s in enumerate(seg_meta):
        mid = t + s["dur"] * 0.6
        R.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{mid:.2f}", "-i", mp4, "-frames:v", "1",
               "-q:v", "2", out_dir / f"{jid}-seg{i}-frame.jpg"], quiet=True)
        t += s["dur"]
    shutil.copy(out_dir / f"{jid}-seg{len(seg_meta) - 1}-frame.jpg", out_dir / f"{jid}-label-frame.jpg")
    shutil.rmtree(tmp, ignore_errors=True)
    extra = {"segments": seg_meta, "final_lufs": lufs, "music": mcfg, "vo": vcfg and {k: v for k, v in vcfg.items()},
             "render_script_seconds": round(time.monotonic() - t0, 1), "caption": job.get("caption"),
             "total_s": round(total, 3)}
    return total, extra
