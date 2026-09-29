"""TEST characters, drawn in code: consistent, free, instant — for testing the pipeline
before the illustrator's artwork exists. Clearly marked "TEST"; saved to
assets/test-cast/<Name>/ so real art in assets/characters/ always wins.

Each pose is saved three times for lip-sync:
  <pose>.png          mouth closed
  <pose>.mouth1.png   mouth half open
  <pose>.mouth2.png   mouth open
The illustrator can deliver the same three files per pose and lip-sync just works.
"""
import math

from PIL import Image, ImageDraw, ImageFont

from .project import ASSETS, POSES, channel

W, H = 1300, 1600
GROUND = H - 40
TEST_DIR = ASSETS / "test-cast"
OUTLINE = (40, 30, 30, 255)

# Deliberately simple and neutral: these are placeholders, not the characters' designs.
SPECS = {
    "Zawadi":     dict(scale=0.95, skin="#8d5a3b", shirt="#e0782f", lower="#2d3a5a", hair="#1b1311", hairstyle="puffs", skirt=False, extra="belt"),
    "Kito":       dict(scale=0.84, skin="#7a4a2e", shirt="#3a86c8", lower="#3b3b3b", hair="#1b1311", hairstyle="cap", skirt=False, extra=None),
    "Ada":        dict(scale=0.95, skin="#6e4128", shirt="#8e44ad", lower="#f2c14e", hair="#140e0c", hairstyle="bun", skirt=True, extra="notebook"),
    "Tesfa":      dict(scale=1.00, skin="#9b6a47", shirt="#2e8b57", lower="#2d3a5a", hair="#1b1311", hairstyle="short", skirt=False, extra=None),
    "Cucu Njeri": dict(scale=1.12, skin="#7f5236", shirt="#b5651d", lower="#6d3f18", hair="#d9d4cc", hairstyle="grey", skirt=True, extra="glasses"),
}

# Hand targets as (dx, dy) in torso-heights from the shoulder, left and right.
ARMS = {
    "default":    ((-0.25, 0.95), (0.25, 0.95)),
    "happy":      ((-0.75, -0.25), (0.75, -0.25)),
    "surprised":  ((-0.55, -0.65), (0.55, -0.65)),
    "thinking":   ((-0.25, 0.95), (0.05, -0.45)),
    "explaining": ((-0.25, 0.95), (0.9, -0.05)),
    "excited":    ((-0.65, -1.0), (0.65, -1.0)),
    "curious":    ((-0.25, 0.95), (0.35, 0.35)),
    "proud":      ((-0.05, 0.55), (0.05, 0.55)),
    "singing":    ((-0.8, 0.05), (0.8, 0.05)),
}
FACE = {  # eyes, brows, mouth shape when closed
    "default": ("dot", 0, "smile"), "happy": ("arc", 0, "grin"), "surprised": ("big", 1, "o"),
    "thinking": ("dot", -1, "line"), "explaining": ("dot", 0, "smile"), "excited": ("arc", 1, "grin"),
    "curious": ("big", 1, "smile"), "proud": ("arc", -1, "smile"), "singing": ("closed", 1, "smile"),
}


def _font(size):
    return ImageFont.truetype(channel()["video"]["font"], size)


def _mouth(d, cx, cy, r, shape, level):
    """level 0 = closed (the pose's own mouth), 1 = half open, 2 = open."""
    if level == 0:
        if shape == "o":
            d.ellipse((cx - r * 0.18, cy - r * 0.1, cx + r * 0.18, cy + r * 0.26), fill=(90, 20, 25, 255))
        elif shape == "line":
            d.line((cx - r * 0.25, cy + r * 0.05, cx + r * 0.2, cy), fill=OUTLINE, width=int(r * 0.07))
        else:
            span = 0.42 if shape == "grin" else 0.32
            box = (cx - r * span, cy - r * 0.25, cx + r * span, cy + r * (0.28 if shape == "grin" else 0.2))
            if shape == "grin":
                d.chord(box, 0, 180, fill=(90, 20, 25, 255), outline=OUTLINE, width=int(r * 0.04))
            else:
                d.arc(box, 20, 160, fill=OUTLINE, width=int(r * 0.07))
        return
    h = r * (0.16 if level == 1 else 0.32)
    w = r * (0.3 if level == 1 else 0.36)
    d.ellipse((cx - w, cy - h * 0.4, cx + w, cy + h), fill=(90, 20, 25, 255), outline=OUTLINE, width=int(r * 0.04))
    if level == 2:
        d.chord((cx - w * 0.6, cy + h * 0.2, cx + w * 0.6, cy + h * 0.95), 180, 360, fill=(215, 95, 100, 255))


