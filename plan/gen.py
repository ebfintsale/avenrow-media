import json, sys, datetime, hashlib
sys.path.insert(0, '/home/claude/avenrow-media/plan')
from catalog import *
import pins as P, videos as V, feed as F
REL = "https://github.com/ebfintsale/avenrow-media/releases/download"
SLUG = {0:"goodmorning",1:"birthday",2:"goodvibes",3:"selfcareclub",4:"boo",5:"hauntedhouse",6:"trickortreat",7:"ghostly",8:"midnight",9:"pumpkin",10:"spooky",
        11:"witching",12:"slowsunday",13:"staycozy",16:"mom",17:"dad",18:"sibling",19:"pet",23:"cwleaving",25:"housewarming",26:"samenew",27:"engagement",
        29:"norush",31:"hcouples",32:"baddec",33:"ghostscan",35:"cwfunny",37:"anniv",39:"cancelled",41:"introvert",43:"friend"}
PLAN_CROP = "feed-o25"
REDO = {"d25-s3-12","d27-s1-10","d29-s1-07"}
def et(d, hhmm, jit=0):
    h, m = map(int, hhmm.split(':'))
    return datetime.datetime(2026, 10, d, h, m) + datetime.timedelta(minutes=jit)
def dubai(t): return t + datetime.timedelta(hours=8)
PIN_T = ["09:00","11:30","14:00","16:30","19:00","21:30"]
TT_T = ["10:30","15:00","20:00"]
IG_T = ["08:00","10:30","12:45","15:00","17:30","19:45","21:45"]
def jit(d, s, k): return (d * 7 + s * 3 + k) % 9
_SC = {i['name']: i for i in json.load(open('/home/claude/avenrow-media/plan/scout.json'))['items']}
def hint_for(p, ph):
    if ph == 2 and 34 <= p <= 43: return {"hint": [.5, .1, .78, .42], "extra": [{"hint": [.22, .2, .52, .55]}]}
    it = _SC[f"{p:02d}-{ph}"]
    c = [x for x in it.get('cands', []) if 100 <= x['area'] <= 1300 and (x['box'][2]-x['box'][0]) <= 0.065 and 0.025 <= (x['box'][3]-x['box'][1]) <= 0.16 and 0.0 <= x['box'][1] <= 0.62 and 0.1 <= (x['box'][0] + x['box'][2]) / 2 <= 0.9]
    pad = lambda bx: [round(max(0, bx[0] - .04), 3), round(max(0, bx[1] - .04), 3), round(min(1, bx[2] + .04), 3), round(min(1, bx[3] + .06), 3)]
    twin = ph == 2 and (p, ph) not in ((31, 2), (32, 2), (33, 2))
    if not twin:
        c = [x for x in c if 0.3 <= (x['box'][0] + x['box'][2]) / 2 <= 0.7] or c
        return {"hint": pad(c[0]['box'])} if c else {"hint": [.36, .03, .66, .38]}
    if len(c) < 2: return {"hint": pad(c[0]['box'])} if c else {"hint": [.5, .1, .78, .42]}
    a0 = c[0]; a1 = next((x for x in c[1:] if abs((x['box'][0]+x['box'][2])/2 - (a0['box'][0]+a0['box'][2])/2) > .15), None)
    if not a1: return {"hint": pad(a0['box'])}
    return {"hint": pad(a0['box']), "extra": [{"hint": pad(a1['box'])}]}
def shot(plat, rec, lines, align, src):
    tt = plat == "tt"
    ytop = 118 if tt else 285
    mo = dict(z0=1.0, z1=1.07, fx0=.5, fx1=.5, fy0=.5, fy1=.5); fr = None; yt = ytop
    if rec == "tight_up": mo = dict(z0=1.2, z1=1.3, fx0=.5, fx1=.5, fy0=.55, fy1=.52)
    elif rec == "pull_back": mo = dict(z0=1.28, z1=1.0, fx0=.5, fx1=.5, fy0=.5, fy1=.5)
    elif rec == "pan_twin": mo = dict(z0=1.0, z1=1.0, fx0=.22, fx1=.78, fy0=.5, fy1=.5)
    elif rec == "frame":
        mo = dict(z0=1.0, z1=1.05, fx0=.5, fx1=.5, fy0=.5, fy1=.5)
        fr = {"top": 420 if tt else 500, "solid": [22, 17, 15]}
    txt = {"v1": True, "weight": "bold", "size": 68, "lines": lines, "align": align, "margin": 100 if align != "right" else 150,
           "y": yt, "leading": 68, "start": 0.5, "end": 3.5, "fade_in": 0.55, "fade_out": 0.45, "rise": 14, "stagger": 0.12}
    if not fr: txt["scrim"] = {"h": 700 if tt else 820, "max": 0.36, "pow": 1.6}
    s = {"src": src, "dur": 8.0, "mode": "cover", "motion": mo, "text": txt}
    if fr: s["frame"] = fr
    return s
