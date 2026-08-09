# Science Shorts Channel — Autonomous Pipeline

Faceless YouTube Shorts channel: 5-fact science videos (space, ocean, physics,
human body, history, animals), narrated with original scripted commentary
over stock/AI-generated visuals. See `ARCHITECTURE.md` (one level up, or copy
it into this folder) for the full design rationale.

This repo is a **scaffold**, not a finished pipeline — every stage in
`pipeline/` has a working structure and a clear `TODO` marking what needs a
real API integration. Build and test each stage one at a time.

## 1. Get this into GitHub Desktop

1. Create a new (empty) repository on GitHub.
2. In GitHub Desktop: File → Clone Repository → your new repo.
3. Copy everything in this scaffold folder into that cloned folder.
4. Commit + push once, so Claude Code has something to work from.

## 2. Local setup

```bash
cd path/to/cloned-repo
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env with real API keys as you get each stage working
```

## 3. Build order (hand this to Claude Code, one stage at a time)

Open a terminal in the repo folder and run `claude`, then work through:

1. `pipeline/topic_discovery.py` — get topic generation working, test with
   `python -m pipeline.topic_discovery`
2. `pipeline/script_writer.py` — script generation + fact verification,
   test with `python -m pipeline.script_writer`
3. `pipeline/tts.py` — voiceover + word timestamps
4. `pipeline/visuals.py` — stock sourcing + AI fallback
5. `pipeline/assemble.py` — get ONE full video rendering locally
6. `pipeline/captions.py` — burn captions onto the rendered video
7. `pipeline/metadata.py` + `pipeline/upload.py` — wire up YouTube OAuth,
   test an upload with `UPLOAD_VISIBILITY=private` in `.env`
8. `pipeline/orchestrator.py` — already wired to call everything above in
   order; just needs the stages above to actually work
9. `.github/workflows/publish.yml` — once `python -m pipeline.orchestrator`
   works end-to-end locally, add your keys as GitHub repo secrets (Settings →
   Secrets and variables → Actions) and the workflow will run on schedule

Test each stage standalone before chaining the next one in — don't debug the
whole pipeline at once.

## 4. Before going fully autonomous

- Keep `REQUIRE_MANUAL_APPROVAL=true` and `UPLOAD_VISIBILITY=private` for the
  first several runs. Actually watch the videos and read the facts.
- Confirm the YouTube upload correctly sets the altered/synthetic content
  disclosure — check this against the current YouTube Data API docs, not
  just this scaffold, since API fields can change.
- Only flip to `REQUIRE_MANUAL_APPROVAL=false` / `UPLOAD_VISIBILITY=public`
  once you've reviewed enough output to trust it unattended.

## 5. One-time YouTube OAuth setup

You need a refresh token before `upload.py` can work headlessly:

1. Create a project in Google Cloud Console, enable the YouTube Data API v3.
2. Create OAuth 2.0 credentials (Desktop app type).
3. Run a local consent flow once (Claude Code can help write this script) to
   authorize your channel and capture the refresh token.
4. Put `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and
   `YOUTUBE_REFRESH_TOKEN` in `.env` locally and as GitHub Actions secrets.

This step only happens once — after that, the refresh token lets the
pipeline mint new access tokens on every run without you logging in again.
