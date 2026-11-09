import json, sys, datetime, re
sys.path.insert(0,'/home/claude/avenrow-media/plan3'); sys.path.insert(0,'/home/claude/avenrow-media/plan2'); sys.path.insert(0,'/home/claude/avenrow-media/plan')
import gen as G, nov as N, n9
from catalog import *
REL="https://github.com/ebfintsale/avenrow-media/releases/download"
def et(d,hhmm,jit=0):
    h,m=map(int,hhmm.split(':')); return datetime.datetime(2026,11,8+d,h,m)+datetime.timedelta(minutes=jit)
def dubai(t): return t+datetime.timedelta(hours=9)
def jit(d,k): return (d*7+k*5)%11-3
def slug(p): return re.sub(r'[^a-z0-9]+','',NAME[p].lower())[:12]
def hint(p,ph):
    if p>=44:
        if (p,ph) in N.HT:
            big,small=N.HT[(p,ph)]; return {"hint":big,"extra":[{"hint":small}]}
        assert ph==1,(p,ph); return {"hint":N.HS[p]}
    return G.hint_for(p,ph)
def music_url(key):
    n=N.MUS[key]; lib="003" if key in ("WM","FG","LE","BM") else "002"
    return f"{REL}/video-music-lib-{lib}/music-lib-{lib}-{n}.wav"
MO={"pull":dict(z0=1.28,z1=1.0,fx0=.5,fx1=.5,fy0=.5,fy1=.5),"pantwin":dict(z0=1.0,z1=1.0,fx0=.22,fx1=.78,fy0=.5,fy1=.5),
    "frame":dict(z0=1.0,z1=1.06,fx0=.5,fx1=.5,fy0=.5,fy1=.5),"drift":dict(z0=1.1,z1=1.02,fx0=.45,fx1=.55,fy0=.5,fy1=.5),
    "rise":dict(z0=1.02,z1=1.12,fx0=.5,fx1=.5,fy0=.58,fy1=.46)}
def shot(plat,rec,lines,align,src,dur,st):
    tt=plat=="tt"; ytop=118 if tt else 285
    sz=st.get("size",68 if not st.get("scrim_b") else 84)
    txt={"v1":True,"weight":"bold","size":max(sz,72) if sz<72 else sz,"lines":lines,"align":align,"margin":100,"y":ytop,"leading":int(sz*1.0),
         "start":0.15,"end":min(3.4,dur-3),"fade_in":0.4,"fade_out":0.4,"rise":12,"stagger":0.1}
    s={"src":src,"dur":dur,"mode":"cover","motion":MO[rec],"text":txt}
    if rec=="frame":
        top=max(st.get("top",420),420 if tt else 500); s["frame"]={"top":top,"solid":FR[st.get("frame","ink")]}
        txt["size"]=68; txt["leading"]=68; txt["y"]=ytop
    elif st.get("scrim_b"):
        txt["y"]=1180; txt["size"]=84; txt["leading"]=84; txt["scrim"]={"h":760,"max":0.45,"pow":1.5,"bottom":True}
        s["scrimtext_y"]=1180
    else:
        txt["scrim"]={"h":700 if tt else 820,"max":0.36,"pow":1.6}
    return s
from n9 import FR
def vjob(plat,d,p,ph,rec,lines,align,mus,start,dur,k,st):
    jid=f"n9-{plat}-{d}-{k:02d}-{slug(p)}"
    fl=hint(p,ph); fl.update({"seed":80+k,"gust_t":round(3.6+(k*37%20)/10,1)})
    if "extra" in fl: fl["extra"]=[dict(e,seed=180+k,gust_t=3.2) for e in fl["extra"]]
    sh=shot(plat,rec,lines,align,img(p,ph),dur,st); sh.pop("scrimtext_y",None)
    return jid,{"id":jid,"type":"flame","product":jid,"audio":"music","flame":fl,"shots":[sh],"typography":"AVENROW Typography V1",
      "music":{"url":music_url(mus),"start":start,"gain_db":0},"note":f"Nov9-15 {plat} d{d}"}
