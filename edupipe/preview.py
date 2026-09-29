"""Local preview site: `edupipe preview` → http://127.0.0.1:8765

Read-only by design: approval stays a deliberate, named step on the command line.
Serves only files inside episodes/, and only on this machine (127.0.0.1).
"""
import json
import mimetypes
import re
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import review
from .project import ASSETS, EPISODES, POSES as STANDARD_POSES, ROOT, Episode, characters, load_yaml

STATIC = ROOT / "edupipe" / "static"
SLUG = re.compile(r"^[A-Za-z0-9._-]+$")


# --- data ---------------------------------------------------------------------
def _mtime(p):
    return int(p.stat().st_mtime) if p.exists() else None


def episode_summary(ep):
    st = ep.state()
    brief = ep.load_brief() if ep.brief.exists() else {}
    script = json.loads(ep.script_json.read_text(encoding="utf-8")) if ep.script_json.exists() else None
    scenes = []
    for i, sc in enumerate((script or {}).get("scenes", []), 1):
        audio = sorted(ep.audio_dir.glob(f"scene_{i:02d}.*")) if ep.audio_dir.exists() else []
        frame = ep.frames_dir / f"scene_{i:02d}.png"
        scenes.append({
            **sc, "n": i,
            "audio": f"audio/{audio[0].name}?v={_mtime(audio[0])}" if audio else None,
            "frame": f"frames/{frame.name}?v={_mtime(frame)}" if frame.exists() else None,
        })
    missing = review.status(ep) if ep.review.exists() else []
    return {
        "slug": ep.slug,
        "topic": brief.get("topic", ep.slug),
        "format": brief.get("format", "short"),
        "age": brief.get("age"),
        "title": (script or {}).get("title"),
        "objective": (script or {}).get("learning_objective") or brief.get("objective"),
        "claims": (script or {}).get("claims", []),
        "review_claims": load_yaml(ep.review).get("claims", []) if ep.review.exists() else [],
        "safety_notes": (script or {}).get("safety_notes", []),
        "scenes": scenes,
        "mock": bool(st.get("script_mock") or st.get("voice_mock")),
        "steps": {
            "script": ep.script_json.exists(),
            "approved": bool(st.get("approved_hash")),
            "voiced": bool(scenes) and all(s["audio"] for s in scenes),
            "video": ep.final.exists(),
            "uploaded": bool(st.get("uploaded_video_id")),
        },
        "approved_by": st.get("approved_by"),
        "approved_at": st.get("approved_at"),
        "review_missing": missing,
        "video": f"final.mp4?v={_mtime(ep.final)}" if ep.final.exists() else None,
        "captions": "captions.vtt" if ep.srt.exists() else None,
        "seconds": st.get("final_seconds"),
        "youtube_id": st.get("uploaded_video_id"),
        "updated": max(filter(None, [_mtime(p) for p in ep.dir.rglob("*") if p.is_file()]), default=0),
    }


def all_episodes():
    if not EPISODES.exists():
        return []
    eps = [episode_summary(Episode(p.name)) for p in EPISODES.iterdir() if p.is_dir() and (p / "brief.yaml").exists()]
    return sorted(eps, key=lambda e: -e["updated"])




def cast_summary():
    """Each character's pose images, and which poses the scripts ask for that don't exist yet."""
    used = {}
    if EPISODES.exists():
        for d in EPISODES.iterdir():
            sj = d / "script.json"
            if not sj.exists():
                continue
            try:
                scenes = json.loads(sj.read_text(encoding="utf-8")).get("scenes", [])
            except ValueError:
                continue
            for sc in scenes:
                pose = (sc.get("pose") or "default").strip().lower()
                used.setdefault(sc.get("speaker"), {}).setdefault(pose, set()).add(d.name)
    out = []
    for name, c in characters().items():
        folder = ASSETS / "characters" / name
        have = sorted(p.stem for p in folder.glob("*.png") if "." not in p.stem) if folder.exists() else []
        test_folder = ASSETS / "test-cast" / name
        test = sorted(p.stem for p in test_folder.glob("*.png") if "." not in p.stem) if test_folder.exists() else []
        wanted = used.get(name, {})
        out.append({
            "name": name,
            "role": c.get("role", ""),
            "color": c.get("color", "#333333"),
            "voice": c.get("gemini_voice") if not c.get("voice_id") else "ElevenLabs",
            "style": c.get("gemini_style", ""),
            "poses": [{"pose": p, "src": f"/cast/{name}/{p}.png?v={_mtime(folder / (p + '.png'))}"} for p in have],
            "has_default": "default" in have,
            "test": {p: f"/test-cast/{name}/{p}.png?v={_mtime(test_folder / (p + '.png'))}" for p in test},
            "missing_used": sorted(
                ({"pose": p, "episodes": sorted(eps)} for p, eps in wanted.items() if p not in have),
                key=lambda x: -len(x["episodes"])),
            "missing_standard": [p for p in STANDARD_POSES if p not in have],
            "scenes": sum(len(e) for e in wanted.values()),
        })
    return out


def srt_to_vtt(text):
    body = re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", text)
    return "WEBVTT\n\n" + body


# --- http ---------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "edupipe-preview"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path):
        """Serves a file with HTTP Range support, so the video player can seek."""
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
        if m:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:  # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                return self._send(416, extra={"Content-Range": f"bytes */{size}"})
        length = end - start + 1
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if m:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining:
                chunk = fh.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the browser cancelled (normal while seeking)
                remaining -= len(chunk)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/episodes":
            return self._send(200, json.dumps(all_episodes()).encode(), "application/json")
        if path == "/api/cast":
            return self._send(200, json.dumps(cast_summary()).encode(), "application/json")
        m = re.match(r"^/(cast|test-cast)/([^/]+)/([A-Za-z0-9 _.-]+\.png)$", path)
        if m:
            base = (ASSETS / ("characters" if m.group(1) == "cast" else "test-cast")).resolve()
            target = (base / m.group(2) / m.group(3)).resolve()
            if target.is_file() and base in target.parents:
                return self._file(target)
        m = re.match(r"^/files/([^/]+)/(.+)$", path)
        if m and SLUG.match(m.group(1)):
            ep_dir = (EPISODES / m.group(1)).resolve()
            if m.group(2) == "captions.vtt":
                srt = ep_dir / "captions.srt"
                if srt.exists():
                    return self._send(200, srt_to_vtt(srt.read_text(encoding="utf-8")).encode(), "text/vtt; charset=utf-8")
            target = (ep_dir / m.group(2)).resolve()
            # never serve anything outside the episode folder
            if target.is_file() and ep_dir in target.parents:
                return self._file(target)
        self._send(404, b"not found")


def serve(port=8765, open_browser=False):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Preview running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


# --- local playback ------------------------------------------------------------------
def play(path):
    """ffplay if installed (closes when done), otherwise the desktop's default player."""
    path = Path(path)
    if shutil.which("ffplay"):
        cmd = ["ffplay", "-autoexit", "-loglevel", "error"]
        if path.suffix in (".mp3", ".wav"):
            cmd.append("-nodisp")
        subprocess.run(cmd + [str(path)])
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(f"No player found. Open it yourself: {path}")