def _eyes(d, cx, cy, r, kind, brows):
    for sx in (-1, 1):
        ex = cx + sx * r * 0.38
        if kind == "big":
            d.ellipse((ex - r * 0.16, cy - r * 0.18, ex + r * 0.16, cy + r * 0.18), fill="white", outline=OUTLINE, width=int(r * 0.03))
            d.ellipse((ex - r * 0.08, cy - r * 0.08, ex + r * 0.08, cy + r * 0.1), fill=OUTLINE)
        elif kind in ("arc", "closed"):
            d.arc((ex - r * 0.14, cy - r * 0.1, ex + r * 0.14, cy + r * 0.16), 200, 340, fill=OUTLINE, width=int(r * 0.07))
        else:
            d.ellipse((ex - r * 0.085, cy - r * 0.11, ex + r * 0.085, cy + r * 0.11), fill=OUTLINE)
            d.ellipse((ex - r * 0.02, cy - r * 0.07, ex + r * 0.04, cy - r * 0.01), fill="white")
        by = cy - r * (0.36 + 0.08 * brows)
        tilt = r * 0.05 * (-brows) * sx
        d.line((ex - r * 0.16, by + tilt, ex + r * 0.16, by - tilt), fill=OUTLINE, width=int(r * 0.06))


def _hair(d, cx, cy, r, spec, back):
    c = spec["hair"]
    style = spec["hairstyle"]
    if back:  # drawn behind the head
        if style == "puffs":
            for sx in (-1, 1):
                d.ellipse((cx + sx * r * 0.95 - r * 0.42, cy - r * 1.02, cx + sx * r * 0.95 + r * 0.42, cy - r * 0.18), fill=c)
        if style == "bun":
            d.ellipse((cx - r * 0.42, cy - r * 1.55, cx + r * 0.42, cy - r * 0.75), fill=c)
        if style == "grey":
            d.ellipse((cx - r * 1.08, cy - r * 1.1, cx + r * 1.08, cy + r * 0.35), fill=c)
        return
    if style == "cap":
        d.chord((cx - r * 1.02, cy - r * 1.05, cx + r * 1.02, cy + r * 0.2), 180, 360, fill=spec["shirt"], outline=OUTLINE, width=int(r * 0.04))
        d.rounded_rectangle((cx - r * 0.1, cy - r * 0.47, cx + r * 1.35, cy - r * 0.3), radius=int(r * 0.08), fill=spec["shirt"], outline=OUTLINE, width=int(r * 0.04))
    else:
        d.chord((cx - r * 1.02, cy - r * 1.04, cx + r * 1.02, cy + r * 0.05), 180, 360, fill=c)


def _limb(d, a, b, width, color, bend):
    mx, my = (a[0] + b[0]) / 2 + bend, (a[1] + b[1]) / 2
    d.line((a, (mx, my), b), fill=color, width=width, joint="curve")
    for p in (a, (mx, my), b):
        d.ellipse((p[0] - width / 2, p[1] - width / 2, p[0] + width / 2, p[1] + width / 2), fill=color)


