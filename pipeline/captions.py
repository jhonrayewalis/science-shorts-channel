"""
Stage 6: Captions.

Burns captions onto the assembled video using the timestamps from tts.py.
Shorts retention depends heavily on captions being present and well-timed,
so don't skip this stage.

"countdown" format: short chunks (a few words at a time) with the
currently-spoken word highlighted, karaoke-style.

"hook" format: static two-line caption blocks (no per-word highlight/
animation) — a few words' worth of text appears as one plain block, then
the next block replaces it, timed off the same word-level data.

Both styles are rendered directly with Pillow (same approach as the rank
badges originally in assemble.py) so this doesn't depend on any font file
being checked into the repo.

Takes the full `script` + `audio` dicts rather than just word_timestamps,
because: (a) it needs script["format"] to pick a caption style, and (b)
each line's exact on-screen duration has to match the segment duration
assemble.py used (derived from the real audio file length, not the last
word's end time) or captions drift out of sync after a few concatenated
segments.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip
from PIL import Image, ImageDraw, ImageFont

from pipeline import config

CAPTION_MAX_TEXT_WIDTH = int(config.VIDEO_WIDTH * 0.88)
CAPTION_FONT_SIZE_MAX = 88
CAPTION_FONT_SIZE_MIN = 44
STROKE_WIDTH = 6
BASE_COLOR = (255, 255, 255, 255)
STROKE_COLOR = (0, 0, 0, 255)

# karaoke (countdown format)
CAPTION_BAND_HEIGHT = 220
CAPTION_Y = int(config.VIDEO_HEIGHT * 0.70)
CAPTION_MAX_WORDS_PER_GROUP = 4
CAPTION_MAX_CHARS_PER_GROUP = 26
WORD_GAP = 22
HIGHLIGHT_COLOR = (255, 214, 10, 255)

# static two-line blocks (hook format)
HOOK_CAPTION_Y = int(config.VIDEO_HEIGHT * 0.60)
HOOK_CAPTION_MAX_WORDS_PER_GROUP = 10
HOOK_CAPTION_MAX_CHARS_PER_GROUP = 60
HOOK_CAPTION_LINE_GAP = 16

_whisper_model = None


def burn_captions(video_path: Path, script: dict, audio: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base_video = VideoFileClip(str(video_path))

    if script["format"] == "hook":
        caption_clips = _build_hook_captions(audio)
    else:
        caption_clips = _build_countdown_captions(audio)

    composite = CompositeVideoClip(
        [base_video, *caption_clips], size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
    )
    composite = composite.with_duration(base_video.duration).with_audio(base_video.audio)
    composite.write_videofile(
        str(out_path), fps=config.VIDEO_FPS, codec="libx264", audio_codec="aac"
    )
    composite.close()
    base_video.close()
    return out_path


def transcribe_with_whisper(audio_path: Path) -> list[dict]:
    """Fallback path if a line came back with no usable word-level timing."""
    global _whisper_model
    if _whisper_model is None:
        import whisper

        _whisper_model = whisper.load_model("base")

    result = _whisper_model.transcribe(str(audio_path), word_timestamps=True)
    words = []
    for segment in result["segments"]:
        for w in segment.get("words", []):
            words.append({"word": w["word"].strip(), "start": w["start"], "end": w["end"]})
    return words


def _audio_duration(audio_path: Path) -> float:
    clip = AudioFileClip(str(audio_path))
    duration = clip.duration
    clip.close()
    return duration


def _group_words(
    words: list[dict],
    max_words: int = CAPTION_MAX_WORDS_PER_GROUP,
    max_chars: int = CAPTION_MAX_CHARS_PER_GROUP,
) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for word in words:
        text = word["word"]
        extra = len(text) + (1 if current else 0)
        if current and (len(current) >= max_words or current_chars + extra > max_chars):
            groups.append(current)
            current, current_chars, extra = [], 0, len(text)
        current.append(word)
        current_chars += extra

    if current:
        groups.append(current)
    return groups


# --- countdown format: karaoke-style, one clip per word ---


def _line_sequence(audio: dict) -> list[tuple[Path, list[dict]]]:
    ts = audio["word_timestamps"]
    sequence = [(audio["hook_audio"], ts["hook"])]
    sequence.extend(zip(audio["fact_audio"], ts["facts"]))
    sequence.append((audio["closer_audio"], ts["closer"]))
    return sequence


def _build_countdown_captions(audio: dict) -> list:
    caption_clips = []
    t_offset = 0.0
    for line_audio_path, words in _line_sequence(audio):
        line_duration = _audio_duration(line_audio_path)
        if not words:
            words = transcribe_with_whisper(line_audio_path)
        caption_clips.extend(_build_karaoke_line_captions(words, t_offset, line_duration))
        t_offset += line_duration
    return caption_clips


def _build_karaoke_line_captions(words: list[dict], line_offset: float, line_duration: float) -> list:
    if not words:
        return []

    clips = []
    flat_index = 0
    for group in _group_words(words):
        for i in range(len(group)):
            start = line_offset + group[i]["start"]
            if flat_index + 1 < len(words):
                end = line_offset + words[flat_index + 1]["start"]
            else:
                end = line_offset + line_duration
            duration = max(end - start, 0.01)

            frame = _render_karaoke_frame(group, active_index=i)
            clips.append(
                ImageClip(frame, duration=duration).with_start(start).with_position((0, CAPTION_Y))
            )
            flat_index += 1
    return clips


def _render_karaoke_frame(group: list[dict], active_index: int) -> np.ndarray:
    words_text = [w["word"].upper() for w in group]

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def measure(font):
        widths = [
            dummy_draw.textbbox((0, 0), w, font=font, stroke_width=STROKE_WIDTH)[2]
            for w in words_text
        ]
        return widths, sum(widths) + WORD_GAP * (len(widths) - 1)

    font_size = CAPTION_FONT_SIZE_MAX
    font = ImageFont.load_default(size=font_size)
    widths, total_width = measure(font)
    while total_width > CAPTION_MAX_TEXT_WIDTH and font_size > CAPTION_FONT_SIZE_MIN:
        font_size -= 4
        font = ImageFont.load_default(size=font_size)
        widths, total_width = measure(font)

    img = Image.new("RGBA", (config.VIDEO_WIDTH, CAPTION_BAND_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x = (config.VIDEO_WIDTH - total_width) // 2
    y = CAPTION_BAND_HEIGHT // 2
    for i, (word, width) in enumerate(zip(words_text, widths)):
        color = HIGHLIGHT_COLOR if i == active_index else BASE_COLOR
        draw.text(
            (x, y),
            word,
            font=font,
            fill=color,
            stroke_width=STROKE_WIDTH,
            stroke_fill=STROKE_COLOR,
            anchor="lm",
        )
        x += width + WORD_GAP

    return np.array(img)


# --- hook format: static two-line blocks, one clip per group ---


def _build_hook_captions(audio: dict) -> list:
    lines = [(audio["hook_audio"], audio["word_timestamps"]["hook"])]
    lines.extend(zip(audio["beat_audio"], audio["word_timestamps"]["beats"]))

    caption_clips = []
    t_offset = 0.0
    for line_audio_path, words in lines:
        line_duration = _audio_duration(line_audio_path)
        if not words:
            words = transcribe_with_whisper(line_audio_path)
        caption_clips.extend(_build_static_line_captions(words, t_offset, line_duration))
        t_offset += line_duration
    return caption_clips


def _build_static_line_captions(words: list[dict], line_offset: float, line_duration: float) -> list:
    if not words:
        return []

    clips = []
    flat_index = 0
    for group in _group_words(
        words, max_words=HOOK_CAPTION_MAX_WORDS_PER_GROUP, max_chars=HOOK_CAPTION_MAX_CHARS_PER_GROUP
    ):
        start = line_offset + group[0]["start"]
        flat_index += len(group)
        if flat_index < len(words):
            end = line_offset + words[flat_index]["start"]
        else:
            end = line_offset + line_duration
        duration = max(end - start, 0.01)

        frame = _render_static_frame([w["word"] for w in group])
        clips.append(
            ImageClip(frame, duration=duration).with_start(start).with_position((0, HOOK_CAPTION_Y))
        )
    return clips


def _render_static_frame(words: list[str]) -> np.ndarray:
    words_text = [w.upper() for w in words]
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def line_width(font, line_words):
        return dummy_draw.textbbox((0, 0), " ".join(line_words), font=font, stroke_width=STROKE_WIDTH)[2]

    def wrap(font):
        lines: list[list[str]] = []
        current: list[str] = []
        for word in words_text:
            candidate = current + [word]
            if current and line_width(font, candidate) > CAPTION_MAX_TEXT_WIDTH:
                lines.append(current)
                current = [word]
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    font_size = CAPTION_FONT_SIZE_MAX
    font = ImageFont.load_default(size=font_size)
    lines = wrap(font)
    while len(lines) > 2 and font_size > CAPTION_FONT_SIZE_MIN:
        font_size -= 4
        font = ImageFont.load_default(size=font_size)
        lines = wrap(font)

    line_height = int(font_size * 1.25)
    band_height = line_height * len(lines) + HOOK_CAPTION_LINE_GAP * max(len(lines) - 1, 0) + 30
    img = Image.new("RGBA", (config.VIDEO_WIDTH, band_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = 15
    for line_words in lines:
        line_text = " ".join(line_words)
        width = draw.textbbox((0, 0), line_text, font=font, stroke_width=STROKE_WIDTH)[2]
        x = (config.VIDEO_WIDTH - width) // 2
        draw.text(
            (x, y), line_text, font=font, fill=BASE_COLOR, stroke_width=STROKE_WIDTH, stroke_fill=STROKE_COLOR
        )
        y += line_height + HOOK_CAPTION_LINE_GAP

    return np.array(img)


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real assembled video.")
