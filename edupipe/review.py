"""Stage 2: the human gate. Nothing is voiced, animated or uploaded until this passes."""
from datetime import datetime, timezone

from .project import PipelineError, load_yaml, sha256
from .script import validate


def status(ep):
    rv = load_yaml(ep.review)
    missing = []
    for c in rv.get("claims", []):
        if not (c.get("verified") and str(c.get("source", "")).strip() and str(c.get("verified_by", "")).strip()):
            missing.append(f"claim {c['id']} needs a source, verified_by and verified: true — \"{c['claim']}\"")
        if c.get("culture") and not rv.get("reviewers", {}).get("cultural_consultant"):
            missing.append(f"claim {c['id']} is about {c['culture']} culture: add reviewers.cultural_consultant")
    for item, ok in rv.get("checklist", {}).items():
        if ok is not True:
            missing.append(f"checklist: {item.replace('_', ' ')}")
    if not rv.get("reviewers", {}).get("educator"):
        missing.append("reviewers.educator is empty")
    return missing


def approve(ep, by):
    if not by.strip():
        raise PipelineError("Give your name: --by \"Your Name\"")
    if ep.state().get("script_mock"):
        raise PipelineError("This is a MOCK script. Use `approve --mock-ok` only for pipeline testing.")
    problems = validate(ep.load_script()) + status(ep)
    if problems:
        raise PipelineError("Not ready to approve:\n  - " + "\n  - ".join(problems))
    return _lock(ep, by)


def approve_mock(ep, by):
    """Testing only: lets a mock script through so voice/visuals/assembly can be exercised."""
    if not ep.state().get("script_mock"):
        raise PipelineError("--mock-ok only works on mock scripts.")
    return _lock(ep, f"{by} (MOCK — testing only)")


def _lock(ep, by):
    return ep.save_state(
        approved_hash=sha256(ep.script_json),
        approved_by=by,
        approved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
