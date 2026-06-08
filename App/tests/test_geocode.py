import httpx
import pytest

import db
import geocode


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    """Disable the inter-request delay so tests don't sleep."""
    monkeypatch.setattr(geocode, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(geocode, "_last_request_at", 0.0)


def _boom(*_args, **_kwargs):
    raise AssertionError("Nominatim should not be queried")


# ── geocode_city resolution order ────────────────────────────────────────────

def test_seed_hit_uses_no_network(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.geocode_city("Berlin") == (52.5200, 13.4050)
    # Case/whitespace-insensitive.
    assert geocode.geocode_city("  münchen ") == (48.1351, 11.5820)


def test_cache_hit_uses_no_network(monkeypatch):
    db.save_city_coords("smalltown", 1.0, 2.0)
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.geocode_city("SmallTown") == (1.0, 2.0)


def test_empty_city_returns_none_without_query(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.geocode_city("") == (None, None)
    assert geocode.geocode_city("   ") == (None, None)
    assert db.get_cached_city_coords("") is None


def test_miss_queries_once_then_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(geocode, "_query_nominatim",
                        lambda c: calls.append(c) or (10.0, 20.0))

    assert geocode.geocode_city("Nowhereville") == (10.0, 20.0)
    # Second call is served from the cache, no second network query.
    assert geocode.geocode_city("nowhereville") == (10.0, 20.0)
    assert calls == ["nowhereville"]
    assert db.get_cached_city_coords("nowhereville") == {"lat": 10.0, "lng": 20.0}


def test_unresolvable_city_is_negatively_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(geocode, "_query_nominatim",
                        lambda c: calls.append(c) or (None, None))

    assert geocode.geocode_city("Atlantis") == (None, None)
    assert geocode.geocode_city("atlantis") == (None, None)
    assert calls == ["atlantis"]  # queried only once
    assert db.get_cached_city_coords("atlantis") == {"lat": None, "lng": None}


def test_transient_error_is_not_cached(monkeypatch):
    """A network/HTTP failure must not be cached as a permanent miss — the city
    has to remain eligible for a retry on a later load."""
    def boom(_city):
        raise geocode.GeocodeError("nominatim down")
    monkeypatch.setattr(geocode, "_query_nominatim", boom)

    assert geocode.geocode_city("Glitchtown") == (None, None)
    assert db.get_cached_city_coords("glitchtown") is None  # not cached → retryable


# ── resolve_cached (no-network path) ─────────────────────────────────────────

def test_resolve_cached_seed_and_cache(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.resolve_cached("Berlin") == (52.5200, 13.4050)
    db.save_city_coords("smalltown", 1.0, 2.0)
    assert geocode.resolve_cached("SmallTown") == (1.0, 2.0)


def test_resolve_cached_returns_none_for_unknown(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.resolve_cached("Neverseen") is None
    assert geocode.resolve_cached("") == (None, None)


# ── background geocoding ─────────────────────────────────────────────────────

def test_select_missing_filters_seed_cache_blanks_and_dupes():
    db.save_city_coords("cachedplace", 1.0, 1.0)
    missing = geocode._select_missing(
        ["Berlin", "", "  ", "cachedplace", "Newcity", "newcity", "Other"]
    )
    assert missing == ["newcity", "other"]  # seed/cached/blank dropped, deduped


def test_request_geocode_resolves_in_background(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", lambda c: (5.0, 6.0))
    worker = geocode.request_geocode(["Faketown", "Berlin", "Faketown"])
    assert worker is not None
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert db.get_cached_city_coords("faketown") == {"lat": 5.0, "lng": 6.0}


def test_request_geocode_noop_when_all_resolved(monkeypatch):
    monkeypatch.setattr(geocode, "_query_nominatim", _boom)
    assert geocode.request_geocode(["Berlin", ""]) is None


# ── _query_nominatim HTTP behaviour ──────────────────────────────────────────

def _patch_client(monkeypatch, handler):
    real_client = httpx.Client

    def factory(*_args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler),
                           headers=kwargs.get("headers"))
    monkeypatch.setattr(geocode.httpx, "Client", factory)


def test_query_parses_first_result(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=[{"lat": "50.5", "lon": "8.5"}])
    _patch_client(monkeypatch, handler)
    assert geocode._query_nominatim("erlangen") == (50.5, 8.5)


def test_query_falls_back_to_worldwide_search(monkeypatch):
    seen = []

    def handler(request):
        country = request.url.params.get("countrycodes")
        seen.append(country)
        if country == "de":
            return httpx.Response(200, json=[])  # not found in Germany
        return httpx.Response(200, json=[{"lat": "40.0", "lon": "-3.7"}])

    _patch_client(monkeypatch, handler)
    assert geocode._query_nominatim("madrid") == (40.0, -3.7)
    assert seen == ["de", None]  # DE first, then worldwide


def test_query_network_error_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")
    _patch_client(monkeypatch, handler)
    with pytest.raises(geocode.GeocodeError):
        geocode._query_nominatim("berlin")


def test_query_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(503)
    _patch_client(monkeypatch, handler)
    with pytest.raises(geocode.GeocodeError):
        geocode._query_nominatim("berlin")


def test_query_not_found_returns_miss(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=[])
    _patch_client(monkeypatch, handler)
    assert geocode._query_nominatim("atlantis") == (None, None)


# ── db cache helpers ─────────────────────────────────────────────────────────

def test_cache_helpers_round_trip():
    assert db.get_cached_city_coords("paris") is None
    db.save_city_coords("paris", 48.85, 2.35)
    assert db.get_cached_city_coords("paris") == {"lat": 48.85, "lng": 2.35}


def test_save_city_coords_upserts():
    db.save_city_coords("x", 1.0, 1.0)
    db.save_city_coords("x", 2.0, 2.0)
    assert db.get_cached_city_coords("x") == {"lat": 2.0, "lng": 2.0}
