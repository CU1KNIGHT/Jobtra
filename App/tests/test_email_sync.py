import json
import pytest
from unittest.mock import AsyncMock, patch

from email_sync import is_relevant, encrypt_password, decrypt_password, process_email_with_llm
from providers.base import ProviderUnavailable, ProviderBadOutput


# ── is_relevant ───────────────────────────────────────────────────────────────

def test_is_relevant_keyword_in_subject():
    assert is_relevant("Interview invite from Acme Corp", "") is True


def test_is_relevant_keyword_in_body():
    assert is_relevant("Re: your inquiry", "Thank you for applying to our position.") is True


def test_is_relevant_rejection_keyword():
    assert is_relevant(
        "Update on your application",
        "Unfortunately we have decided to move forward with other candidates.",
    ) is True


def test_is_relevant_offer():
    assert is_relevant("Congratulations!", "We are pleased to extend an offer.") is True


def test_is_relevant_no_match():
    assert is_relevant("Newsletter April 2026", "Check out our latest deals.") is False


def test_is_relevant_empty_strings():
    assert is_relevant("", "") is False


# ── encrypt / decrypt ────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    password = "super_secret_p@ssw0rd!"
    encrypted = encrypt_password(password)
    assert encrypted != password
    assert decrypt_password(encrypted) == password


def test_encrypt_produces_unique_ciphertext():
    # Fernet includes a random IV so two encryptions of the same plaintext differ
    p = "same_password"
    assert encrypt_password(p) != encrypt_password(p)


# ── process_email_with_llm ────────────────────────────────────────────────────

_MSG = {
    "subject": "Re: Your application to Acme",
    "sender": "hr@acme.com",
    "body_text": "Congratulations! We would like to invite you for an interview next week.",
}

_VALID_LLM_JSON = json.dumps({
    "relevant": True,
    "status": "interview_invite",
    "company": "Acme",
    "position": "Backend Engineer",
    "confidence": 0.95,
    "notes": "Interview scheduled.",
})


async def test_process_email_success():
    mock_provider = AsyncMock()
    mock_provider.complete.return_value = _VALID_LLM_JSON

    with patch("email_sync.get_provider", return_value=mock_provider):
        result = await process_email_with_llm(_MSG, "llama3.1:8b", "ollama")

    assert result["relevant"] is True
    assert result["status"] == "interview_invite"
    assert result["company"] == "Acme"
    mock_provider.complete.assert_awaited_once()


async def test_process_email_irrelevant_response():
    payload = json.dumps({"relevant": False, "status": None, "company": None,
                          "position": None, "confidence": 0.1, "notes": ""})
    mock_provider = AsyncMock()
    mock_provider.complete.return_value = payload

    with patch("email_sync.get_provider", return_value=mock_provider):
        result = await process_email_with_llm(_MSG, "llama3.1:8b", "ollama")

    assert result["relevant"] is False


async def test_process_email_provider_unavailable():
    mock_provider = AsyncMock()
    mock_provider.complete.side_effect = ProviderUnavailable("Ollama is not running")

    with patch("email_sync.get_provider", return_value=mock_provider):
        with pytest.raises(ProviderUnavailable):
            await process_email_with_llm(_MSG, "llama3.1:8b", "ollama")


async def test_process_email_bad_json_raises():
    mock_provider = AsyncMock()
    mock_provider.complete.return_value = "not valid json at all %%"

    with patch("email_sync.get_provider", return_value=mock_provider):
        with pytest.raises(ProviderBadOutput):
            await process_email_with_llm(_MSG, "llama3.1:8b", "ollama")


async def test_process_email_passes_system_prompt():
    mock_provider = AsyncMock()
    mock_provider.complete.return_value = _VALID_LLM_JSON

    with patch("email_sync.get_provider", return_value=mock_provider):
        await process_email_with_llm(_MSG, "llama3.1:8b", "ollama")

    call_args = mock_provider.complete.call_args
    system_arg = call_args[0][0]
    assert "relevant" in system_arg.lower() or "job" in system_arg.lower()
