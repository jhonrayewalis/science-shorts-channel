"""
Shared config and constants for the pipeline. Loads secrets from .env locally,
or from real environment variables when running in GitHub Actions.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
RENDER_DIR = ROOT / "render"  # gitignored scratch dir for in-progress video files
ASSETS_DIR = ROOT / "assets"

USED_TOPICS_PATH = STATE_DIR / "used_topics.json"
UPLOAD_LOG_PATH = STATE_DIR / "upload_log.json"

# --- Video spec ---
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
MAX_DURATION_SECONDS = 59  # 1s of margin under the 60s Shorts hard ceiling
FACTS_PER_VIDEO = 5

# --- Video formats ---
# "countdown": hook + N ranked facts (each fact is 1-2 "beats" — a 2nd beat
# only when a fact has genuine extra depth to add) + closer. "hook": single
# hook + payoff beats, no countdown. Both scale actual duration to how much
# real content the topic supports, up to MAX_DURATION_SECONDS — more beats,
# not slower pacing, is what makes a video longer; a thin topic should come
# out shorter rather than being padded toward the ceiling. orchestrator.py
# picks between the two formats at random each run so we can compare
# performance.
VIDEO_FORMATS = ("countdown", "hook")

# --- Seed categories for topic discovery ---
SCIENCE_CATEGORIES = [
    "space and astronomy",
    "deep ocean",
    "human body",
    "physics",
    "ancient history",
    "animal behavior",
    "the brain",
    "geology and volcanoes",
    "weather and climate",
    "chemistry in everyday life",
]

# --- Env vars ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "")  # optional override; provider-specific default used if blank

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")
TTS_API_KEY = os.getenv("TTS_API_KEY")
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID")
TTS_VOICE_ID_2 = os.getenv("TTS_VOICE_ID_2", "")  # optional; adds a second voice to pick from at random
TTS_VOICE_IDS = [v for v in [TTS_VOICE_ID, TTS_VOICE_ID_2] if v] or [TTS_VOICE_ID]  # preserve prior None-passthrough behavior (openai provider defaults to "alloy") when unset
TTS_MODEL = os.getenv("TTS_MODEL", "")  # optional override; provider-specific default used if blank

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

IMAGE_GEN_PROVIDER = os.getenv("IMAGE_GEN_PROVIDER", "replicate")
IMAGE_GEN_API_KEY = os.getenv("IMAGE_GEN_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "")  # optional override; provider-specific default used if blank

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

UPLOAD_VISIBILITY = os.getenv("UPLOAD_VISIBILITY", "private")
REQUIRE_MANUAL_APPROVAL = os.getenv("REQUIRE_MANUAL_APPROVAL", "true").lower() == "true"

# This channel's format (TTS narration of an AI-assisted script over stock
# photos / illustrative AI-generated stills, no realistic depiction of real
# people/places/events) falls under YouTube's own documented examples of
# content that does NOT require the "altered or synthetic content"
# disclosure. Flip this if that ever changes (e.g. photorealistic AI video
# of real-looking people/events) — see status.containsSyntheticMedia at
# https://developers.google.com/youtube/v3/docs/videos#status.containsSyntheticMedia
CONTAINS_SYNTHETIC_MEDIA = os.getenv("CONTAINS_SYNTHETIC_MEDIA", "false").lower() == "true"
