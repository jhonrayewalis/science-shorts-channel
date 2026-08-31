"""
Stage 3: Voiceover.

Converts each script line to audio, and returns word-level timestamps so
captions.py can burn in synced subtitles. Handles both script formats (see
script_writer.py): "countdown" (hook/facts/closer) and "hook" (hook/payoff).

- elevenlabs: uses the timestamped TTS endpoint, which returns
  character-level alignment; grouped into words here.
- openai: the TTS endpoint returns no timing data at all, so the generated
  audio is transcribed locally with Whisper (already in requirements.txt)
  to recover word-level timestamps.
"""
import base64
import difflib
import random
import re
from pathlib import Path

from pipeline import config, script_writer

DEFAULT_MODELS = {
    "elevenlabs": "eleven_multilingual_v2",
    "openai": "gpt-4o-mini-tts",
}

# ElevenLabs generation isn't fully deterministic — the same text occasionally
# comes back with the narration derailing into hallucinated words (observed
# in production on dense numeric content like year ranges). Its own
# alignment data can't catch this: that's a forced alignment of the AUDIO
# against the INTENDED text, so it still returns "clean" timestamps even when
# the audio itself says something else. Independently transcribing the
# result and comparing against the intended text catches that; regenerating
# (a fresh stochastic sample) reliably fixes it in practice.
TTS_QA_ATTEMPTS = 3
_MIN_TRANSCRIPT_SIMILARITY = 0.75
_WORD_RE = re.compile(r"[a-z0-9']+")

_whisper_model = None


