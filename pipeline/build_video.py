#!/usr/bin/env python3
"""Printamoo Shorts builder.

Usage:
  python3 pipeline/build_video.py setup                 # install TTS, fonts, model (cached)
  python3 pipeline/build_video.py preview SPEC.json OUTDIR   # contact sheet of key frames (OUTDIR/preview.png)
  python3 pipeline/build_video.py build SPEC.json OUTDIR     # full video -> OUTDIR/video.mp4

SPEC.json (paths relative to the spec file):
{
  "keyword": "gratitude cards",                 # shown in the bottom search CTA: "<keyword> printamoo.com"
  "headline": "Gratitude Cards",                 # big title on the opening screen (keep <= 18 chars)
  "tagline": "Less prep, more thankful moments", # one short line under the headline
  "hook": {"line1": "No crafting needed.", "line2": "Just print, cut & write.",
           "tags": ["Jar slips", "Table cards", "Prompt cards", "Pocket cards"]},   # tags: 2-4, optional
  "scene_label": "HOW TO USE",                   # pill text prefix, e.g. "HOW TO USE", "HOW TO STYLE", "HOW TO PLAY"
  "scenes": [ {"image": "img/a.jpg", "title": "On-screen card name", "tips": ["tip 1", "tip 2"],
               "say": "Narration for this scene (do not say the card name)."} ],   # 3-7 scenes
  "tips": {"title": "Before you print", "items": ["...", "..."], "say": "..."},     # optional
  "say": {"title": "...free printable ...", "hook": "...", "end": "Download them all free at printamoo dot com."},
  "end_sub": "Color & black-and-white versions",   # optional small line on the end screen
  "thumb_title": "Free Gratitude Cards",           # optional thumbnail headline (default: headline), <= 24 chars
  "thumb_badge": "FREE PRINTABLES"                  # optional badge text on the thumbnail
}
"""
import sys, os, json, math, subprocess, shutil, random, wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/printamoo-video")
W, H, FPS = 1080, 1920, 30
LEAD, FADE = 0.5, 0.35
INK, SOFT = (46, 26, 80), (104, 84, 140)
ACC, MAG, BLUE, LAV = (91, 45, 145), (162, 62, 135), (63, 127, 216), (126, 87, 194)
BLACK = (20, 18, 24)
CTA_Y = H - 330          # search bar top; keeps it clear of YouTube Shorts' bottom overlay
BOTTOM = CTA_Y - 70      # content must end above this
SCENE_COLORS = [MAG, LAV, BLUE, ACC, MAG, BLUE, LAV]

FONT_URLS = {
    "Fredoka.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/fredoka/Fredoka%5Bwdth,wght%5D.ttf",
    "Nunito.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/nunito/Nunito%5Bwght%5D.ttf",
}
MODEL_URLS = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}

def setup():
    os.makedirs(CACHE, exist_ok=True)
    for name, url in {**FONT_URLS, **MODEL_URLS}.items():
        p = os.path.join(CACHE, name)
        if not os.path.exists(p) or os.path.getsize(p) < 1000:
            subprocess.run(["curl", "-sSL", "-o", p, url], check=True)
    try:
        import kokoro_onnx, soundfile, scipy  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages",
                        "kokoro-onnx", "soundfile", "scipy"], check=True)
    print("setup ok")

# ---------------- drawing helpers ----------------
def fredoka(size, w="SemiBold"):
    f = ImageFont.truetype(os.path.join(CACHE, "Fredoka.ttf"), size); f.set_variation_by_name(w); return f
def nunito(size, w="SemiBold"):
    f = ImageFont.truetype(os.path.join(CACHE, "Nunito.ttf"), size); f.set_variation_by_name(w); return f
_LOGO = None
def logo(width):
    global _LOGO
    if _LOGO is None: _LOGO = Image.open(os.path.join(HERE, "assets", "logo.png")).convert("RGBA")
    return _LOGO.resize((width, int(_LOGO.height * width / _LOGO.width)), Image.LANCZOS)

def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3

def wrap(text, font, maxw):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            t = (line + " " + w).strip()
            if font.getlength(t) <= maxw: line = t
            else: out.append(line); line = w
        out.append(line)
    return out

