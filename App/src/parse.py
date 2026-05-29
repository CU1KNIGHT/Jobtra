from providers import get_provider
import settings as app_settings


async def _run_parse(text: str, source_url: str = "", source_text: str = "") -> dict:
    """Run active provider parse and attach source fields. Raises provider exceptions."""
    s = app_settings.get_settings()
    p = get_provider(s["provider"])
    result = await p.parse(text, s["model"])
    result["source_url"] = source_url
    result["source_text"] = source_text or text
    return result