def kid(name, pose, level):
    spec = SPECS[name]
    s = spec["scale"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    leg, torso, r = 330 * s, 390 * s, 165 * s
    tw = 300 * s
    cx = W / 2
    hip = GROUND - leg
    sh = hip - torso
    tilt = 14 if pose == "curious" else 0
    hcx, hcy = cx + tilt * s, sh - r * 0.82
    jump = -40 * s if pose == "excited" else 0
    hip, sh, hcy = hip + jump, sh + jump, hcy + jump

    # legs + shoes
    for sx in (-1, 1):
        x = cx + sx * tw * 0.2
        d.rounded_rectangle((x - 34 * s, hip - 10, x + 34 * s, GROUND + jump - 30 * s), radius=int(20 * s), fill=spec["skin"])
        d.rounded_rectangle((x - 48 * s + sx * 10 * s, GROUND + jump - 48 * s, x + 48 * s + sx * 10 * s, GROUND + jump), radius=int(18 * s), fill="#2b2b2b")
    # lower clothing
    if spec["skirt"]:
        d.polygon([(cx - tw * 0.42, hip - 60 * s), (cx + tw * 0.42, hip - 60 * s), (cx + tw * 0.62, hip + 110 * s), (cx - tw * 0.62, hip + 110 * s)], fill=spec["lower"])
    else:
        d.rounded_rectangle((cx - tw * 0.46, hip - 70 * s, cx + tw * 0.46, hip + 80 * s), radius=int(24 * s), fill=spec["lower"])
    # arms behind torso for proud (hands on hips) look natural either way
    shoulder = [(cx - tw * 0.5, sh + 55 * s), (cx + tw * 0.5, sh + 55 * s)]
    arm_w = int(58 * s)
    for (dx, dy), sp, sx in zip(ARMS[pose], shoulder, (-1, 1)):
        hand = (sp[0] + dx * torso * (1 if abs(dx) > 0.3 else 1.4) + (sx * tw * 0.35 if pose == "proud" else 0), sp[1] + dy * torso)
        _limb(d, sp, hand, arm_w, spec["shirt"], sx * (70 * s if pose == "proud" else 18 * s))
        d.ellipse((hand[0] - 38 * s, hand[1] - 38 * s, hand[0] + 38 * s, hand[1] + 38 * s), fill=spec["skin"])
    # torso
    d.rounded_rectangle((cx - tw / 2, sh, cx + tw / 2, hip + 10 * s), radius=int(70 * s), fill=spec["shirt"], outline=OUTLINE, width=int(6 * s))
    if spec["extra"] == "belt":
        d.rectangle((cx - tw / 2 + 6, hip - 50 * s, cx + tw / 2 - 6, hip - 22 * s), fill="#6b4a2b")
        d.rounded_rectangle((cx + tw * 0.12, hip - 60 * s, cx + tw * 0.38, hip + 20 * s), radius=int(8 * s), fill="#8a6440")
    if spec["extra"] == "notebook":
        d.rectangle((cx - tw * 0.38, sh + torso * 0.35, cx - tw * 0.08, sh + torso * 0.62), fill="#fdf6e3", outline=OUTLINE, width=int(4 * s))
    # neck + head
    d.rectangle((hcx - 40 * s, hcy + r * 0.6, hcx + 40 * s, sh + 20 * s), fill=spec["skin"])
    _hair(d, hcx, hcy, r, spec, back=True)
    d.ellipse((hcx - r, hcy - r, hcx + r, hcy + r), fill=spec["skin"], outline=OUTLINE, width=int(6 * s))
    for sx in (-1, 1):  # ears
        d.ellipse((hcx + sx * r * 0.98 - r * 0.16, hcy - r * 0.1, hcx + sx * r * 0.98 + r * 0.16, hcy + r * 0.28), fill=spec["skin"])
    _hair(d, hcx, hcy, r, spec, back=False)
    eyes, brows, mshape = FACE[pose]
    _eyes(d, hcx, hcy + r * 0.05, r, eyes, brows)
    if spec["extra"] == "glasses":
        for sx in (-1, 1):
            ex = hcx + sx * r * 0.38
            d.ellipse((ex - r * 0.25, hcy - r * 0.18, ex + r * 0.25, hcy + r * 0.28), outline=OUTLINE, width=int(r * 0.05))
        d.line((hcx - r * 0.13, hcy + r * 0.02, hcx + r * 0.13, hcy + r * 0.02), fill=OUTLINE, width=int(r * 0.05))
    for sx in (-1, 1):  # cheeks
        d.ellipse((hcx + sx * r * 0.55 - r * 0.13, hcy + r * 0.3, hcx + sx * r * 0.55 + r * 0.13, hcy + r * 0.44), fill=(200, 110, 100, 90))
    _mouth(d, hcx, hcy + r * 0.52, r, mshape, level)
    if pose == "singing":
        for i, (nx, ny) in enumerate(((0.75, -0.95), (1.05, -1.3))):
            x, y = hcx + r * nx * 1.3, hcy + r * ny
            d.ellipse((x - 22 * s, y, x + 22 * s, y + 34 * s), fill=OUTLINE)
            d.line((x + 20 * s, y + 16 * s, x + 20 * s, y - 60 * s), fill=OUTLINE, width=int(8 * s))
    _stamp(d)
    return img


def gecko(pose, level):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    green, belly = "#6b8e23", "#b6cf6d"
    cx, cy = W / 2, GROUND - 330
    lift = -60 if pose in ("excited", "happy") else 0
    cy += lift
    # tail
    pts = [(cx - 40 + 300 * math.cos(t) * (1 - t / 9), cy + 140 + 180 * math.sin(t) * (1 - t / 9)) for t in [i / 10 for i in range(0, 60)]]
    d.line(pts, fill=green, width=70, joint="curve")
    d.line(pts, fill=green, width=40)
    # legs
    for (lx, ly, fx) in ((-150, 90, -1), (150, 90, 1), (-120, 250, -1), (120, 250, 1)):
        foot = (cx + lx + fx * 70, cy + ly + (60 if ly > 100 else -30))
        d.line(((cx + lx * 0.5, cy + ly), (cx + lx, cy + ly + 20), foot), fill=green, width=44, joint="curve")
        for k in (-1, 0, 1):
            d.ellipse((foot[0] + k * 26 - 18, foot[1] - 18 + abs(k) * 6, foot[0] + k * 26 + 18, foot[1] + 18 + abs(k) * 6), fill=green)
    # body
    d.ellipse((cx - 180, cy - 20, cx + 180, cy + 320), fill=green, outline=OUTLINE, width=6)
    d.ellipse((cx - 100, cy + 40, cx + 100, cy + 280), fill=belly)
    for sp in ((-80, 60), (70, 110), (-40, 200), (90, 230)):
        d.ellipse((cx + sp[0] - 18, cy + sp[1] - 12, cx + sp[0] + 18, cy + sp[1] + 12), fill="#4f6b16")
    # head
    hr = 170
    hcx, hcy = cx, cy - 150
    if pose == "curious":
        hcx += 25
    d.ellipse((hcx - hr * 1.2, hcy - hr, hcx + hr * 1.2, hcy + hr * 0.9), fill=green, outline=OUTLINE, width=6)
    eyes, brows, mshape = FACE[pose]
    big = eyes != "arc" and eyes != "closed"
    for sx in (-1, 1):
        ex, ey = hcx + sx * hr * 0.62, hcy - hr * 0.55
        d.ellipse((ex - hr * 0.42, ey - hr * 0.42, ex + hr * 0.42, ey + hr * 0.42), fill=green, outline=OUTLINE, width=6)
        if big:
            d.ellipse((ex - hr * 0.3, ey - hr * 0.3, ex + hr * 0.3, ey + hr * 0.3), fill="#f4e04d")
            pr = hr * (0.16 if eyes == "big" else 0.11)
            d.ellipse((ex - pr * 0.45, ey - pr * 1.6, ex + pr * 0.45, ey + pr * 1.6), fill=OUTLINE)
        else:
            d.arc((ex - hr * 0.26, ey - hr * 0.15, ex + hr * 0.26, ey + hr * 0.3), 200, 340, fill=OUTLINE, width=12)
        by = ey - hr * (0.5 + 0.12 * brows)
        d.line((ex - hr * 0.3, by + sx * brows * 10, ex + hr * 0.3, by - sx * brows * 10), fill=OUTLINE, width=12)
    _mouth(d, hcx, hcy + hr * 0.3, hr * 1.3, "grin" if mshape in ("smile", "grin") else mshape, level)
    if pose == "proud":  # a little "ahem" chest-out
        d.arc((cx - 60, cy - 10, cx + 60, cy + 60), 200, 340, fill=OUTLINE, width=8)
    _stamp(d)
    return img


def _stamp(d):
    d.text((W - 24, H - 18), "TEST", font=_font(34), fill=(120, 120, 120, 170), anchor="rd")


def build(names=None):
    """Writes every pose × mouth level for each character to assets/test-cast/."""
    out = []
    for name in (names or list(SPECS) + ["Mjusi"]):
        folder = TEST_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        for pose in POSES:
            for level in (0, 1, 2):
                img = gecko(pose, level) if name == "Mjusi" else kid(name, pose, level)
                suffix = "" if level == 0 else f".mouth{level}"
                img.save(folder / f"{pose}{suffix}.png")
        out.append(name)
    return out
