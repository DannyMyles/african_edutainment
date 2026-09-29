"""Stage 3: one voice file per scene, each speaker in their own cast voice."""
import hashlib
import os
import struct
import wave

import requests

from .project import PipelineError, channel, characters

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
GEMINI_TTS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


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


def _gemini(path, text, voice, cfg):
    """Free-tier Gemini TTS. Returns a WAV (24 kHz mono)."""
    import base64
    import time

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise PipelineError("GEMINI_API_KEY is not set (see .env.example), or run with --mock.")
    content = {"type": "text", "text": text}
    if voice.get("gemini_style"):
        content["annotations"] = [{"type": "speech_metadata", "style": voice["gemini_style"]}]
    body = {
        "model": cfg["voice"]["gemini_model"],
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice.get("gemini_voice", "Kore")}]},
    }
    for attempt in range(4):
        resp = requests.post(GEMINI_TTS_URL, headers={"x-goog-api-key": api_key}, json=body, timeout=120)
        if resp.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(5 * (attempt + 1))  # free tier gets busy: back off and retry
            continue
        break
    if resp.status_code != 200:
        raise PipelineError(f"Gemini TTS error {resp.status_code}: {resp.text[:300]}")
    try:
        audio = next(c for step in resp.json()["steps"] for c in step.get("content", []) if c.get("type") == "audio")
    except (StopIteration, KeyError, ValueError):
        raise PipelineError("Gemini TTS returned no audio. Try again.")
    path.write_bytes(base64.b64decode(audio["data"]))


def run(ep, mock=False):
    ep.require_approved()
    cfg, cast = channel(), characters()
    provider = "mock" if mock else cfg["voice"].get("provider", "elevenlabs")
    script = ep.load_script()
    ep.audio_dir.mkdir(exist_ok=True)
    cache = ep.state().get("voice_cache", {})
    files = []
    for i, sc in enumerate(script["scenes"], 1):
        voice = cast[sc["speaker"]]
        if provider == "elevenlabs" and not voice.get("voice_id"):
            raise PipelineError(f"{sc['speaker']} has no voice_id in config/characters.yaml (or use --mock).")
        ext = "mp3" if provider == "elevenlabs" else "wav"
        path = ep.audio_dir / f"scene_{i:02d}.{ext}"
        who = {"mock": "mock", "elevenlabs": voice.get("voice_id"),
               "gemini": f"{voice.get('gemini_voice')}|{voice.get('gemini_style')}"}[provider]
        model = cfg["voice"]["gemini_model"] if provider == "gemini" else cfg["voice"]["model"]
        key = _key(sc["narration"], who, model)
        if path.exists() and cache.get(path.name) == key:
            files.append(path)
            continue  # unchanged line: don't pay to regenerate it
        for old in ep.audio_dir.glob(f"scene_{i:02d}.*"):
            old.unlink()
        if provider == "mock":
            _mock_audio(path, sc["narration"])
        elif provider == "gemini":
            _gemini(path, sc["narration"], voice, cfg)
        else:
            _eleven(path, sc["narration"], voice, cfg)
        cache[path.name] = key
        files.append(path)
        print(f"  voiced scene {i:02d} ({sc['speaker']})")
    ep.save_state(voice_cache=cache, voice_mock=mock)
    return files
