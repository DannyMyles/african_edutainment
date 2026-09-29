"""Stage 4: one frame per scene.

For each scene, the first thing that exists wins:
  1. episodes/<slug>/art/scene_NN.png          full frame drawn by your artist
  2. character pose over a background:
       assets/characters/<Speaker>/<pose>.png  (or default.png)  — renders from your 2D rig
       episodes/<slug>/art/bg_NN.png           AI background (--ai-backgrounds), or
       assets/backgrounds/<background>.png     your library, or a soft gradient
  3. a placeholder card showing who speaks and what the artist needs to draw
"""
import base64
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .project import ASSETS, PipelineError, channel, characters


def _font(size):
    return ImageFont.truetype(channel()["video"]["font"], size)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _gradient(size, color):
    w, h = size
    top, bottom = _hex(color), (16, 18, 22)
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(top[k] * (1 - t) * 0.55 + bottom[k] * (0.45 + 0.55 * t)) for k in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def _cover(img, size):
    """Scale-and-crop to fill `size` (like CSS object-fit: cover)."""
    w, h = size
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _pose_path(speaker, pose):
    """Real art first; then the TEST cast (if enabled); requested pose, then default."""
    dirs = [ASSETS / "characters" / speaker]
    if channel()["video"].get("use_test_cast", True):
        dirs.append(ASSETS / "test-cast" / speaker)
    for d in dirs:
        for name in (f"{pose}.png", "default.png"):
            if (d / name).exists():
                return d / name
    return None


def _mouth_variants(pose_path):
    """[closed, half, open] images for lip-sync, or just [closed] if the variants don't exist."""
    variants = [pose_path.with_name(f"{pose_path.stem}.mouth{n}.png") for n in (1, 2)]
    if channel()["video"].get("lip_sync", True) and all(v.exists() for v in variants):
        return [pose_path] + variants
    return [pose_path]


def _ai_background(ep, i, scene, size):
    path = ep.art_dir / f"bg_{i:02d}.png"
    if path.exists():
        return path
    from openai import OpenAI

    orientation = "1024x1536" if size[1] > size[0] else "1536x1024"
    prompt = (
        "Background plate for a children's 2D animated show set in modern Nairobi, Kenya. "
        "Bright, warm, flat colours, clean shapes, storybook style. No people, no animals, no text, no logos. "
        f"Scene: {scene.get('background', '')}. {scene.get('visual', '')}"
    )
    res = OpenAI().images.generate(model=channel()["llm"]["image_model"], prompt=prompt, size=orientation)
    ep.art_dir.mkdir(exist_ok=True)
    path.write_bytes(base64.b64decode(res.data[0].b64_json))
    return path


def _placeholder(size, scene, color, i):
    img = _gradient(size, color)
    d = ImageDraw.Draw(img)
    w, h = size
    unit = w / 1080
    d.text((w / 2, h * 0.22), scene["speaker"], font=_font(int(96 * unit)), fill="white", anchor="mm")
    d.text((w / 2, h * 0.22 + 90 * unit), f"{scene['beat'].upper()} · pose: {scene.get('pose', 'default')}",
           font=_font(int(36 * unit)), fill=(255, 255, 255, 180), anchor="mm")
    body = textwrap.fill("ART NEEDED: " + scene.get("visual", ""), width=34 if h > w else 60)
    d.multiline_text((w / 2, h * 0.42), body, font=_font(int(40 * unit)), fill=(235, 235, 235),
                     anchor="ma", align="center", spacing=int(12 * unit))
    d.text((w - 30 * unit, 30 * unit), f"#{i:02d}", font=_font(int(36 * unit)), fill=(255, 255, 255), anchor="ra")
    return img


def _frame(ep, i, scene, size, ai):
    art = ep.art_dir / f"scene_{i:02d}.png"
    if art.exists():
        return [_cover(Image.open(art).convert("RGB"), size)], "art"
    cast = characters()
    pose = _pose_path(scene["speaker"], scene.get("pose", "default"))
    if not pose:
        return [_placeholder(size, scene, cast[scene["speaker"]].get("color", "#333333"), i)], "placeholder"
    bg_path = None
    if ai:
        bg_path = _ai_background(ep, i, scene, size)
    elif scene.get("background") and (ASSETS / "backgrounds" / f"{scene['background']}.png").exists():
        bg_path = ASSETS / "backgrounds" / f"{scene['background']}.png"
    bg = _cover(Image.open(bg_path).convert("RGB"), size) if bg_path else _gradient(size, cast[scene["speaker"]].get("color", "#333"))
    w, h = size
    target_h = int(h * (0.55 if h > w else 0.75))
    frames = []
    for path in _mouth_variants(pose):
        char = Image.open(path).convert("RGBA")
        char = char.resize((int(char.width * target_h / char.height), target_h), Image.LANCZOS)
        # Portrait: character sits low-centre above the caption band; landscape: bottom-left third.
        x = (w - char.width) // 2 if h > w else int(w * 0.33 - char.width / 2)
        y = int(h * 0.64) - char.height if h > w else h - char.height
        frame = bg.copy()
        frame.paste(char, (x, y), char)
        frames.append(frame)
    kind = "test character" if "test-cast" in pose.parts else "character"
    return frames, kind


def run(ep, ai_backgrounds=False):
    ep.require_approved()
    if ai_backgrounds and not os.environ.get("OPENAI_API_KEY"):
        raise PipelineError("OPENAI_API_KEY is needed for --ai-backgrounds.")
    fmt = ep.fmt()
    size = (fmt["width"], fmt["height"])
    ep.frames_dir.mkdir(exist_ok=True)
    kinds = {}
    for i, scene in enumerate(ep.load_script()["scenes"], 1):
        imgs, kind = _frame(ep, i, scene, size, ai_backgrounds)
        for old in ep.frames_dir.glob(f"scene_{i:02d}.mouth*.png"):
            old.unlink()
        imgs[0].save(ep.frames_dir / f"scene_{i:02d}.png")
        for n, img in enumerate(imgs[1:], 1):  # lip-sync mouth frames
            img.save(ep.frames_dir / f"scene_{i:02d}.mouth{n}.png")
        kinds[kind] = kinds.get(kind, 0) + 1
    return kinds
