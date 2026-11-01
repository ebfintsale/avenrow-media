import json, sys, datetime, re
sys.path.insert(0, '/home/claude/avenrow-media/plan2'); sys.path.insert(0, '/home/claude/avenrow-media/plan')
import gen as G
from catalog import *
import nov as N
REL = G.REL
def et(d, hhmm, jit=0):
    h, m = map(int, hhmm.split(':'))
    return datetime.datetime(2026, 11, d, h, m) + datetime.timedelta(minutes=jit)
def dubai(t): return t + datetime.timedelta(hours=9)
def jit(d, s, k): return (d * 7 + s * 3 + k) % 9
def slug(p): return re.sub(r'[^a-z0-9]+', '', NAME[p].lower())[:14]
def hint(p, ph):
    if p >= 44:
        if (p, ph) in N.HT:
            big, small = N.HT[(p, ph)]; return {"hint": big, "extra": [{"hint": small}]}
        assert ph == 1, (p, ph)
        return {"hint": N.HS[p]}
    return G.hint_for(p, ph)
def music_url(key):
    n = N.MUS[key]; lib = "003" if key in ("WM", "FG", "LE", "BM") else "002"
    return f"{REL}/video-music-lib-{lib}/music-lib-{lib}-{n}.wav"
def vjob(plat, d, s, p, ph, rec, lines, align, mus, start, k, dur):
    jid = f"n1-{plat}-{d}-{s}-{slug(p)}"
    fl = hint(p, ph); fl.update({"seed": 60 + k, "gust_t": round(3.6 + (k * 37 % 20) / 10, 1)})
    if "extra" in fl: fl["extra"] = [dict(e, seed=160 + k, gust_t=3.2) for e in fl["extra"]]
    sh = G.shot(plat, rec, lines, align, img(p, ph)); sh["dur"] = dur
    return jid, {"id": jid, "type": "flame", "product": jid, "audio": "music", "flame": fl, "shots": [sh], "typography": "AVENROW Typography V1",
                 "music": {"url": music_url(mus), "start": start, "gain_db": 0}, "note": f"Nov1-7 {plat} d{d} s{s}"}
PIN_JOB = lambda d: "nvp-1" if d == 1 else "nvp-2" if d <= 3 else "nvp-3" if d <= 5 else "nvp-4"
def build():
    out, jobs = [], {}
    pj = {}
    for n, (d, s, p, ph, lay, args, board, title, desc) in enumerate(N.PINS):
        name = f"d{d}-s{s}-{p:02d}"; jid = PIN_JOB(d)
        it = {"name": name, "layout": lay, "src": img(p, ph)}; it.update(args)
        pj.setdefault(jid, {"id": jid, "type": "pin", "items": []})["items"].append(it)
        t = et(d, N.PIN_T[d][s], jit(d, s, 0))
        assert URL[p], p
        out.append(dict(plat="pinterest", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{jid}/{jid}-crop-{name}.jpg",
                        board=board, title=title, text=desc, link=URL[p], layout=lay))
    jobs.update(pj)
    k = 0
    for (d, s, p, ph, rec, lines, align, mus, start, cap, tags) in N.TT:
        k += 1
        jid, j = vjob("tt", d, s, p, ph, rec, lines, align, mus, start, k, 8.0); jobs[jid] = j
        t = et(d, N.TT_T[d][s], jit(d, s, 1)); cta = N.CTA[(k * 3) % len(N.CTA)]
        out.append(dict(plat="tiktok", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{jid}/{jid}.mp4",
                        text=f"{cap} {tags} {cta}", music=N.MUS[mus], job=jid, recipe=rec, hook=" / ".join(lines)))
    for (d, s, p, ph, rec, lines, align, mus, start, cap, tags) in N.RL:
        k += 1
        jid, j = vjob("ig", d, s, p, ph, rec, lines, align, mus, start, k, 9.0); jobs[jid] = j
        t = et(d, N.IG_T[d][s], jit(d, s, 2)); cta = "" if k % 3 else "\n\nShop AVENROW → link in bio"
        out.append(dict(plat="instagram", fmt="REEL", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{jid}/{jid}.mp4",
                        text=f"{cap}{cta}\n\n{tags}", music=N.MUS[mus], job=jid, recipe=rec, hook=" / ".join(lines)))
    items = []
    for n, (d, s, p, ph, z, fx, fy, cap, alt, tags) in enumerate(N.FEED):
        name = f"d{d}-s{s}-{p:02d}"; items.append(dict(name=name, src=img(p, ph), z=z, fx=fx, fy=fy))
        t = et(d, N.IG_T[d][s], jit(d, s, 2))
        out.append(dict(plat="instagram", fmt="POST", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-nvf-1/nvf-1-crop-{name}.jpg",
                        text=f"{cap}\n\n{tags}", alt=alt))
    jobs["nvf-1"] = {"id": "nvf-1", "type": "crop", "items": items}
    return out, jobs
if __name__ == "__main__":
    out, jobs = build()
    json.dump(out, open('/home/claude/avenrow-media/plan2/manifest_nov.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(jobs, open('/tmp/claude-0/jobs_nov.json', 'w'))
    from collections import Counter
    print(len(out), Counter((o['plat'], o.get('fmt')) for o in out), len(jobs))
    print(sorted(Counter((o['plat'], o['day']) for o in out).items()))
    # ET day sanity
    for o in out:
        e = datetime.datetime.fromisoformat(o['et']); assert e.day == o['day'], o
    print("first slots:", sorted((o['et'], o['plat']) for o in out)[:6])
