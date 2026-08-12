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
from pathlib import Path

from pipeline import config, script_writer

DEFAULT_MODELS = {
    "elevenlabs": "eleven_multilingual_v2",
    "openai": "gpt-4o-mini-tts",
}

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

    if script["format"] == "hook":
        return _generate_voiceover_hook(script, out_dir)
    return _generate_voiceover_countdown(script, out_dir)


def _generate_voiceover_countdown(script: dict, out_dir: Path) -> dict:
    hook_audio, hook_ts = _synthesize_line(script["hook"], out_dir / "hook.mp3")

    fact_audio = []
    fact_ts = []
    for i, beat in enumerate(script_writer.flatten_countdown_facts(script)):
        audio, ts = _synthesize_line(beat["text"], out_dir / f"fact_{i}.mp3")
        fact_audio.append(audio)
        fact_ts.append(ts)

    closer_audio, closer_ts = _synthesize_line(script["closer"], out_dir / "closer.mp3")

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


def _generate_voiceover_hook(script: dict, out_dir: Path) -> dict:
    hook_audio, hook_ts = _synthesize_line(script["hook"], out_dir / "hook.mp3")

    beat_audio = []
    beat_ts = []
    for i, beat in enumerate(script["payoff_beats"]):
        audio, ts = _synthesize_line(beat["text"], out_dir / f"beat_{i}.mp3")
        beat_audio.append(audio)
        beat_ts.append(ts)

    return {
        "hook_audio": hook_audio,
        "beat_audio": beat_audio,
        "word_timestamps": {"hook": hook_ts, "beats": beat_ts},
    }


def _synthesize_line(text: str, out_path: Path) -> tuple[Path, list[dict]]:
    """
    Returns (path_to_audio_file, word_timestamps) where word_timestamps is a
    list like [{"word": "The", "start": 0.0, "end": 0.18}, ...]
    """
    if config.TTS_PROVIDER == "elevenlabs":
        return _synthesize_elevenlabs(text, out_path)
    elif config.TTS_PROVIDER == "openai":
        return _synthesize_openai(text, out_path)
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {config.TTS_PROVIDER!r}")


def _synthesize_elevenlabs(text: str, out_path: Path) -> tuple[Path, list[dict]]:
    from elevenlabs.client import ElevenLabs

    if not config.TTS_VOICE_ID:
        raise ValueError("TTS_VOICE_ID is required for the elevenlabs provider.")

    client = ElevenLabs(api_key=config.TTS_API_KEY)
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=config.TTS_VOICE_ID,
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


def _synthesize_openai(text: str, out_path: Path) -> tuple[Path, list[dict]]:
    import openai

    client = openai.OpenAI(api_key=config.TTS_API_KEY)
    response = client.audio.speech.create(
        model=config.TTS_MODEL or DEFAULT_MODELS["openai"],
        voice=config.TTS_VOICE_ID or "alloy",
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
        import whisper

        _whisper_model = whisper.load_model("base")
    return _whisper_model


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script — no standalone test data here.")
