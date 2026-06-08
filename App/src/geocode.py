"""City → (lat, lng) resolution for the dashboard map.

Resolution order for each city:
  1. Offline seed of common (mostly German) cities — instant, no network.
  2. SQLite cache (`city_coords`) — every previously looked-up city, including
     negatively-cached misses.
  3. Nominatim (OpenStreetMap) geocoding API — queried once per new city, then
     persisted to the cache.

Nominatim's usage policy requires a descriptive User-Agent and at most ~1
request/second, so network lookups are throttled and only ever happen for
cities not already in the seed or cache.
"""
import threading
import time
from typing import Optional

import httpx

import db
from config import VERSION

# Offline seed of common cities so the typical case needs zero network calls and
# the map still works fully offline. Anything not here is geocoded on demand.
_SEED: dict[str, tuple[float, float]] = {
    "berlin": (52.5200, 13.4050),
    "hamburg": (53.5511, 9.9937),
    "münchen": (48.1351, 11.5820), "munich": (48.1351, 11.5820),
    "köln": (50.9375, 6.9603), "cologne": (50.9375, 6.9603),
    "frankfurt": (50.1109, 8.6821), "frankfurt am main": (50.1109, 8.6821),
    "stuttgart": (48.7758, 9.1829),
    "düsseldorf": (51.2277, 6.7735), "dusseldorf": (51.2277, 6.7735),
    "leipzig": (51.3397, 12.3731),
    "dortmund": (51.5136, 7.4653),
    "essen": (51.4556, 7.0116),
    "bremen": (53.0793, 8.8017),
    "dresden": (51.0504, 13.7373),
    "hannover": (52.3759, 9.7320), "hanover": (52.3759, 9.7320),
    "nürnberg": (49.4521, 11.0767), "nuremberg": (49.4521, 11.0767),
    "duisburg": (51.4344, 6.7623),
    "bochum": (51.4818, 7.2162),
    "wuppertal": (51.2562, 7.1508),
    "bielefeld": (52.0302, 8.5325),
    "bonn": (50.7374, 7.0982),
    "münster": (51.9607, 7.6261), "munster": (51.9607, 7.6261),
    "karlsruhe": (49.0069, 8.4037),
    "mannheim": (49.4875, 8.4660),
    "augsburg": (48.3705, 10.8978),
    "wiesbaden": (50.0782, 8.2398),
    "mönchengladbach": (51.1805, 6.4428),
    "gelsenkirchen": (51.5177, 7.0857),
    "aachen": (50.7753, 6.0839),
    "braunschweig": (52.2689, 10.5268),
    "chemnitz": (50.8278, 12.9214),
    "kiel": (54.3233, 10.1228),
    "halle": (51.4969, 11.9688),
    "magdeburg": (52.1205, 11.6276),
    "freiburg": (47.9990, 7.8421),
    "krefeld": (51.3388, 6.5853),
    "mainz": (49.9929, 8.2473),
    "lübeck": (53.8655, 10.6866), "lubeck": (53.8655, 10.6866),
    "erfurt": (50.9848, 11.0299),
    "rostock": (54.0924, 12.0991),
    "kassel": (51.3127, 9.4797),
    "potsdam": (52.3906, 13.0645),
    "saarbrücken": (49.2402, 6.9969), "saarbrucken": (49.2402, 6.9969),
    "regensburg": (49.0134, 12.1016),
    "jena": (50.9271, 11.5892),
    "heidelberg": (49.3988, 8.6724),
    "ingolstadt": (48.7665, 11.4258),
    "ulm": (48.4011, 9.9876),
    "würzburg": (49.7913, 9.9534), "wurzburg": (49.7913, 9.9534),
    # a few common non-DE hubs
    "vienna": (48.2082, 16.3738), "wien": (48.2082, 16.3738),
    "zurich": (47.3769, 8.5417), "zürich": (47.3769, 8.5417),
    "london": (51.5074, -0.1278),
    "amsterdam": (52.3676, 4.9041),
    "paris": (48.8566, 2.3522),
}

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = f"Jobtra/{VERSION} (https://github.com/CU1KNIGHT/Jobtra)"
_MIN_INTERVAL = 1.1  # seconds between Nominatim requests (policy: max ~1/sec)

