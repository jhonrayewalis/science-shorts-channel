"""
Thin wrapper around whichever LLM provider is configured (config.LLM_PROVIDER).
Shared by every pipeline stage that needs a text or JSON completion —
topic_discovery, script_writer, metadata.
"""
import json
import re

from pipeline import config

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5-20250929",
    "openai": "gpt-4o-mini",
}


def complete(prompt: str, max_tokens: int = 512) -> str:
    """Returns the raw text completion from the configured provider."""
    if config.LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    elif config.LLM_PROVIDER == "openai":
        return _call_openai(prompt, max_tokens)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER!r}")


def complete_json(prompt: str, max_tokens: int = 512):
    """Same as complete(), but parses the result as JSON (tolerates markdown fences)."""
    raw = complete(prompt, max_tokens=max_tokens).strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    return json.loads(raw)


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
    response = client.messages.create(
        model=config.LLM_MODEL or DEFAULT_MODELS["anthropic"],
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_openai(prompt: str, max_tokens: int) -> str:
    import openai

    client = openai.OpenAI(api_key=config.LLM_API_KEY)
    response = client.chat.completions.create(
        model=config.LLM_MODEL or DEFAULT_MODELS["openai"],
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
