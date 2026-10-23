"""Scout job (read-only): fetch images, detect lit-flame candidates (bright, tall, narrow blobs), and tile
labelled contact sheets with the candidate boxes drawn. Output: <id>-sheetN.jpg and <id>.json
Job: {"id":..,"type":"scout","tw":240,"cols":6,"rows":6,"items":[{"name":..,"url":..}]}"""
import pathlib, tempfile, shutil, json
import cv2, numpy as np
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R

COL = [(0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 0, 255)]


def candidates(img, thr_list=(228, 236, 244, 220, 250, 212)):
    h, w = img.shape[:2]
    half = cv2.resize(img, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    lum = (0.114 * half[..., 0] + 0.587 * half[..., 1] + 0.299 * half[..., 2]).astype(np.float32)
    for thr in thr_list:
        mask = (lum >= thr).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = []
        for i in range(1, n):
            x, y, ww, hh, a = stats[i]
            if a < 120 or a > 40000 or hh < 1.25 * ww:
                continue
            score = min(hh / max(ww, 1), 4.0) * np.sqrt(a) * (1.0 + 0.3 * float(lum[lab == i].mean() > 240))
            out.append((float(score), x / lum.shape[1], y / lum.shape[0], (x + ww) / lum.shape[1], (y + hh) / lum.shape[0], int(a)))
        if out:
            out.sort(reverse=True)
            return thr, out[:4]
    return None, []


def run_scout(job, out_dir):
    tw = int(job.get("tw", 240)); cols = int(job.get("cols", 6)); rows = int(job.get("rows", 6))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="scout_"))
    meta, tiles = [], []
    for n, it in enumerate(job["items"], 1):
        try:
            p = R.fetch(it["url"], tmp, n)
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            h, w = img.shape[:2]
            thr, cands = candidates(img)
            th = int(tw * h / w)
            t = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
            for k, (s, x0, y0, x1, y1, a) in enumerate(cands):
                cv2.rectangle(t, (int(x0 * tw), int(y0 * th)), (int(x1 * tw), int(y1 * th)), COL[k], 1)
            meta.append({"name": it["name"], "url": it["url"], "size": [w, h], "thr": thr,
                         "cands": [{"score": round(s, 1), "box": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)], "area": a}
                                   for (s, x0, y0, x1, y1, a) in cands]})
            label = f"{it['name']} {w}x{h} c{len(cands)}"
        except Exception as e:  # keep going
            t = np.zeros((tw, tw, 3), np.uint8); label = f"{it['name']} FAIL"
            meta.append({"name": it["name"], "url": it["url"], "error": str(e)[:200]})
        cv2.rectangle(t, (0, 0), (tw, 16), (0, 0, 0), -1)
        cv2.putText(t, label, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(cv2.resize(t, (tw, tw), interpolation=cv2.INTER_AREA) if t.shape[0] != tw else t)
    per = cols * rows
    for s in range(0, len(tiles), per):
        chunk = tiles[s:s + per]
        while len(chunk) % cols:
            chunk.append(np.zeros_like(tiles[0]))
        rws = [np.hstack(chunk[i:i + cols]) for i in range(0, len(chunk), cols)]
        cv2.imwrite(str(out_dir / f"{job['id']}-sheet{s // per + 1}.jpg"), np.vstack(rws), [cv2.IMWRITE_JPEG_QUALITY, 85])
    shutil.rmtree(tmp, ignore_errors=True)
    return {"id": job["id"], "type": "scout", "items": meta}
