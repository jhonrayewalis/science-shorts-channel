"""
Stage 5: Assembly.

Composites voiceover + visuals + background music into a single 1080x1920
video, before captions are burned in by captions.py.

"countdown" format: one visual+audio segment per line (hook, each fact,
closer), concatenated. "hook" format: same idea, one segment per beat
(hook, then each payoff beat) — the visual cuts to a new image every few
seconds as the narration progresses, instead of holding one image for the
whole video.

Background music is optional: drop any number of tracks into assets/music/
and each render randomly picks one, so everything dropped in there rotates
into use automatically with no code change. With no track present, the
export just carries the narration audio. See music_attribution.py for the
per-track credit info that pairs with whatever gets picked.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    afx,
    concatenate_videoclips,
    vfx,
)
from PIL import Image

from pipeline import config

KEN_BURNS_ZOOM = 0.08  # fraction the image slowly zooms in over a segment's duration
MUSIC_VOLUME = 0.15


def assemble_video(script: dict, audio: dict, visuals: dict, out_path: Path) -> tuple[Path, Path | None]:
    """
    audio: output of tts.generate_voiceover()
    visuals: output of visuals.source_visuals()
    Returns (video_path, music_track_path). music_track_path is the file from
    assets/music/ actually mixed in (or None if none was found) — the caller
    needs this to know which track's attribution, if any, belongs on this
    specific video; see pipeline/music_attribution.py.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    segments = [_build_segment(visuals["hook"][0], audio["hook_audio"])]
    if script["format"] == "hook":
        for i in range(len(script["payoff_beats"])):
            segments.append(_build_segment(visuals[f"beat_{i}"][0], audio["beat_audio"][i]))
    else:
        # audio["fact_audio"] is already flattened to one entry per beat
        # (facts can have 1-2 each) by tts.py, so its length is the real
        # segment count regardless of how many beats each fact used.
        for i in range(len(audio["fact_audio"])):
            segments.append(_build_segment(visuals[f"fact_{i}"][0], audio["fact_audio"][i]))
        segments.append(_build_segment(visuals["closer"][0], audio["closer_audio"]))

    music_track = _concatenate_and_export(segments, out_path)
    return out_path, music_track


def _build_segment(visual: Path, audio_path: Path):
    """Build one MoviePy clip: visual (Ken-Burns-panned if it's a still image) + its matching audio."""
    audio_clip = AudioFileClip(str(audio_path))
    duration = audio_clip.duration

    segment = CompositeVideoClip(
        [_build_visual_clip(visual, duration)], size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
    )
    return segment.with_duration(duration).with_audio(audio_clip)


def _build_visual_clip(visual: Path, duration: float):
    if visual.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError(
            f"Unsupported visual file type {visual.suffix!r} for {visual} — "
            "visuals.py currently only produces still images, so video-clip "
            "handling (VideoFileClip) hasn't been implemented here yet."
        )

    frame = _cover_resize_crop(visual)
    clip = ImageClip(frame, duration=duration)
    clip = clip.with_effects([vfx.Resize(lambda t: 1 + KEN_BURNS_ZOOM * (t / duration))])
    return clip.with_position("center")


def _cover_resize_crop(image_path: Path) -> np.ndarray:
    """Center-crop + resize a source image so it exactly fills the target frame."""
    img = Image.open(image_path).convert("RGB")
    target_ratio = config.VIDEO_WIDTH / config.VIDEO_HEIGHT
    src_ratio = img.width / img.height

    if src_ratio > target_ratio:
        crop_width, crop_height = int(img.height * target_ratio), img.height
    else:
        crop_width, crop_height = img.width, int(img.width / target_ratio)

    left = (img.width - crop_width) // 2
    top = (img.height - crop_height) // 2
    img = img.crop((left, top, left + crop_width, top + crop_height))
    img = img.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.Resampling.LANCZOS)
    return np.array(img)


def _concatenate_and_export(segments, out_path: Path) -> Path | None:
    video = concatenate_videoclips(segments, method="compose")
    video, music_track = _with_background_music(video)
    video.write_videofile(
        str(out_path),
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
    )
    video.close()
    return music_track


def _with_background_music(video):
    music_path = _find_music_track()
    if music_path is None:
        print("No background music found in assets/music/ — exporting narration-only audio.")
        return video, None

    music = AudioFileClip(str(music_path)).with_effects([
        afx.AudioLoop(duration=video.duration),
        afx.MultiplyVolume(MUSIC_VOLUME),
    ])
    return video.with_audio(CompositeAudioClip([video.audio, music])), music_path


def _find_music_track() -> Path | None:
    """Randomly picks among every track in assets/music/, so anything dropped
    in there rotates into use without needing a code change."""
    music_dir = config.ASSETS_DIR / "music"
    if not music_dir.exists():
        return None
    tracks = [p for ext in ("*.mp3", "*.wav", "*.m4a") for p in music_dir.glob(ext)]
    return random.choice(tracks) if tracks else None


if __name__ == "__main__":
    print("Run this via orchestrator.py with real script/audio/visuals.")
