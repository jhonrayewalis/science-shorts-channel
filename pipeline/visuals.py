"""
Stage 4: Visual sourcing.

For each script line's visual_keywords, pulls matching stock footage/images
(Pexels primary) with AI image generation as a fallback when no good match
exists. Everything here is either licensed-for-reuse stock or freshly
generated — never footage/clips pulled from any specific creator's content.

TODO (Claude Code): implement `_search_pexels` and `_generate_image`.
"""
from pathlib import Path

from pipeline import config


def source_visuals(script: dict, out_dir: Path) -> dict:
    """
    Returns a dict mapping each line ("hook", "fact_0"..."fact_N", "closer")
    to a list of local file paths (image or short video clip) to use for
    that segment.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}

    result["hook"] = _source_for_keywords(["science", "mystery"], out_dir, "hook")

    for i, fact in enumerate(script["facts"]):
        result[f"fact_{i}"] = _source_for_keywords(
            fact["visual_keywords"], out_dir, f"fact_{i}"
        )

    result["closer"] = _source_for_keywords(["subscribe", "follow"], out_dir, "closer")
    return result


def _source_for_keywords(keywords: list[str], out_dir: Path, label: str) -> list[Path]:
    for kw in keywords:
        hit = _search_pexels(kw, out_dir, label)
        if hit:
            return [hit]
    # Nothing found in stock — fall back to AI generation
    return [_generate_image(keywords[0] if keywords else label, out_dir, label)]


def _search_pexels(keyword: str, out_dir: Path, label: str) -> Path | None:
    raise NotImplementedError("Wire up Pexels API here. See config.PEXELS_API_KEY.")


def _generate_image(prompt: str, out_dir: Path, label: str) -> Path:
    raise NotImplementedError(
        "Wire up an image-gen provider here. See config.IMAGE_GEN_PROVIDER / config.IMAGE_GEN_API_KEY."
    )


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script.")
