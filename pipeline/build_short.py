#!/usr/bin/env python3
"""Printamoo Shorts builder, v2: hook-first, numbered list, kinetic captions, zooms, whooshes.

Usage:
  python3 pipeline/build_short.py preview SPEC.json OUTDIR   # OUTDIR/preview.png (key frames, captions approximate)
  python3 pipeline/build_short.py build SPEC.json OUTDIR     # OUTDIR/video.mp4 + OUTDIR/thumbnail.jpg

SPEC.json (image paths relative to the spec file):
{
  "keyword": "gratitude cards",                       # bottom search bar: "<keyword> printamoo.com"
  "headline": "Gratitude Cards",                       # used for the thumbnail (or "thumb_title")
  "hook": {"text": "Stop buying gratitude journals",   # BIG on-screen hook, 3-6 words, pops in word by word
           "sub": "7 free ways to use these instead",  # pill under the hook (the promise / open loop)
           "say": "Stop buying gratitude journals. These cards are free, and here are seven ways to use them. Stay for the last one."},
  "scenes": [ {"image": "img/a.jpg",
               "title": "Family gratitude jar",         # on-screen, 2-4 words, what to DO (not the product name)
               "say": "One. Turn any jar into a family gratitude jar...",   # 8-16 words, starts with the number word
               "focus": [0.5, 0.35]} ],                 # optional zoom target (x, y as 0-1 of the image); default top-centre
  "end": {"text": "All free. Every one.", "say": "They're all free. Search gratitude cards printamoo dot com."},
  "voice": "af_heart", "speed": 1.08,                  # optional
  "thumb_title": "...", "thumb_badge": "FREE PRINTABLES"   # optional
}
Rules of thumb: hook <= 3 s of voice, scenes 3-5 s each, whole video 30-45 s, last scene = the promised "best one".
"""
import sys, os, json, math, subprocess, random, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_video as bv
from build_video import W, H, FPS, INK, SOFT, ACC, MAG, BLUE, LAV, BLACK, CTA_Y, ease, fade, fredoka, nunito, card, wrap

SR = 44100
SLIDE = 0.22          # seconds for the whip-in of each scene
LEAD = 0.25           # voice starts this long after a scene cut
TAIL = 0.35           # hold after the voice ends
COLS = [MAG, BLUE, LAV, ACC, MAG, BLUE, LAV, ACC]
NUM_WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]

# ---------------- word timing from the voice track ----------------
def word_times(audio, sr, text):
    """Spread words over the voiced parts of the clip, weighted by length; pauses land on punctuation."""
    words = text.split()
    hop = int(sr * 0.02)
    e = np.array([np.sqrt(np.mean(audio[i:i + hop] ** 2)) for i in range(0, max(1, len(audio) - hop), hop)])
    thr = max(0.012, 0.18 * np.percentile(e, 90))
    voiced = e > thr
    # close tiny gaps (< 120 ms)
    v = voiced.copy(); gap = 0
    for i in range(len(v)):
        if not voiced[i]: gap += 1
        else:
            if 0 < gap <= 6: v[i - gap:i] = True
            gap = 0
    times = np.nonzero(v)[0] * 0.02
    if len(times) == 0: times = np.linspace(0, len(audio) / sr, 50)
    wts = np.array([len(w.strip(".,!?")) + 2 + (3 if w[-1] in ".,!?" else 0) for w in words], float)
    cum = np.concatenate([[0], np.cumsum(wts)]) / wts.sum()
    idx = np.clip((cum * (len(times) - 1)).astype(int), 0, len(times) - 1)
    starts = [float(times[idx[i]]) for i in range(len(words))]
    ends = [float(times[max(idx[i], idx[i + 1] - 1)]) + 0.02 for i in range(len(words))]
    out = list(zip(words, starts, ends))
    merged = []
    i = 0
    while i < len(out):
        if i + 2 < len(out) and out[i + 1][0].lower() == "dot" and out[i + 2][0].lower().strip(".,!?") == "com":
            tail = out[i + 2][0][3:]
            merged.append((out[i][0] + ".com" + tail, out[i][1], out[i + 2][2])); i += 3
        else:
            merged.append(out[i]); i += 1
    return merged

