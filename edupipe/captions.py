"""Burned-in captions + an .srt sidecar. Kids' content should always be captioned."""
import textwrap

from PIL import Image, ImageDraw, ImageFont


def chunks(text, max_words=6):
    """Split into the fewest pieces of <= max_words, balanced so no piece is a lone word."""
    words = text.split()
    if not words:
        return []
    n = -(-len(words) // max_words)
    base, extra = divmod(len(words), n)
    out, i = [], 0
    for k in range(n):
        size = base + (1 if k < extra else 0)
        out.append(" ".join(words[i:i + size]))
        i += size
    return out


def timeline(scene_texts, scene_durations, speak_fraction):
    """[(start, end, text)] for the whole video. Each scene's chunks share the spoken part of
    the scene in proportion to their length (good enough without word-level timestamps)."""
    out, t0 = [], 0.0
    for text, dur, frac in zip(scene_texts, scene_durations, speak_fraction):
        parts = chunks(text)
        spoken = dur * frac
        total = sum(len(p) for p in parts) or 1
        t = t0
        for p in parts:
            d = spoken * len(p) / total
            out.append((t, t + d, p))
            t += d
        t0 += dur
    return out


def _stamp(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path, cues, offset=0.0):
    lines = []
    for n, (a, b, text) in enumerate(cues, 1):
        lines += [str(n), f"{_stamp(a + offset)} --> {_stamp(b + offset)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def render(text, width, font_path, font_size):
    """A caption image: bold white text on a rounded dark pill, sized to the text."""
    font = ImageFont.truetype(font_path, font_size)
    wrapped = textwrap.fill(text, width=22 if width < 1300 else 40)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = (round(v) for v in probe.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=8))
    pad_x, pad_y = int(font_size * 0.6), int(font_size * 0.35)
    img = Image.new("RGBA", (r - l + 2 * pad_x, b - t + 2 * pad_y), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=int(font_size * 0.45), fill=(10, 12, 14, 200))
    d.multiline_text((pad_x - l, pad_y - t), wrapped, font=font, fill="white", align="center", spacing=8)
    return img
