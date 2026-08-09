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
TARGET_DURATION_SECONDS = 50  # keep comfortably under the 60s Shorts ceiling
FACTS_PER_VIDEO = 5

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

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")
TTS_API_KEY = os.getenv("TTS_API_KEY")
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

IMAGE_GEN_PROVIDER = os.getenv("IMAGE_GEN_PROVIDER")
IMAGE_GEN_API_KEY = os.getenv("IMAGE_GEN_API_KEY")

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

UPLOAD_VISIBILITY = os.getenv("UPLOAD_VISIBILITY", "private")
REQUIRE_MANUAL_APPROVAL = os.getenv("REQUIRE_MANUAL_APPROVAL", "true").lower() == "true"
