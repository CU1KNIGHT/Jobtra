from fastapi import APIRouter

import db
import geocode

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def get_dashboard():
    data = db.get_dashboard_stats()
    cities = [entry.get("city") or "" for entry in data["by_city"]]
    for entry, city in zip(data["by_city"], cities):
        entry["lat"], entry["lng"] = geocode.resolve_cached(city) or (None, None)
    # Resolve any not-yet-cached cities in the background so this response is not
    # blocked on (throttled) Nominatim calls; they appear on the next load.
    geocode.request_geocode(cities)
    return data