def build():
    out,jobs=[],{}
    PJ=lambda d:"n9p-1" if d<=2 else "n9p-2" if d<=4 else "n9p-3" if d<=6 else "n9p-4"
    for n,(d,t,p,ph,lay,args,board,title,desc,hol) in enumerate(n9.PINS):
        name=f"d{d}-{n:02d}-{p:02d}"; jid=PJ(d)
        it={"name":name,"layout":lay,"src":img(p,ph)}; it.update(args)
        if lay=="duo": it["src2"]=img(p,2)
        jobs.setdefault(jid,{"id":jid,"type":"pin","items":[]})["items"].append(it)
        assert URL[p].startswith("https://www.etsy.com/listing/"),p
        tt=et(d,t,jit(d,n))
        out.append(dict(plat="pinterest",day=d,prod=p,et=str(tt),dubai=str(dubai(tt)),media=[f"{REL}/video-{jid}/{jid}-crop-{name}.jpg"],board=board,title=title,text=desc,link=URL[p],layout=lay,hol=hol))
    k=0
    for (d,t,p,ph,rec,lines,al,mus,start,dur,cap,tags,hol,st) in n9.TT:
        k+=1; jid,j=vjob("tt",d,p,ph,rec,lines,al,mus,start,dur,k,st); jobs[jid]=j
        tt=et(d,t,jit(d,k)); cta=N.CTA[(k*3)%len(N.CTA)]
        out.append(dict(plat="tiktok",day=d,prod=p,et=str(tt),dubai=str(dubai(tt)),media=[f"{REL}/video-{jid}/{jid}.mp4"],text=f"{cap} {tags} {cta}",music=N.MUS[mus],job=jid,recipe=rec,hook=" / ".join(lines),hol=hol))
    for (d,t,p,ph,rec,lines,al,mus,start,dur,cap,tags,hol,st) in n9.RL:
        k+=1; jid,j=vjob("ig",d,p,ph,rec,lines,al,mus,start,dur,k,st); jobs[jid]=j
        tt=et(d,t,jit(d,k)); cta="" if k%3 else "\n\nShop AVENROW → link in bio"
        out.append(dict(plat="instagram",fmt="REEL",day=d,prod=p,et=str(tt),dubai=str(dubai(tt)),media=[f"{REL}/video-{jid}/{jid}.mp4"],text=f"{cap}{cta}\n\n{tags}",music=N.MUS[mus],job=jid,recipe=rec,hook=" / ".join(lines),hol=hol))
    items=[]
    for n,(d,t,p,slides,st,cap,alt,tags,hol) in enumerate(n9.FEED):
        urls=[]
        for i,sl in enumerate(slides):
            name=f"d{d}-{n:02d}-{p:02d}-{i+1}"
            it={"name":name,"src":img(p,sl["p"]),"fx":sl.get("fx",.5),"fy":sl.get("fy",.5),"z":sl.get("z",1.0)}
            if st and i==0: it.update(st)
            items.append(it); urls.append(f"{REL}/video-n9f-1/n9f-1-crop-{name}.jpg")
        tt=et(d,t,jit(d,n+40))
        out.append(dict(plat="instagram",fmt="POST",day=d,prod=p,et=str(tt),dubai=str(dubai(tt)),media=urls,text=f"{cap}\n\n{tags}",alt=alt,hol=hol))
    jobs["n9f-1"]={"id":"n9f-1","type":"crop","items":items}
    return out,jobs
if __name__=="__main__":
    out,jobs=build()
    json.dump(out,open('/home/claude/avenrow-media/plan3/manifest9.json','w'),indent=1,ensure_ascii=False)
    json.dump(jobs,open('/tmp/claude-0/jobs_n9.json','w'))
    from collections import Counter
    print(len(out),Counter((o['plat'],o.get('fmt')) for o in out),len(jobs))
    for o in out:
        e=datetime.datetime.fromisoformat(o['et']); assert e.day==8+o['day'],o
    print(sorted(Counter((o['plat'],o['day']) for o in out).items()))
    print(sorted((o['et'],o['plat']) for o in out)[:4])
