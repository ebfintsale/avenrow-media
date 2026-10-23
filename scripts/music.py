"""Original AVENROW instrumental library. Compositions are written here (deterministic, seeded) as MIDI,
rendered with FluidSynth + FluidR3_GM (MIT-style license, copied into the log), then loudness-normalised.
No noise beds, no samples from third-party songs. Job: {"id":..,"type":"music","tracks":[names or "all"]}"""
import random, struct, subprocess, pathlib, json, re, shutil, glob

SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
TPQ = 480

def vlq(n):
    b = [n & 0x7F]; n >>= 7
    while n: b.append((n & 0x7F) | 0x80); n >>= 7
    return bytes(reversed(b))

def write_mid(path, tempo, ts, chans):
    """chans: {ch: (program, [(tick,dur,note,vel)])}"""
    trks = []
    meta = vlq(0) + b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / tempo))[1:] + vlq(0) + b"\xFF\x58\x04" + bytes([ts[0], {2:1,4:2,8:3}[ts[1]], 24, 8]) + vlq(0) + b"\xFF\x2F\x00"
    trks.append(meta)
    for ch, (prog, notes) in chans.items():
        ev = []
        if ch != 9: ev.append((0, 0, bytes([0xC0 | ch, prog])))
        ev.append((0, 0, bytes([0xB0 | ch, 7, 100])))
        ev.append((0, 0, bytes([0xB0 | ch, 91, 70 if ch != 9 else 30])))  # reverb send
        for t, d, n, v in notes:
            ev.append((t, 2, bytes([0x90 | ch, n, max(1, min(127, v))])))
            ev.append((t + max(d, 20), 1, bytes([0x80 | ch, n, 0])))
        ev.sort(key=lambda e: (e[0], e[1]))
        out = b""; last = 0
        for t, _, m in ev:
            out += vlq(t - last) + m; last = t
        out += vlq(0) + b"\xFF\x2F\x00"
        trks.append(out)
    data = b"MThd" + struct.pack(">IHHH", 6, 1, len(trks), TPQ)
    for t in trks: data += b"MTrk" + struct.pack(">I", len(t)) + t
    pathlib.Path(path).write_bytes(data)

