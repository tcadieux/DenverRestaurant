# Denver Restaurant Openings & Closings

An automated tracker of Denver-area restaurant openings and closings, sourced from [Westword](https://www.westword.com/tag/openings-closings/) and plotted on an interactive map.

**[View the map (v2)](https://tcadieux.github.io/DenverRestaurant/map2.html)** — modern split-panel UI with card list, timeline chart, and filters

**[View the classic map](https://tcadieux.github.io/DenverRestaurant/map.html)** — sidebar + Folium-based map with hover tooltips

---

## How It Works

1. **Scraper** (`westword_scraper.py`) — crawls Westword's openings/closings tag page and parses each article for structured opening and closing events. Runs incrementally, skipping articles already seen.

2. **Geocoder** (`enrich_geocode.py`) — takes each address and looks up its latitude/longitude via [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap). Only new or previously failed addresses are retried. Falls back to stripping cardinal directions (North, South, East, West) when the full address doesn't match.

3. **Map generators**:
   - `generate_map.py` — Folium-based classic map with sidebar filters
   - `generate_map_v2.py` — modern split-panel UI built on raw Leaflet with card list, timeline bar chart, and responsive mobile layout

4. **GitHub Actions** (`.github/workflows/scrape.yml`) — runs the full pipeline every Sunday at 3am Mountain Time and commits updated data back to the repo. GitHub Pages then serves the updated maps automatically.

---

## Map Features

### v2 (map2.html)
- **Split panel** — scrollable card list on the left, map on the right
- **Click a card** to pan the map; click a marker to highlight its card
- **Filters collapse** when viewing a card to maximize detail space
- **Timeline bar chart** with dual-thumb range slider showing opened/closed activity by month
- **City filter** with checkbox dropdown for multi-select
- **Status chips** — All / Opened / Closed / Changed
- **Mobile** — full-screen map with hamburger menu for filters, bottom sheet on marker tap
- Cards show colored left borders (green=open, red=closed), status badges, and full event history with article links

### Classic (map.html)
- **Hover** a marker to see the full event timeline at that address
- **Click** a marker to pin the popup open
- **Green** markers = currently open, **Red** = closed, **Orange** = approximate location
- **Filters**: Status, City, Year, Month, Name search
- Desktop sidebar with project info; mobile hamburger menu

---

## Data Files

| File | Description |
| --- | --- |
| `westword_openings_closings.csv` | Deduplicated scrape output |
| `westword_enriched.csv` | Above + lat/lng/geocode_status |
| `westword_geocode_errors.csv` | Addresses that could not be geocoded |
| `westword_duplicates.csv` | Entries removed during deduplication, with reason |
| `map.html` | Classic interactive map (Folium) |
| `map2.html` | Modern split-panel map (Leaflet) |

---

## Manual Corrections

To manually fix a geocoding miss, edit `westword_enriched.csv` directly:

- Set `lat` and `lng` to the correct coordinates
- Set `geocode_status` to `ok`
- Rerun `python generate_map.py && python generate_map_v2.py` and push

---

*Built with Python, BeautifulSoup, Nominatim, Folium, and Leaflet. Data sourced from Westword — all credit to their restaurant journalism.*
