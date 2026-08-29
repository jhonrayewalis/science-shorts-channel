"""
Stage 9: Orchestrator.

Chains all pipeline stages together in order, with a manual-approval gate
before upload (controlled by config.REQUIRE_MANUAL_APPROVAL).

This is deliberately the LAST file to build — get every stage above working
independently first (each has a `python -m pipeline.<stage>` manual test),
then wire them together here.

When the approval gate stops a run, topic/script/metadata are saved to disk
(pending_review.json) alongside final.mp4, so a separate later step —
upload_pending(), wired up to `--upload-pending` below and to
.github/workflows/approve.yml — can publish that exact reviewed video
without regenerating anything (a fresh run() call would pick a new random
topic and script, not resume the one that was actually reviewed).
"""
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config, topic_discovery, script_writer, tts, visuals, assemble, captions, metadata, upload


def log_upload(topic: dict, script: dict, video_id: str) -> None:
    if not config.UPLOAD_LOG_PATH.exists():
        data = {"uploads": []}
    else:
        data = json.loads(config.UPLOAD_LOG_PATH.read_text())

    data["uploads"].append({
        "topic": topic["topic"],
        "category": topic["category"],
        "video_id": video_id,
        "format": script["format"],
        "hook_style": script.get("hook_style"),  # only set for "hook" format
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })
    config.UPLOAD_LOG_PATH.write_text(json.dumps(data, indent=2))


def upload_pending(run_dir: Path) -> str:
    """
    Uploads an already-rendered, already-reviewed run without regenerating
    anything. run_dir must contain final.mp4 and pending_review.json, both
    written by run() before it stopped at the approval gate.
    """
    pending = json.loads((run_dir / "pending_review.json").read_text())
    video_id = upload.upload_video(run_dir / "final.mp4", pending["metadata"])
    log_upload(pending["topic"], pending["script"], video_id)
    print(f"Uploaded: https://youtube.com/watch?v={video_id}")
    return video_id


def run() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work_dir = config.RENDER_DIR / run_id

    topic = topic_discovery.pick_topic()
    print(f"[1/8] Topic: {topic}")

    # Alternate formats at random for now so we can compare how each performs.
    video_format = random.choice(config.VIDEO_FORMATS)
    script = script_writer.write_script(topic, video_format=video_format)
    script = script_writer.verify_facts(script)
    print(f"[2/8] Script written ({video_format} format) and fact-checked")

    if script["flagged_facts"] and not config.REQUIRE_MANUAL_APPROVAL:
        # Unattended run with claims fact-checked as inaccurate/disputed (not
        # merely a hedged theory, which verify_facts already rewrote in
        # place) — refuse to auto-publish. Raising fails the job, and
        # retry-on-failure.yml reruns it fresh with a new random topic/script
        # rather than retrying this same flagged one.
        raise RuntimeError(
            f"Refusing to auto-publish: fact-check flagged {script['flagged_facts']} as "
            "inaccurate or disputed. Re-run for a fresh topic, or set "
            "REQUIRE_MANUAL_APPROVAL=true to review flagged claims by hand."
        )

    audio = tts.generate_voiceover(script, work_dir / "audio")
    print("[3/8] Voiceover generated")

    vis = visuals.source_visuals(script, work_dir / "visuals")
    print("[4/8] Visuals sourced")

    raw_video, music_track = assemble.assemble_video(script, audio, vis, work_dir / "assembled.mp4")
    print("[5/8] Video assembled")

    final_video = captions.burn_captions(raw_video, script, audio, work_dir / "final.mp4")
    print("[6/8] Captions burned in")

    # Warns (doesn't raise) if music_track has no attribution.json entry —
    # see music_attribution.py.
    meta = metadata.generate_metadata(script, topic, music_track)
    print(f"[7/8] Metadata generated: {meta['title']}")

    (work_dir / "pending_review.json").write_text(
        json.dumps({"topic": topic, "script": script, "metadata": meta}, indent=2)
    )

    if config.REQUIRE_MANUAL_APPROVAL:
        print(f"\n>>> Approval gate: review {final_video} before continuing.")
        print(f">>> To publish this exact video after reviewing it, run:")
        print(f">>>   python -m pipeline.orchestrator --upload-pending {work_dir}")
        print(">>> Set REQUIRE_MANUAL_APPROVAL=false to skip this gate on future runs.")
        return

    video_id = upload.upload_video(final_video, meta)
    log_upload(topic, script, video_id)
    print(f"[8/8] Uploaded: https://youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--upload-pending":
        upload_pending(Path(sys.argv[2]))
    else:
        run()
