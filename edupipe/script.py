"""Stage 1: draft a structured script with an LLM (never the final word)."""
import json

import yaml

from .project import ROOT, PipelineError, channel, characters

BEATS = ["hook", "problem", "investigate", "concept", "adventure", "discovery", "recap", "question"]


def _system_prompt(brief):
    cfg = channel()
    fmt = cfg["formats"][brief["format"]]
    cast = "\n".join(f"- {name}: {c.get('role', '')}" for name, c in characters().items())
    template = (ROOT / "prompts" / "script_system.md").read_text(encoding="utf-8")
    return template.format(
        channel=cfg["channel_name"], age=brief["age"], cast=cast,
        format=brief["format"], seconds=fmt["max_seconds"],
    )


def _user_prompt(brief):
    lines = [f"Topic: {brief['topic']}"]
    if brief.get("objective"):
        lines.append(f"Learning objective (from the educator): {brief['objective']}")
    if brief.get("notes"):
        lines.append(f"Notes: {brief['notes']}")
    if brief.get("sources"):
        lines.append("Use ONLY these verified facts/sources; anything else must go in claims for checking:")
        lines += [f"- {s}" for s in brief["sources"]]
    return "\n".join(lines)


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _client():
    """Gemini is reached through its OpenAI-compatible endpoint, so one client does both."""
    import os

    from openai import OpenAI  # imported lazily so --mock works without keys

    llm = channel()["llm"]
    if llm["provider"] == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise PipelineError("GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey")
        return OpenAI(api_key=key, base_url=GEMINI_BASE_URL), llm["model"]
    if not os.environ.get("OPENAI_API_KEY"):
        raise PipelineError("OPENAI_API_KEY is not set (or set llm.provider: gemini in config/channel.yaml).")
    return OpenAI(), llm["model"]


