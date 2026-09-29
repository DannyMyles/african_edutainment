"""Paths, config and per-episode state.

Each episode lives in episodes/<slug>/:
  brief.yaml      topic, age, format, objective (written by `new`)
  script.json     structured draft from `script` (human-editable)
  script.md       readable version for reviewers
  review.yaml     claim sources + checklist; `approve` locks it
  audio/          one voice file per scene
  frames/         one image per scene
  captions.srt    sidecar captions (upload to YouTube by hand if you like)
  final.mp4       the assembled video
  state.json      pipeline bookkeeping (approval hash, upload id, ...)
"""
import hashlib
import json
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
ASSETS = ROOT / "assets"
SECRETS = ROOT / "secrets"

load_dotenv(ROOT / ".env")


class PipelineError(Exception):
    """A problem the user needs to fix (shown without a traceback)."""


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def channel():
    cfg = load_yaml(ROOT / "config" / "channel.yaml")
    cfg["llm"]["script_model"] = os.environ.get("SCRIPT_MODEL", cfg["llm"]["script_model"])
    cfg["llm"]["image_model"] = os.environ.get("IMAGE_MODEL", cfg["llm"]["image_model"])
    return cfg


def characters():
    return load_yaml(ROOT / "config" / "characters.yaml")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "episode"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Episode:
    def __init__(self, slug):
        self.slug = slug
        self.dir = EPISODES / slug
        if not self.dir.is_dir():
            raise PipelineError(f"No episode '{slug}'. Create it with: edupipe new \"<topic>\"")

    # --- paths ---------------------------------------------------------------
    brief = property(lambda s: s.dir / "brief.yaml")
    script_json = property(lambda s: s.dir / "script.json")
    script_md = property(lambda s: s.dir / "script.md")
    review = property(lambda s: s.dir / "review.yaml")
    audio_dir = property(lambda s: s.dir / "audio")
    frames_dir = property(lambda s: s.dir / "frames")
    art_dir = property(lambda s: s.dir / "art")
    srt = property(lambda s: s.dir / "captions.srt")
    final = property(lambda s: s.dir / "final.mp4")
    state_path = property(lambda s: s.dir / "state.json")

    # --- state ---------------------------------------------------------------
    def state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {}

    def save_state(self, **changes):
        st = self.state()
        st.update(changes)
        self.state_path.write_text(json.dumps(st, indent=2))
        return st

    def load_brief(self):
        return load_yaml(self.brief)

    def load_script(self):
        if not self.script_json.exists():
            raise PipelineError(f"No script yet. Run: edupipe script {self.slug}")
        return json.loads(self.script_json.read_text(encoding="utf-8"))

    def fmt(self):
        return channel()["formats"][self.load_brief().get("format", "short")]

    # --- the human gate ----------------------------------------------------------
    def require_approved(self):
        """Production stages refuse to run on an unapproved or since-edited script."""
        st = self.state()
        if not st.get("approved_hash"):
            raise PipelineError(
                f"'{self.slug}' is not approved. Review {self.review.relative_to(ROOT)}, "
                f"then run: edupipe approve {self.slug} --by \"Your Name\""
            )
        if sha256(self.script_json) != st["approved_hash"]:
            raise PipelineError(
                "script.json changed after approval. Re-review it and run `edupipe approve` again."
            )