_throttle_lock = threading.Lock()
_last_request_at = 0.0

# Cities currently being geocoded by a background worker, so overlapping
# dashboard requests don't queue the same city twice.
_pending_lock = threading.Lock()
_pending: set[str] = set()


class GeocodeError(Exception):
    """A Nominatim lookup failed transiently (network/HTTP/parse error).

    Distinct from a successful "city not found" so callers can avoid caching a
    transient failure as a permanent miss.
    """


def _normalize(city: str) -> str:
    return (city or "").strip().lower()


def resolve_cached(city: str) -> Optional[tuple[Optional[float], Optional[float]]]:
    """Resolve a city using only the offline seed and DB cache — never the
    network. Returns the coords (which may be (None, None) for a cached miss),
    or None if the city has not been geocoded yet."""
    key = _normalize(city)
    if not key:
        return (None, None)
    if key in _SEED:
        return _SEED[key]
    cached = db.get_cached_city_coords(key)
    if cached is not None:
        return (cached["lat"], cached["lng"])
    return None


def geocode_city(city: str) -> tuple[Optional[float], Optional[float]]:
    """Resolve a city to (lat, lng), querying Nominatim if needed.

    Genuine results (a hit or a confirmed "not found") are written to the cache;
    a transient lookup failure is NOT cached, so the city is retried next time.
    """
    cached = resolve_cached(city)
    if cached is not None:
        return cached

    key = _normalize(city)
    try:
        lat, lng = _query_nominatim(key)
    except GeocodeError:
        return (None, None)  # don't cache: allow a retry on the next load
    db.save_city_coords(key, lat, lng)
    return (lat, lng)


def request_geocode(cities) -> Optional[threading.Thread]:
    """Geocode any not-yet-cached cities in a background thread so the request
    that triggers it returns immediately. Returns the worker thread (mainly for
    tests), or None if there was nothing to do."""
    keys = _select_missing(cities)
    with _pending_lock:
        keys = [k for k in keys if k not in _pending]
        _pending.update(keys)
    if not keys:
        return None
    worker = threading.Thread(target=_geocode_missing, args=(keys,), daemon=True)
    worker.start()
    return worker


def _select_missing(cities) -> list[str]:
    """Distinct normalized cities that are neither in the seed nor the cache."""
    keys: list[str] = []
    seen: set[str] = set()
    for city in cities:
        key = _normalize(city)
        if not key or key in _SEED or key in seen:
            continue
        seen.add(key)
        if db.get_cached_city_coords(key) is None:
            keys.append(key)
    return keys


def _geocode_missing(keys: list[str]) -> None:
    for key in keys:
        try:
            geocode_city(key)
        finally:
            with _pending_lock:
                _pending.discard(key)


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _query_nominatim(city: str) -> tuple[Optional[float], Optional[float]]:
    """Look up a single city via Nominatim, returning (lat, lng) or (None, None)
    if the city genuinely has no match. Biases to Germany first (the app's
    primary region) and falls back to a worldwide search. Raises GeocodeError on
    a network/HTTP/parse failure so a transient outage is not cached as a miss."""
    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as client:
            hit = _search(client, city, country="de")
            if hit is None:
                hit = _search(client, city, country=None)
            return hit if hit is not None else (None, None)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise GeocodeError(str(exc)) from exc


def _search(client: httpx.Client, city: str, country: Optional[str]):
    params = {"q": city, "format": "jsonv2", "limit": 1}
    if country:
        params["countrycodes"] = country
    _throttle()
    resp = client.get(_NOMINATIM_URL, params=params)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return (float(results[0]["lat"]), float(results[0]["lon"]))
