"""edupipe — draft → HUMAN REVIEW → voice → visuals → assemble → private upload.

  edupipe new "Why do shadows move?" --objective "..." [--format short|episode] [--age 5-8]
  edupipe script  <slug> [--mock]
  edupipe review  <slug>                       # what's still missing before approval
  edupipe approve <slug> --by "Name"           # locks the script; later stages check it
  edupipe produce <slug> [--mock] [--ai-backgrounds]   # voice + visuals + assemble
  edupipe upload  <slug> [--ai-music] [--dry-run]
  edupipe status  [<slug>]
"""
import argparse
import json
import sys
from datetime import date

import yaml

from . import assemble, review, script, upload, visuals, voice
from .project import EPISODES, Episode, PipelineError, channel, slugify


def cmd_new(a):
    slug = a.slug or f"{date.today():%Y%m%d}-{slugify(a.topic)}"
    d = EPISODES / slug
    if d.exists():
        raise PipelineError(f"episodes/{slug} already exists")
    d.mkdir(parents=True)
    (d / "art").mkdir()
    brief = {
        "topic": a.topic,
        "objective": a.objective or "",
        "age": a.age or channel()["default_age"],
        "format": a.format,
        "notes": "",
        "sources": [],            # verified facts/sources the writer may use
        "educator": "",
        "cultural_consultant": "",
        "tags": [],
    }
    (d / "brief.yaml").write_text(yaml.safe_dump(brief, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Created episodes/{slug}/brief.yaml — add verified sources there, then: edupipe script {slug}")


def cmd_script(a):
    ep = Episode(a.slug)
    s = script.run(ep, mock=a.mock)
    print(f"Draft: {len(s['scenes'])} scenes, ~{script.estimate_seconds(s):.0f}s, {len(s['claims'])} claims to verify.")
    print(f"Read   episodes/{a.slug}/script.md  (edit script.json to change anything)")
    print(f"Fill   episodes/{a.slug}/review.yaml, then: edupipe approve {a.slug} --by \"Your Name\"")


def cmd_review(a):
    missing = review.status(Episode(a.slug))
    if missing:
        print("Still needed before approval:")
        for m in missing:
            print("  -", m)
    else:
        print("Everything is filled in. Run: edupipe approve", a.slug, '--by "Your Name"')


def cmd_approve(a):
    ep = Episode(a.slug)
    st = review.approve_mock(ep, a.by) if a.mock_ok else review.approve(ep, a.by)
    print(f"Approved by {st['approved_by']} at {st['approved_at']}. Next: edupipe produce {a.slug}")


def cmd_produce(a):
    ep = Episode(a.slug)
    print("1/3 voice")
    voice.run(ep, mock=a.mock)
    print("2/3 visuals")
    kinds = visuals.run(ep, ai_backgrounds=a.ai_backgrounds)
    print("   ", ", ".join(f"{n} {k}" for k, n in kinds.items()))
    if kinds.get("placeholder"):
        print("    (placeholder cards show what art is needed — add renders to assets/characters/)")
    print("3/3 assemble")
    secs = assemble.run(ep)
    print(f"Done: episodes/{a.slug}/final.mp4 ({secs:.1f}s) + captions.srt. Watch it before uploading.")


def cmd_upload(a):
    ep = Episode(a.slug)
    res = upload.run(ep, ai_music=a.ai_music, realistic=a.realistic, dry_run=a.dry_run)
    if a.dry_run:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"Uploaded as {channel()['youtube']['privacy']}: https://youtu.be/{res['id']}  — publish it in YouTube Studio.")


def cmd_status(a):
    slugs = [a.slug] if a.slug else sorted(p.name for p in EPISODES.iterdir() if p.is_dir())
    for slug in slugs:
        ep = Episode(slug)
        st = ep.state()
        steps = [
            ("script", ep.script_json.exists()),
            ("approved", bool(st.get("approved_hash"))),
            ("voiced", ep.audio_dir.exists() and any(ep.audio_dir.iterdir())),
            ("video", ep.final.exists()),
            ("uploaded", bool(st.get("uploaded_video_id"))),
        ]
        flags = " ".join(("✓ " if ok else "· ") + name for name, ok in steps)
        mock = "  [MOCK]" if st.get("script_mock") or st.get("voice_mock") else ""
        print(f"{slug:48} {flags}{mock}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="edupipe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="start an episode brief")
    n.add_argument("topic")
    n.add_argument("--objective", help='e.g. "After watching, a child can explain why shadows change."')
    n.add_argument("--format", choices=["short", "episode"], default="short")
    n.add_argument("--age")
    n.add_argument("--slug")
    n.set_defaults(fn=cmd_new)

    s = sub.add_parser("script", help="draft the script (AI)")
    s.add_argument("slug")
    s.add_argument("--mock", action="store_true", help="offline placeholder script, for testing")
    s.set_defaults(fn=cmd_script)

    r = sub.add_parser("review", help="show what the review still needs")
    r.add_argument("slug")
    r.set_defaults(fn=cmd_review)

    ap = sub.add_parser("approve", help="human sign-off (required before production)")
    ap.add_argument("slug")
    ap.add_argument("--by", required=True)
    ap.add_argument("--mock-ok", action="store_true", help="testing only: approve a mock script")
    ap.set_defaults(fn=cmd_approve)

    pr = sub.add_parser("produce", help="voice + visuals + assemble")
    pr.add_argument("slug")
    pr.add_argument("--mock", action="store_true", help="silent placeholder voices, for testing")
    pr.add_argument("--ai-backgrounds", action="store_true", help="generate background plates with an image model")
    pr.set_defaults(fn=cmd_produce)

    u = sub.add_parser("upload", help="upload to YouTube as private")
    u.add_argument("slug")
    u.add_argument("--ai-music", action="store_true", help="the music was AI-generated (YouTube asks you to disclose it)")
    u.add_argument("--realistic", action="store_true", help="contains realistic AI footage (disclosure required)")
    u.add_argument("--dry-run", action="store_true", help="print the metadata without uploading")
    u.set_defaults(fn=cmd_upload)

    st = sub.add_parser("status", help="where each episode is")
    st.add_argument("slug", nargs="?")
    st.set_defaults(fn=cmd_status)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except PipelineError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
