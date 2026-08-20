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

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from pipeline import captions, config, script_writer

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# --- End card (closer) branding ---
#
# The closer used to be sourced from Pexels like every other beat, searching
# "subscribe"/"follow" for a matching stock photo. That query doesn't have an
# abstract "please subscribe" concept to photograph, so Pexels' top result is
# literal photos of phones/screens showing *someone's actual* subscribe
# button — which come with whatever real channel name and branding happened
# to be on that screen when the photo was shot (e.g. a stranger's YouTube
# channel page). That's how another creator's name and handle ended up
# burned into the pixels of every video's end card. It isn't an attribution
# requirement (Pexels' license doesn't require credit), it's just what you
# get when you search stock photography for a UI concept instead of building
# the card yourself. Generating it locally guarantees our own branding, every
# time, with no stock-photo lottery involved.
BRAND_ICON_PATH = config.ASSETS_DIR / "branding" / "icon.png"

END_CARD_BG_TOP = (8, 12, 22)  # sampled from assets/branding/icon.png
END_CARD_BG_BOTTOM = (17, 24, 42)
END_CARD_CYAN = (77, 214, 255)
END_CARD_GOLD = (208, 148, 58)
END_CARD_WHITE = (255, 255, 255)

CHANNEL_NAME = "The Fact Dose"
SUBSCRIBE_CTA = "for daily science facts"

# captions.py burns karaoke captions over every line's audio, including the
# closer's — so the card layout has to stay clear of that band or the
# SUBSCRIBE button/text gets captions burned on top of it.
CAPTION_SAFE_MARGIN = 40


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

    result["hook"] = _source_for_keywords(
        script["hook_visual_keywords"],
        out_dir,
        "hook",
        used_photo_ids,
        prefer_ai=script.get("hook_prefer_ai_visual", False),
        is_internal_anatomy=script.get("hook_is_internal_anatomy", False),
    )

    for i, beat in enumerate(script_writer.flatten_countdown_facts(script)):
        result[f"fact_{i}"] = _source_for_keywords(
            beat["visual_keywords"],
            out_dir,
            f"fact_{i}",
            used_photo_ids,
            prefer_ai=beat.get("prefer_ai_visual", False),
            is_internal_anatomy=beat.get("is_internal_anatomy", False),
        )

    result["closer"] = [_build_end_card(out_dir)]
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


def _build_end_card(out_dir: Path) -> Path:
    """Renders the branded closer card locally — see the module-level comment
    above BRAND_ICON_PATH for why this isn't sourced from Pexels."""
    img = Image.new("RGB", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), END_CARD_BG_TOP)
    _apply_vertical_gradient(img, END_CARD_BG_TOP, END_CARD_BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Everything below this line is reserved for the karaoke caption band.
    safe_bottom = captions.CAPTION_Y - CAPTION_SAFE_MARGIN

    if BRAND_ICON_PATH.exists():
        icon = _icon_with_transparent_bg(BRAND_ICON_PATH)
        icon_size = int(config.VIDEO_WIDTH * 0.36)
        icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        icon_pos = ((config.VIDEO_WIDTH - icon_size) // 2, int(safe_bottom * 0.05))
        img.paste(icon, icon_pos, icon)

    title_font = ImageFont.load_default(size=88)
    _draw_centered_text(
        draw, CHANNEL_NAME, title_font, int(safe_bottom * 0.58),
        END_CARD_WHITE, stroke_width=2, stroke_fill=(0, 0, 0),
    )

    button_font = ImageFont.load_default(size=48)
    button_text = "SUBSCRIBE"
    bbox = draw.textbbox((0, 0), button_text, font=button_font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 56, 28
    btn_w, btn_h = text_w + pad_x * 2, text_h + pad_y * 2
    btn_x = (config.VIDEO_WIDTH - btn_w) // 2
    btn_y = int(safe_bottom * 0.74)
    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], radius=btn_h // 2, fill=END_CARD_GOLD
    )
    draw.text(
        (btn_x + pad_x - bbox[0], btn_y + pad_y - bbox[1]), button_text,
        font=button_font, fill=END_CARD_BG_TOP,
    )

    subtitle_font = ImageFont.load_default(size=38)
    _draw_centered_text(draw, SUBSCRIBE_CTA, subtitle_font, btn_y + btn_h + 28, END_CARD_CYAN)

    out_path = out_dir / "closer.png"
    img.save(out_path)
    return out_path


def _apply_vertical_gradient(img: Image.Image, top: tuple, bottom: tuple) -> None:
    width, height = img.size
    gradient = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / (height - 1)
        gradient.putpixel((0, y), tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3)))
    img.paste(gradient.resize((width, height)), (0, 0))


