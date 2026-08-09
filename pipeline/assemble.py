"""
Stage 5: Assembly.

Composites voiceover + visuals + on-screen rank badges (5 -> 1 countdown) +
background music into a single 1080x1920 video, before captions are burned
in by captions.py.

TODO (Claude Code): implement using MoviePy (or swap for a Remotion-based
approach if you want more polished templated graphics). Start by getting
ONE segment (e.g. just the hook) rendering correctly before chaining all of
them together.
"""
from pathlib import Path

from pipeline import config


def assemble_video(script: dict, audio: dict, visuals: dict, out_path: Path) -> Path:
    """
    audio: output of tts.generate_voiceover()
    visuals: output of visuals.source_visuals()
    Returns the path to the assembled (pre-caption) video file.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    segments = []
    segments.append(_build_segment(
        visual=visuals["hook"][0], audio_path=audio["hook_audio"], rank_label=None
    ))
    for i, fact in enumerate(script["facts"]):
        segments.append(_build_segment(
            visual=visuals[f"fact_{i}"][0],
            audio_path=audio["fact_audio"][i],
            rank_label=str(fact["rank"]),
        ))
    segments.append(_build_segment(
        visual=visuals["closer"][0], audio_path=audio["closer_audio"], rank_label=None
    ))

    _concatenate_and_export(segments, out_path)
    return out_path


def _build_segment(visual: Path, audio_path: Path, rank_label: str | None):
    """
    Build one MoviePy clip: visual (Ken-Burns-panned if it's a still image) +
    its matching audio + an optional rank-number overlay graphic.
    """
    raise NotImplementedError("Implement with MoviePy: ImageClip/VideoFileClip + AudioFileClip.")


def _concatenate_and_export(segments, out_path: Path) -> None:
    raise NotImplementedError(
        f"Concatenate segments and export at {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}, "
        f"{config.VIDEO_FPS}fps, plus a background music track at low volume."
    )


if __name__ == "__main__":
    print("Run this via orchestrator.py with real script/audio/visuals.")
