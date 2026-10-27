"""Which LLM provider the agents call (D-024): Anthropic (Claude) or OpenAI behind the same interface.

LLM_PROVIDER=openai | anthropic picks it; unset → anthropic only when ANTHROPIC_API_KEY is the only key set, else
openai (also with no key, so a keyless re-run replays OpenAI's cached decisions). Every agent
(Guide, Builder, Creator, LLM parser, solver agent, transcript rewriter) gets its client from `make()` and keeps
its Claude model id: agent/openai_llm.py maps it to an OpenAI model. `live(client)` is true for either real
client (not the offline or scripted test clients)."""

import os

import anthropic

PROVIDERS = ("openai", "anthropic")


def provider() -> str:
    choice = os.environ.get("LLM_PROVIDER", "").lower()
    if choice in PROVIDERS:
        return choice
    only_claude = os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY")
    return "anthropic" if only_claude else "openai"


def key_name(name: str | None = None) -> str:
    """The API key variable the provider (default: the configured one) needs."""
    return "OPENAI_API_KEY" if (name or provider()) == "openai" else "ANTHROPIC_API_KEY"


def has_key() -> bool:
    return bool(os.environ.get(key_name()))


def make(max_retries: int | None = None, name: str | None = None) -> object:
    """A client for `name` (default: the configured provider)."""
    if (name or provider()) == "openai":
        from agent.openai_llm import OpenAIClient

        return OpenAIClient(max_retries=max_retries)
    return anthropic.Anthropic(max_retries=max_retries) if max_retries is not None else anthropic.Anthropic()


def live(client: object) -> bool:
    from agent.openai_llm import OpenAIClient

    return isinstance(client, (anthropic.Anthropic, OpenAIClient))
