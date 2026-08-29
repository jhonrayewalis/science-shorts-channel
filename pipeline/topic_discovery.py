"""
Stage 1: Topic discovery.

Picks a science sub-topic + a specific angle (e.g. category "space and astronomy"
-> topic "why black holes glow at the edges"), checked against previously used
topics so the channel doesn't repeat itself.

No external scraping needed for this niche — topics are LLM-generated from a
seed category list (see config.SCIENCE_CATEGORIES), which keeps this stage
simple and dependency-free.
"""
import json
import random

from pipeline import config, llm_client


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

    topic = _call_llm(category=category, exclude=used)
    if topic in used:
        # Model ignored the exclusion list once — retry with the near-miss added.
        topic = _call_llm(category=category, exclude=used + [topic])

    save_used_topic(topic)
    return {"category": category, "topic": topic}


def _build_prompt(category: str, exclude: list[str]) -> str:
    exclusions = "\n".join(f"- {t}" for t in exclude) if exclude else "(none yet)"
    return (
        "You are picking a topic for a science-facts YouTube Short in the "
        f'category "{category}".\n\n'
        "Return ONE specific, narrow topic suitable for a '5 facts about X' "
        "video. It should be concrete enough to support 5 distinct, "
        'verifiable facts, but narrow enough to feel fresh (e.g. "why black '
        'holes glow at the edges" rather than just "black holes").\n\n'
        "This channel's credibility depends on not presenting speculation as "
        "settled science, so avoid topics whose central claim is purely "
        "speculative, philosophical, or untestable with no direct observational "
        "evidence (e.g. multiverse theory, simulation theory, string theory's "
        "extra dimensions, fringe/minority-view interpretations). A topic built "
        "around a genuine, evidence-backed leading theory that just isn't fully "
        "confirmed yet (e.g. a specific mechanism proposed for an observed "
        "phenomenon) is still fine — the script will frame it as a theory, not "
        "as settled fact.\n\n"
        "Do NOT repeat or closely overlap with any of these already-used "
        f"topics:\n{exclusions}\n\n"
        "Respond with ONLY the topic as a short phrase (under 12 words). "
        "No quotes, no numbering, no explanation."
    )


def _call_llm(category: str, exclude: list[str]) -> str:
    prompt = _build_prompt(category, exclude)
    raw = llm_client.complete(prompt, max_tokens=60)
    return raw.strip().strip('"').strip("'")


if __name__ == "__main__":
    # Quick manual test: python -m pipeline.topic_discovery
    result = pick_topic()
    print(json.dumps(result, indent=2))
