"""
Stage 2: Script generation.

Turns a topic into a structured script. Two formats — orchestrator.py picks
between them at random each run:

- "countdown": a hook line, N ranked facts (see config.FACTS_PER_VIDEO,
  5->1), and a closer. Each fact is 1-2 "beats" — a 2nd beat only when the
  fact has genuine extra depth (mechanism, why it matters, a standout
  detail) worth a beat of its own, not the same point restated slower.
- "hook": a single short, punchy hook (in one of several rotating opener
  styles, not just "what if" every time) plus a payoff broken into beats,
  same idea as countdown facts. No countdown, no closer.

Every beat (hook, fact beat, payoff beat, closer) becomes its own audio
clip and its own image in assemble.py, so video length and "how many image
cuts happen" are both direct, coupled consequences of how many beats got
written — not something tuned separately by slowing down pacing.

Output is JSON, not prose, so every downstream stage (TTS, visuals,
assembly, captions) can work off a consistent contract, keyed by
script["format"].
"""
import json
import random
import re

from pipeline import config, llm_client

# LLMs sometimes write em/en-dashes glued directly to words with no
# surrounding space (e.g. "all—they"). That breaks caption word-boundary
# detection (TTS timestamps treat it as one "word") and the dash glyph
# often isn't in Pillow's default font (renders as a missing-glyph box).
# Normalizing here fixes it once for every downstream consumer (TTS
# pronunciation too) instead of working around it in captions.py.
_DASH_RUN = re.compile(r"\s*[–—]\s*")

MAX_EXTRA_BEATS_PER_FACT = 1  # a fact may have at most this many beats beyond its first
MAX_FACTS_WITH_EXTRA_BEAT = 3  # at most this many of the FACTS_PER_VIDEO facts may use it

SCRIPT_SCHEMA_EXAMPLE = {
    "format": "countdown",
    "hook": "The ocean has swallowed more secrets than space has stars.",
    "hook_visual_keywords": ["bioluminescent deep sea creature", "dark ocean trench"],
    "hook_prefer_ai_visual": False,
    "hook_is_internal_anatomy": False,
    "facts": [
        {
            "rank": 5,
            "beats": [
                {
                    "text": "...",
                    "visual_keywords": ["bioluminescent fish", "deep sea"],
                    "source_hint": "NOAA Ocean Exploration",
                    "prefer_ai_visual": False,
                    "is_internal_anatomy": False,
                }
                # 1 beat for a simple, self-contained fact. 2 beats only
                # when there's genuinely more to say (see prompt) — the 2nd
                # beat is real new information, not the 1st beat restated.
            ],
        }
        # ... FACTS_PER_VIDEO total
    ],
    "closer": "Which one surprised you most? Follow for more.",
}

HOOK_SCRIPT_SCHEMA_EXAMPLE = {
    "format": "hook",
    "hook_style": "curiosity_gap",
    "hook": "Why does your brain delete most of your dreams the second you wake up?",
    "hook_visual_keywords": ["person waking up startled in bed", "fading dream imagery"],
    "hook_is_internal_anatomy": False,
    "payoff_beats": [
        {
            "text": "...",
            "visual_keywords": ["hippocampus, cross-section of a real brain model"],
            "is_internal_anatomy": True,
        }
        # 2-8 total depending on how much real depth the topic has — one
        # per payoff sentence — each gets its own AI-generated image,
        # cutting to a new one as the narration moves through the beats
        # (instead of one static image held for the whole video).
    ],
    "source_hint": "sleep neuroscience research",
}