def text_layer(lines, font, fill, spacing=1.2):
    asc, desc = font.getmetrics(); lh = int((asc + desc) * spacing)
    w = int(max(font.getlength(l) for l in lines)) + 8
    im = Image.new("RGBA", (w, lh * len(lines) + 10), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text(((w - font.getlength(l)) / 2, i * lh), l, font=font, fill=fill)
    return im

def fit_text(text, maxw, size, w="SemiBold", maxlines=2, minsize=48):
    while True:
        f = fredoka(size, w); lines = wrap(text, f, maxw)
        if len(lines) <= maxlines or size <= minsize: return f, lines
        size -= 4

def fade(im, a):
    if a >= 1: return im
    im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * a))); return im

def background(seed=1):
    rnd = random.Random(seed)
    bg = Image.new("RGB", (W, H), (245, 241, 253))
    st = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(st)
    for x in range(-H, W, 46):
        d.line((x, H, x + H, 0), fill=(126, 87, 194, 16), width=14)
    for _ in range(26):
        x, y = rnd.randint(20, W - 20), rnd.randint(20, H - 20)
        c = rnd.choice([LAV, MAG, BLUE])
        if rnd.random() < 0.5:
            r = rnd.randint(10, 18)
            d.polygon([(x, y - r), (x + r * .3, y - r * .3), (x + r, y), (x + r * .3, y + r * .3), (x, y + r),
                       (x - r * .3, y + r * .3), (x - r, y), (x - r * .3, y - r * .3)], fill=c + (60,))
        else:
            for k in range(3):
                ang = rnd.random() * 6.28 + k * 0.5
                d.line((x + 10 * math.cos(ang), y + 10 * math.sin(ang), x + 26 * math.cos(ang), y + 26 * math.sin(ang)),
                       fill=c + (70,), width=5)
    bg.paste(st, (0, 0), st)
    tint = (220, 205, 250)
    blob = Image.new("RGBA", (W, H), tint + (0,)); d = ImageDraw.Draw(blob)
    d.ellipse((-300, -250, 700, 650), fill=tint + (150,)); d.ellipse((500, 1300, 1500, 2300), fill=tint + (130,))
    blob = blob.filter(ImageFilter.GaussianBlur(120)); bg.paste(blob, (0, 0), blob)
    return bg