def chunks(words, font, maxw, maxlines=2):
    """Group (word,start,end) into caption pages that fit maxlines lines."""
    pages, cur = [], []
    for w in words:
        trial = cur + [w]
        if len(wrap(" ".join(x[0] for x in trial), font, maxw)) > maxlines or (cur and cur[-1][0][-1] in ".!?"):
            pages.append(cur); cur = [w]
        else: cur = trial
    if cur: pages.append(cur)
    return pages

def draw_caption(im, words_t, t, box, size=54):
    """Karaoke caption inside box=(x0,y0,x1,y1): current word magenta + slightly bigger, spoken words ink, upcoming soft."""
    x0, y0, x1, y1 = box
    f = nunito(size, "ExtraBold"); fb = nunito(int(size * 1.08), "Black")
    pages = chunks(words_t, f, x1 - x0 - 80)
    page = pages[0]
    for p in pages:
        if t >= p[0][1] - 0.05: page = p
    lines = []; line = []
    for w in page:
        if line and f.getlength(" ".join(x[0] for x in line + [w])) > x1 - x0 - 80: lines.append(line); line = [w]
        else: line.append(w)
    if line: lines.append(line)
    d = ImageDraw.Draw(im); lh = int(size * 1.35)
    cur = None
    for w in page:
        if t >= w[1] - 0.03: cur = w
    ty = (y0 + y1) / 2 - lh * len(lines) / 2
    for li, ln in enumerate(lines):
        widths = [f.getlength(w[0]) for w in ln]; sp = f.getlength(" ")
        tw = sum(widths) + sp * (len(ln) - 1); x = (x0 + x1) / 2 - tw / 2
        for (wd, s, e), wdt in zip(ln, widths):
            if cur is not None and (wd, s, e) == cur and t <= e + 0.25:
                d.text((x - (fb.getlength(wd) - wdt) / 2, ty + li * lh - 3), wd, font=fb, fill=MAG)
            else:
                d.text((x, ty + li * lh), wd, font=f, fill=INK if t > e else (178, 166, 205))
            x += wdt + sp

# ---------------- shared visuals ----------------
def progress(im, n, cur, frac):
    """Segmented progress bar under the logo: done segments filled, current one fills over time."""
    d = ImageDraw.Draw(im); total = 760; gap = 12; segw = (total - gap * (n - 1)) / n; x = (W - total) / 2; y = 168
    for i in range(n):
        d.rounded_rectangle((x, y, x + segw, y + 12), 6, fill=(255, 255, 255, 200), outline=(126, 87, 194, 120), width=2)
        f = 1 if i < cur else (frac if i == cur else 0)
        if f > 0: d.rounded_rectangle((x, y, x + max(12, segw * f), y + 12), 6, fill=MAG + (255,))
        x += segw + gap

def window(img_path, ww, wh):
    """Pre-load a printable for Ken-Burns cropping."""
    im = Image.open(img_path).convert("RGB")
    s = max(ww * 1.5 / im.width, wh * 1.5 / im.height, 1.0)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS) if s > 1.0 else im

def kb_frame(src, ww, wh, zoom, fx, fy):
    """Crop src to the window aspect at zoom (1 = whole image fits), centred toward focus (fx,fy)."""
    sw, sh = src.size; asp = ww / wh
    if sw / sh > asp: bh = sh; bw = sh * asp
    else: bw = sw; bh = sw / asp
    # zoom 1: fit whole image (letterbox); >1: crop
    cw, ch = bw / zoom, bh / zoom
    cx = min(max(fx * sw, cw / 2), sw - cw / 2); cy = min(max(fy * sh, ch / 2), sh - ch / 2)
    return src.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize((ww, wh), Image.BILINEAR)

