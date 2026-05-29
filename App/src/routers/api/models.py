from fastapi import APIRouter, HTTPException, Query
from starlette.responses import JSONResponse

from providers import get_provider
from providers.base import ProviderAuthError, ProviderUnavailable
from util import VALID_PROVIDERS

router = APIRouter(tags=["job"])

@router.get("/api/models")
async def list_models(provider: str = Query(...)):
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unknown provider: {provider}")
    try:
        p = get_provider(provider)
        models = await p.list_models()
        return {"models": models}
    except ProviderAuthError as e:
        key_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        return JSONResponse(
            status_code=401,
            content={"error": str(e), "hint": f"Add {key_name} to .env"},
        )
    except ProviderUnavailable as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e), "hint": "Start Ollama with: ollama serve"},
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
