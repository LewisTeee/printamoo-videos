#!/usr/bin/env python3
"""Download a Printamoo post's printable preview images.

Usage: python3 pipeline/fetch_post.py POST_URL OUTDIR
Writes OUTDIR/post.json: {url, title, intro, printables: [{file, alt, members_only, pdf}], text}
and saves each printable preview image as OUTDIR/img/NN.jpg.
Only images inside the post body are kept (logo, author photo and "related posts" cards are skipped).
"""
import sys, os, re, json, html, subprocess

def get(url):
    import time
    for attempt in range(5):
        r = subprocess.run(["curl", "-sSL", "--retry", "3", "-A", "Mozilla/5.0 PrintamooVideoBot", url], capture_output=True)
        if r.returncode == 0 and r.stdout: return r.stdout
        time.sleep(2 + attempt * 2)
    raise RuntimeError("download failed: " + url)

def main(url, outdir):
    os.makedirs(os.path.join(outdir, "img"), exist_ok=True)
    h = get(url).decode("utf-8", "replace")
    title = html.unescape(re.sub(r"<[^>]+>", "", (re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S) or [None, ""])[1])).strip()
    body = h
    m = re.search(r'<div[^>]+class="[^"]*entry-content[^"]*"', h)
    if m: body = h[m.start():]
    for stop in ['class="author-box', "Search 5,000+ Printables", 'id="comments"', "Featured Pages"]:
        k = body.find(stop)
        if k > 0: body = body[:k]
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)))).strip()
    printables, seen = [], set()
    for im in re.finditer(r"<img[^>]+>", body):
        tag = im.group(0)
        src = re.search(r'(?:data-src|data-lazy-src|src)="([^"]+)"', tag)
        if not src: continue
        src = src.group(1)
        if "/wp-content/uploads/" not in src or "logo" in src or src.startswith("data:"): continue
        base = re.sub(r"-\d+x\d+(?=\.\w+$)", "", src)
        if base in seen: continue
        seen.add(base)
        alt = html.unescape((re.search(r'alt="([^"]*)"', tag) or [None, ""])[1])
        window = body[im.end(): im.end() + 2500]
        members = bool(re.search(r"members[- ]only", window[:1500], re.I)) and not re.search(r'href="[^"]+\.pdf"', window[:600])
        pdf = (re.search(r'href="([^"]+\.pdf)"', window) or [None, None])[1]
        n = len(printables)
        path = os.path.join(outdir, "img", f"{n:02d}.jpg")
        data = get(base)
        if len(data) < 5000:
            data = get(src)
        open(path, "wb").write(data)
        printables.append({"file": f"img/{n:02d}.jpg", "src": base, "alt": alt, "members_only": members, "pdf": pdf})
    intro = text[:600]
    out = {"url": url, "title": title, "intro": intro, "printables": printables, "text": text[:6000]}
    json.dump(out, open(os.path.join(outdir, "post.json"), "w"), indent=1)
    print(json.dumps({"title": title, "count": len(printables),
                      "free": sum(1 for p in printables if not p["members_only"])}))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