def _draw_centered_text(draw, text: str, font, y: int, fill, stroke_width: int = 0, stroke_fill=None) -> None:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    x = (config.VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2 - bbox[0]
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def _icon_with_transparent_bg(path: Path, low: int = 20, high: int = 60) -> Image.Image:
    """Chroma-keys out the icon's flat background so it composites cleanly
    onto the card's gradient instead of showing a visible square behind it."""
    rgb = np.array(Image.open(path).convert("RGB"), dtype=np.int16)
    bg = rgb[0, 0]
    dist = np.linalg.norm(rgb - bg, axis=-1)
    alpha = (np.clip((dist - low) / (high - low), 0, 1) * 255).astype(np.uint8)
    rgba = np.dstack([rgb.astype(np.uint8), alpha])
    return Image.fromarray(rgba)


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


REPLICATE_ATTEMPTS = 6
REPLICATE_RETRY_DELAY_SECONDS = 15  # Replicate's own 429s report resetting in ~7s under throttling


REPLICATE_POLL_INTERVAL_SECONDS = 2
REPLICATE_POLL_TIMEOUT_SECONDS = 120  # generation itself finishes in seconds; this is a ceiling


def _generate_image_replicate(prompt: str, out_dir: Path, label: str) -> Path:
    import time

    # The replicate SDK's client.run() normally blocks on a single HTTP
    # request held open (via the "Prefer: wait" header) for up to ~60s while
    # Replicate finishes the prediction. On this network that request
    # reliably raises a ReadTimeout around the 60s mark instead of returning
    # (reproduced with both the SDK and plain curl), even though generation
    # itself only takes a few seconds. Worse, un-pinned "owner/name" model
    # refs (like flux-schnell) return "version": null until the prediction
    # resolves, which crashes the SDK's response parsing (pydantic requires
    # a non-null version) on any non-terminal status. Posting without a wait
    # header and polling manually with plain `requests` sidesteps both: each
    # request is short-lived, and we parse the JSON ourselves.
    model = config.IMAGE_GEN_MODEL or DEFAULT_IMAGE_MODELS["replicate"]
    headers = {"Authorization": f"Bearer {config.IMAGE_GEN_API_KEY}"}
    model_input = {
        "prompt": prompt,
        "aspect_ratio": "9:16",  # matches the 1080x1920 Shorts frame exactly
        "output_format": "png",
        "num_outputs": 1,
    }

    # Accounts with under $5 credit get throttled to 6 requests/min with a
    # burst of 1 (Replicate's own policy) — a video needing several images
    # in a row (one per hook-format beat) can exceed that burst and either
    # queue long enough to blow past a poll timeout, or get an explicit 429.
    # A "failed" prediction whose error mentions "unexpected error handling
    # prediction" is a separate, transient failure on Replicate's own
    # infrastructure side, not caused by our prompt — also worth retrying.
    for attempt in range(REPLICATE_ATTEMPTS):
        try:
            resp = requests.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers=headers,
                json={"input": model_input},
                timeout=30,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == REPLICATE_ATTEMPTS - 1:
                    resp.raise_for_status()
                time.sleep(REPLICATE_RETRY_DELAY_SECONDS)
                continue
            resp.raise_for_status()
            prediction = resp.json()
            get_url = prediction["urls"]["get"]

            deadline = time.monotonic() + REPLICATE_POLL_TIMEOUT_SECONDS
            while prediction["status"] not in ("succeeded", "failed", "canceled"):
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Replicate prediction {prediction['id']} still {prediction['status']!r} "
                        f"after {REPLICATE_POLL_TIMEOUT_SECONDS}s"
                    )
                time.sleep(REPLICATE_POLL_INTERVAL_SECONDS)
                prediction = requests.get(get_url, headers=headers, timeout=30).json()

            if prediction["status"] == "succeeded":
                output = prediction["output"]
                output_url = output[0] if isinstance(output, list) else output
                image_bytes = requests.get(output_url, timeout=30).content
                out_path = out_dir / f"{label}.png"
                out_path.write_bytes(image_bytes)
                return out_path

            error = str(prediction.get("error") or "")
            is_transient = "unexpected error handling prediction" in error.lower()
            if not is_transient or attempt == REPLICATE_ATTEMPTS - 1:
                raise RuntimeError(f"Replicate prediction failed: {error}")
            time.sleep(REPLICATE_RETRY_DELAY_SECONDS)

        except (requests.Timeout, TimeoutError):
            if attempt == REPLICATE_ATTEMPTS - 1:
                raise
            time.sleep(REPLICATE_RETRY_DELAY_SECONDS)

    raise RuntimeError("Replicate image generation failed after all retries")


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
