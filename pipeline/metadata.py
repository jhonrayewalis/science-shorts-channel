"""
Stage 7: Metadata.

Generates the YouTube title, description, tags, and hashtags from the
finished script.

TODO (Claude Code): implement `_call_llm`. Keep the title punchy and under
~60 chars for Shorts, include 2-3 relevant hashtags in the description
(#shorts is close to mandatory), and generate 8-12 tags.
"""
from pipeline import config


def generate_metadata(script: dict, topic: dict) -> dict:
    """
    Returns:
    {
        "title": "...",
        "description": "...",
        "tags": ["...", ...],
        "category_id": "27",   # YouTube category: 27 = Education
    }
    """
    return _call_llm(script, topic)


def _call_llm(script: dict, topic: dict) -> dict:
    raise NotImplementedError("Wire up your LLM provider here.")


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script.")