def framed(content, radius=34, border=8):
    w, h = content.size
    out = Image.new("RGBA", (w + 80, h + 90), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 46, w + 50, h + 66), radius, fill=(60, 30, 110, 90))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    mask = Image.new("L", (w, h), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    c = content.convert("RGBA"); c.putalpha(mask)
    ImageDraw.Draw(out).rounded_rectangle((40 - border, 40 - border, 40 + w + border - 1, 40 + h + border - 1), radius + border,
                                          fill=(255, 255, 255, 255), outline=ACC + (255,), width=border)
    out.alpha_composite(c, (40, 40))
    return out

def caption_panel(y0, y1):
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(p)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((60, y0 + 10, W - 60, y1 + 14), 40, fill=(60, 30, 110, 60))
    p.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    ImageDraw.Draw(p).rounded_rectangle((60, y0, W - 60, y1), 40, fill=(255, 255, 255, 248), outline=ACC + (255,), width=6)
    return p

# ---------------- scenes ----------------
class S:
    pass

def hook_scene(spec, base, words_t, dur, nscenes):
    hk = spec["hook"]; bg = bv.background(7)
    imgs = [base(x["image"]) for x in spec["scenes"]][:3]
    while len(imgs) < 3: imgs.append(imgs[-1])
    cards = [card(p, 430, a, max_h=520) for p, a in zip(imgs, (-12, 11, -2))]
    # dim veil so text pops
    veil = Image.new("RGBA", (W, H), (245, 241, 253, 120))
    words = hk["text"].split()
    size = 150
    while True:
        f = fredoka(size, "Bold"); lines = wrap(hk["text"], f, 960)
        if len(lines) <= 3 or size <= 90: break
        size -= 8
    # map each hook word to the time its spoken counterpart starts (first N words of narration)
    spoken = [w for w in words_t]
    starts = []
    for i, w in enumerate(words):
        starts.append(spoken[i][1] if i < len(spoken) else (starts[-1] + 0.15 if starts else 0))
    sub = hk.get("sub", "")
    sf = nunito(46, "ExtraBold"); subw = int(sf.getlength(sub)) + 100
    pillim = Image.new("RGBA", (subw, 96), (0, 0, 0, 0)); pd = ImageDraw.Draw(pillim)
    pd.rounded_rectangle((0, 0, subw - 1, 95), 48, fill=MAG + (255,)); pd.text((50, 18), sub, font=sf, fill=(255, 255, 255))
    sub_t = spoken[min(len(spoken) - 1, len(words) + 1)][1] if spoken else 1.5
    asc, desc = f.getmetrics(); lh = int((asc + desc) * 0.98)
    ty0 = 330
    def frame(t):
        im = bg.copy().convert("RGBA")
        # cards drift + slow spin behind
        for i, (cd, (x, y)) in enumerate(zip(cards, [(10, 1040), (540, 1060), (W // 2 - cards[2].width // 2, 1110)])):
            a = ease((t - 0.05 * i) / 0.5)
            dx = int(14 * math.sin(t * 1.6 + i)); dy = int(160 * (1 - a)) + int(10 * math.cos(t * 1.3 + i))
            im.alpha_composite(fade(cd, a), (x + dx, y + dy))
        im.alpha_composite(veil)
        d = ImageDraw.Draw(im); wi = 0
        for li, ln in enumerate(lines):
            lw = ln.split(); x = (W - f.getlength(ln)) / 2
            for wd in lw:
                st = starts[min(wi, len(starts) - 1)]; a = ease((t - st + 0.08) / 0.18)
                if a > 0:
                    s = 1.0 + 0.25 * (1 - a)
                    ff = fredoka(int(size * s), "Bold")
                    col = MAG if wi == len(words) - 1 else ACC
                    dx = (ff.getlength(wd) - f.getlength(wd)) / 2
                    d.text((x - dx, ty0 + li * lh - (ff.size - size) / 2), wd, font=ff, fill=col, stroke_width=12, stroke_fill=(255, 255, 255))
                x += f.getlength(wd + " "); wi += 1
        a = ease((t - sub_t) / 0.3)
        if a > 0:
            s = 0.7 + 0.3 * a + 0.04 * math.sin(max(0, t - sub_t - 0.3) * 6) * (1 if t > sub_t + 0.3 else 0)
            pp = pillim.resize((int(subw * s), int(96 * s)), Image.BILINEAR)
            im.alpha_composite(fade(pp, a), ((W - pp.width) // 2, ty0 + len(lines) * lh + 50 - (pp.height - 96) // 2))
        draw_caption(im, words_t, t, (60, 1290, W - 60, 1500), 50) if False else None
        progress(im, nscenes, -1, 0)
        return im
    return frame, bg

def item_scene(spec, base, idx, words_t, dur, nscenes):
    sc = spec["scenes"][idx]; col = COLS[idx % len(COLS)]; bg = bv.background(7)
    ww, wh = 900, 1000; wy = 330
    src = window(base(sc["image"]), ww, wh)
    fx, fy = sc.get("focus", [0.5, 0.38]); zmax = sc.get("zoom", 0.25)
    last = idx == nscenes - 1
    # title row with number badge
    tf = fredoka(66, "SemiBold")
    title = sc["title"]
    while tf.getlength(title) > 800 and tf.size > 44: tf = fredoka(tf.size - 4, "SemiBold")
    badge_r = 52
    capbox = (60, 1440, W - 60, 1660)
    panel = caption_panel(capbox[1], capbox[3])
    star = None
    if last:
        sf = nunito(32, "Black"); star_t = "MY FAVORITE"; sw_ = int(sf.getlength(star_t)) + 50
        star = Image.new("RGBA", (sw_, 56), (0, 0, 0, 0)); sd = ImageDraw.Draw(star)
        sd.rounded_rectangle((0, 0, sw_ - 1, 55), 28, fill=(255, 196, 61, 255)); sd.text((25, 9), star_t, font=sf, fill=BLACK)
    def frame(t):
        im = bg.copy().convert("RGBA")
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # window with Ken Burns: quick punch 1.0->1.12 then slow push to ~1.45 toward focus
        z = 1.0 + 0.10 * ease(t / 0.5) + zmax * max(0, (t - 0.5)) / max(0.5, dur - 0.5)
        k = kb_frame(src, ww, wh, z, 0.5 + (fx - 0.5) * min(1, t / dur * 1.4), 0.5 + (fy - 0.5) * min(1, t / dur * 1.4))
        fr = framed(k)
        layer.alpha_composite(fr, ((W - fr.width) // 2, wy - 40))
        # title row
        d = ImageDraw.Draw(layer)
        tw = tf.getlength(title); rowx = (W - (tw + badge_r * 2 + 24)) / 2; cy = 262
        a = ease((t - 0.08) / 0.25); r = badge_r * (0.4 + 0.6 * a) * (1 + 0.15 * math.sin(min(1, a) * math.pi))
        d.ellipse((rowx + badge_r - r, cy - r, rowx + badge_r + r, cy + r), fill=col + (255,), outline=(255, 255, 255, 255), width=5)
        nf = fredoka(int(64 * (r / badge_r)), "Bold"); n = str(idx + 1)
        d.text((rowx + badge_r - nf.getlength(n) / 2, cy - nf.size * 0.62), n, font=nf, fill=(255, 255, 255))
        d.text((rowx + badge_r * 2 + 24, cy - tf.size * 0.62), title, font=tf, fill=INK)
        if star is not None:
            a2 = ease((t - 0.3) / 0.3)
            if a2 > 0:
                s = 0.6 + 0.4 * a2; st = star.resize((int(star.width * s), int(star.height * s)), Image.BILINEAR)
                layer.alpha_composite(fade(st, a2), (W - 60 - st.width - 40, wy + 10))
        layer.alpha_composite(panel)
        draw_caption(layer, words_t, t - LEAD, capbox)
        # whip-in from the right
        off = int(W * (1 - ease(t / SLIDE))) if t < SLIDE else 0
        im.alpha_composite(layer, (off, 0))
        progress(im, nscenes, idx, min(1, t / dur))
        return im
    return frame, bg

def end_scene(spec, base, words_t, dur, nscenes):
    e = spec["end"]; bg = bv.background(7)
    imgs = [base(x["image"]) for x in spec["scenes"]][:7]
    n = len(imgs); cols = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 3, 7: 4}[n]
    cw = {4: 230, 3: 280, 2: 330, 1: 380}[cols]
    cs = [card(p, cw, a, max_h=380) for p, a in zip(imgs, [-6, 5, -3, 6, -5, 3, -2])]
    pos = []
    for i, c in enumerate(cs):
        r, ci = divmod(i, cols); rowc = min(cols, n - r * cols)
        x = W / 2 + (ci - (rowc - 1) / 2) * {4: 245, 3: 310, 2: 390, 1: 0}[cols] - c.width / 2
        pos.append((int(x), 470 + r * 400))
    tf = fredoka(110, "Bold"); lines = wrap(e["text"], tf, 980)
    capbox = (60, 1440, W - 60, 1660); panel = caption_panel(capbox[1], capbox[3])
    qf = nunito(36, "ExtraBold"); kw = spec["keyword"] + " "
    while qf.getlength(kw) + qf.getlength("printamoo.com") > W - 220: qf = nunito(qf.size - 2, "ExtraBold")
    bw = qf.getlength(kw) + qf.getlength("printamoo.com") + 150
    def frame(t):
        im = bg.copy().convert("RGBA"); layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for i, (cd, (x, y)) in enumerate(zip(cs, pos)):
            a = ease((t - 0.1 - i * 0.07) / 0.35)
            layer.alpha_composite(fade(cd, a), (x, y + int(120 * (1 - a))))
        d = ImageDraw.Draw(layer)
        for li, ln in enumerate(lines):
            a = ease((t - 0.1 - li * 0.15) / 0.3)
            if a > 0:
                ff = fredoka(int(110 * (1 + 0.2 * (1 - a))), "Bold")
                d.text(((W - ff.getlength(ln)) / 2, 230 + li * 120 - (ff.size - 110) / 2), ln, font=ff, fill=MAG if li == len(lines) - 1 else ACC,
                       stroke_width=10, stroke_fill=(255, 255, 255))
        layer.alpha_composite(panel)
        draw_caption(layer, words_t, t - LEAD, capbox)
        off = int(W * (1 - ease(t / SLIDE))) if t < SLIDE else 0
        im.alpha_composite(layer, (off, 0))
        # pulse ring around the search bar once the voice says "search"
        st = next((s for w, s, _ in words_t if w.lower().startswith("search")), 1.0) + LEAD
        if t > st:
            ph = (t - st) % 0.9 / 0.9; dd = ImageDraw.Draw(im)
            pad = int(10 + 26 * ph); al = int(200 * (1 - ph))
            dd.rounded_rectangle((W / 2 - bw / 2 - pad, CTA_Y - pad, W / 2 + bw / 2 + pad, CTA_Y + 78 + pad), 39 + pad, outline=MAG + (al,), width=6)
        progress(im, nscenes, nscenes, 1)
        return im
    return frame, bg

# ---------------- audio ----------------
def tts_all(spec, outdir):
    import soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(bv.CACHE, "kokoro-v1.0.onnx"), os.path.join(bv.CACHE, "voices-v1.0.bin"))
    texts = [spec["hook"]["say"]] + [s["say"] for s in spec["scenes"]] + [spec["end"]["say"]]
    out = []
    for i, t in enumerate(texts):
        a, sr = k.create(t, voice=spec.get("voice", "af_heart"), speed=spec.get("speed", 1.08), lang="en-us")
        nz = np.where(np.abs(a) > 0.01)[0]; a = a[max(0, nz[0] - 400): nz[-1] + 1600]
        import scipy.signal as ss
        if sr != SR: a = ss.resample_poly(a, SR, sr)
        sf.write(os.path.join(outdir, f"vo{i:02d}.wav"), a, SR)
        out.append((t, a))
    return out

def upbeat_music(total, path, seed=11):
    N = int(SR * total); out = np.zeros((N, 2)); bpm = 112; beat = 60 / bpm; bar = 4 * beat
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    rng = np.random.default_rng(seed)
    def add(sig, start, pan=0.0):
        i = int(start * SR)
        if i >= N: return
        if sig.ndim == 1: sig = np.stack([sig * (1 - max(0, pan)), sig * (1 + min(0, pan))], 1)
        j = min(N, i + len(sig)); out[i:j] += sig[: j - i]
    def pluck(f, length, vel):
        t = np.arange(int(SR * length)) / SR
        s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) * np.exp(-t * 8) + 0.25 * np.sin(6 * np.pi * f * t) * np.exp(-t * 12)
        return s * np.exp(-t * 7) * (1 - np.exp(-t * 600)) * vel
    def kick():
        t = np.arange(int(SR * 0.25)) / SR; f = 120 * np.exp(-t * 25) + 45
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14) * 0.5
    def clap():
        t = np.arange(int(SR * 0.15)) / SR; n = rng.standard_normal(len(t))
        n = np.convolve(n, [1, -0.9], "same"); return n * np.exp(-t * 30) * 0.08
    def padc(freqs, length):
        t = np.arange(int(SR * length)) / SR; a = np.minimum(1, t / .3) * np.minimum(1, (length - t) / .3)
        s = sum(np.sin(2 * np.pi * f * t) + .2 * np.sin(4 * np.pi * f * t) for f in freqs)
        return s * a * 0.035 / len(freqs)
    # C - G - Am - F
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    bass = [36, 43, 45, 41]
    nb = int(total / bar) + 1
    for b in range(nb):
        t0 = b * bar; ch = chords[b % 4]
        add(padc([midi(m) for m in ch], bar), t0)
        for k in range(8):
            m = ch[[0, 1, 2, 1, 2, 0, 1, 2][k]] + 12
            add(pluck(midi(m), 0.4, 0.13 + 0.03 * rng.random()), t0 + k * beat / 2, 0.3 if k % 2 else -0.3)
        for k in range(4):
            add(pluck(midi(bass[b % 4]), 0.35, 0.3), t0 + k * beat)
            if b >= 1: add(kick(), t0 + k * beat)
            if b >= 1 and k % 2 == 1: add(clap(), t0 + k * beat, 0.1)
    t = np.arange(N) / SR
    out *= (np.minimum(1, t / 0.4) * np.clip((total - t) / 1.2, 0, 1))[:, None]
    out = np.tanh(out * 1.3); out /= np.max(np.abs(out)) / 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((out * 32767).astype("int16").tobytes())

def sfx_track(cuts, pops, total, path):
    N = int(SR * total); out = np.zeros(N); rng = np.random.default_rng(3)
    for c in cuts:  # whoosh: band-passed noise sweep
        ln = int(SR * 0.35); t = np.arange(ln) / SR
        n = rng.standard_normal(ln); env = np.sin(np.pi * np.clip(t / 0.35, 0, 1)) ** 2
        f = 600 + 3000 * t / 0.35; ph = np.cumsum(f) / SR
        s = n * env * (0.5 + 0.5 * np.sin(2 * np.pi * ph)) * 0.10
        s = np.convolve(s, np.ones(6) / 6, "same")
        i = int(max(0, c - 0.12) * SR); j = min(N, i + ln); out[i:j] += s[: j - i]
    for p in pops:  # pop: short pitched blip
        ln = int(SR * 0.09); t = np.arange(ln) / SR
        s = np.sin(2 * np.pi * (900 - 4000 * t) * t) * np.exp(-t * 45) * 0.22
        i = int(p * SR); j = min(N, i + ln); out[i:j] += s[: j - i]
    with wave.open(path, "wb") as w:
        st = np.stack([out, out], 1)
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(st, -1, 1) * 32767).astype("int16").tobytes())

# ---------------- build ----------------
_J = {}
def _render(i):
    J = _J; kind, idx = J["segs"][i]; dur = J["durs"][i]; spec = J["spec"]; base = J["base"]; wt = J["wts"][i]; n = len(spec["scenes"])
    if kind == "hook": frame, bg = hook_scene(spec, base, [(w, s + LEAD, e + LEAD) for w, s, e in wt], dur, n)
    elif kind == "item": frame, bg = item_scene(spec, base, idx, wt, dur, n)
    else: frame, bg = end_scene(spec, base, wt, dur, n)
    ov = J["ov"]; nf = int(round(dur * FPS))
    tmp = os.path.join(J["out"], f"s{i:02d}.tmp.mp4"); fin = os.path.join(J["out"], f"s{i:02d}.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for k in range(nf):
        t = k / FPS; im = frame(t)
        if kind == "hook" and t < 0.12: im = Image.blend(bg.convert("RGBA"), im, t / 0.12)
        im.alpha_composite(ov); p.stdin.write(im.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError(f"scene {i} failed")
    os.replace(tmp, fin); return i

def prepare(spec_path):
    spec = json.load(open(spec_path)); bdir = os.path.dirname(os.path.abspath(spec_path))
    base = lambda p: p if os.path.isabs(p) else os.path.join(bdir, p)
    for s in spec["scenes"]: assert os.path.exists(base(s["image"])), s["image"]
    segs = [("hook", None)] + [("item", i) for i in range(len(spec["scenes"]))] + [("end", None)]
    return spec, base, segs

def build(spec_path, outdir, preview_only=False):
    from multiprocessing import Pool
    import soundfile as sf
    spec, base, segs = prepare(spec_path); os.makedirs(outdir, exist_ok=True)
    if preview_only:
        wts = []; durs = []
        texts = [spec["hook"]["say"]] + [s["say"] for s in spec["scenes"]] + [spec["end"]["say"]]
        for t in texts:
            d = max(1.0, len(t.split()) * 0.33); a = np.ones(int(SR * d)) * 0.1
            wts.append(word_times(a, SR, t)); durs.append(d + LEAD + TAIL)
    else:
        vos = tts_all(spec, outdir)
        wts = [word_times(a, SR, t) for t, a in vos]
        durs = [round((len(a) / SR + LEAD + TAIL) * FPS) / FPS for _, a in vos]
        durs[0] = round((len(vos[0][1]) / SR + LEAD + 0.15) * FPS) / FPS   # hook cuts fast
        durs[-1] += 1.2
    _J.update(spec=spec, base=base, segs=segs, durs=durs, wts=wts, out=outdir, ov=bv.overlay(spec["keyword"]))
    if preview_only:
        shots = []
        for i, (kind, idx) in enumerate(segs):
            n = len(spec["scenes"]); wt = wts[i]; dur = durs[i]
            if kind == "hook": fr, _ = hook_scene(spec, base, [(w, s + LEAD, e + LEAD) for w, s, e in wt], dur, n)
            elif kind == "item": fr, _ = item_scene(spec, base, idx, wt, dur, n)
            else: fr, _ = end_scene(spec, base, wt, dur, n)
            im = fr(dur * 0.6); im.alpha_composite(_J["ov"]); shots.append(im.convert("RGB").resize((360, 640)))
        cols = 5; rows = (len(shots) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 370, rows * 650), "black")
        for i, s in enumerate(shots): sheet.paste(s, ((i % cols) * 370, (i // cols) * 650))
        sheet.save(os.path.join(outdir, "preview.png")); print(os.path.join(outdir, "preview.png")); return
    with Pool(min(6, os.cpu_count() or 2)) as pool:
        for _ in pool.imap_unordered(_render, range(len(segs))): pass
    with open(os.path.join(outdir, "list.txt"), "w") as f:
        for i in range(len(segs)): f.write(f"file '{os.path.join(outdir, f's{i:02d}.mp4')}'\n")
    silent = os.path.join(outdir, "silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(outdir, "list.txt"), "-c", "copy", silent], check=True)
    total = sum(durs)
    voice = np.zeros(int(total * SR) + SR); off = 0; cuts = []; pops = []
    for i, d in enumerate(durs):
        a, _ = sf.read(os.path.join(outdir, f"vo{i:02d}.wav"))
        st = int((off + LEAD) * SR); voice[st:st + len(a)] += a
        if i > 0: cuts.append(off)
        if segs[i][0] == "item": pops.append(off + 0.1)
        off += d
    sf.write(os.path.join(outdir, "voice.wav"), voice[:int(total * SR)], SR)
    upbeat_music(total, os.path.join(outdir, "music.wav"))
    sfx_track(cuts, pops, total, os.path.join(outdir, "sfx.wav"))
    fin = os.path.join(outdir, "video.mp4"); tmp = os.path.join(outdir, "video.tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", os.path.join(outdir, "voice.wav"),
                    "-i", os.path.join(outdir, "music.wav"), "-i", os.path.join(outdir, "sfx.wav"),
                    "-filter_complex",
                    "[1:a]aformat=channel_layouts=stereo,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,volume=2.0,asplit=2[v1][vsc];"
                    "[2:a]volume=0.30[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=5:attack=15:release=300[md];"
                    "[3:a]volume=0.9[fx];[v1][md][fx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
                    "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, fin)
    c = bv.Ctx(dict(spec, scenes=spec["scenes"]), os.path.dirname(os.path.abspath(spec_path)))
    bv.thumbnail(c, os.path.join(outdir, "thumbnail.jpg"))
    print(json.dumps({"video": fin, "thumbnail": os.path.join(outdir, "thumbnail.jpg"), "seconds": round(total, 2), "bytes": os.path.getsize(fin)}))

if __name__ == "__main__":
    cmd = sys.argv[1]; bv.setup()
    if cmd == "preview": build(sys.argv[2], sys.argv[3], preview_only=True)
    elif cmd == "build": build(sys.argv[2], sys.argv[3])