def vjob(plat, d, s, p, ph, rec, lines, align, mus, start, k):
    jid = f"o25-{plat}-{d}-{s}-{SLUG.get(p,p)}"
    fl = hint_for(p, ph); fl.update({"seed": 40 + k, "gust_t": round(3.6 + (k * 37 % 20) / 10, 1)})
    if "extra" in fl:
        fl["extra"] = [dict(e, seed=140 + k, gust_t=3.2) for e in fl["extra"]]
    return jid, {"id": jid, "type": "flame", "product": jid, "audio": "music", "flame": fl,
            "shots": [shot(plat, rec, lines, align, img(p, ph))], "typography": "AVENROW Typography V1",
            "music": {"url": f"{REL}/video-music-lib-002/music-lib-002-{V.M[mus]}.wav", "start": start, "gain_db": 0},
            "note": f"Oct25-31 {plat} d{d} s{s}"}
def build():
    out = []  # manifest rows
    jobs = {}
    # pins
    changed = {(25,0),(25,3),(25,5),(26,3),(26,5),(27,1),(27,5),(28,2),(29,2),(29,3),(30,1),(30,5),(31,0)}
    for n, (d, s, p, ph, lay, args, board, title, desc) in enumerate(P.PINS):
        name = f"d{d}-s{s}-{p:02d}"
        rid = "pins-r3" if (d, s) in changed else f"pins-r2-{n // 14 + 1}"
        t = et(d, PIN_T[s], jit(d, s, 0))
        out.append(dict(plat="pinterest", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{rid}/{rid}-crop-{name}.jpg",
                        board=board, title=title, text=desc, link=URL[p], layout=lay))
    k = 0
    for (d, s, p, ph, rec, lines, align, mus, start, cap, tags) in V.TT:
        k += 1
        jid, j = vjob("tt", d, s, p, ph, rec, lines, align, mus, start, k); jobs[jid] = j
        t = et(d, TT_T[s], jit(d, s, 1))
        cta = V.CTA[(k * 3) % len(V.CTA)]
        out.append(dict(plat="tiktok", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{jid}/{jid}.mp4",
                        text=f"{cap} {tags} {cta}", music=V.M[mus], job=jid, recipe=rec, hook=" / ".join(lines)))
    for (d, s, p, ph, rec, lines, align, mus, start, cap, tags) in V.RL:
        k += 1
        jid, j = vjob("ig", d, s, p, ph, rec, lines, align, mus, start, k); jobs[jid] = j
        t = et(d, IG_T[s], jit(d, s, 2))
        cta = "" if k % 3 else "\n\nShop AVENROW → link in bio"
        out.append(dict(plat="instagram", fmt="REEL", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=f"{REL}/video-{jid}/{jid}.mp4",
                        text=f"{cap}{cta}\n\n{tags}", music=V.M[mus], job=jid, recipe=rec, hook=" / ".join(lines)))
    items = []
    for n, (d, s, p, ph, z, fx, fy, cap, alt, tags) in enumerate(F.FEED):
        name = f"d{d}-s{s}-{p:02d}"
        items.append(dict(name=name, src=img(p, ph), z=z, fx=fx, fy=fy))
        t = et(d, IG_T[s], jit(d, s, 2))
        cta = "\n\nLink in bio to shop." if n % 4 == 1 else ""
        out.append(dict(plat="instagram", fmt="POST", day=d, slot=s, prod=p, photo=ph, et=str(t), dubai=str(dubai(t)), media=(f"{REL}/video-feed-o25b/feed-o25b-crop-{name}.jpg" if name in REDO else f"{REL}/video-{PLAN_CROP}/{PLAN_CROP}-crop-{name}.jpg"),
                        text=f"{cap}{cta}\n\n{tags}", alt=alt))
    jobs[PLAN_CROP] = {"id": PLAN_CROP, "type": "crop", "items": items}
    jobs["feed-o25b"] = {"id": "feed-o25b", "type": "crop", "items": [i for i in items if i["name"] in REDO]}
    return out, jobs
if __name__ == "__main__":
    out, jobs = build()
    json.dump(out, open('/home/claude/avenrow-media/plan/manifest.json', 'w'), indent=1, ensure_ascii=False)
    json.dump({k: v for k, v in jobs.items()}, open('/tmp/claude-0/jobs_all.json', 'w'))
    from collections import Counter
    print(len(out), Counter((o['plat'], o.get('fmt')) for o in out), len(jobs))
    # ET-day counts
    c = Counter((o['plat'], o['day']) for o in out); print(sorted(c.items()))
