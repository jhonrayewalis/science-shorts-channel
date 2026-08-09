"""
Stage 9: Orchestrator.

Chains all pipeline stages together in order, with a manual-approval gate
before upload (controlled by config.REQUIRE_MANUAL_APPROVAL).

This is deliberately the LAST file to build — get every stage above working
independently first (each has a `python -m pipeline.<stage>` manual test),
then wire them together here.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config, topic_discovery, script_writer, tts, visuals, assemble, captions, metadata, upload


def log_upload(topic: dict, video_id: str) -> None:
    if not config.UPLOAD_LOG_PATH.exists():
        data = {"uploads": []}
    else:
        data = json.loads(config.UPLOAD_LOG_PATH.read_text())

    data["uploads"].append({
        "topic": topic["topic"],
        "category": topic["category"],
        "video_id": video_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })
    config.UPLOAD_LOG_PATH.write_text(json.dumps(data, indent=2))


def run() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work_dir = config.RENDER_DIR / run_id

    topic = topic_discovery.pick_topic()
    print(f"[1/8] Topic: {topic}")

    script = script_writer.write_script(topic)
    script = script_writer.verify_facts(script)
    print("[2/8] Script written and fact-checked")

    audio = tts.generate_voiceover(script, work_dir / "audio")
    print("[3/8] Voiceover generated")

    vis = visuals.source_visuals(script, work_dir / "visuals")
    print("[4/8] Visuals sourced")

    raw_video = assemble.assemble_video(script, audio, vis, work_dir / "assembled.mp4")
    print("[5/8] Video assembled")

    final_video = captions.burn_captions(raw_video, audio["word_timestamps"], work_dir / "final.mp4")
    print("[6/8] Captions burned in")

    meta = metadata.generate_metadata(script, topic)
    print(f"[7/8] Metadata generated: {meta['title']}")

    if config.REQUIRE_MANUAL_APPROVAL:
        print(f"\n>>> Approval gate: review {final_video} before continuing.")
        print(">>> Set REQUIRE_MANUAL_APPROVAL=false once you trust the pipeline.")
        return  # stop here — a human reviews the file, then re-runs with upload enabled,
                # OR you extend this to notify a webhook and wait for approval

    video_id = upload.upload_video(final_video, meta)
    log_upload(topic, video_id)
    print(f"[8/8] Uploaded: https://youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    run()
