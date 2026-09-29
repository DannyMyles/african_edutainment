"""Stage 5: frames + voices + captions (+ intro/outro/music) -> final.mp4, with MoviePy 2."""
import tempfile
from pathlib import Path

import numpy as np
from moviepy import (AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, VideoClip, VideoFileClip,
                     afx, concatenate_videoclips)
from PIL import Image

from . import captions
from .project import ROOT, PipelineError, channel


def _audio_for(ep, i):
    found = sorted(ep.audio_dir.glob(f"scene_{i:02d}.*"))
    if not found:
        raise PipelineError(f"No audio for scene {i}. Run: edupipe voice {ep.slug}")
    return found[0]


def mouth_levels(audio, fps, speech_seconds):
    """0/1/2 (closed/half/open) for every video frame, from the voice's loudness."""
    rate = 16000
    samples = audio.to_soundarray(fps=rate)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    per = int(rate / fps)
    n = int(np.ceil(speech_seconds * fps))
    rms = np.array([np.sqrt(np.mean(samples[k * per:(k + 1) * per] ** 2)) if k * per < len(samples) else 0.0
                    for k in range(n)])
    peak = np.percentile(rms[rms > 0], 95) if np.any(rms > 0) else 1.0
    speaking = rms / (peak or 1.0) >= 0.12
    # Among speaking frames, only the loudest ~40% open fully: talking reads as quick
    # open/half alternation, not a mouth held wide open.
    cut = np.percentile(rms[speaking], 60) if np.any(speaking) else 0
    levels = np.where(~speaking, 0, np.where(rms >= cut, 2, 1))
    # smooth: hold each shape for at least 2 frames so the mouth doesn't flicker
    for k in range(1, len(levels) - 1):
        if levels[k] != levels[k - 1] and levels[k] != levels[k + 1]:
            levels[k] = levels[k - 1]
    return levels


def _kenburns(frame_paths, size, dur, zoom, levels=None, fps=30):
    """A slow push-in (crop a shrinking centred window, scale back up) — much faster than
    MoviePy's per-frame resize. With `levels`, picks the mouth frame for each video frame."""
    imgs = [Image.open(p).convert("RGB").resize(size, Image.LANCZOS) for p in frame_paths]
    if not zoom and levels is None:
        return ImageClip(np.asarray(imgs[0])).with_duration(dur)
    w, h = size

    def frame(t):
        img = imgs[0]
        if levels is not None:
            k = int(t * fps)
            img = imgs[levels[k]] if k < len(levels) else imgs[0]
        if not zoom:
            return np.asarray(img)
        s = 1 + zoom * min(t, dur) / dur
        cw, ch = w / s, h / s
        box = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
        return np.asarray(img.resize(size, Image.BILINEAR, box=box))

    return VideoClip(frame, duration=dur)


def run(ep):
    ep.require_approved()
    cfg = channel()
    vcfg = cfg["video"]
    fmt = ep.fmt()
    size = (fmt["width"], fmt["height"])
    scenes = ep.load_script()["scenes"]
    frames = [ep.frames_dir / f"scene_{i:02d}.png" for i in range(1, len(scenes) + 1)]
    if not all(f.exists() for f in frames):
        raise PipelineError(f"Missing frames. Run: edupipe visuals {ep.slug}")

    gap = vcfg["scene_gap_seconds"]
    audios = [AudioFileClip(str(_audio_for(ep, i))) for i in range(1, len(scenes) + 1)]
    durations = [a.duration + gap for a in audios]
    total = sum(durations)
    if total > fmt["max_seconds"] + 0.5:
        print(f"  ! {total:.1f}s is longer than the {fmt['max_seconds']}s target for this format")

    font_size = int(vcfg["caption_font_size"] * size[0] / 1080)
    cues = captions.timeline([s["narration"] for s in scenes], durations, [a.duration / d for a, d in zip(audios, durations)])
    tmp = Path(tempfile.mkdtemp(prefix="caps_", dir=ep.dir))

    clips, t0 = [], 0.0
    for i, (frame, audio, dur) in enumerate(zip(frames, audios, durations)):
        mouths = [frame.with_name(f"{frame.stem}.mouth{n}.png") for n in (1, 2)]
        if all(m.exists() for m in mouths):
            levels = mouth_levels(audio, vcfg["fps"], audio.duration)
            base = _kenburns([frame, *mouths], size, dur, vcfg["ken_burns_zoom"], levels, vcfg["fps"])
        else:
            base = _kenburns([frame], size, dur, vcfg["ken_burns_zoom"])
        layers = [base]
        for a, b, text in cues:
            if t0 <= a < t0 + dur - 1e-6:
                cap_path = tmp / f"cap_{len(list(tmp.iterdir())):03d}.png"
                img = captions.render(text, size[0], vcfg["font"], font_size)
                img.save(cap_path)
                y = int(size[1] * (0.74 if size[1] > size[0] else 0.82))
                layers.append(ImageClip(str(cap_path)).with_start(a - t0).with_duration(b - a)
                              .with_position(("center", y)))
        clips.append(CompositeVideoClip(layers, size=size).with_duration(dur).with_audio(audio))
        t0 += dur

    video = concatenate_videoclips(clips)  # all scenes share one size: no compositing needed

    def _brand(key):
        path = vcfg.get(key)
        return VideoFileClip(str(ROOT / path)).resized(new_size=size) if path else None

    intro, outro = _brand("intro_clip"), _brand("outro_clip")

    if vcfg.get("music"):
        bed = AudioFileClip(str(ROOT / vcfg["music"])).with_effects(
            [afx.AudioLoop(duration=video.duration), afx.MultiplyVolume(vcfg["music_volume"])])
        video = video.with_audio(CompositeAudioClip([video.audio, bed]))

    offset = intro.duration if intro else 0.0
    if intro or outro:
        video = concatenate_videoclips([c for c in (intro, video, outro) if c], method="compose")

    captions.write_srt(ep.srt, cues, offset=offset)
    # Render to a temp name and swap it in at the end, so nothing (e.g. the preview site)
    # ever sees a half-written final.mp4.
    partial = ep.final.with_name("final.partial.mp4")
    video.write_videofile(str(partial), fps=vcfg["fps"], codec="libx264", audio_codec="aac",
                          preset="medium", threads=4, logger=None)
    partial.replace(ep.final)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    ep.save_state(final_seconds=round(video.duration, 1), uploaded_video_id=None)
    return video.duration