def card(path, width, angle=0.0, max_h=None, radius=18):
    im = Image.open(path).convert("RGB")
    if max_h and im.height * width / im.width > max_h:
        width = int(im.width * max_h / im.height)
    h = int(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    pad = 60
    canvas = Image.new("RGBA", (width + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad - 14, pad + 2, pad + width + 14, pad + h + 26), radius + 10, fill=(60, 30, 110, 80))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
    mask = Image.new("L", (width, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, h - 1), radius, fill=255)
    paper = Image.new("RGBA", (width, h)); paper.paste(im); paper.putalpha(mask)
    ImageDraw.Draw(canvas).rounded_rectangle((pad - 14, pad - 14, pad + width + 13, pad + h + 13), radius + 10,
                                             fill=(255, 255, 255, 255), outline=ACC + (255,), width=max(4, width // 120))
    canvas.alpha_composite(paper, (pad, pad))
    if angle: canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=True)
    return canvas

def pill(text, color):
    f = nunito(28, "Bold"); tw = int(f.getlength(text))
    im = Image.new("RGBA", (tw + 56, 60), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, tw + 55, 59), 30, fill=color + (255,)); d.text((28, 12), text, font=f, fill=(255, 255, 255))
    return im

def bullets_panel(items, color):
    f = nunito(38, "Bold"); pw = 960; tx = 120; maxw = pw - tx - 40
    rows = [wrap(t, f, maxw) for t in items]; lh = 54; gap = 34
    heights = [len(r) * lh for r in rows]
    ph = sum(heights) + gap * (len(rows) - 1) + 80
    layers = []; y = 40
    for i, (r, hh) in enumerate(zip(rows, heights)):
        lay = Image.new("RGBA", (pw, ph), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); cy = y + 27
        d.ellipse((40, cy - 25, 90, cy + 25), fill=color + (255,))
        n = str(i + 1); nf = nunito(28, "ExtraBold")
        d.text((65 - nf.getlength(n) / 2, cy - 21), n, font=nf, fill=(255, 255, 255))
        for j, l in enumerate(r): d.text((tx, y + j * lh), l, font=f, fill=INK)
        layers.append(lay); y += hh + gap
    base = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    sh = Image.new("RGBA", (pw + 80, ph + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((40, 50, pw + 40, ph + 50), 36, fill=(60, 30, 110, 50))
    ImageDraw.Draw(base).rounded_rectangle((0, 0, pw - 1, ph - 1), 36, fill=(255, 255, 255, 250), outline=ACC + (255,), width=6)
    return sh.filter(ImageFilter.GaussianBlur(20)), base, layers

def overlay(keyword):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lg = logo(330); ov.alpha_composite(lg, ((W - lg.width) // 2, 40))
    cap_f = nunito(27, "Bold"); cap = "To get these free printables, search"
    q1, q2 = keyword + " ", "printamoo.com"
    qf = nunito(36, "ExtraBold")
    while qf.getlength(q1) + qf.getlength(q2) > W - 220: qf = nunito(qf.size - 2, "ExtraBold")
    tw = qf.getlength(q1) + qf.getlength(q2); bw, bh = int(tw + 150), 78; bx, by = (W - bw) // 2, CTA_Y
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((bx, by + 8, bx + bw, by + bh + 8), bh // 2, fill=(60, 30, 110, 60))
    ov.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(ov)
    d.text(((W - cap_f.getlength(cap)) / 2, by - 44), cap, font=cap_f, fill=SOFT)
    d.rounded_rectangle((bx, by, bx + bw, by + bh), bh // 2, fill=(255, 255, 255, 240), outline=ACC + (255,), width=4)
    cx, cy = bx + 48, by + bh // 2 - 3
    d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline=MAG, width=5); d.line((cx + 10, cy + 10, cx + 22, cy + 22), fill=MAG, width=6)
    ty = by + (bh - qf.getbbox("Ag")[3]) // 2 - 2
    d.text((bx + 86, ty), q1, font=qf, fill=BLACK); d.text((bx + 86 + qf.getlength(q1), ty), q2, font=qf, fill=BLACK)
    return ov

# ---------------- scenes ----------------
class Ctx:
    def __init__(self, spec, base): self.spec = spec; self.base = base
    def img(self, p): return p if os.path.isabs(p) else os.path.join(self.base, p)

def title_scene(c, dur, vo):
    s = c.spec; bg = background(2)
    imgs = [c.img(x["image"]) for x in s["scenes"]][:3]
    while len(imgs) < 3: imgs.append(imgs[-1])
    k1 = pill("FREE PRINTABLES", MAG)
    tf, tl = fit_text(s["headline"], 980, 124, "Bold", 2, 80); t1 = text_layer(tl, tf, ACC, 1.0)
    sf = fredoka(52, "Medium"); t2 = text_layer(wrap(s.get("tagline", ""), sf, 940) or [""], sf, MAG)
    ty2 = 420 + t1.height + 30; top = ty2 + t2.height + 60
    cards = [card(p, 440, a, max_h=min(560, BOTTOM - top - 230)) for p, a in zip(imgs, (-8, 8, 0))]
    pos = [(W // 2 - 250 - cards[0].width // 2, top), (W // 2 + 250 - cards[1].width // 2, top + 20),
           (W // 2 - cards[2].width // 2, top + 100)]
    def frame(t):
        im = bg.copy().convert("RGBA")
        for i, (cd, (x, y)) in enumerate(zip(cards, pos)):
            a = ease((t - 0.15 - i * 0.2) / 0.7); im.alpha_composite(fade(cd, a), (x, y + int(160 * (1 - a))))
        a = ease((t - 0.3) / 0.5); im.alpha_composite(fade(k1, a), ((W - k1.width) // 2, 330 + int(20 * (1 - a))))
        a = ease((t - 0.4) / 0.6); im.alpha_composite(fade(t1, a), ((W - t1.width) // 2, 420 + int(30 * (1 - a))))
        a = ease((t - 0.7) / 0.6); im.alpha_composite(fade(t2, a), ((W - t2.width) // 2, ty2 + int(30 * (1 - a))))
        return im.convert("RGB")
    return frame, bg

def hook_scene(c, dur, vo):
    h = c.spec["hook"]; bg = background(3)
    f, l1 = fit_text(h["line1"], 960, 80, "SemiBold", 2, 56); t1 = text_layer(l1, f, INK)
    f2 = fredoka(64, "Medium"); t2 = text_layer(wrap(h.get("line2", ""), f2, 960) or [""], f2, ACC)
    tags = [pill(t.upper(), col) for t, col in zip(h.get("tags", [])[:4], [MAG, ACC, BLUE, LAV])]
    y1 = 760; y2 = y1 + t1.height + 40; y3 = y2 + t2.height + 80
    def frame(t):
        im = bg.copy().convert("RGBA")
        a = ease((t - 0.35) / 0.5); im.alpha_composite(fade(t1, a), ((W - t1.width) // 2, y1 + int(30 * (1 - a))))
        a = ease((t - min(1.6, vo * 0.5)) / 0.6); im.alpha_composite(fade(t2, a), ((W - t2.width) // 2, y2 + int(30 * (1 - a))))
        for i, tg in enumerate(tags):
            a = ease((t - min(2.4, vo * 0.7) - i * 0.2) / 0.5)
            cx = W // 2 + (-200 if i % 2 == 0 else 200) if len(tags) > 1 else W // 2
            im.alpha_composite(fade(tg, a), (cx - tg.width // 2, y3 + (i // 2) * 100 + int(20 * (1 - a))))
        return im.convert("RGB")
    return frame, bg

def item_scene(c, idx, dur, vo):
    s = c.spec; sc = s["scenes"][idx]; n = len(s["scenes"]); col = SCENE_COLORS[idx % len(SCENE_COLORS)]
    bg = background(10 + idx)
    pl = pill(f"{s.get('scene_label', 'HOW TO USE')}  ·  {idx + 1} OF {n}", col)
    tf, tl = fit_text(sc["title"], 960, 70, "SemiBold", 2, 50); tlay = text_layer(tl, tf, INK, 1.12)
    cd = card(c.img(sc["image"]), 760, 1.6 if idx % 2 == 0 else -1.6)
    sh, base, rows = bullets_panel(sc["tips"], col)
    title_y = 250; card_top = title_y + tlay.height + 30; panel_y = BOTTOM - base.height - 40
    avail = panel_y - card_top - 10; scale0 = min(1.0, (avail - 40) / (cd.height - 60), 1000 / cd.width)
    b0 = LEAD + 0.3; step = max(0.6, (vo - 0.3) / max(1, len(rows)))
    def frame(t):
        im = bg.copy().convert("RGBA")
        a = ease(t / 0.5); im.alpha_composite(fade(pl, a), ((W - pl.width) // 2, 165 + int(20 * (1 - a))))
        a = ease((t - 0.1) / 0.6); im.alpha_composite(fade(tlay, a), ((W - tlay.width) // 2, title_y + int(30 * (1 - a))))
        a = ease((t - 0.25) / 0.8); sc_ = scale0 * (0.94 + 0.06 * a + 0.03 * (t / dur))
        cc = cd.resize((int(cd.width * sc_), int(cd.height * sc_)), Image.BILINEAR)
        im.alpha_composite(fade(cc, a), ((W - cc.width) // 2, card_top + (avail - cc.height) // 2 + 10 + int(80 * (1 - a))))
        a = ease((t - 0.9) / 0.6); px = (W - base.width) // 2; py = panel_y + int(60 * (1 - a))
        im.alpha_composite(fade(sh, a), (px - 40, py - 40)); im.alpha_composite(fade(base, a), (px, py))
        for i, r in enumerate(rows):
            b = ease((t - b0 - i * step) / 0.5)
            if b > 0: im.alpha_composite(fade(r, b), (px + int(30 * (1 - b)), py))
        return im.convert("RGB")
    return frame, bg

def tips_scene(c, dur, vo):
    tp = c.spec["tips"]; bg = background(30)
    pl = pill("PRINTING TIPS", MAG)
    tf, tl = fit_text(tp.get("title", "Before you print"), 960, 76); tlay = text_layer(tl, tf, INK)
    sh, base, rows = bullets_panel(tp["items"], ACC)
    imgs = [c.img(x["image"]) for x in c.spec["scenes"]]
    fan = [card(p, 360, g, max_h=420) for p, g in zip([imgs[min(1, len(imgs) - 1)], imgs[min(3, len(imgs) - 1)]], (-6, 5))]
    py = 420 + tlay.height + 60; fy = py + base.height + 80
    b0 = LEAD + 0.2; step = max(0.6, (vo - 0.2) / max(1, len(rows)))
    def frame(t):
        im = bg.copy().convert("RGBA")
        a = ease(t / 0.5); im.alpha_composite(fade(pl, a), ((W - pl.width) // 2, 330 + int(20 * (1 - a))))
        a = ease((t - 0.1) / 0.6); im.alpha_composite(fade(tlay, a), ((W - tlay.width) // 2, 420 + int(30 * (1 - a))))
        for i, (cd, x) in enumerate(zip(fan, (W // 2 + 20 - fan[0].width, W // 2 - 20))):
            a = ease((t - 0.3 - i * 0.15) / 0.7); im.alpha_composite(fade(cd, a), (x, fy + int(140 * (1 - a))))
        px = (W - base.width) // 2; a = ease((t - 0.4) / 0.6)
        im.alpha_composite(fade(sh, a), (px - 40, py - 40 + int(60 * (1 - a)))); im.alpha_composite(fade(base, a), (px, py + int(60 * (1 - a))))
        for i, r in enumerate(rows):
            b = ease((t - b0 - i * step) / 0.5)
            if b > 0: im.alpha_composite(fade(r, b), (px + int(30 * (1 - b)), py))
        return im.convert("RGB")
    return frame, bg

def end_scene(c, dur, vo):
    s = c.spec; bg = background(40)
    imgs = [c.img(x["image"]) for x in s["scenes"]][:7]
    angs = [-7, 5, -3, 6, -5, 3, -2]
    allpos = {1: [(390, 760)], 2: [(170, 760), (560, 780)], 3: [(30, 760), (350, 740), (670, 770)],
              4: [(170, 700), (560, 720), (170, 1040), (560, 1060)], 5: [(30, 700), (350, 680), (670, 710), (170, 990), (510, 980)],
              6: [(30, 700), (350, 680), (670, 710), (30, 1000), (350, 990), (670, 1010)],
              7: [(30, 700), (350, 680), (670, 710), (170, 950), (510, 940), (30, 1190), (670, 1180)]}
    pos = allpos[len(imgs)]
    cs = [card(p, 250, a, max_h=330) for p, a in zip(imgs, angs)]
    pos = [(x + 10, y - 40) for x, y in pos]
    t1 = text_layer(["Download them all free at"], fredoka(66), INK, 1.1)
    t2 = text_layer(["printamoo.com"], fredoka(100, "Bold"), MAG)
    t3 = text_layer([s.get("end_sub", "")] if s.get("end_sub") else [" "], fredoka(44, "Medium"), SOFT)
    def frame(t):
        im = bg.copy().convert("RGBA")
        for i, (cd, (x, y)) in enumerate(zip(cs, pos)):
            a = ease((t - 0.2 - i * 0.1) / 0.6); im.alpha_composite(fade(cd, a), (x, y + int(120 * (1 - a))))
        a = ease((t - 0.2) / 0.6); im.alpha_composite(fade(t1, a), ((W - t1.width) // 2, 300 + int(30 * (1 - a))))
        a = ease((t - 0.4) / 0.6); k = 1 + (0.03 * math.sin((t - 1.0) * 2.4) if t > 1 else 0)
        tt = t2.resize((int(t2.width * k), int(t2.height * k)), Image.BILINEAR)
        im.alpha_composite(fade(tt, a), ((W - tt.width) // 2, 400 + int(30 * (1 - a)) - (tt.height - t2.height) // 2))
        a = ease((t - 0.8) / 0.6); im.alpha_composite(fade(t3, a), ((W - t3.width) // 2, 560 + int(20 * (1 - a))))
        return im.convert("RGB")
    return frame, bg

def thumbnail(c, path):
    """Vertical 1080x1920 thumbnail: logo, FREE badge, big headline, fanned printables, URL banner."""
    s = c.spec; im = background(5).convert("RGBA")
    lg = logo(460); im.alpha_composite(lg, ((W - lg.width) // 2, 80))
    bf = nunito(44, "ExtraBold"); bt = s.get("thumb_badge", "FREE PRINTABLES")
    bw = int(bf.getlength(bt)) + 90; badge = Image.new("RGBA", (bw, 84), (0, 0, 0, 0)); bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle((0, 0, bw - 1, 83), 42, fill=MAG + (255,)); bd.text((45, 14), bt, font=bf, fill=(255, 255, 255))
    by = 80 + lg.height + 40; im.alpha_composite(badge, ((W - bw) // 2, by))
    head = s.get("thumb_title", s["headline"])
    size = 170
    while True:
        f = fredoka(size, "Bold"); lines = wrap(head, f, 980)
        if (len(lines) <= 2 and all(f.getlength(l) <= 980 for l in lines)) or size <= 90: break
        size -= 6
    asc, desc = f.getmetrics(); lh = int((asc + desc) * 0.98); ty = by + 84 + 30
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text(((W - f.getlength(l)) / 2, ty + i * lh), l, font=f, fill=ACC, stroke_width=12, stroke_fill=(255, 255, 255))
    top = ty + len(lines) * lh + 40
    imgs = [c.img(x["image"]) for x in s["scenes"]][:3]
    while len(imgs) < 3: imgs.append(imgs[-1])
    avail = 1700 - top
    imgs = [imgs[1], imgs[2], imgs[0]]   # first scene's printable sits in front
    cards = [card(p, 520, a, max_h=int(avail * 0.82)) for p, a in zip(imgs, (-9, 9, 0))]
    pos = [(W // 2 - 270 - cards[0].width // 2, top), (W // 2 + 270 - cards[1].width // 2, top + 20),
           (W // 2 - cards[2].width // 2, top + 70)]
    for cd, (x, y) in zip(cards, pos): im.alpha_composite(cd, (x, y))
    uf = nunito(46, "ExtraBold"); ut = "Free at printamoo.com"
    uw = int(uf.getlength(ut)) + 110; bx = (W - uw) // 2; by2 = 1745
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((bx, by2 + 8, bx + uw, by2 + 98), 48, fill=(60, 30, 110, 70))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((bx, by2, bx + uw, by2 + 92), 46, fill=(255, 255, 255, 255), outline=ACC + (255,), width=5)
    d.text((bx + 55, by2 + 16), ut, font=uf, fill=BLACK)
    im.convert("RGB").save(path, "JPEG", quality=88)
    return path

def plan(spec):
    """Ordered list of (kind, idx, narration)."""
    segs = [("title", None, spec["say"]["title"])]
    if spec.get("hook"): segs.append(("hook", None, spec["say"]["hook"]))
    for i, sc in enumerate(spec["scenes"]): segs.append(("item", i, sc["say"]))
    if spec.get("tips"): segs.append(("tips", None, spec["tips"]["say"]))
    segs.append(("end", None, spec["say"]["end"]))
    return segs

def make_scene(c, kind, idx, dur, vo):
    if kind == "title": return title_scene(c, dur, vo)
    if kind == "hook": return hook_scene(c, dur, vo)
    if kind == "item": return item_scene(c, idx, dur, vo)
    if kind == "tips": return tips_scene(c, dur, vo)
    return end_scene(c, dur, vo)

# ---------------- audio ----------------
def tts(segs, outdir, voice="af_heart"):
    import numpy as np, soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(CACHE, "kokoro-v1.0.onnx"), os.path.join(CACHE, "voices-v1.0.bin"))
    durs = []
    for i, (_, _, text) in enumerate(segs):
        a, sr = k.create(text, voice=voice, speed=1.0, lang="en-us")
        nz = np.where(np.abs(a) > 0.01)[0]; a = a[max(0, nz[0] - 800): nz[-1] + 2000]
        sf.write(os.path.join(outdir, f"vo{i:02d}.wav"), a, sr); durs.append(len(a) / sr)
    return durs

def music(total, path, seed=7):
    import numpy as np
    SR = 44100; N = int(SR * total); out = np.zeros((N, 2)); beat = 60 / 84; bar = 4 * beat
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    def piano(freq, length, vel):
        t = np.arange(int(SR * length)) / SR; env = np.exp(-t * 2.2) * (1 - np.exp(-t * 400)); s = np.zeros_like(t)
        for h, a in [(1, 1), (2, .45), (3, .18), (4, .09), (5, .04)]:
            s += a * np.sin(2 * np.pi * freq * h * t * (1 + .0004 * h)) * np.exp(-t * .8 * h)
        return s * env * vel
    def pad(freqs, length, vel=.08):
        t = np.arange(int(SR * length)) / SR; a = np.minimum(1, t / .8) * np.minimum(1, (length - t) / .8); s = np.zeros((len(t), 2))
        for f in freqs:
            for det, ch in ((.997, 0), (1.003, 1)): s[:, ch] += np.sin(2 * np.pi * f * det * t) + .25 * np.sin(4 * np.pi * f * det * t)
        return s * a[:, None] * vel / len(freqs)
    def add(sig, start, pan=0.0):
        i = int(start * SR)
        if i >= N: return
        if sig.ndim == 1: sig = np.stack([sig * (1 - max(0, pan)), sig * (1 + min(0, pan))], 1)
        j = min(N, i + len(sig)); out[i:j] += sig[: j - i]
    chords = [[53, 57, 60, 65], [50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64]]
    mel = [[77, 76, 74, 72, 74, 72, 69, None], [74, 72, 69, 67, 69, None, 65, 67], [70, 69, 67, 65, 67, 69, 70, 72], [72, 74, 72, 70, 69, 67, 69, None]]
    rng = np.random.default_rng(seed); nbars = int(total / bar) + 1
    for b in range(nbars):
        t0 = b * bar; ch = chords[b % 4]
        add(pad([midi(m) for m in ch], bar + .6), t0); add(piano(midi(ch[0] - 12), bar * 1.2, .35), t0)
        for k, p in enumerate([0, 2, 1, 3, 2, 1, 3, 2]):
            add(piano(midi(ch[p] + 12), 1.6, .16 + .03 * rng.random()), t0 + k * beat / 2, .35 if k % 2 else -.35)
        if 2 <= b < nbars - 2:
            mm = mel[b % 4] if (b // 4) % 2 == 0 else mel[(b + 2) % 4]
            for k, m in enumerate(mm):
                if m is None or ((b // 4) % 2 == 1 and k % 2 == 1): continue
                add(piano(midi(m), 2.0, .26), t0 + k * beat / 2 + .01)
        if 4 <= b < nbars - 1:
            for k in range(8):
                ln = int(.05 * SR); tt = np.arange(ln) / SR
                nz = np.diff(np.concatenate([[0], rng.standard_normal(ln) * np.exp(-tt * 70) * (.025 if k % 2 else .012)]))
                add(nz, t0 + k * beat / 2, .2)
    rev = np.zeros_like(out)
    for d, g in [(.031, .35), (.047, .3), (.071, .25), (.113, .2), (.167, .15)]:
        k = int(d * SR); rev[k:] += out[:-k] * g
    out = out + .5 * rev
    t = np.arange(N) / SR; out *= (np.minimum(1, t / 1.5) * np.clip((total - t) / 3.0, 0, 1))[:, None]
    out = np.tanh(out * 1.2); out /= np.max(np.abs(out)) / .8
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((out * 32767).astype("int16").tobytes())

# ---------------- render ----------------
_JOB = {}
def _render_one(i):
    c, segs, durs, vos, outdir, kw = _JOB["c"], _JOB["segs"], _JOB["durs"], _JOB["vos"], _JOB["outdir"], _JOB["kw"]
    kind, idx, _ = segs[i]; dur = durs[i]
    frame, bg = make_scene(c, kind, idx, dur, vos[i]); ov = overlay(kw); bgc = bg.convert("RGB")
    n = int(round(dur * FPS)); tmp = os.path.join(outdir, f"s{i:02d}.tmp.mp4"); final = os.path.join(outdir, f"s{i:02d}.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for k in range(n):
        t = k / FPS; im = frame(t)
        if t < FADE: im = Image.blend(bgc, im, t / FADE)
        elif t > dur - FADE: im = Image.blend(bgc, im, max(0, (dur - t) / FADE))
        im = im.convert("RGBA"); im.alpha_composite(ov); p.stdin.write(im.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError(f"scene {i} failed")
    os.replace(tmp, final); return i

def scene_durs(segs, vos):
    mins = {"title": 3.8, "hook": 4.0, "item": 5.0, "tips": 5.0, "end": 4.0}
    d = [max(mins[k], round(v + LEAD + 0.9, 2)) for (k, _, _), v in zip(segs, vos)]
    d[-1] += 0.8
    return [round(x * FPS) / FPS for x in d]

def load(spec_path):
    spec = json.load(open(spec_path)); c = Ctx(spec, os.path.dirname(os.path.abspath(spec_path)))
    for sc in spec["scenes"]:
        assert os.path.exists(c.img(sc["image"])), "missing image " + sc["image"]
    assert 1 <= len(spec["scenes"]) <= 7
    return spec, c

def preview(spec_path, outdir):
    spec, c = load(spec_path); os.makedirs(outdir, exist_ok=True)
    segs = plan(spec); ov = overlay(spec["keyword"]); shots = []
    for kind, idx, _ in segs:
        frame, bg = make_scene(c, kind, idx, 8.0, 5.0)
        im = frame(6.0).convert("RGBA"); im.alpha_composite(ov); shots.append(im.convert("RGB").resize((360, 640)))
    cols = 4; rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 370, rows * 650), "black")
    for i, s in enumerate(shots): sheet.paste(s, ((i % cols) * 370, (i // cols) * 650))
    sheet.save(os.path.join(outdir, "preview.png")); print(os.path.join(outdir, "preview.png"))

def build(spec_path, outdir):
    import numpy as np, soundfile as sf
    from multiprocessing import Pool
    spec, c = load(spec_path); os.makedirs(outdir, exist_ok=True)
    segs = plan(spec)
    vos = tts(segs, outdir, spec.get("voice", "af_heart"))
    durs = scene_durs(segs, vos); total = sum(durs)
    _JOB.update(c=c, segs=segs, durs=durs, vos=vos, outdir=outdir, kw=spec["keyword"])
    with Pool(min(6, os.cpu_count() or 2)) as pool:
        for i in pool.imap_unordered(_render_one, range(len(segs))): pass
    with open(os.path.join(outdir, "list.txt"), "w") as f:
        for i in range(len(segs)): f.write(f"file '{os.path.join(outdir, f's{i:02d}.mp4')}'\n")
    silent = os.path.join(outdir, "silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(outdir, "list.txt"), "-c", "copy", silent], check=True)
    SR = 44100; import scipy.signal as ss
    voice = np.zeros(int(total * SR) + SR); off = 0
    for i, d in enumerate(durs):
        a, sr = sf.read(os.path.join(outdir, f"vo{i:02d}.wav"))
        if sr != SR: a = ss.resample_poly(a, SR, sr)
        st = int((off + LEAD) * SR); voice[st:st + len(a)] += a; off += d
    sf.write(os.path.join(outdir, "voice.wav"), voice[:int(total * SR)], SR)
    music(total, os.path.join(outdir, "music.wav"))
    final = os.path.join(outdir, "video.mp4"); tmp = os.path.join(outdir, "video.tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", os.path.join(outdir, "voice.wav"), "-i", os.path.join(outdir, "music.wav"),
                    "-filter_complex", "[1:a]aformat=channel_layouts=stereo,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,volume=2.0,asplit=2[v1][vsc];"
                    "[2:a]volume=0.28[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=400[md];"
                    "[v1][md]amix=inputs=2:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=11[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
                    "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, final)
    thumbnail(c, os.path.join(outdir, "thumbnail.jpg"))
    print(json.dumps({"thumbnail": os.path.join(outdir, "thumbnail.jpg"), "video": final, "seconds": round(total, 2), "bytes": os.path.getsize(final)}))

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "setup": setup()
    elif cmd == "preview": setup(); preview(sys.argv[2], sys.argv[3])
    elif cmd == "build": setup(); build(sys.argv[2], sys.argv[3])
    elif cmd == "thumb":
        setup(); spec, c = load(sys.argv[2]); os.makedirs(sys.argv[3], exist_ok=True)
        print(thumbnail(c, os.path.join(sys.argv[3], "thumbnail.jpg")))
