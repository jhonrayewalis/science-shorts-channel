"""
Stage 7: Metadata.

Generates the YouTube title, description, tags, and hashtags from the
finished script. category_id is fixed to "27" (Education) in code rather
than left to the model, since every video on this channel belongs there.

If assemble.py mixed in a background music track that requires attribution
(see music_attribution.py), the required credit block is appended to the
description here — before upload.py ever runs — rather than as a step that
could be forgotten per video.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import llm_client, music_attribution

EDUCATION_CATEGORY_ID = "27"


def generate_metadata(script: dict, topic: dict, music_track: Path | None = None) -> dict:
    """
    music_track: the path returned by assemble.assemble_video(), if any.

    Returns:
    {
        "title": "...",
        "description": "...",
        "tags": ["...", ...],
        "category_id": "27",   # YouTube category: 27 = Education
    }
    """
    meta = _call_llm(script, topic)
    meta["description"] = _ensure_shorts_hashtag(meta["description"])
    meta["description"] = _append_music_attribution(meta["description"], music_track)
    meta["category_id"] = EDUCATION_CATEGORY_ID
    _validate_metadata(meta)
    return meta


def _ensure_shorts_hashtag(description: str) -> str:
    if "#shorts" not in description.lower():
        description = description.rstrip() + "\n\n#shorts"
    return description


def _append_music_attribution(description: str, music_track: Path | None) -> str:
    attribution_block = music_attribution.get_attribution_block(music_track)
    if attribution_block is None:
        return description
    return description.rstrip() + "\n\n" + attribution_block


def _validate_metadata(meta: dict) -> None:
    assert meta.get("title"), "Metadata missing title"
    assert len(meta["title"]) <= 100, "Title exceeds YouTube's 100-character limit"
    assert meta.get("description"), "Metadata missing description"
    assert meta.get("tags"), "Metadata missing tags"


def _build_prompt(script: dict, topic: dict) -> str:
    if script["format"] == "hook":
        return _build_hook_prompt(script, topic)
    return _build_countdown_prompt(script, topic)


def _build_countdown_prompt(script: dict, topic: dict) -> str:
    facts_lines = "\n".join(
        f"{f['rank']}. " + " ".join(beat["text"] for beat in f["beats"])
        for f in sorted(script["facts"], key=lambda f: -f["rank"])
    )
    return (
        f'Write YouTube Shorts metadata for a science-facts video about "{topic["topic"]}" '
        f'(category: {topic["category"]}).\n\n'
        f"Video script:\nHook: {script['hook']}\n{facts_lines}\nCloser: {script['closer']}\n\n"
        "Requirements:\n"
        "- `title`: punchy, curiosity-driven, under 60 characters, no clickbait falsehoods.\n"
        "- `description`: 2-4 sentences summarizing the video, ending with 2-3 relevant "
        "hashtags including #shorts.\n"
        "- `tags`: 8-12 relevant search tags as short phrases, no leading #.\n\n"
        "Respond with ONLY valid JSON, no markdown fences, no commentary, in this exact shape:\n"
        '{"title": "...", "description": "...", "tags": ["...", "..."]}'
    )


def _build_hook_prompt(script: dict, topic: dict) -> str:
    payoff = " ".join(beat["text"] for beat in script["payoff_beats"])
    return (
        f'Write YouTube Shorts metadata for a science video about "{topic["topic"]}" '
        f'(category: {topic["category"]}).\n\n'
        f"Video script:\nHook: {script['hook']}\nPayoff: {payoff}\n\n"
        "Requirements:\n"
        "- `title`: punchy, curiosity-driven, under 60 characters, no clickbait falsehoods.\n"
        "- `description`: 2-4 sentences summarizing the video, ending with 2-3 relevant "
        "hashtags including #shorts.\n"
        "- `tags`: 8-12 relevant search tags as short phrases, no leading #.\n\n"
        "Respond with ONLY valid JSON, no markdown fences, no commentary, in this exact shape:\n"
        '{"title": "...", "description": "...", "tags": ["...", "..."]}'
    )


def _call_llm(script: dict, topic: dict) -> dict:
    prompt = _build_prompt(script, topic)
    return llm_client.complete_json(prompt, max_tokens=600)


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script.")
