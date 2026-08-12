"""
Attribution for background music tracks in assets/music/.

Some sources (e.g. freetouse.com) require attribution text in the video
description, or the upload can trigger a copyright claim; others (e.g.
Pixabay) don't. assets/music/attribution.json maps each track filename to
whether it needs attribution and, if so, the exact info to credit it with.

Checked from metadata.py, which runs before upload.py in orchestrator.py's
sequence. A track with no entry here prints a loud console warning rather
than crashing the run or silently omitting attribution — so a forgotten
entry is impossible to miss in the output, without blocking the pipeline
over it.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline import config

ATTRIBUTION_PATH = config.ASSETS_DIR / "music" / "attribution.json"


def load_attribution() -> dict:
    if not ATTRIBUTION_PATH.exists():
        return {}
    return json.loads(ATTRIBUTION_PATH.read_text())


def get_attribution_block(track_path: Path | None) -> str | None:
    """
    Returns the attribution text to append to the video description, or None
    if no track was used, the track doesn't require attribution, or the
    track has no entry at all (in which case a warning is printed — see
    module docstring).
    """
    if track_path is None:
        return None

    entry = load_attribution().get(track_path.name)
    if entry is None:
        print(
            f"\n>>> WARNING: no attribution entry for {track_path.name!r} in "
            f"{ATTRIBUTION_PATH}.\n"
            ">>> This video's description will NOT include any music attribution. "
            "If this track's license requires it, add an entry before publishing — "
            "see assets/music/attribution.json.\n"
        )
        return None

    if not entry.get("requires_attribution", False):
        return None

    return (
        f"Music from {entry['source_name']}\n"
        f"Source: {entry['source_url']}\n"
        f"{entry['title']} by {entry['artist']}"
    )


if __name__ == "__main__":
    print(json.dumps(load_attribution(), indent=2))
