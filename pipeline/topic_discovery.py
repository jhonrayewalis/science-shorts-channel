"""
Stage 1: Topic discovery.

Picks a science sub-topic + a specific angle (e.g. category "space and astronomy"
-> topic "why black holes glow at the edges"), checked against previously used
topics so the channel doesn't repeat itself.

No external scraping needed for this niche — topics are LLM-generated from a
seed category list (see config.SCIENCE_CATEGORIES), which keeps this stage
simple and dependency-free.

TODO (Claude Code): implement `_call_llm` using config.LLM_PROVIDER /
config.LLM_API_KEY. Test this file standalone first, with a hardcoded
category, before wiring it into the orchestrator.
"""
import json
import random

from pipeline import config


def load_used_topics() -> list[str]:
    if not config.USED_TOPICS_PATH.exists():
        return []
    data = json.loads(config.USED_TOPICS_PATH.read_text())
    return data.get("used_topics", [])


def save_used_topic(topic: str) -> None:
    data = {"used_topics": load_used_topics() + [topic]}
    config.USED_TOPICS_PATH.write_text(json.dumps(data, indent=2))


def pick_topic() -> dict:
    """
    Returns a dict like:
    {
        "category": "deep ocean",
        "topic": "creatures that survive without sunlight",
    }
    """
    used = load_used_topics()
    category = random.choice(config.SCIENCE_CATEGORIES)

    # TODO: replace with a real LLM call. Prompt should:
    #   - ask for ONE specific, narrow topic within `category`
    #   - explicitly exclude anything in `used` (pass the list in the prompt)
    #   - return a short topic string, not a full script
    topic = _call_llm(category=category, exclude=used)

    save_used_topic(topic)
    return {"category": category, "topic": topic}


def _call_llm(category: str, exclude: list[str]) -> str:
    raise NotImplementedError(
        "Wire up your LLM provider here. See config.LLM_PROVIDER / config.LLM_API_KEY."
    )


if __name__ == "__main__":
    # Quick manual test: python -m pipeline.topic_discovery
    result = pick_topic()
    print(json.dumps(result, indent=2))