def _parse_json(text):
    """JSON object from a reply, tolerating ```json fences some models add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise PipelineError("The model didn't return JSON. Try `edupipe script` again.")
    return json.loads(text[start:end + 1])


BUSY = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "high demand")


def _complete(client, model, messages):
    try:
        return client.chat.completions.create(
            model=model, messages=messages, temperature=0.8, response_format={"type": "json_object"})
    except Exception as err:  # some endpoints reject JSON mode: ask plainly instead
        if "response_format" in str(err):
            return client.chat.completions.create(model=model, messages=messages, temperature=0.8)
        raise


def _call_llm(brief):
    """Free tiers get busy: retry with backoff, then try the fallback models."""
    import time

    client, model = _client()
    llm = channel()["llm"]
    models = [model] + [m for m in (llm.get("fallback_models") or []) if m != model]
    messages = [
        {"role": "system", "content": _system_prompt(brief)},
        {"role": "user", "content": _user_prompt(brief)},
    ]
    last = None
    for m in models:
        for attempt in range(3):
            try:
                resp = _complete(client, m, messages)
                if m != model:
                    print(f"  (used fallback model {m})")
                return _parse_json(resp.choices[0].message.content)
            except PipelineError:
                raise
            except Exception as err:
                last = err
                if not any(k in str(err) for k in BUSY):
                    raise PipelineError(f"Script model error: {err}") from err
                wait = 5 * (attempt + 1)
                print(f"  {m} is busy, retrying in {wait}s…")
                time.sleep(wait)
    raise PipelineError(f"All script models are busy right now. Try again in a few minutes. ({last})")


def _mock(brief):
    """A fixed, obviously-placeholder script so the whole pipeline can be tested offline."""
    t = brief["topic"]
    return {
        "title": f"[MOCK] {t}",
        "learning_objective": brief.get("objective") or f"After watching, a child can explain one fact about {t}.",
        "age_range": brief["age"],
        "scenes": [
            {"beat": "hook", "speaker": "Kito", "pose": "surprised", "background": "courtyard",
             "narration": "Whoa! My shadow ran away from me!", "visual": "Kito jumps; his shadow is long and thin."},
            {"beat": "problem", "speaker": "Zawadi", "pose": "thinking", "background": "courtyard",
             "narration": "This morning it was long. Now it is short. What is going on?", "visual": "Two shadows side by side."},
            {"beat": "investigate", "speaker": "Mjusi", "pose": "proud", "background": "wall",
             "narration": "Easy! Shadows get tired and shrink after lunch.", "visual": "Mjusi the gecko, very sure of himself."},
            {"beat": "concept", "speaker": "Tesfa", "pose": "explaining", "background": "courtyard",
             "narration": "The Sun looks like it moves across the sky. When the Sun is high, your shadow is short.",
             "visual": "Arrow showing the Sun low, then high."},
            {"beat": "discovery", "speaker": "Kito", "pose": "happy", "background": "courtyard",
             "narration": "So my shadow didn't run away. The Sun moved higher!", "visual": "Kito points at the sky."},
            {"beat": "recap", "speaker": "Ada", "pose": "singing", "background": "courtyard",
             "narration": "Sun low, shadow long. Sun high, shadow small!", "visual": "The crew chants and claps."},
            {"beat": "question", "speaker": "Narrator", "pose": "default", "background": "sky",
             "narration": "With a grown-up, check your shadow in the morning and at lunchtime. Which one is longer?",
             "visual": "End card with the Jua Crew."},
        ],
        "claims": [
            {"id": "C1", "scene": 4, "claim": "When the Sun is high in the sky, shadows are shorter.", "culture": ""},
        ],
        "safety_notes": ["Mock script: replace before any real production."],
    }


def validate(script):
    problems = []
    cast = set(characters())
    for key in ("title", "learning_objective", "scenes", "claims"):
        if key not in script:
            problems.append(f"missing '{key}'")
    for i, sc in enumerate(script.get("scenes", []), 1):
        if sc.get("speaker") not in cast:
            problems.append(f"scene {i}: unknown speaker '{sc.get('speaker')}'")
        text = sc.get("narration", "")
        if not text.strip():
            problems.append(f"scene {i}: empty narration")
        if any(ch in text for ch in "[]{}*#"):
            problems.append(f"scene {i}: narration contains stage directions/markup")
        if sc.get("beat") not in BEATS:
            problems.append(f"scene {i}: unknown beat '{sc.get('beat')}'")
    return problems


def estimate_seconds(script, wps=2.5):
    words = sum(len(s["narration"].split()) for s in script["scenes"])
    return words / wps + 0.35 * len(script["scenes"])


def to_markdown(script, brief):
    out = [f"# {script['title']}", "",
           f"**Topic:** {brief['topic']}  ", f"**Age:** {script.get('age_range', brief['age'])}  ",
           f"**Learning objective:** {script['learning_objective']}  ",
           f"**Estimated length:** ~{estimate_seconds(script):.0f}s", "", "## Scenes", ""]
    for i, sc in enumerate(script["scenes"], 1):
        out += [f"### {i}. {sc['beat'].upper()} — {sc['speaker']} ({sc.get('pose', 'default')})",
                f"> {sc['narration']}", "", f"*Visual:* {sc.get('visual', '')}", ""]
    out += ["## Claims to verify", ""]
    for c in script.get("claims", []):
        culture = f" — culture: {c['culture']}" if c.get("culture") else ""
        out.append(f"- **{c['id']}** (scene {c.get('scene', '?')}): {c['claim']}{culture}")
    if script.get("safety_notes"):
        out += ["", "## Safety notes from the draft", ""] + [f"- {n}" for n in script["safety_notes"]]
    return "\n".join(out) + "\n"


def review_template(script):
    return {
        "approved_by": "",
        "reviewers": {"educator": "", "cultural_consultant": ""},
        "claims": [
            {"id": c["id"], "claim": c["claim"], "culture": c.get("culture", ""),
             "source": "", "verified_by": "", "verified": False}
            for c in script.get("claims", [])
        ],
        "checklist": {
            "learning_objective_is_clear_and_taught": False,
            "language_fits_the_age_group": False,
            "every_fact_has_a_real_source": False,
            "cultures_named_precisely_and_reviewed_or_na": False,
            "nothing_frightening_or_unsafe": False,
            "no_requests_for_personal_info_or_comments": False,
            "no_brands_or_buying": False,
        },
        "notes": "",
    }


def run(ep, mock=False):
    brief = ep.load_brief()
    script = _mock(brief) if mock else _call_llm(brief)
    problems = validate(script)
    ep.script_json.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    ep.script_md.write_text(to_markdown(script, brief), encoding="utf-8")
    ep.review.write_text(yaml.safe_dump(review_template(script), sort_keys=False, allow_unicode=True), encoding="utf-8")
    ep.save_state(approved_hash=None, approved_by=None, script_mock=mock)
    if problems:
        raise PipelineError("Draft saved, but fix these in script.json before review:\n  - " + "\n  - ".join(problems))
    return script
