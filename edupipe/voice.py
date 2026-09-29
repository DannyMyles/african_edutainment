"""Stage 3: one voice file per scene, each speaker in their own cast voice."""
import hashlib
import os
import struct
import wave

import requests

from .project import PipelineError, channel, characters

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def _key(text, voice_id, model):
    return hashlib.sha1(f"{voice_id}|{model}|{text}".encode()).hexdigest()[:12]


def _mock_audio(path, text, wps=2.6, rate=22050):
    """Silent WAV sized to the line, so timing/captions/assembly can be tested offline."""
    seconds = max(1.2, len(text.split()) / wps)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(seconds * rate))


def _eleven(path, text, voice, cfg):
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise PipelineError("ELEVENLABS_API_KEY is not set (see .env.example), or run with --mock.")
    resp = requests.post(
        ELEVEN_URL.format(voice_id=voice["voice_id"]),
        params={"output_format": cfg["voice"]["output_format"]},
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        json={"text": text, "model_id": cfg["voice"]["model"], "voice_settings": voice.get("voice_settings", {})},
        timeout=120,
    )
    if resp.status_code != 200:
        raise PipelineError(f"ElevenLabs error {resp.status_code}: {resp.text[:300]}")
    path.write_bytes(resp.content)


def run(ep, mock=False):
    ep.require_approved()
    cfg, cast = channel(), characters()
    script = ep.load_script()
    ep.audio_dir.mkdir(exist_ok=True)
    cache = ep.state().get("voice_cache", {})
    files = []
    for i, sc in enumerate(script["scenes"], 1):
        voice = cast[sc["speaker"]]
        if not mock and not voice.get("voice_id"):
            raise PipelineError(f"{sc['speaker']} has no voice_id in config/characters.yaml (or use --mock).")
        ext = "wav" if mock else "mp3"
        path = ep.audio_dir / f"scene_{i:02d}.{ext}"
        key = _key(sc["narration"], "mock" if mock else voice["voice_id"], cfg["voice"]["model"])
        if path.exists() and cache.get(path.name) == key:
            files.append(path)
            continue  # unchanged line: don't pay to regenerate it
        for old in ep.audio_dir.glob(f"scene_{i:02d}.*"):
            old.unlink()
        if mock:
            _mock_audio(path, sc["narration"])
        else:
            _eleven(path, sc["narration"], voice, cfg)
        cache[path.name] = key
        files.append(path)
        print(f"  voiced scene {i:02d} ({sc['speaker']})")
    ep.save_state(voice_cache=cache, voice_mock=mock)
    return files
