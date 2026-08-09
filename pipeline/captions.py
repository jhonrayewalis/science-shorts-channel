"""
Stage 6: Captions.

Burns word-synced captions onto the assembled video using the timestamps
from tts.py. Shorts retention depends heavily on captions being present and
well-timed, so don't skip this stage.

TODO (Claude Code): implement using MoviePy TextClips driven by the
word_timestamps dict from audio, or (if your TTS provider doesn't return
usable word timing) fall back to running the exported audio through Whisper
locally to get timestamps instead.
"""
from pathlib import Path


def burn_captions(video_path: Path, word_timestamps: dict, out_path: Path) -> Path:
    raise NotImplementedError(
        "Overlay word-synced TextClips onto video_path using word_timestamps, export to out_path."
    )


def transcribe_with_whisper(audio_path: Path) -> list[dict]:
    """Fallback path if the TTS provider doesn't return word-level timing."""
    raise NotImplementedError("Run openai-whisper locally and return word-level timestamps.")


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real assembled video.")
