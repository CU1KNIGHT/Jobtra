from .ollama import OllamaProvider
from .lmstudio import LMStudioProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
    "lmstudio": LMStudioProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


# Local providers whose endpoint URL is user-configurable.
_LOCAL = {"ollama", "lmstudio"}


def get_provider(name: str, base_url: str = None):
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}")
    if name in _LOCAL:
        if not base_url:
            import settings  # lazy import to avoid an import cycle at startup
            base_url = settings.local_provider_url(name)
        return cls(base_url=base_url)
    return cls()
