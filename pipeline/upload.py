"""
Stage 8: Upload.

Resumable upload to YouTube via the Data API v3.

Sets status.containsSyntheticMedia per config.CONTAINS_SYNTHETIC_MEDIA
(confirmed current as of the YouTube Data API docs: added 2024-10-30, still
listed under Videos.status). Defaults to False — see the comment above
config.CONTAINS_SYNTHETIC_MEDIA for why this channel's format doesn't
trigger YouTube's disclosure requirement by default.
"""
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
            "containsSyntheticMedia": config.CONTAINS_SYNTHETIC_MEDIA,
        },
    }

    return _do_resumable_upload(youtube, video_path, body)


def _build_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _do_resumable_upload(youtube, video_path: Path, body: dict) -> str:
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    return response["id"]


if __name__ == "__main__":
    print("Do NOT run this standalone until UPLOAD_VISIBILITY=private is confirmed in .env.")
