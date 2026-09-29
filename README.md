# edu-video-pipeline

A **human-in-the-loop** pipeline for short educational videos for children
(built for the "Jua Crew" pilot: ages 5–8, recurring African cast).

```
new → script (AI draft) → REVIEW + APPROVE (people) → produce (voice · visuals · captions · video) → upload (private)
```

AI does the drafting and the grunt work. People own the facts, the culture and the final say:

- **Production refuses to run until a named person approves the script.** If `script.json`
  changes after approval, it refuses again.
- Approval needs every factual/cultural claim to have a **real source** and a named verifier,
  an educator named, a cultural consultant named for any culture-specific claim, and a
  child-safety checklist ticked.
- The AI is told never to invent sources, proverbs, history or African-language words.
- Uploads are **private** (or unlisted), **Made for Kids**, with the AI-disclosure flag set
  when needed. You watch the video and publish it yourself in YouTube Studio.
- Mock (offline test) episodes can never be uploaded.

This is deliberate: YouTube demonetises templated, mass-produced AI content, and its kids
quality principles penalise low-effort videos. The value of the channel is the people and
characters behind it.

## Setup

```bash
cd ~/Desktop/programming/edu-video-pipeline
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # already done
cp .env.example .env        # add GEMINI_API_KEY (free) and ELEVENLABS_API_KEY
```

- **Cast voices:** put each character's ElevenLabs `voice_id` in `config/characters.yaml`.
  Use your voice actors (or clones of their voices made with their **written consent**).
- **Character art:** transparent PNG renders from your 2D rig go in
  `assets/characters/<Name>/<pose>.png` (`default.png` is the fallback). Until then, scenes
  render as placeholder cards saying what the artist needs to draw.
- **Backgrounds:** `assets/backgrounds/<name>.png`, matched to each scene's `background`.
  Or pass `--ai-backgrounds` to generate plates with an image model (no people or text).
- **Full custom frames:** drop `episodes/<slug>/art/scene_NN.png` to override any scene.
- **Music / intro / outro:** set paths in `config/channel.yaml`. Use human-composed or
  properly licensed music. If you use AI music, upload with `--ai-music` (YouTube asks you
  to disclose it).
- **YouTube:** create an OAuth client ("Desktop app") in Google Cloud Console with the
  YouTube Data API v3 enabled, save it as `secrets/client_secret.json`. The first upload opens
  a browser to sign in. Until Google audits your API project, API uploads stay private
  anyway, which suits this workflow.

## Making an episode

```bash
./edupipe.sh new "Why do shadows move?" \
  --objective "After watching, a child can explain why shadows are long in the morning and short at midday."
# optional: add verified facts/sources to episodes/<slug>/brief.yaml under `sources:`

./edupipe.sh script <slug>          # AI draft -> script.json, script.md, review.yaml
# read script.md; edit script.json freely (it's the source of truth)
# fill review.yaml: a source + verifier for every claim, reviewers, checklist
./edupipe.sh review <slug>          # lists what's still missing
./edupipe.sh approve <slug> --by "Your Name"

./edupipe.sh produce <slug>         # voices, frames, captions, final.mp4 + captions.srt
# WATCH final.mp4
./edupipe.sh upload <slug> --dry-run   # check title/description/flags
./edupipe.sh upload <slug>             # private upload; publish in YouTube Studio
./edupipe.sh status
```

## Previewing

```bash
./edupipe.sh preview            # opens http://127.0.0.1:8765
./edupipe.sh play <slug>        # final.mp4 in ffplay (if installed) or your default player
./edupipe.sh play <slug> --scene 3   # just one line of dialogue
```

The preview site lists every episode with its progress (script → approved → voiced →
video → uploaded), and for the selected one shows:
- the video with captions (seekable)
- what the review still needs, or who approved it and when
- each claim and whether it has a verified source
- every scene: frame, speaker, line, the artist's note, and that line's audio
- the exact next command to run

It refreshes by itself as you work, without interrupting a playing video. It is read-only
and only reachable from this computer: approving stays a deliberate step on the command
line. (Install `ffplay` with `sudo apt install ffmpeg` if you want `play` to use it.)

Changing one line and re-running `produce` only re-voices the lines that changed.

### Test everything offline (no API keys)

```bash
./edupipe.sh new "Why do shadows move?" --slug test
./edupipe.sh script test --mock
./edupipe.sh approve test --by "Me" --mock-ok     # test-only approval
./edupipe.sh produce test --mock                  # silent voices, placeholder art
```

## Layout

```
config/channel.yaml      formats (short 1080x1920 / episode 1920x1080), fonts, models, YouTube settings
config/characters.yaml   the cast: roles, voice IDs, voice settings, placeholder colours
prompts/script_system.md the writer's brief: structure, age rules, hard rules, JSON shape
edupipe/                 script · review · voice · visuals · captions · assemble · upload · cli
assets/                  characters/, backgrounds/, music/, brand/
episodes/<slug>/         everything for one episode (git-ignored)
secrets/                 YouTube OAuth files (git-ignored)
```

## Notes

- Scripts use Gemini (`gemini-3.8-flash`, free tier) by default, via its OpenAI-compatible
  endpoint. Set `llm.provider: openai` in config/channel.yaml to use OpenAI instead.
  Note: on Gemini's free tier Google may use prompts to improve its products; the scripts
  contain no personal data, but switch to a paid tier if that matters to you.
  Voices use ElevenLabs `eleven_multilingual_v2`.
- Caption timing is spread across each line's audio in proportion to its length. It's good
  enough for short lines; check `captions.srt` before uploading it as a sidecar.
- A 30-second Short takes about 3 minutes to render on this laptop.
# african_edutainment
