"""Read-only inspection job: download image URLs and tile them into labelled contact sheets."""
import pathlib, tempfile, cv2, numpy as np
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render as R

TW = 200
TWV = [200]


def thumb(path, label, TW=None):
    TW = TW or TWV[0]
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        img = np.zeros((300, TW, 3), np.uint8)
        ih, iw = 300, TW
    else:
        ih, iw = img.shape[:2]
    h = int(TW * ih / iw)
    t = cv2.resize(img, (TW, h), interpolation=cv2.INTER_AREA) if img.shape[1] != TW or img.shape[0] != h else img
    t = cv2.copyMakeBorder(t, 0, 0, 0, 0, cv2.BORDER_CONSTANT)
    cv2.rectangle(t, (0, 0), (TW, 22), (0, 0, 0), -1)
    cv2.putText(t, f"{label} {iw}x{ih}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return t


def run_contact(job, out_dir):
    TWV[0] = int(job.get('tw', 200))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="contact_"))
    rows, meta, n = [], [], 0
    for g in job["groups"]:
        ts = []
        for i, u in enumerate(g["urls"], 1):
            n += 1
            try:
                p = R.fetch(u, tmp, n)
                ts.append(thumb(p, f"{g['label']}#{i}"))
                meta.append({"group": g["label"], "idx": i, "url": u, "ok": True})
            except Exception as e:  # keep going; report failures
                ts.append(thumb("/nonexistent", f"{g['label']}#{i} FAIL"))
                meta.append({"group": g["label"], "idx": i, "url": u, "ok": False, "err": str(e)[:120]})
        H = max(t.shape[0] for t in ts)
        ts = [cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in ts]
        rows.append(np.hstack(ts))
    W = max(r.shape[1] for r in rows)
    rows = [cv2.copyMakeBorder(r, 0, 4, 0, W - r.shape[1], cv2.BORDER_CONSTANT) for r in rows]
    per = int(job.get("rows_per_sheet", 3))
    for s in range(0, len(rows), per):
        cv2.imwrite(str(out_dir / f"{job['id']}-sheet{s // per + 1}.jpg"), np.vstack(rows[s:s + per]),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
    import json
    (out_dir / f"{job['id']}.json").write_text(json.dumps({"id": job["id"], "ok": True, "images": meta}, indent=1))
