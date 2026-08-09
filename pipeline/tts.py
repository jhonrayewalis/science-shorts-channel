"""
Stage 3: Voiceover.

Converts each script line (hook, facts, closer) to audio, and returns
word-level timestamps so captions.py can burn in synced subtitles.

TODO (Claude Code): implement `_synthesize_line` against config.TTS_PROVIDER.
ElevenLabs and OpenAI TTS both support returning timing/alignment data —
check the provider's docs for the exact response shape and adapt
`_extract_word_timestamps` accordingly.
"""
from pathlib import Path

from pipeline import config


def generate_voiceover(script: dict, out_dir: Path) -> dict:
    """
    Returns:
    {
        "hook_audio": Path,
        "fact_audio": [Path, ...],   # one per fact, same order as script["facts"]
        "closer_audio": Path,
        "word_timestamps": {...}     # per-line word timing, for captions.py
    }
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    hook_audio, hook_ts = _synthesize_line(script["hook"], out_dir / "hook.mp3")

    fact_audio = []
    fact_ts = []
    for i, fact in enumerate(script["facts"]):
        audio, ts = _synthesize_line(fact["text"], out_dir / f"fact_{i}.mp3")
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


def _synthesize_line(text: str, out_path: Path) -> tuple[Path, list[dict]]:
    """
    Returns (path_to_audio_file, word_timestamps) where word_timestamps is a
    list like [{"word": "The", "start": 0.0, "end": 0.18}, ...]
    """
    raise NotImplementedError(
        f"Wire up {config.TTS_PROVIDER} here. See config.TTS_API_KEY / config.TTS_VOICE_ID."
    )


if __name__ == "__main__":
    print("Run this via orchestrator.py with a real script — no standalone test data here.")
