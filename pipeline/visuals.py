"""
Stage 4: Visual sourcing.

"countdown" format: for each script line's visual_keywords, pulls matching
stock footage/images (Pexels primary) with AI image generation as a
fallback when no good match exists — or as the primary source for facts
script_writer.py flagged as `prefer_ai_visual` (a specific real subject
generic stock is unlikely to have an accurate photo of, e.g. a particular
species' distinctive behavior — Pexels will still return *something* for
almost any query, just not necessarily anything relevant, so an
empty-results check alone doesn't catch this).

"hook" format: always AI-generates one image per beat (the hook line, then
each payoff beat) instead of stock — a distinct image per beat is the point
(the visual cuts as the narration progresses), and stock is unlikely to
have an accurate match for the specific claim in each beat anyway.

Everything here is either licensed-for-reuse stock or freshly generated —
never footage/clips pulled from any specific creator's content.
"""
from __future__ import annotations

from pathlib import Path

import requests

from pipeline import config, script_writer

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"


def source_visuals(script: dict, out_dir: Path) -> dict:
    """
    For "countdown" format, returns a dict mapping each line ("hook",
    "fact_0"..."fact_N", "closer") to a list of local file paths.

    For "hook" format, returns a dict mapping each beat ("hook",
    "beat_0"..."beat_N") to a list containing one AI-generated image path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if script["format"] == "hook":
        return _source_visuals_hook(script, out_dir)
    return _source_visuals_countdown(script, out_dir)


def _source_visuals_hook(script: dict, out_dir: Path) -> dict:
    result = {
        "hook": [
            _generate_image(
                ", ".join(script["hook_visual_keywords"]),
                out_dir,
                "hook",
                is_internal_anatomy=script.get("hook_is_internal_anatomy", False),
            )
        ]
    }
    for i, beat in enumerate(script["payoff_beats"]):
        description = ", ".join(beat["visual_keywords"])
        result[f"beat_{i}"] = [
            _generate_image(
                description, out_dir, f"beat_{i}", is_internal_anatomy=beat.get("is_internal_anatomy", False)
            )
        ]
    return result


def _source_visuals_countdown(script: dict, out_dir: Path) -> dict:
    used_photo_ids: set[int] = set()
    result = {}

    result["hook"] = _source_for_keywords(["science", "mystery"], out_dir, "hook", used_photo_ids)

    for i, beat in enumerate(script_writer.flatten_countdown_facts(script)):
        result[f"fact_{i}"] = _source_for_keywords(
            beat["visual_keywords"],
            out_dir,
            f"fact_{i}",
            used_photo_ids,
            prefer_ai=beat.get("prefer_ai_visual", False),
            is_internal_anatomy=beat.get("is_internal_anatomy", False),
        )

    result["closer"] = _source_for_keywords(
        ["subscribe", "follow"], out_dir, "closer", used_photo_ids
    )
    return result


def _source_for_keywords(
    keywords: list[str],
    out_dir: Path,
    label: str,
    used_photo_ids: set[int],
    prefer_ai: bool = False,
    is_internal_anatomy: bool = False,
) -> list[Path]:
    if not prefer_ai:
        for kw in keywords:
            hit = _search_pexels(kw, out_dir, label, used_photo_ids)
            if hit:
                return [hit]
    # Either flagged as needing a specific subject stock is unlikely to have,
    # or nothing relevant turned up in stock — fall back to AI generation.
    description = ", ".join(keywords) if keywords else label
    return [_generate_image(description, out_dir, label, is_internal_anatomy=is_internal_anatomy)]


def _search_pexels(
    keyword: str, out_dir: Path, label: str, used_photo_ids: set[int]
) -> Path | None:
    response = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": keyword, "per_page": 5, "orientation": "portrait"},
        timeout=15,
    )
    response.raise_for_status()
    photos = response.json().get("photos", [])
    # Pexels' top result often converges on the same photo across related
    # keywords within one topic — skip anything already used in this video.
    fresh = [p for p in photos if p["id"] not in used_photo_ids]
    if not fresh:
        return None

    photo = fresh[0]
    used_photo_ids.add(photo["id"])
    out_path = out_dir / f"{label}.jpg"
    _download(photo["src"]["large2x"], out_path)
    return out_path


IMAGE_PROMPT_TEMPLATE = (
    "A photorealistic photograph of {keyword}. Realistic photography, shot on a "
    "professional camera, natural lighting, high detail, real textures and materials, "
    "as if captured in a real documentary or studio photography setting. "
    "Not a 3D render, not digital art, not a diagram, not a vector illustration, "
    "not an infographic. "
    "No text, no labels, no arrows, no watermarks, no identifiable people, vertical composition."
)

# Used only when script_writer.py flags a visual as `is_internal_anatomy` — a
# subject no camera could normally photograph directly (organ cross-sections,
# tissue layers, cellular structures). A single template with "if internal
# anatomy, do X" conditional phrasing doesn't work here: diffusion models
# don't obey conditional instructions, they respond to every word in the
# prompt as a simultaneous cue, so material words like "silicone/resin" meant
# only for anatomy shots were leaking into unrelated images (e.g. warping a
# tornado into a rubbery shape) when both cases shared one template. Keeping
# two fully separate templates, picked in code, avoids that entirely.
ANATOMY_MODEL_PROMPT_TEMPLATE = (
    "A studio product photograph of a real physical anatomical teaching model or "
    "specimen depicting {keyword}. Professional product photography on a plain "
    "background: realistic photographic lighting, shallow depth of field, visible "
    "real surface detail and material texture of a molded or preserved model "
    "(not living tissue, not a diagram). "
    "Not a 3D render, not digital art, not a diagram, not a vector illustration, "
    "not an infographic. "
    "No text, no labels, no arrows, no watermarks, no identifiable people, vertical composition."
)

DEFAULT_IMAGE_MODELS = {
    "replicate": "black-forest-labs/flux-schnell",
    "openai": "gpt-image-1",
}


def _generate_image(keyword: str, out_dir: Path, label: str, is_internal_anatomy: bool = False) -> Path:
    template = ANATOMY_MODEL_PROMPT_TEMPLATE if is_internal_anatomy else IMAGE_PROMPT_TEMPLATE
    prompt = template.format(keyword=keyword)

    if config.IMAGE_GEN_PROVIDER == "replicate":
        return _generate_image_replicate(prompt, out_dir, label)
    elif config.IMAGE_GEN_PROVIDER == "openai":
        return _generate_image_openai(prompt, out_dir, label)
    raise ValueError(f"Unsupported IMAGE_GEN_PROVIDER: {config.IMAGE_GEN_PROVIDER!r}")


REPLICATE_ATTEMPTS = 4
REPLICATE_RETRY_DELAY_SECONDS = 10  # Replicate's own 429s report resetting in ~7s under throttling


def _generate_image_replicate(prompt: str, out_dir: Path, label: str) -> Path:
    import time

    import httpx
    import replicate

    # Accounts with under $5 credit get throttled to 6 requests/min with a
    # burst of 1 (Replicate's own policy) — a video needing several images
    # in a row (one per hook-format beat) can exceed that burst and either
    # queue long enough to blow past a client-side read timeout, or get an
    # explicit 429. Both are transient and worth retrying with a delay.
    client = replicate.Client(api_token=config.IMAGE_GEN_API_KEY, timeout=httpx.Timeout(240.0))
    model_input = {
        "prompt": prompt,
        "aspect_ratio": "9:16",  # matches the 1080x1920 Shorts frame exactly
        "output_format": "png",
        "num_outputs": 1,
    }

    output = None
    for attempt in range(REPLICATE_ATTEMPTS):
        try:
            output = client.run(config.IMAGE_GEN_MODEL or DEFAULT_IMAGE_MODELS["replicate"], input=model_input)
            break
        except (httpx.TimeoutException, replicate.exceptions.ReplicateError) as exc:
            is_throttled = isinstance(exc, replicate.exceptions.ReplicateError) and exc.status == 429
            if not (isinstance(exc, httpx.TimeoutException) or is_throttled):
                raise
            if attempt == REPLICATE_ATTEMPTS - 1:
                raise
            time.sleep(REPLICATE_RETRY_DELAY_SECONDS)

    file_output = output[0] if isinstance(output, list) else output

    out_path = out_dir / f"{label}.png"
    out_path.write_bytes(file_output.read())
    return out_path


def _generate_image_openai(prompt: str, out_dir: Path, label: str) -> Path:
    import base64

    import openai

    client = openai.OpenAI(api_key=config.IMAGE_GEN_API_KEY)
    response = client.images.generate(
        model=config.IMAGE_GEN_MODEL or DEFAULT_IMAGE_MODELS["openai"],
        prompt=prompt,
        size="1024x1536",  # tallest standard size across gpt-image model variants
        n=1,
    )

    out_path = out_dir / f"{label}.png"
    out_path.write_bytes(base64.b64decode(response.data[0].b64_json))
    return out_path


def _download(url: str, out_path: Path) -> None:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    out_path.write_bytes(response.content)


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script.")