def generate_voiceover(script: dict, out_dir: Path) -> dict:
    """
    For "countdown" format, returns:
    {
        "hook_audio": Path,
        "fact_audio": [Path, ...],   # one per BEAT (facts can have 1-2 each), flattened in order
        "closer_audio": Path,
        "word_timestamps": {...}     # per-line word timing, for captions.py
    }

    For "hook" format, returns:
    {
        "hook_audio": Path,
        "beat_audio": [Path, ...],   # one per beat, same order as script["payoff_beats"]
        "word_timestamps": {"hook": [...], "beats": [[...], [...], ...]}
    }
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Picked once per video (not per line) so a single video doesn't have its
    # narrator change mid-clip; random rather than alternating to match how
    # orchestrator.py already picks VIDEO_FORMATS, with no extra state to persist.
    voice_id = random.choice(config.TTS_VOICE_IDS)

    if script["format"] == "hook":
        return _generate_voiceover_hook(script, out_dir, voice_id)
    return _generate_voiceover_countdown(script, out_dir, voice_id)


def _generate_voiceover_countdown(script: dict, out_dir: Path, voice_id: str) -> dict:
    hook_audio, hook_ts = _synthesize_line(script["hook"], out_dir / "hook.mp3", voice_id)

    fact_audio = []
    fact_ts = []
    for i, beat in enumerate(script_writer.flatten_countdown_facts(script)):
        audio, ts = _synthesize_line(beat["text"], out_dir / f"fact_{i}.mp3", voice_id)
        fact_audio.append(audio)
        fact_ts.append(ts)

    closer_audio, closer_ts = _synthesize_line(script["closer"], out_dir / "closer.mp3", voice_id)

    return {
        "hook_audio": hook_audio,
        "fact_audio": fact_audio,
        "closer_audio": closer_audio,
        "word_timestamps": {
            "hook": hook_ts,
            "facts": fact_ts,
            "closer": closer_ts,
        },
    }


def _generate_voiceover_hook(script: dict, out_dir: Path, voice_id: str) -> dict:
    hook_audio, hook_ts = _synthesize_line(script["hook"], out_dir / "hook.mp3", voice_id)

    beat_audio = []
    beat_ts = []
    for i, beat in enumerate(script["payoff_beats"]):
        audio, ts = _synthesize_line(beat["text"], out_dir / f"beat_{i}.mp3", voice_id)
        beat_audio.append(audio)
        beat_ts.append(ts)

    return {
        "hook_audio": hook_audio,
        "beat_audio": beat_audio,
        "word_timestamps": {"hook": hook_ts, "beats": beat_ts},
    }


def _synthesize_line(text: str, out_path: Path, voice_id: str) -> tuple[Path, list[dict]]:
    """
    Returns (path_to_audio_file, word_timestamps) where word_timestamps is a
    list like [{"word": "The", "start": 0.0, "end": 0.18}, ...]

    Retries generation up to TTS_QA_ATTEMPTS times if the audio doesn't
    transcribe back to (roughly) the intended text — see the TTS_QA_ATTEMPTS
    comment above for why that check is necessary.
    """
    audio, words = None, None
    for attempt in range(TTS_QA_ATTEMPTS):
        if config.TTS_PROVIDER == "elevenlabs":
            audio, words = _synthesize_elevenlabs(text, out_path, voice_id)
            transcript_words = _transcribe_word_timestamps(audio)
        elif config.TTS_PROVIDER == "openai":
            audio, words = _synthesize_openai(text, out_path, voice_id)
            transcript_words = words  # already came from a Whisper transcription
        else:
            raise ValueError(f"Unknown TTS_PROVIDER: {config.TTS_PROVIDER!r}")

        similarity = _transcript_similarity(text, transcript_words)
        if similarity >= _MIN_TRANSCRIPT_SIMILARITY:
            return audio, words
        print(
            f">>> WARNING: TTS output for {out_path.name!r} didn't match the "
            f"intended text closely enough (similarity {similarity:.2f}) - "
            f"regenerating (attempt {attempt + 1}/{TTS_QA_ATTEMPTS})"
        )

    print(
        f">>> WARNING: TTS QA still failing after {TTS_QA_ATTEMPTS} attempts "
        f"for {out_path.name!r}; keeping the last attempt anyway."
    )
    return audio, words


def _transcript_similarity(intended_text: str, transcript_words: list[dict]) -> float:
    intended = _WORD_RE.findall(intended_text.lower())
    if not intended:
        return 1.0
    transcribed = _WORD_RE.findall(" ".join(w["word"] for w in transcript_words).lower())
    return difflib.SequenceMatcher(a=intended, b=transcribed).ratio()


def _synthesize_elevenlabs(text: str, out_path: Path, voice_id: str) -> tuple[Path, list[dict]]:
    from elevenlabs.client import ElevenLabs

    if not voice_id:
        raise ValueError("TTS_VOICE_ID is required for the elevenlabs provider.")

    client = ElevenLabs(api_key=config.TTS_API_KEY)
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id=config.TTS_MODEL or DEFAULT_MODELS["elevenlabs"],
        output_format="mp3_44100_128",
    )

    out_path.write_bytes(base64.b64decode(response.audio_base_64))
    return out_path, _words_from_character_alignment(response.alignment)


def _words_from_character_alignment(alignment) -> list[dict]:
    """ElevenLabs gives per-character timing; group on whitespace into words."""
    words = []
    word_chars: list[str] = []
    word_start = None
    last_char_end = 0.0

    def flush():
        if word_chars:
            words.append({
                "word": "".join(word_chars),
                "start": word_start,
                "end": last_char_end,
            })
            word_chars.clear()

    for char, start, end in zip(
        alignment.characters,
        alignment.character_start_times_seconds,
        alignment.character_end_times_seconds,
    ):
        if char.isspace():
            flush()
            word_start = None
            continue
        if word_start is None:
            word_start = start
        word_chars.append(char)
        last_char_end = end
    flush()
    return words


def _synthesize_openai(text: str, out_path: Path, voice_id: str) -> tuple[Path, list[dict]]:
    import openai

    client = openai.OpenAI(api_key=config.TTS_API_KEY)
    response = client.audio.speech.create(
        model=config.TTS_MODEL or DEFAULT_MODELS["openai"],
        voice=voice_id or "alloy",
        input=text,
        response_format="mp3",
    )
    response.write_to_file(out_path)

    return out_path, _transcribe_word_timestamps(out_path)


def _transcribe_word_timestamps(audio_path: Path) -> list[dict]:
    model = _get_whisper_model()
    result = model.transcribe(str(audio_path), word_timestamps=True)

    words = []
    for segment in result["segments"]:
        for w in segment.get("words", []):
            words.append({"word": w["word"].strip(), "start": w["start"], "end": w["end"]})
    return words


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _ensure_ffmpeg_on_path()
        import whisper

        _whisper_model = whisper.load_model("base")
    return _whisper_model


def _ensure_ffmpeg_on_path() -> None:
    """
    Whisper shells out to a literal `ffmpeg` on PATH — moviepy's bundled
    imageio-ffmpeg binary doesn't satisfy that (its filename is platform-
    specific, e.g. ffmpeg-macos-aarch64-v7.1, so PATH lookup for the exact
    name "ffmpeg" still fails even with its directory on PATH). CI installs
    a real ffmpeg (see publish.yml), but local dev environments often only
    have the bundled one, so fall back to a symlink shim named "ffmpeg".
    """
    import os
    import shutil
    import tempfile

    if shutil.which("ffmpeg"):
        return
    import imageio_ffmpeg

    shim_dir = Path(tempfile.gettempdir()) / "science_shorts_ffmpeg_shim"
    shim_dir.mkdir(exist_ok=True)
    shim_path = shim_dir / "ffmpeg"
    if not shim_path.exists():
        shim_path.symlink_to(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = str(shim_dir) + os.pathsep + os.environ.get("PATH", "")


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script — no standalone test data here.")
