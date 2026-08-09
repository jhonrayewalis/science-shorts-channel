"""
Stage 8: Upload.

Resumable upload to YouTube via the Data API v3, with the altered/synthetic
content disclosure set on the video.

TODO (Claude Code):
  1. One-time setup: create OAuth credentials in Google Cloud Console
     (YouTube Data API v3 enabled), run a local consent flow ONCE to get a
     refresh token, then put client id/secret/refresh token in .env
     (locally) and GitHub Actions secrets (production).
  2. Implement `_build_youtube_client` using google-auth + the refresh token
     (no interactive login needed after the one-time setup).
  3. Confirm the exact API field for synthetic-content disclosure against
     the current YouTube Data API docs before shipping — this is a
     policy-relevant field and worth double-checking against the live docs
     rather than assuming the field name.
"""
from pathlib import Path

from pipeline import config


def upload_video(video_path: Path, metadata: dict) -> str:
    """
    Returns the uploaded video's ID.
    Respects config.UPLOAD_VISIBILITY ("private" during the approval-gate phase).
    """
    youtube = _build_youtube_client()

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata.get("category_id", "27"),
        },
        "status": {
            "privacyStatus": config.UPLOAD_VISIBILITY,
            "selfDeclaredMadeForKids": False,
            # TODO: confirm current field name for the synthetic/altered
            # content disclosure against the live YouTube Data API docs.
        },
    }

    return _do_resumable_upload(youtube, video_path, body)


def _build_youtube_client():
    raise NotImplementedError(
        "Build an authenticated googleapiclient client using config.YOUTUBE_* creds."
    )


def _do_resumable_upload(youtube, video_path: Path, body: dict) -> str:
    raise NotImplementedError("Use MediaFileUpload + youtube.videos().insert(...).execute()")


if __name__ == "__main__":
    print("Do NOT run this standalone until UPLOAD_VISIBILITY=private is confirmed in .env.")
