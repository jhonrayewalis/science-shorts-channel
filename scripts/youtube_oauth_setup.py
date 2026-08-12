"""
One-time setup: run a local OAuth consent flow to mint a YouTube refresh
token, so upload.py can mint fresh access tokens headlessly without you
logging in again.

Requires YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET already set in .env (from
a Desktop-app OAuth client created in Google Cloud Console).

Usage: python -m scripts.youtube_oauth_setup

This opens your default browser for the Google consent screen. Since
youtube.upload is a "Sensitive" scope, an unverified app shows a warning —
click "Advanced" -> "Go to <app name> (unsafe)" to proceed; that's expected
for a personal project's own OAuth client.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

from pipeline import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    if not config.YOUTUBE_CLIENT_ID or not config.YOUTUBE_CLIENT_SECRET:
        raise SystemExit(
            "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env before running this."
        )

    client_config = {
        "installed": {
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # prompt="consent" forces Google to reissue a refresh_token even if this
    # client was already authorized before (it's only returned on consent).
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print("\nSuccess. Add this to your .env (and as a GitHub Actions secret):\n")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
