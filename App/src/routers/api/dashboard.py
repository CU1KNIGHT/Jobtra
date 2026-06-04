from fastapi import APIRouter

import db

router = APIRouter(tags=["dashboard"])

# Static lookup of major (mostly German) cities → (lat, lng). Cities not found
# are returned with null coordinates and skipped by the map renderer.
_CITY_COORDS = {
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


@router.get("/api/dashboard")
def get_dashboard():
    data = db.get_dashboard_stats()
    for entry in data["by_city"]:
        coord = _CITY_COORDS.get((entry.get("city") or "").strip().lower())
        entry["lat"], entry["lng"] = coord if coord else (None, None)
    return data
