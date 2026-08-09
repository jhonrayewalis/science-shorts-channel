# Autonomous YouTube Shorts Channel — Architecture

**Format:** Vertical Shorts (under 60s), faceless narrated
**Niche:** Science facts — space, ocean, physics, human body, history, animals (original scripted commentary, illustrative AI/stock visuals)
**Autonomy target:** Scheduled, unattended publishing via GitHub Actions, with a manual approval gate for the first weeks

---

## 1. Concept

Each video is a "Top 5 mind-blowing facts about black holes" / "5 things you didn't know about the ocean" style Short. Fully self-contained content — no dependency on external trends, no third-party media, no real identifiable people. This is the lowest-risk, easiest-to-automate niche of the options considered: evergreen topic supply, zero copyright exposure, zero accuracy-about-real-people risk.

---

## 2. Pipeline stages

| # | Stage | What it does | Suggested tool/API |
|---|-------|---------------|---------------------|
| 1 | Topic discovery | LLM generates a topic + 5 sub-facts from a rotating seed list of science categories (space, ocean, physics, human body, ancient history, animals, etc.). Deduplicates against a running list of used topics/facts. No external scraping needed. | LLM call + a `used_topics.json` state file |
| 2 | Script generation | LLM writes a structured ranked script: hook (first 2-3s), 5 ranked items with a line each, closer. Output as JSON (text + est. duration per line), not raw prose. | Claude/OpenAI API |
| 3 | Voiceover | Converts each script line to audio, returns word-level timestamps for captions. | ElevenLabs or OpenAI TTS |
| 4 | Visual sourcing | For each fact, pulls stock footage/images matching its *topic keywords* (e.g. nebulae, deep-sea creatures, brain scans). AI image generation as fallback when no stock match exists. | Pexels/Pixabay API (free) + fallback image-gen API |
| 5 | Assembly | Composites voiceover + visuals + on-screen rank badges (5→1 countdown graphics) + background music into a 1080×1920 video. A templated approach (consistent rank-card design) works better here than raw slideshow. | ffmpeg via Python (MoviePy), or Remotion if you want React-templated graphics |
| 6 | Captions | Burns in word-synced captions from the TTS timestamps. | Same TTS timing data, or Whisper as fallback |
| 7 | Metadata | Generates title, description, tags, hashtags from the script. | LLM |
| 8 | Upload | Resumable upload via YouTube Data API v3, with the "altered/synthetic content" disclosure flag set. | YouTube Data API v3 + OAuth2 |
| 9 | Logging | Appends topic, video ID, and timestamp to the state file; commits back to the repo. | Git |

---

## 3. Repo structure

```
/pipeline
  topic_discovery.py
  script_writer.py
  tts.py
  visuals.py
  assemble.py
  captions.py
  metadata.py
  upload.py
  orchestrator.py
/state
  used_topics.json
  upload_log.json
/assets
  music/ (royalty-free background tracks)
  fonts/ (caption + rank-badge fonts)
.github/workflows/publish.yml
.env.example
README.md
```

---

## 4. Secrets (GitHub Actions secrets, never committed)

- `LLM_API_KEY` (Claude or OpenAI)
- `TTS_API_KEY`
- `STOCK_MEDIA_API_KEY` (Pexels/Pixabay)
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

The YouTube refresh token is obtained once via a local OAuth consent flow (you approve it in a browser one time), then stored as a secret — the pipeline uses it to mint new access tokens on every run without you logging in again.

---

## 5. Scheduling & quota math

- YouTube Data API default quota: 10,000 units/day. One upload = ~1,600 units → hard ceiling of ~6/day without a quota increase request.
- Recommended cadence: **1 upload/day** to start. This keeps you well under quota, gives you time to review output quality, and avoids anything that reads as "mass-produced" under YouTube's inauthentic-content policy.
- GitHub Actions cron trigger (`schedule:` in the workflow YAML) runs the orchestrator daily at a fixed time.

---

## 6. Fact accuracy (important for a science niche)

LLMs hallucinate — confidently stating wrong facts is the single biggest reputational and demonetization risk for a facts/education channel, more than any copyright issue. Two safeguards worth building in from the start:

- **Grounding:** have the script-writer prompt explicitly require citing where each fact comes from, and consider a lightweight verification pass (a second LLM call or web-search check) before a script proceeds to voiceover.
- **Human spot-checks:** during the approval-gate period (see below), actually read the facts, not just watch for production quality — this is the main thing worth your manual review time even after other checks become routine.

---

## 7. Human-in-the-loop gate (recommended for first 2-4 weeks)

Rather than auto-uploading immediately, have the workflow stop after assembly and either:
- Post the finished video + metadata to a Slack/email/Discord webhook for a thumbs up/down, or
- Upload as **unlisted/private** and require a manual "make public" step

Once you trust the output consistently, remove the gate and let it go fully autonomous.

---

## 8. Rough cost stack (per video, at low volume)

- LLM calls (topic + script + metadata): a few cents
- TTS (~150 words): a few cents
- Stock media: free tier covers this at 1/day
- GitHub Actions: free tier (2,000 min/month) is more than enough at 1 upload/day
- **Total: well under $1/video** at this scale

---

## 9. Build order (what to hand Claude Code, in sequence)

1. Repo scaffold + `.env.example` + README
2. `script_writer.py` — get script generation working with a hardcoded test topic first
3. `tts.py` — voiceover + timestamp extraction
4. `visuals.py` — stock sourcing keyed off script keywords
5. `assemble.py` — get one full video rendering locally before touching upload
6. `captions.py` — burn in captions on the rendered video
7. `metadata.py` + `upload.py` — wire up YouTube OAuth and test an upload as **private**
8. `topic_discovery.py` — automate the topic-picking step last, once everything downstream works on a manual topic
9. `orchestrator.py` — chain it all together with the approval gate
10. `.github/workflows/publish.yml` — move it from "runs on my laptop" to "runs on a schedule"

Build and test each stage locally with Claude Code before wiring the next one in — don't build the full chain blind.
