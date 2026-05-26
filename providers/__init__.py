from .ollama import OllamaProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str):
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}")
    return cls()