NOTE = {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
def midi(n):  # "F#3" -> int
    m = re.match(r"([A-G])([#b]?)(-?\d)", n); v = NOTE[m[1]] + (1 if m[2]=="#" else -1 if m[2]=="b" else 0)
    return v + 12 * (int(m[3]) + 1)
CH = {  # chord name -> (root note name for bass, voicing list)
 "Fmaj7":("F2",["A3","C4","E4","G4"]), "Em7":("E2",["G3","B3","D4","G4"]), "Dm7":("D2",["F3","A3","C4","F4"]),
 "Cmaj7":("C2",["E3","G3","B3","E4"]), "Am7":("A1",["C4","E4","G4","C5"]), "G6":("G1",["B3","D4","E4","G4"]),
 "Fm7":("F2",["Ab3","C4","Eb4","G4"]), "Bbmaj7":("Bb1",["D4","F4","A4","D5"]), "Gm7":("G1",["Bb3","D4","F4","Bb4"]),
 "Dm":("D2",["F3","A3","D4"]), "Am":("A1",["E3","A3","C4"]), "Bb":("Bb1",["F3","Bb3","D4"]), "C":("C2",["E3","G3","C4"]),
 "F":("F2",["A3","C4","F4"]), "G":("G1",["B3","D4","G4"]), "Em":("E2",["G3","B3","E4"]), "D":("D2",["F#3","A3","D4"]),
 "Gm":("G1",["Bb3","D4","G4"]), "Cm":("C2",["Eb3","G3","C4"]), "Ab":("Ab1",["Eb3","Ab3","C4"]), "Eb":("Eb2",["G3","Bb3","Eb4"]),
 "Bm7":("B1",["D4","F#4","A4","D5"]), "Gmaj7":("G1",["B3","D4","F#4","B4"]), "Dmaj7":("D2",["F#3","A3","C#4","F#4"]),
 "Bbm7":("Bb1",["Db4","F4","Ab4","Db5"]), "Ebmaj7":("Eb2",["G3","Bb3","D4","G4"]), "Ab6":("Ab1",["C4","Eb4","F4","Ab4"]),
 "Dm9":("D2",["F3","A3","C4","E4"]), "Fmaj9":("F2",["A3","C4","E4","G4"]), "Cmaj9":("C2",["E3","G3","B3","D4"]),
}
SCALES = {"Cmaj":["C","D","E","G","A"], "Fmaj":["F","G","A","C","D"], "Amin":["A","C","D","E","G"], "Dmin":["D","F","G","A","C"],
          "Gmaj":["G","A","B","D","E"], "Cmin":["C","Eb","F","G","Bb"], "Gmin":["G","Bb","C","D","F"], "Ebmaj":["Eb","F","G","Bb","C"]}

def scale_notes(key, lo, hi):
    names = SCALES[key]; out = []
    for o in range(1, 8):
        for nme in names:
            n = midi(f"{nme}{o}")
            if lo <= n <= hi: out.append(n)
    return sorted(out)

def melody(rng, key, lo, hi, bars, beats, rhythm_choices, density, vel=70, start_bar=0):
    pool = scale_notes(key, midi(lo), midi(hi)); i = len(pool)//2; notes = []
    for b in range(start_bar, bars):
        t = b * beats * TPQ; pos = 0.0
        if rng.random() > density: continue
        while pos < beats - 0.01:
            d = rng.choice(rhythm_choices); d = min(d, beats - pos)
            if rng.random() < 0.18: pos += d; continue
            i = max(0, min(len(pool)-1, i + rng.choice([-2,-1,-1,0,1,1,2])))
            notes.append((int(t + pos*TPQ), int(d*TPQ*0.9), pool[i], vel + rng.randint(-8, 8)))
            pos += d
    return notes

def build(spec):
    rng = random.Random(spec["seed"]); beats = spec["ts"][0] if spec["ts"][1] == 4 else spec["ts"][0]/2*1.0
    if spec["ts"] == (3, 4): beats = 3
    prog = spec["prog"]; bars = spec["bars"]; bt = beats
    ch = {}
    swing = spec.get("swing", 0.0)
    def hum(t): return max(0, t + rng.randint(-8, 8))
    chords, bass = [], []
    for b in range(bars):
        cn = prog[b % len(prog)]; root, voi = CH[cn]; t0 = int(b * bt * TPQ); v = [midi(x) for x in voi]
        style = spec["comp"]
        if style == "sustain":
            for n in v: chords.append((hum(t0), int(bt*TPQ*0.95), n, 52 + rng.randint(-4, 4)))
        elif style == "offbeat":  # lo-fi stabs
            for beat in ([0.0, 1.5, 2.5] if bt == 4 else [0.0, 1.0]):
                for n in v: chords.append((hum(int(t0 + beat*TPQ)), int(0.9*TPQ), n, 55 + rng.randint(-5, 5)))
        elif style == "arp":
            seq = v + v[::-1][1:-1]; step = spec.get("step", 0.5); k = 0; pos = 0.0
            while pos < bt - 0.01:
                chords.append((hum(int(t0 + pos*TPQ)), int(step*TPQ*2.2), seq[k % len(seq)] - (12 if spec.get("arp_low") else 0), 58 + rng.randint(-6, 6))); k += 1; pos += step
        elif style == "waltz":
            chords.append((hum(t0), int(0.9*TPQ), v[0]-12, 60))
            for beat in (1, 2):
                for n in v[1:]: chords.append((hum(int(t0 + beat*TPQ)), int(0.8*TPQ), n, 46 + rng.randint(-4, 4)))
        elif style == "comp_jazz":
            for beat in ([0.0, 1.5] if rng.random() < .5 else [0.5, 2.0]):
                for n in v: chords.append((hum(int(t0 + beat*TPQ)), int(0.7*TPQ), n, 50 + rng.randint(-5, 5)))
        r = midi(root)
        bstyle = spec["bass"]
        if bstyle == "root": bass += [(int(t0), int(bt*TPQ*0.9), r, 70)] if bt==3 else [(int(t0), int(1.8*TPQ), r, 72), (int(t0+2.5*TPQ), int(1.2*TPQ), r, 62)]
        elif bstyle == "walk":
            fifth = r + 7
            for k, n in enumerate([r, r+2 if rng.random()<.5 else r+4, fifth, r+9 if rng.random()<.5 else r+5][:int(bt)]):
                bass.append((int(t0 + k*TPQ), int(0.95*TPQ), n, 66))
        elif bstyle == "pulse":
            for k in range(int(bt)*2):
                bass.append((hum(int(t0 + k*0.5*TPQ)), int(0.4*TPQ), r if k % 4 != 3 else r+7, 58))
    ch[0] = (spec["chord_prog"], chords)
    ch[1] = (spec["bass_prog"], bass)
    if spec.get("pad"):
        pad = []
        for b in range(bars):
            _, voi = CH[prog[b % len(prog)]]; t0 = int(b*bt*TPQ)
            for n in [midi(x) for x in voi][:3]: pad.append((t0, int(bt*TPQ*1.0), n, 36))
        ch[2] = (spec["pad"], pad)
    if spec.get("lead"):
        lp, lo, hi, rc, dens, vel = spec["lead"]
        ch[3] = (lp, melody(rng, spec["key"], lo, hi, bars, bt, rc, dens, vel, start_bar=spec.get("lead_start", 2)))
    if spec.get("second"):
        sp, lo, hi, rc, dens, vel = spec["second"]
        ch[4] = (sp, melody(rng, spec["key"], lo, hi, bars, bt, rc, dens, vel, start_bar=spec.get("second_start", 4)))
    if spec.get("drums"):
        dr = []; kind = spec["drums"]
        for b in range(bars):
            t0 = int(b*bt*TPQ)
            if b < spec.get("drum_start", 0): continue
            if kind == "lofi":
                dr += [(t0, 100, 36, 78), (int(t0+2.5*TPQ), 100, 36, 62), (int(t0+1*TPQ), 100, 37, 52), (int(t0+3*TPQ), 100, 37, 56)]
                for k in range(8): dr.append((int(t0 + k*0.5*TPQ + (0.12*TPQ if k%2 else 0)), 60, 42, 34 + (10 if k%2==0 else 0) + rng.randint(-4,4)))
            elif kind == "light":
                dr += [(t0, 100, 36, 60), (int(t0+2*TPQ), 100, 36, 50), (int(t0+1*TPQ), 100, 37, 45), (int(t0+3*TPQ), 100, 37, 48)]
                for k in range(4): dr.append((int(t0+k*TPQ), 60, 42, 30))
            elif kind == "brush":
                for k in range(4): dr.append((int(t0+k*TPQ), 80, 51, 40))
                dr += [(int(t0+(k+0.66)*TPQ), 80, 51, 28) for k in (1,3)]
                dr += [(int(t0+1*TPQ), 80, 38, 22), (int(t0+3*TPQ), 80, 38, 24)]
            elif kind == "waltz":
                dr += [(t0, 100, 36, 50)] + [(int(t0+k*TPQ), 60, 42, 26) for k in (1, 2)]
        ch[9] = (0, dr)
    return ch

LIB = {
 "lofi-rhodes-warm": dict(seed=11, tempo=78, ts=(4,4), key="Fmaj", prog=["Fmaj7","Em7","Dm7","Cmaj7"], bars=16, comp="offbeat", chord_prog=4, bass="root", bass_prog=33, lead=(11,"F4","C6",[0.5,1,1,1.5],0.7,64), lead_start=2, drums="lofi", drum_start=1, pad=89, mood="warm lo-fi bedroom"),
 "indie-nylon-morning": dict(seed=23, tempo=92, ts=(4,4), key="Cmaj", prog=["C","G","Am","F"], bars=16, comp="arp", step=0.5, chord_prog=24, bass="root", bass_prog=32, lead=(11,"E5","G6",[1,1,2],0.55,60), lead_start=4, drums="light", drum_start=2, mood="light indie acoustic"),
 "music-box-waltz-halloween": dict(seed=31, tempo=108, ts=(3,4), key="Amin", prog=["Am","Am","Dm","Am","F","E" if False else "Em","Am","Am"], bars=16, comp="waltz", chord_prog=45, bass="root", bass_prog=32, lead=(10,"A4","E6",[1,1,1,2],0.85,66), lead_start=1, second=(8,"A5","A6",[1,2],0.4,48), second_start=4, drums=None, mood="Halloween music box waltz"),
 "witchy-harp-cello": dict(seed=43, tempo=66, ts=(4,4), key="Dmin", prog=["Dm","Bb","Gm","Am"], bars=12, comp="arp", step=1.0, chord_prog=46, bass="root", bass_prog=42, lead=(42,"D3","D4",[2,4],0.95,58), lead_start=2, second=(8,"D5","A6",[1,2],0.35,44), second_start=4, drums=None, pad=48, mood="subtle spooky strings and harp"),
 "jazz-vibes-cozy": dict(seed=59, tempo=100, ts=(4,4), key="Fmaj", prog=["Dm7","Gm7","Cmaj7","Fmaj7"], bars=16, comp="comp_jazz", chord_prog=0, bass="walk", bass_prog=32, lead=(11,"F4","C6",[0.5,0.5,1,1,1.5],0.8,66), lead_start=2, drums="brush", mood="cozy jazz vibraphone"),
 "dreamy-bedroom-rhodes": dict(seed=67, tempo=70, ts=(4,4), key="Gmaj", prog=["Gmaj7","Em7","Cmaj7","Dmaj7"], bars=12, comp="sustain", chord_prog=4, bass="root", bass_prog=33, lead=(9,"B4","D6",[1,2,2],0.55,56), lead_start=2, pad=89, drums="light", drum_start=4, mood="dreamy bedroom Rhodes"),
 "playful-pizzicato-day": dict(seed=71, tempo=112, ts=(4,4), key="Cmaj", prog=["C","Am","F","G"], bars=16, comp="arp", step=0.5, arp_low=True, chord_prog=45, bass="pulse", bass_prog=32, lead=(12,"C5","A6",[0.5,0.5,1,1],0.8,66), lead_start=2, drums="light", drum_start=2, mood="playful light pizzicato and marimba"),
 "soft-piano-gift": dict(seed=79, tempo=72, ts=(4,4), key="Ebmaj", prog=["Ebmaj7","Bbm7","Ab6","Bbm7"] if False else ["Ebmaj7","Gm7","Ab6","Bbm7"], bars=12, comp="arp", step=0.5, chord_prog=0, bass="root", bass_prog=32, lead=(0,"Bb4","G5",[1,1.5,2],0.6,58), lead_start=3, pad=48, mood="soft piano, gifting"),
 "pumpkin-folk-guitar": dict(seed=83, tempo=96, ts=(4,4), key="Gmaj", prog=["G","Em","C","D"], bars=16, comp="arp", step=0.5, chord_prog=25, bass="root", bass_prog=32, lead=(11,"D5","G6",[1,1,2],0.5,58), lead_start=4, drums="light", drum_start=2, mood="autumn folk guitar"),
 "spooky-cozy-lofi-hop": dict(seed=97, tempo=82, ts=(4,4), key="Cmin", prog=["Cm","Ab","Eb","Gm"], bars=16, comp="offbeat", chord_prog=4, bass="root", bass_prog=33, lead=(8,"G5","C7",[1,1,1.5,2],0.55,52), lead_start=2, drums="lofi", drum_start=1, pad=89, mood="spooky-cozy minor lo-fi"),
}

def run_music(job, out_dir):
    names = list(LIB) if job.get("tracks", "all") == "all" else job["tracks"]
    tmp = pathlib.Path("music_tmp"); tmp.mkdir(exist_ok=True)
    info = {"id": job["id"], "tracks": [], "tool": subprocess.run(["fluidsynth", "--version"], capture_output=True, text=True).stdout.strip().splitlines()[:1]}
    lic = pathlib.Path("/usr/share/doc/fluid-soundfont-gm/copyright")
    info["soundfont_license_text"] = lic.read_text()[:3000] if lic.exists() else "MISSING"
    for nme in names:
        sp = LIB[nme]; chans = build(sp); mid = tmp / f"{nme}.mid"
        write_mid(mid, sp["tempo"], sp["ts"], chans)
        wav = tmp / f"{nme}-raw.wav"
        subprocess.run(["fluidsynth", "-ni", "-g", "0.8", "-r", "44100", "-F", str(wav), SF2, str(mid)], check=True, capture_output=True)
        outp = out_dir / f"{job['id']}-{nme}.wav"
        # trim tail ring, fade in/out, normalise to -19 LUFS integrated, true peak -2
        dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(wav)],capture_output=True,text=True).stdout)
        subprocess.run(["ffmpeg","-y","-v","error","-i",str(wav),"-af",f"afade=t=in:d=0.4,afade=t=out:st={max(0,dur-2.5):.2f}:d=2.5,loudnorm=I=-19:TP=-2:LRA=7,lowpass=f=9500","-ar","44100","-ac","2",str(outp)],check=True)
        lufs = subprocess.run(["ffmpeg","-i",str(outp),"-af","ebur128=peak=true","-f","null","-"],capture_output=True,text=True).stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", lufs); pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", lufs)
        info["tracks"].append({"name": nme, "mood": sp["mood"], "bpm": sp["tempo"], "ts": f"{sp['ts'][0]}/{sp['ts'][1]}", "dur_s": round(dur, 1),
                               "lufs": float(m[-1]) if m else None, "peak_dbfs": float(pk[-1]) if pk else None,
                               "composition": "original (AVENROW, generated from seeded MIDI patterns in scripts/music.py)", "sound_source": "FluidR3_GM soundfont"})
    shutil.rmtree(tmp, ignore_errors=True)
    return info
