# Changelog

## 2026-03-30

### Added

- **map2.html** — new modern split-panel UI built on raw Leaflet
  - Scrollable card list on the left, map on the right
  - Cards with colored left borders (green/red) and status badges
  - Click card to pan map; click marker to highlight card
  - Filters collapse on card selection, giving more room to detail view
  - City filter uses checkbox dropdown for easy multi-select
  - Timeline bar chart with stacked opened/closed bars and dual-thumb date range slider
  - Mobile: full-screen map, hamburger menu for filters, bottom sheet on marker tap with full event history and article links
- **generate_map_v2.py** — generator for the new map UI
- **CHANGELOG.md** — this file

### Changed

- **generate_map.py** — classic map improvements:
  - Responsive layout: desktop sidebar (always visible) + mobile hamburger menu
  - Timeline bar chart with date range slider added to both views
  - Marker hover shows full event timeline; click pins the popup
  - "Changed" status filter for locations with multiple businesses
  - City dropdown fixed (was showing single letters)
- **enrich_geocode.py**:
  - Cardinal direction fallback: retries addresses after stripping North/South/East/West
  - `ok_approx` geocode status for approximate matches (shown as orange markers)
  - `state=Colorado` added to structured Nominatim queries
  - Writes `westword_geocode_errors.csv` with all failed rows
  - Only retries `no_result`/`error` rows on rerun (skips `ok`/`ok_approx`)
- **westword_scraper.py**:
  - Rich logging with article URL, title, and date on all warnings
  - DIA/airport entries normalized to `8500 Pena Boulevard` with concourse in notes
  - Dedup key uses `(name, address, status, year, month)` to avoid merging separate events
  - Writes `westword_duplicates.csv` with duplicate reason notes
- **.github/workflows/scrape.yml**:
  - Added `permissions: contents: write` for push access
  - Fixed `--ignore-unmatch` syntax
  - Now generates both `map.html` and `map2.html`
- **README.md** — rewritten with links to both map versions, full feature lists, and data file table

## 2026-03-19 (Initial)

- Initial scraper, geocoder, and Folium map
- GitHub Actions weekly workflow
- GitHub Pages deployment
