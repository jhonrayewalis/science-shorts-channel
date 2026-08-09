"""
Stage 2: Script generation.

Turns a topic into a structured script: a hook line, N fact lines (see
config.FACTS_PER_VIDEO), and a closer. Output is JSON, not prose, so every
downstream stage (TTS, visuals, assembly) can work off a consistent contract.

TODO (Claude Code): implement `_call_llm`. The prompt should explicitly:
  - require accuracy and ask the model to only state facts it's confident about
  - ask for a `source_hint` per fact (a rough citation/topic area) to support
    the verification pass in `verify_facts`
  - keep each line short enough to read aloud in ~6-8 seconds
"""
import json

from pipeline import config

SCRIPT_SCHEMA_EXAMPLE = {
    "hook": "The ocean has swallowed more secrets than space has stars.",
    "facts": [
        {
            "rank": 5,
            "text": "...",
            "visual_keywords": ["bioluminescent fish", "deep sea"],
            "source_hint": "NOAA Ocean Exploration",
        }
        # ... FACTS_PER_VIDEO total
    ],
    "closer": "Which one surprised you most? Follow for more.",
}


def write_script(topic: dict) -> dict:
    """
    topic: the dict returned by topic_discovery.pick_topic()
    Returns a dict matching SCRIPT_SCHEMA_EXAMPLE.
    """
    script = _call_llm(topic)
    _validate_script(script)
    return script


def verify_facts(script: dict) -> dict:
    """
    Lightweight accuracy pass. Recommended before this script proceeds to TTS.

    TODO: implement one of:
      - a second LLM call asking it to fact-check its own output against
        what it knows, flagging low-confidence claims
      - a web-search-backed check for each fact's source_hint

    Return the script with any flagged facts marked, so orchestrator.py can
    decide whether to reject/regenerate.
    """
    raise NotImplementedError("Implement a fact-check pass before going live.")


def _validate_script(script: dict) -> None:
    assert "hook" in script and script["hook"], "Script missing hook"
    assert len(script.get("facts", [])) == config.FACTS_PER_VIDEO, (
        f"Expected {config.FACTS_PER_VIDEO} facts, got {len(script.get('facts', []))}"
    )
    assert "closer" in script and script["closer"], "Script missing closer"


def _call_llm(topic: dict) -> dict:
    raise NotImplementedError(
        "Wire up your LLM provider here. Return JSON matching SCRIPT_SCHEMA_EXAMPLE."
    )


if __name__ == "__main__":
    # Quick manual test with a hardcoded topic:
    test_topic = {"category": "deep ocean", "topic": "creatures that survive without sunlight"}
    print(json.dumps(write_script(test_topic), indent=2))