HOOK_STYLES = [
    {
        "name": "curiosity_gap",
        "instruction": (
            "Open with a question that creates a knowledge gap the viewer needs filled "
            '(e.g. "Why does X do Y?").'
        ),
    },
    {
        "name": "myth_bust",
        "instruction": (
            "Open by directly contradicting a common belief "
            '(e.g. "Everything you were taught about X is wrong.").'
        ),
    },
    {
        "name": "surprising_claim",
        "instruction": (
            "Open with a bold, specific, surprising factual claim stated directly, no "
            "question mark."
        ),
    },
    {
        "name": "explainer_setup",
        "instruction": (
            'Open with a "here\'s why X happens" or "here\'s what\'s actually going on with '
            'X" setup that promises an explanation.'
        ),
    },
    {
        "name": "what_if",
        "instruction": 'Open with a "what would happen if..." hypothetical scenario.',
    },
]


def write_script(topic: dict, video_format: str = "countdown") -> dict:
    """
    topic: the dict returned by topic_discovery.pick_topic()
    video_format: one of config.VIDEO_FORMATS
    Returns a dict matching SCRIPT_SCHEMA_EXAMPLE or HOOK_SCRIPT_SCHEMA_EXAMPLE.
    """
    if video_format not in config.VIDEO_FORMATS:
        raise ValueError(f"Unknown video_format {video_format!r}, expected one of {config.VIDEO_FORMATS}")

    if video_format == "hook":
        script = _call_hook_llm(topic)
        _sanitize_script_text(script)
        _validate_hook_script(script)
    else:
        script = _call_llm(topic)
        _sanitize_script_text(script)
        _validate_countdown_script(script)

    script["format"] = video_format  # enforce in code rather than trusting the model to echo it back
    return script


def flatten_countdown_facts(script: dict) -> list[dict]:
    """
    Flattens script["facts"] (each {rank, beats: [...]}) into an ordered
    flat list of beat dicts, for stages (tts, visuals) that just need "the
    next segment" without caring which fact/beat it came from. Facts are
    already in rank 5->1 order.
    """
    return [beat for fact in script["facts"] for beat in fact["beats"]]


def _sanitize_script_text(script: dict) -> None:
    for key in ("hook", "closer"):
        if isinstance(script.get(key), str):
            script[key] = _sanitize_text(script[key])
    for fact in script.get("facts", []):
        for beat in fact.get("beats", []):
            beat["text"] = _sanitize_text(beat["text"])
    for beat in script.get("payoff_beats", []):
        beat["text"] = _sanitize_text(beat["text"])


