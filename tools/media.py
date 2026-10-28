"""Build a poster image and a short muted preview clip for every video in media/ids.txt.

Each line of media/ids.txt is "<google-drive-file-id> <v|l>" (vertical or landscape).
Outputs go to assets/thumbs/<id>.jpg and assets/prev/<id>.mp4. Existing outputs are skipped.
A summary is written to media/report.txt.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMBS = os.path.join(ROOT, "assets", "thumbs")
PREV = os.path.join(ROOT, "assets", "prev")
TMP = os.path.join(ROOT, ".tmp")
os.makedirs(THUMBS, exist_ok=True)
os.makedirs(PREV, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def url(fid):
    return f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"


def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def duration(src):
    r = run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration",
             "-of", "json", src] if src.startswith("http") else
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", src], 180)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def build(fid, orient, src):
    is_http = src.startswith("http")
    inp = (["-user_agent", UA] if is_http else [])
    dur = duration(src)
    if dur is None:
        return False, "probe failed"
    start = 1.0 if dur < 20 else min(dur * 0.2, 60.0)
    if start + 6 > dur:
        start = max(0.0, dur - 6.5)
    if orient == "v":
        thumb_scale, prev_scale = "scale=-2:960", "scale=-2:640"
    else:
        thumb_scale, prev_scale = "scale=1280:-2", "scale=640:-2"
    tp = os.path.join(THUMBS, fid + ".jpg")
    pp = os.path.join(PREV, fid + ".mp4")
    r1 = run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start + 1:.2f}", *inp, "-i", src,
              "-frames:v", "1", "-vf", thumb_scale, "-q:v", "4", tp])
    r2 = run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", *inp, "-i", src,
              "-t", "6", "-an", "-vf", prev_scale + ",fps=24", "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", pp])
    ok = os.path.exists(tp) and os.path.getsize(tp) > 1000 and os.path.exists(pp) and os.path.getsize(pp) > 5000
    if not ok:
        for p in (tp, pp):
            if os.path.exists(p):
                os.remove(p)
        return False, (r1.stderr + r2.stderr)[-300:]
    return True, f"dur={dur:.0f}s"


def main():
    lines = [l.split() for l in open(os.path.join(ROOT, "media", "ids.txt")) if l.strip()]
    report = []
    for fid, orient in lines:
        if os.path.exists(os.path.join(THUMBS, fid + ".jpg")) and os.path.exists(os.path.join(PREV, fid + ".mp4")):
            report.append(f"{fid} skip")
            continue
        try:
            ok, msg = build(fid, orient, url(fid))
            if not ok:
                # Fallback: download the whole file with gdown, then build from disk.
                local = os.path.join(TMP, fid)
                g = run([sys.executable, "-m", "gdown", "--quiet", "-O", local, fid], 1800)
                if os.path.exists(local) and os.path.getsize(local) > 10000:
                    ok, msg = build(fid, orient, local)
                    os.remove(local)
                else:
                    msg = "download failed: " + (g.stderr or "")[-200:]
        except Exception as e:  # keep going on any single failure
            ok, msg = False, repr(e)[:200]
        report.append(f"{fid} {'ok' if ok else 'FAIL'} {msg}".replace("\n", " "))
        print(report[-1], flush=True)
    open(os.path.join(ROOT, "media", "report.txt"), "w").write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
