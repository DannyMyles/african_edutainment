"""Stage 6: upload as PRIVATE (or unlisted), marked Made for Kids. You publish by hand.

Note: until Google audits your API project, YouTube keeps API uploads private anyway.
"""
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .project import SECRETS, PipelineError, channel

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret, token = SECRETS / "client_secret.json", SECRETS / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not secret.exists():
            raise PipelineError("Put your OAuth client file at secrets/client_secret.json (see README).")
        creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def metadata(ep, ai_music=False, realistic=False):
    cfg = channel()
    script, brief = ep.load_script(), ep.load_brief()
    question = next((s["narration"] for s in script["scenes"] if s["beat"] == "question"), "")
    reviewers = [n for n in (brief.get("educator"), brief.get("cultural_consultant")) if n]
    desc = [
        script["learning_objective"],
        "",
        f"Try this: {question}" if question else "",
        "",
        f"{cfg['channel_name']} is an original African children's show. Scripts are written and fact-checked "
        "by people; AI tools help with drafting and production.",
    ]
    if reviewers:
        desc.append("Reviewed by: " + ", ".join(reviewers))
    return {
        "snippet": {
            "title": script["title"][:100],
            "description": "\n".join(desc).strip(),
            "tags": cfg["youtube"]["default_tags"] + brief.get("tags", []),
            "categoryId": cfg["youtube"]["category_id"],
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": cfg["youtube"]["privacy"],
            "selfDeclaredMadeForKids": True,
            # YouTube's altered/synthetic disclosure: needed for realistic content and AI-generated
            # music; not for clearly animated content.
            "containsSyntheticMedia": bool(ai_music or realistic),
        },
    }


def run(ep, ai_music=False, realistic=False, dry_run=False):
    ep.require_approved()
    if ep.state().get("script_mock") or ep.state().get("voice_mock"):
        raise PipelineError("This episode uses a MOCK script or voices. Mock episodes are never uploaded.")
    if not ep.final.exists():
        raise PipelineError(f"No final.mp4. Run: edupipe assemble {ep.slug}")
    cfg = channel()
    if cfg["youtube"]["privacy"] not in ("private", "unlisted"):
        raise PipelineError("config youtube.privacy must be 'private' or 'unlisted'. Publish from YouTube Studio.")
    body = metadata(ep, ai_music, realistic)
    if dry_run:
        return body
    yt = _service()
    media = MediaFileUpload(str(ep.final), mimetype="video/mp4", chunksize=-1, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  uploaded {int(status.progress() * 100)}%")
    ep.save_state(uploaded_video_id=response["id"])
    return response
