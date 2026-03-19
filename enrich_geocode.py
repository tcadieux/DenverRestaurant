#!/usr/bin/env python3
"""
Geocode Enrichment
------------------
Reads westword_openings_closings.csv, geocodes each row via Nominatim
(OpenStreetMap), and writes westword_enriched.csv.

Added columns: lat, lng, geocode_status
  geocode_status values:
    ok        - lat/lng found with original address
    ok_approx - lat/lng found after stripping cardinal directions; may be slightly off
    no_result - Nominatim returned no match
    error     - request failed

Reruns are incremental: rows with geocode_status already set are skipped.
"""

import csv
import logging
import re
import time

import requests

# ---- Config ------------------------------------------------------------------
INPUT_FILE    = "westword_openings_closings.csv"
OUTPUT_FILE   = "westword_enriched.csv"
ERRORS_FILE   = "westword_geocode_errors.csv"
REQUEST_DELAY = 1.1   # Nominatim fair-use policy: max 1 req/sec
USER_AGENT    = "WestwordEnricher/1.0 (local research project)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

GEOCODE_FIELDS = ["lat", "lng", "geocode_status"]

# Cardinal directions to strip when retrying a failed geocode
_CARDINAL_RE = re.compile(
    r"\b(North|South|East|West|N\.?|S\.?|E\.?|W\.?)\s+", re.IGNORECASE
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("enrich_geocode.log"),
        logging.StreamHandler(),
    ],
)


# ---- Geocoding ---------------------------------------------------------------
def _nominatim_get(params):
    """Make a single Nominatim request; return list of results or []."""
    resp = requests.get(
        NOMINATIM_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def geocode(address, city):
    """Return (lat, lng, status) for a given address + city.

    Attempts in order:
      1. Structured query (street + city)
      2. Free-form query (catches airport/mall addresses)
      3. Strip cardinal directions from street, retry structured + free-form
         → status 'ok_approx' (location may be slightly off)
    """
    try:
        # 1. Structured
        results = _nominatim_get({
            "street": address, "city": city, "state": "Colorado", "country": "US",
            "format": "json", "limit": 1, "addressdetails": 0,
        })
        if results:
            return results[0]["lat"], results[0]["lon"], "ok"

        # 2. Free-form
        results = _nominatim_get({
            "q": f"{address}, {city}, CO, USA",
            "format": "json", "limit": 1,
        })
        if results:
            return results[0]["lat"], results[0]["lon"], "ok"

        # 3. Strip cardinal directions and retry
        stripped = _CARDINAL_RE.sub("", address).strip()
        if stripped != address:
            logging.info("Retrying without cardinal directions: %r → %r", address, stripped)
            time.sleep(REQUEST_DELAY)
            results = _nominatim_get({
                "street": stripped, "city": city, "state": "Colorado", "country": "US",
                "format": "json", "limit": 1, "addressdetails": 0,
            })
            if results:
                return results[0]["lat"], results[0]["lon"], "ok_approx"
            time.sleep(REQUEST_DELAY)
            results = _nominatim_get({
                "q": f"{stripped}, {city}, CO, USA",
                "format": "json", "limit": 1,
            })
            if results:
                return results[0]["lat"], results[0]["lon"], "ok_approx"

        return "", "", "no_result"
    except Exception as e:
        logging.warning("Geocode error for %r, %r — %s: %s", address, city, type(e).__name__, e)
        return "", "", "error"


# ---- Main --------------------------------------------------------------------
def main():
    import os

    # Load existing enriched file if present (for incremental runs)
    enriched_existing = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row.get("restaurant_name", ""), row.get("address", ""), row.get("status", ""))
                if row.get("geocode_status") in ("ok", "ok_approx"):
                    enriched_existing[key] = {f: row.get(f, "") for f in GEOCODE_FIELDS}
        logging.info("Loaded %d already-geocoded rows from %s", len(enriched_existing), OUTPUT_FILE)

    # Read input
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fieldnames = reader.fieldnames or []
        rows = list(reader)

    fieldnames = input_fieldnames + [f for f in GEOCODE_FIELDS if f not in input_fieldnames]

    total   = len(rows)
    skipped = 0
    done    = 0
    errors  = 0

    error_rows = []

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for i, row in enumerate(rows, 1):
            key = (row.get("restaurant_name", ""), row.get("address", ""), row.get("status", ""))

            if key in enriched_existing:
                row.update(enriched_existing[key])
                skipped += 1
            else:
                address = row.get("address", "").strip()
                city    = row.get("city", "").strip()
                logging.info("[%d/%d] Geocoding: %s, %s", i, total, address, city)
                lat, lng, status = geocode(address, city)
                row["lat"]            = lat
                row["lng"]            = lng
                row["geocode_status"] = status
                if status in ("ok", "ok_approx"):
                    done += 1
                else:
                    errors += 1
                    error_rows.append(row)
                time.sleep(REQUEST_DELAY)

            writer.writerow(row)

    with open(ERRORS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(error_rows)

    logging.info("Done. %d geocoded, %d skipped (already done), %d no result/error. Saved to %s",
                 done, skipped, errors, OUTPUT_FILE)
    if error_rows:
        logging.info("%d failed rows written to %s", len(error_rows), ERRORS_FILE)


if __name__ == "__main__":
    main()
