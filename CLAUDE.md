# edu-video-pipeline — context for Claude

Human-in-the-loop pipeline for short educational videos for an original African
children's YouTube channel ("Jua Crew", working title; ages 5–8). See README.md for usage.

## Background decisions (from the original planning conversation)
- The goal is a sustainable, trustworthy kids' brand, not maximum output. YouTube's
  "inauthentic content" monetisation policy (2025, tightened July 2026) and kids quality
  principles penalise templated, mass-produced AI content, so people stay in charge:
  AI drafts and does grunt work; people own facts, culture and the final say.
- **Never remove or weaken the approval gate.** Production (`voice`, `visuals`,
  `assemble`, `upload`) must refuse unless a named person approved the exact current
  `script.json` (sha256 stored in state.json). Mock episodes can never be uploaded.
- The AI must never be the source of cultural/historical facts, proverbs or
  African-language words: claims go in `claims`, sources are filled in by people.
  Name cultures precisely ("Kikuyu tradition"), never "in Africa".
- Uploads are private/unlisted + Made for Kids; the human publishes in YouTube Studio.
  Set `containsSyntheticMedia` for realistic AI content or AI-generated music.
- Cast (config/characters.yaml): Zawadi, Kito, Ada, Tesfa, Cucu Njeri, Mjusi (gecko who
  voices misconceptions), Narrator. Voices should be real actors or consented clones.
- Visual approach: 2D rigged character renders for dialogue + optional AI backgrounds;
  placeholder cards until art exists.

## Tech
- Python 3.12 venv in `.venv`; run via `./edupipe.sh <command>`.
- Gemini `gemini-3.8-flash` (default, free tier, via OpenAI-compatible endpoint) or OpenAI
  for scripts (`llm.provider`); OpenAI images for optional backgrounds, voices via Gemini TTS `gemini-3.8-flash-tts` (default, free; `voice.provider`) or
  ElevenLabs `eleven_multilingual_v2`,
  MoviePy 2 (assembly; no system ffmpeg — uses imageio-ffmpeg), YouTube Data API v3
  (scope `youtube.upload` only).
- `edupipe preview` = local read-only site (edupipe/preview.py + static/index.html).
- Test offline with `--mock` (script/produce) and `approve --mock-ok`.
- Status: pipeline tested end to end offline; real API calls not yet tested (no keys).
