# Denver Restaurant Openings & Closings

An automated tracker of Denver-area restaurant openings and closings, sourced from [Westword](https://www.westword.com/tag/openings-closings/) and plotted on an interactive map.

**[View the live map](https://tcadieux.github.io/DenverRestaurant/map.html)**

---

## How It Works

1. **Scraper** (`westword_scraper.py`) — crawls Westword's openings/closings tag page and parses each article for structured opening and closing events. Runs incrementally, skipping articles already seen.

2. **Geocoder** (`enrich_geocode.py`) — takes each address and looks up its latitude/longitude via [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap). Only new or previously failed addresses are retried.

3. **Map generator** (`generate_map.py`) — reads the enriched data and produces a self-contained `map.html` with interactive filters.

4. **GitHub Actions** (`.github/workflows/scrape.yml`) — runs the full pipeline every Sunday at 3am Mountain Time and commits updated data back to the repo. GitHub Pages then serves the updated map automatically.

---

## Map Features

- **Hover** a marker to see the full event timeline at that address
- **Click** a marker to pin the popup open
- **Green** markers = currently open, **Red** = closed, **Orange** = approximate location (address matched after dropping cardinal direction)
- **Filters**: Status (Open / Closed / Changed), City, Year, Month, Name search — all support multi-select
- **Changed** filter shows locations where multiple different businesses have operated

---

## Data Files

| File                              | Description                                        |
| --------------------------------- | -------------------------------------------------- |
| `westword_openings_closings.csv`  | Deduplicated scrape output                         |
| `westword_enriched.csv`           | Above + lat/lng/geocode_status                     |
| `westword_geocode_errors.csv`     | Addresses that could not be geocoded               |
| `westword_duplicates.csv`         | Entries removed during deduplication, with reason  |
| `westword_seen_urls.txt`          | All article URLs fetched (prevents re-scraping)    |
| `map.html`                        | Self-contained interactive map                     |

---

## Manual Corrections

To manually fix a geocoding miss, edit `westword_enriched.csv` directly:

- Set `lat` and `lng` to the correct coordinates
- Set `geocode_status` to `ok`
- Rerun `python generate_map.py` and push

---

*Built with Python, BeautifulSoup, Nominatim, and Folium. Data sourced from Westword — all credit to their restaurant journalism.*
