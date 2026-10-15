"""Fetch DM Sans (SIL OFL) static SemiBold/Bold TTFs into fonts/. Tries static files first,
then instances the variable font with fontTools. Prints exactly what it found."""
import pathlib, subprocess, sys, urllib.request

OUT = pathlib.Path("fonts"); OUT.mkdir(exist_ok=True)
STATIC = {
    "DMSans-SemiBold.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/dmsans/static/DMSans-SemiBold.ttf",
        "https://raw.githubusercontent.com/googlefonts/dm-fonts/main/Sans/Exports/DMSans-SemiBold.ttf",
    ],
    "DMSans-Bold.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/dmsans/static/DMSans-Bold.ttf",
        "https://raw.githubusercontent.com/googlefonts/dm-fonts/main/Sans/Exports/DMSans-Bold.ttf",
    ],
}
VAR = ["https://raw.githubusercontent.com/google/fonts/main/ofl/dmsans/DMSans%5Bopsz%2Cwght%5D.ttf"]

def get(url, dest):
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
        if data[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
            dest.write_bytes(data); return True
        print("not a font:", url, data[:60])
    except Exception as e:
        print("fail", url, e)
    return False

for name, urls in STATIC.items():
    p = OUT / name
    if p.exists(): continue
    for u in urls:
        if get(u, p):
            print("static ok", name, u); break
if not all((OUT / n).exists() for n in STATIC):
    var = OUT / "DMSans-var.ttf"
    if any(get(u, var) for u in VAR):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "fonttools"], check=False)
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        for name, w in (("DMSans-SemiBold.ttf", 600), ("DMSans-Bold.ttf", 700)):
            if (OUT / name).exists(): continue
            f = TTFont(var)
            inst = instancer.instantiateVariableFont(f, {"wght": w, "opsz": 14})
            inst.save(OUT / name); print("instanced", name, w)
for n in STATIC:
    print(n, (OUT / n).exists() and (OUT / n).stat().st_size)