def _sanitize_text(text: str) -> str:
    text = _DASH_RUN.sub(", ", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("…", "...")
    return text


def verify_facts(script: dict) -> dict:
    """
    Lightweight accuracy pass: asks the model to fact-check its own claims
    against what it knows, flagging anything it isn't confident about.

    Mutates and returns `script` with per-claim verification info and a
    top-level `flagged_facts` list (beat ids like "rank5_beat0" for
    "countdown"; "hook"/"beat_N" ids for "hook") so orchestrator.py can
    decide whether to reject/regenerate, regardless of format.
    """
    if script["format"] == "hook":
        return _verify_hook_claims(script)
    return _verify_countdown_facts(script)


# --- countdown format ---


def _verify_countdown_facts(script: dict) -> dict:
    verdicts = _call_verification_llm(script)
    verdict_by_id = {v["id"]: v for v in verdicts}

    flagged = []
    for fact in script["facts"]:
        for i, beat in enumerate(fact["beats"]):
            claim_id = f"rank{fact['rank']}_beat{i}"
            verdict = verdict_by_id.get(
                claim_id, {"confidence": "unknown", "note": "no verdict returned"}
            )
            beat["verification"] = verdict
            if verdict.get("confidence") != "high":
                flagged.append(claim_id)

    script["flagged_facts"] = flagged
    return script


def _validate_countdown_script(script: dict) -> None:
    assert "hook" in script and script["hook"], "Script missing hook"
    assert script.get("hook_visual_keywords"), "Script missing hook_visual_keywords"
    assert isinstance(script.get("hook_prefer_ai_visual"), bool), (
        "Script missing boolean hook_prefer_ai_visual"
    )
    assert isinstance(script.get("hook_is_internal_anatomy"), bool), (
        "Script missing boolean hook_is_internal_anatomy"
    )
    facts = script.get("facts", [])
    assert len(facts) == config.FACTS_PER_VIDEO, (
        f"Expected {config.FACTS_PER_VIDEO} facts, got {len(facts)}"
    )
    ranks = {fact.get("rank") for fact in facts}
    assert ranks == set(range(1, config.FACTS_PER_VIDEO + 1)), (
        f"Facts must have ranks 1..{config.FACTS_PER_VIDEO} exactly once, got {sorted(ranks)}"
    )

    facts_with_extra_beat = 0
    for fact in facts:
        beats = fact.get("beats", [])
        assert 1 <= len(beats) <= 1 + MAX_EXTRA_BEATS_PER_FACT, (
            f"Fact rank {fact.get('rank')} must have 1-{1 + MAX_EXTRA_BEATS_PER_FACT} beats, "
            f"got {len(beats)}"
        )
        if len(beats) > 1:
            facts_with_extra_beat += 1
        for i, beat in enumerate(beats):
            assert beat.get("text"), f"Fact rank {fact.get('rank')} beat {i} missing text"
            assert beat.get("visual_keywords"), (
                f"Fact rank {fact.get('rank')} beat {i} missing visual_keywords"
            )
            assert isinstance(beat.get("prefer_ai_visual"), bool), (
                f"Fact rank {fact.get('rank')} beat {i} missing boolean prefer_ai_visual"
            )
            assert isinstance(beat.get("is_internal_anatomy"), bool), (
                f"Fact rank {fact.get('rank')} beat {i} missing boolean is_internal_anatomy"
            )
    assert facts_with_extra_beat <= MAX_FACTS_WITH_EXTRA_BEAT, (
        f"At most {MAX_FACTS_WITH_EXTRA_BEAT} facts may have a 2nd beat, "
        f"got {facts_with_extra_beat}"
    )
    assert "closer" in script and script["closer"], "Script missing closer"


def _build_script_prompt(topic: dict) -> str:
    return (
        f'Write a script for a {config.FACTS_PER_VIDEO}-facts YouTube Short '
        f"about \"{topic['topic']}\" (category: {topic['category']}).\n\n"
        "Structure:\n"
        "- A one-sentence hook (under 15 words) creating curiosity, said before any facts.\n"
        "- `hook_visual_keywords`: 2-4 concrete, filmable subjects for ONE single, cohesive, "
        "physically real scene that captures the hook line's visual idea — specific to this "
        "topic, not a generic placeholder like \"science\" or \"mystery\". Same rules as the "
        "per-beat visual_keywords below (no size-comparison objects, no abstract processes).\n"
        "- `hook_prefer_ai_visual` and `hook_is_internal_anatomy`: same meaning as the "
        "per-beat booleans described below, applied to the hook's own visual.\n"
        f"- Exactly {config.FACTS_PER_VIDEO} facts, ranked {config.FACTS_PER_VIDEO} (least "
        "surprising) down to 1 (most surprising/mind-blowing) — this is a countdown, so order "
        "the `facts` array from rank 5 to rank 1.\n"
        "- A one-sentence closer inviting engagement (e.g. asks which fact surprised them most, "
        "encourages a follow), under 15 words.\n\n"
        "Each fact has 1-2 `beats` — each beat becomes its own image, cutting to a new one as "
        "the narration progresses:\n"
        "- Give a fact 1 beat when it's a simple, self-contained point.\n"
        "- Give a fact a 2nd beat ONLY when there's genuinely more to say: the mechanism behind "
        "it, why it matters, a specific standout number or detail, or a real consequence — "
        "actual new information the 1st beat didn't cover. Never use a 2nd beat to restate the "
        "1st beat more slowly or pad it with filler.\n"
        f"- At most {MAX_FACTS_WITH_EXTRA_BEAT} of the {config.FACTS_PER_VIDEO} facts should get "
        "a 2nd beat — reserve it for the facts that truly earn it. If a topic doesn't have that "
        "much real depth, most or all facts should stay at 1 beat and the video should come out "
        "shorter — that's the correct result, not something to fix.\n\n"
        "Requirements:\n"
        "- Only state facts you are genuinely confident are accurate. Do not invent statistics, "
        "dates, or numbers you are not sure about.\n"
        "- Each beat (hook, fact beat, closer) is readable aloud in about 5-9 seconds, driven by "
        "having one real, specific idea to say — not by pacing it slower or adding filler "
        f"words. The full video (hook + all fact beats + closer) can run up to about "
        f"{config.MAX_DURATION_SECONDS} seconds when multiple facts genuinely earn a 2nd beat; "
        "a topic where every fact is simple should come out shorter, with one beat per fact.\n"
        "- Each beat needs 2-4 `visual_keywords` describing ONE single, cohesive, physically "
        'real scene or subject — concrete and filmable (e.g. "bioluminescent jellyfish"), not '
        "abstract ideas. Two rules that matter a lot for image generation:\n"
        "  1. Never pair the subject with an unrelated object as a size/scale comparison (e.g. "
        'do NOT write "giant squid eye" + "basketball" to convey size — an image generator '
        "renders both literally and fuses them into one object. Instead let close-up framing "
        'imply scale, e.g. "extreme close-up of a giant squid\'s eye filling the frame".\n'
        '  2. Never describe an invisible/abstract process (electrical signals, "neural '
        'activity", energy, data flow) — there\'s no real photo of that, so an image generator '
        "defaults to diagram-style glowing lines/nodes. Always name a tangible physical object "
        'or specimen instead (e.g. instead of "brain neural activity", write "close-up of a '
        'real brain model\'s surface" or "brainstem cross-section").\n'
        "- Each beat needs a `source_hint`: the type of source it would come from (e.g. "
        '"NASA JPL", "peer-reviewed marine biology study") — not a fabricated URL.\n'
        "- Each beat needs a `prefer_ai_visual` boolean: true if the visual_keywords describe "
        "a specific real subject that generic stock photo libraries are unlikely to have an "
        "accurate match for — a particular species' distinctive behavior, a named phenomenon, "
        "a specific artifact/event, OR any organism/subject that is rare, deep-sea, "
        "expedition-only, microscopic, extinct, or otherwise not something an ordinary "
        "photographer could easily go photograph (default to true for these — stock sites are "
        "flooded with generic/wrong-species substitutes for exactly this kind of subject, e.g. "
        "searching a specific hydrothermal-vent species returns whatever unrelated worm or "
        "forest-floor photo tagged similarly). False only for genuinely generic, "
        "commonly-and-correctly-photographed concepts (oceans, brains, lightning, space, "
        "common animals like dogs/lions/eagles, generic lab equipment) that stock libraries "
        "reliably have accurate matches for.\n"
        "- Each beat needs an `is_internal_anatomy` boolean: true only if the visual_keywords "
        "depict something no camera could photograph directly in real life — an internal "
        "organ cross-section, a tissue/cellular layer, something that would require cutting "
        "something open to see. False for everything else, including external anatomy "
        "(a whole brain's surface, an animal's body) and any environmental, physical, or "
        "astronomical subject, even if it's usually studied scientifically.\n\n"
        "Respond with ONLY valid JSON matching this exact shape, no markdown fences, no "
        "commentary:\n"
        f"{json.dumps(SCRIPT_SCHEMA_EXAMPLE, indent=2)}"
    )


def _build_verification_prompt(script: dict) -> str:
    claims = [
        {"id": f"rank{fact['rank']}_beat{i}", "text": beat["text"], "source_hint": beat.get("source_hint")}
        for fact in script["facts"]
        for i, beat in enumerate(fact["beats"])
    ]
    return (
        "You are fact-checking claims for a science-facts video, using only your own "
        f"knowledge (no browsing). For EACH of these {len(claims)} claims, assess how confident "
        "you are that it is accurate as stated:\n\n"
        f"{json.dumps(claims, indent=2)}\n\n"
        "Respond with ONLY a valid JSON array, no markdown fences, no commentary, one object "
        "per claim, in this exact shape:\n"
        '[{"id": "rank5_beat0", "confidence": "high", "note": ""}, ...]\n\n'
        'confidence must be exactly one of "high", "medium", "low". Use "medium" or "low" for '
        "anything exaggerated, outdated, or misremembered, and use `note` to say what's "
        "questionable and, if you know it, what the accurate version would be."
    )


def _call_llm(topic: dict) -> dict:
    prompt = _build_script_prompt(topic)
    # Up to 5 facts x 2 beats = 10 fact-beats, each with several fields, plus
    # the hook's own visual fields.
    return llm_client.complete_json(prompt, max_tokens=2400)


def _call_verification_llm(script: dict) -> list[dict]:
    prompt = _build_verification_prompt(script)
    return llm_client.complete_json(prompt, max_tokens=1600)


# --- hook format ---


def _verify_hook_claims(script: dict) -> dict:
    prompt = _build_hook_verification_prompt(script)
    verdicts = llm_client.complete_json(prompt, max_tokens=1400)
    verdict_by_id = {v["id"]: v for v in verdicts}

    claim_ids = ["hook"] + [f"beat_{i}" for i in range(len(script["payoff_beats"]))]
    flagged = []
    claim_verifications = {}
    for claim_id in claim_ids:
        verdict = verdict_by_id.get(claim_id, {"confidence": "unknown", "note": "no verdict returned"})
        claim_verifications[claim_id] = verdict
        if verdict.get("confidence") != "high":
            flagged.append(claim_id)

    script["claim_verifications"] = claim_verifications
    script["flagged_facts"] = flagged
    return script


def _validate_hook_script(script: dict) -> None:
    valid_styles = {s["name"] for s in HOOK_STYLES}
    assert script.get("hook_style") in valid_styles, f"Unknown hook_style {script.get('hook_style')!r}"
    assert script.get("hook"), "Script missing hook"
    assert script.get("hook_visual_keywords"), "Script missing hook_visual_keywords"
    assert isinstance(script.get("hook_is_internal_anatomy"), bool), (
        "Script missing boolean hook_is_internal_anatomy"
    )
    beats = script.get("payoff_beats", [])
    assert beats, "Script missing payoff_beats"
    for i, beat in enumerate(beats):
        assert beat.get("text"), f"payoff_beats[{i}] missing text"
        assert beat.get("visual_keywords"), f"payoff_beats[{i}] missing visual_keywords"
        assert isinstance(beat.get("is_internal_anatomy"), bool), (
            f"payoff_beats[{i}] missing boolean is_internal_anatomy"
        )


def _build_hook_script_prompt(topic: dict, style: dict) -> str:
    return (
        f'Write a short-form science video script about "{topic["topic"]}" '
        f'(category: {topic["category"]}).\n\n'
        "This is a fast, single-topic hook format — NOT a countdown/list. Structure:\n"
        f"- `hook`: one punchy opening line, under 15 words, readable aloud in 3-4 seconds. "
        f"{style['instruction']}\n"
        "- `payoff_beats`: the answer/explanation broken into beats, each covering ONE distinct "
        "sub-idea (cause, then mechanism, then a specific consequence or standout detail, then "
        "why it matters, a common misconception it corrects, etc.) — each beat should teach the "
        "viewer something the previous beat didn't, not restate it more slowly. Each beat is "
        "readable aloud in about 4-8 seconds, driven by having a real specific point to make.\n"
        "- Use 2-3 beats for a topic with one simple mechanism and nothing more to add. Use up "
        "to 7-8 beats for a topic with several genuinely distinct steps/parts/angles worth "
        "showing separately. The full video (hook + beats) can run up to about "
        f"{config.MAX_DURATION_SECONDS} seconds when the topic has that much real depth; a "
        "topic that only supports 2-3 beats should stay short — that's correct, not a gap to "
        "fill with padding or slower pacing.\n\n"
        "Requirements:\n"
        "- Only state facts you are genuinely confident are accurate. Do not invent "
        "statistics, dates, or numbers you are not sure about.\n"
        "- `hook_visual_keywords` (on the script) and `visual_keywords` (on each beat): 2-4 "
        "concrete, filmable subjects describing ONE single, cohesive, physically real scene "
        "that captures that specific line's visual idea as a single striking image (each "
        "becomes its own AI-generated image, not stock footage). Two rules that matter a lot "
        "for image generation:\n"
        "  1. Never pair the subject with an unrelated object as a size/scale comparison (e.g. "
        'do NOT write "giant squid eye" + "basketball" to convey size — an image generator '
        "renders both literally and fuses them into one object. Instead let close-up framing "
        'imply scale, e.g. "extreme close-up of a giant squid\'s eye filling the frame".\n'
        '  2. Never describe an invisible/abstract process (electrical signals, "neural '
        'activity", energy, data flow) — there\'s no real photo of that, so an image generator '
        "defaults to diagram-style glowing lines/nodes. Always name a tangible physical object "
        'or specimen instead (e.g. instead of "brain neural activity", write "close-up of a '
        'real brain model\'s surface" or "brainstem cross-section").\n'
        "- `hook_is_internal_anatomy` (on the script) and `is_internal_anatomy` (on each beat): "
        "true only if that line's visual_keywords depict something no camera could photograph "
        "directly in real life — an internal organ cross-section, a tissue/cellular layer, "
        "something that would require cutting something open to see. False for everything "
        "else, including external anatomy and any environmental, physical, or astronomical "
        "subject, even if it's usually studied scientifically.\n"
        '- `source_hint`: the type of source this would come from (e.g. "NASA JPL", '
        '"peer-reviewed neuroscience study") — not a fabricated URL.\n\n'
        "Respond with ONLY valid JSON matching this exact shape, no markdown fences, no "
        f'commentary, and set "hook_style" to exactly "{style["name"]}":\n'
        f"{json.dumps(HOOK_SCRIPT_SCHEMA_EXAMPLE, indent=2)}"
    )


def _build_hook_verification_prompt(script: dict) -> str:
    claims = [{"id": "hook", "text": script["hook"]}]
    claims.extend(
        {"id": f"beat_{i}", "text": beat["text"]} for i, beat in enumerate(script["payoff_beats"])
    )
    return (
        "You are fact-checking claims for a science-facts video, using only your own "
        "knowledge (no browsing). For EACH of these claims, assess how confident you are "
        'that it is accurate as stated (a pure question with no factual assertion should '
        'get "high" confidence by default):\n\n'
        f"{json.dumps(claims, indent=2)}\n\n"
        "Respond with ONLY a valid JSON array, no markdown fences, no commentary, one object "
        "per claim, in this exact shape:\n"
        '[{"id": "hook", "confidence": "high", "note": ""}, ...]\n\n'
        'confidence must be exactly one of "high", "medium", "low". Use "medium" or "low" for '
        "anything exaggerated, outdated, or misremembered, and use `note` to say what's "
        "questionable and, if you know it, what the accurate version would be."
    )


def _call_hook_llm(topic: dict) -> dict:
    style = random.choice(HOOK_STYLES)
    prompt = _build_hook_script_prompt(topic, style)
    # Up to 7-8 beats now (was 5-6) — leave headroom to avoid truncated JSON.
    script = llm_client.complete_json(prompt, max_tokens=1400)
    script["hook_style"] = style["name"]  # enforce in code rather than trusting the model
    return script


if __name__ == "__main__":
    # Quick manual test with a hardcoded topic, one run per format:
    test_topic = {"category": "deep ocean", "topic": "creatures that survive without sunlight"}
    for fmt in config.VIDEO_FORMATS:
        test_script = write_script(test_topic, video_format=fmt)
        test_script = verify_facts(test_script)
        print(f"--- {fmt} ---")
        print(json.dumps(test_script, indent=2))
