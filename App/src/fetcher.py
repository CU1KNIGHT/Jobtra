import re
import ipaddress
import urllib.parse
import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_TEXT_CHARS = 12_000
CHUNK_SIZE = 8192


class FetchError(Exception):
    def __init__(self, message: str, hint: str = "", status: int = 400):
        super().__init__(message)
        self.hint = hint
        self.status = status


def _is_private_host(host: str) -> bool:
    # Reject obvious names
    lowered = host.lower()
    if lowered in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        pass
    # Also block hosts that look like internal ones
    if lowered.endswith(".local") or lowered.endswith(".internal"):
        return True
    return False


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(
            "Only http/https URLs are supported",
            hint="Use a public http/https URL",
            status=400,
        )
    host = parsed.hostname or ""
    if not host:
        raise FetchError("Invalid URL: no host", status=400)
    if _is_private_host(host):
        raise FetchError(
            "Local/private URLs are not allowed",
            hint="Use a public http/https URL",
            status=400,
        )


def html_to_text(html: str) -> str:
    # Drop script/style/noscript blocks including content
    html = re.sub(
        r"<(script|style|noscript)\b[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Convert block tags to newlines
    html = re.sub(r"</(p|div|li|h[1-6]|br|tr)>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    html = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n\s*\n+", "\n\n", html)
    return html.strip()


async def fetch_as_text(url: str) -> str:
    """Fetch URL, return cleaned plain text. Raises FetchError on failure."""
    _validate_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": "Jobtra/1.0"},
        ) as client:
            async with client.stream("GET", url) as resp:
                # Check content length header
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                    raise FetchError("Page is too large", status=502)

                # Check content type
                ct = resp.headers.get("content-type", "")
                if not (ct.startswith("text/html") or ct.startswith("application/xhtml")):
                    raise FetchError("URL is not an HTML page", status=502)

                if resp.status_code >= 400:
                    hint = ""
                    if resp.status_code in (401, 403):
                        hint = "Site may require login. Try copy-pasting the text instead."
                    raise FetchError(
                        f"Page returned HTTP {resp.status_code}",
                        hint=hint,
                        status=502,
                    )

                # Read response in chunks, enforcing size cap
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise FetchError("Page is too large", status=502)
                    chunks.append(chunk)

        raw_html = b"".join(chunks).decode("utf-8", errors="replace")
    except FetchError:
        raise
    except httpx.TimeoutException:
        raise FetchError("Page took too long to load", status=408)
    except httpx.ConnectError as e:
        raise FetchError(f"Could not connect to {url}", status=502)
    except httpx.TooManyRedirects:
        raise FetchError("Too many redirects", status=502)

    text = html_to_text(raw_html)
    return text[:MAX_TEXT_CHARS]
