#!/usr/bin/env python3
"""
Modern Map UI (v2)
------------------
Reads westword_enriched.csv and generates map2.html — a modern split-panel
interface with a scrollable card list on the left and Leaflet map on the right.
"""

import argparse
import csv
import json
from collections import defaultdict

INPUT_FILE = "westword_enriched.csv"
OUTPUT_FILE = "map2.html"

MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def load_data():
    raw = defaultdict(list)
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("geocode_status") not in ("ok", "ok_approx"):
                continue
            key = (row["address"].strip(), row["city"].strip())
            raw[key].append(row)

    locations = []
    for (address, city), events in raw.items():
        events.sort(key=lambda r: r.get("post_date") or "")
        last = events[-1]
        if not last.get("lat") or not last.get("lng"):
            continue
        names = {e.get("restaurant_name", "").strip() for e in events if e.get("restaurant_name")}
        approx = any(e.get("geocode_status") == "ok_approx" for e in events)
        locations.append({
            "lat": float(last["lat"]),
            "lng": float(last["lng"]),
            "address": address,
            "city": city,
            "current_status": last.get("status", ""),
            "current_name": last.get("restaurant_name", ""),
            "approx": approx,
            "changed": len(names) > 1,
            "events": [
                {
                    "date": e.get("post_date", ""),
                    "status": e.get("status", ""),
                    "name": e.get("restaurant_name", ""),
                    "notes": e.get("notes", ""),
                    "url": e.get("article_url", ""),
                }
                for e in events
            ],
        })
    return locations


def build_timeline(locations):
    counts = defaultdict(lambda: {"opened": 0, "closed": 0})
    for loc in locations:
        for e in loc["events"]:
            d = e.get("date", "")
            if len(d) >= 7:
                ym = d[:7]
                counts[ym][e.get("status", "closed")] += 1
    timeline = []
    for ym in sorted(counts):
        year, month = ym.split("-")
        label = f"{MONTH_ORDER[int(month)-1][:3]} {year}"
        timeline.append({
            "ym": ym, "label": label,
            "opened": counts[ym].get("opened", 0),
            "closed": counts[ym].get("closed", 0),
        })
    return timeline


def get_cities(locations):
    return sorted({loc["city"] for loc in locations if loc.get("city")})


def generate_html(locations, timeline, cities):
    data_json = json.dumps(locations)
    timeline_json = json.dumps(timeline)
    cities_json = json.dumps(cities)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Denver Restaurant Tracker</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{
    --bg: #ffffff;
    --card: #ffffff;
    --text: #1a1a1a;
    --muted: #888;
    --border: #eaeaea;
    --accent: #2563eb;
    --open: #10b981;
    --open-bg: #ecfdf5;
    --closed: #ef4444;
    --closed-bg: #fef2f2;
    --approx: #f59e0b;
    --radius: 12px;
    --shadow: 0 2px 8px rgba(0,0,0,.06);
    --shadow-lg: 0 8px 24px rgba(0,0,0,.1);
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: var(--bg); color: var(--text);
    height:100vh; overflow:hidden;
  }}

  /* ---- Layout ---- */
  .app {{ display:flex; height:100vh; }}
  .panel {{
    width:420px; min-width:420px; display:flex; flex-direction:column;
    background:var(--bg);
    border-right:1px solid var(--border);
    position:relative; z-index:10;
  }}
  .map-wrap {{ flex:1; position:relative; }}
  #map {{ height:100%; width:100%; }}

  /* ---- Panel header ---- */
  .panel-header {{
    padding:20px 20px 0; flex-shrink:0;
    transition:max-height .3s ease, opacity .3s ease;
    overflow:hidden;
  }}
  .panel-header.collapsed {{
    max-height:0 !important; padding:0 20px; opacity:0;
    pointer-events:none;
  }}
  .panel-expand-bar {{
    display:none; padding:8px 20px; cursor:pointer;
    font-size:12px; color:var(--accent); font-weight:500;
    border-bottom:1px solid var(--border); text-align:center;
    user-select:none;
  }}
  .panel-expand-bar:hover {{ background:#f9fafb; }}
  .panel-expand-bar.visible {{ display:block; }}
  .brand {{
    display:flex; align-items:center; gap:10px; margin-bottom:14px;
  }}
  .brand-icon {{
    width:40px; height:40px;
    background:linear-gradient(135deg, var(--open), var(--accent));
    border-radius:10px;
    display:flex; align-items:center; justify-content:center;
    font-size:20px; color:white; font-weight:700;
    box-shadow:0 2px 8px rgba(37,99,235,.25);
  }}
  .brand h1 {{ font-size:18px; font-weight:700; letter-spacing:-.3px; }}
  .brand-sub {{
    font-size:12.5px; color:var(--muted); margin-top:2px; line-height:1.4;
  }}
  .brand-sub a {{ color:var(--accent); text-decoration:none; font-weight:500; }}
  .brand-sub a:hover {{ text-decoration:underline; }}

  .search-wrap {{
    position:relative; margin-bottom:14px;
  }}
  .search-wrap svg {{
    position:absolute; left:12px; top:50%; transform:translateY(-50%);
    color:var(--muted); width:16px; height:16px;
  }}
  .search-input {{
    width:100%; padding:11px 14px 11px 38px;
    border:none; border-radius:var(--radius);
    font-size:14px; background:#f3f4f6;
    transition:all .15s;
  }}
  .search-input:focus {{
    outline:none; background:#fff;
    box-shadow:0 0 0 2px var(--accent);
  }}

  /* ---- Filter chips ---- */
  .chips {{
    display:flex; gap:6px; flex-wrap:wrap; padding-bottom:14px;
    border-bottom:1px solid var(--border);
  }}
  .chip {{
    padding:7px 16px; border-radius:20px; font-size:12px; font-weight:600;
    border:none; background:#f3f4f6;
    cursor:pointer; user-select:none; transition:all .15s;
    white-space:nowrap; color:#555;
  }}
  .chip:hover {{ background:#e5e7eb; }}
  .chip.active {{ background:var(--accent); color:white; box-shadow:0 2px 8px rgba(37,99,235,.3); }}
  .chip.open.active {{ background:var(--open); box-shadow:0 2px 8px rgba(16,185,129,.3); }}
  .chip.closed.active {{ background:var(--closed); box-shadow:0 2px 8px rgba(239,68,68,.3); }}

  .filter-row {{
    display:flex; gap:8px; padding:10px 0;
    border-bottom:1px solid var(--border);
  }}
  .filter-select {{
    flex:1; padding:8px 12px; border:none;
    border-radius:var(--radius); font-size:12px; background:#f3f4f6;
    cursor:pointer; appearance:none;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23777' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
    background-repeat:no-repeat; background-position:right 10px center;
    padding-right:28px;
  }}
  .filter-select:focus {{ outline:none; box-shadow:0 0 0 2px var(--accent); }}

  .city-section {{
    padding:10px 0; border-bottom:1px solid var(--border);
  }}
  .city-label {{
    font-size:11px; font-weight:600; color:var(--muted);
    text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px;
  }}
  .city-dropdown {{ position:relative; }}
  .city-dd-toggle {{
    display:flex; justify-content:space-between; align-items:center;
    padding:8px 12px; background:#f3f4f6; border-radius:var(--radius);
    cursor:pointer; font-size:12px; user-select:none;
    overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
  }}
  .city-dd-toggle:hover {{ background:#e5e7eb; }}
  .city-dd-list {{
    display:none; position:absolute; top:100%; left:0; right:0;
    margin-top:4px; background:white; border:1px solid var(--border);
    border-radius:var(--radius); max-height:200px; overflow-y:auto;
    z-index:20; box-shadow:var(--shadow-lg);
  }}
  .city-dd-list.open {{ display:block; }}
  .city-dd-item {{
    display:flex; align-items:center; gap:8px;
    padding:6px 12px; font-size:12px; cursor:pointer;
  }}
  .city-dd-item:hover {{ background:#f9fafb; }}
  .city-dd-item input {{ margin:0; accent-color:var(--accent); }}

  .results-meta {{
    padding:10px 0; font-size:12px; color:var(--muted);
    display:flex; justify-content:space-between; align-items:center;
  }}
  .results-meta a {{
    color:var(--accent); text-decoration:none; font-weight:500;
  }}

  /* ---- Card list ---- */
  .card-list {{
    flex:1; overflow-y:auto; padding:0 20px 20px;
    -webkit-overflow-scrolling:touch;
  }}
  .card {{
    background:var(--card); border-radius:var(--radius);
    padding:14px 16px; margin-bottom:10px;
    box-shadow:var(--shadow); cursor:pointer;
    border-left:4px solid transparent;
    transition:all .2s;
  }}
  .card.card-opened {{ border-left-color:var(--open); }}
  .card.card-closed {{ border-left-color:var(--closed); }}
  .card:hover {{ box-shadow:var(--shadow-lg); transform:translateY(-1px); }}
  .card.active {{
    box-shadow:0 0 0 2px var(--accent), var(--shadow-lg);
    transform:translateY(-1px);
  }}

  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .card-name {{ font-size:15px; font-weight:600; line-height:1.3; }}
  .card-badge {{
    flex-shrink:0; padding:4px 10px; border-radius:20px;
    font-size:10px; font-weight:700; text-transform:uppercase;
    letter-spacing:.5px; margin-left:10px;
  }}
  .badge-opened {{ background:var(--open-bg); color:var(--open); }}
  .badge-closed {{ background:var(--closed-bg); color:var(--closed); }}

  .card-address {{
    font-size:12px; color:var(--muted); margin-top:4px;
  }}
  .card-date {{
    font-size:11px; color:var(--muted); margin-top:6px;
  }}
  .card-history {{
    margin-top:8px; padding-top:8px; border-top:1px solid var(--border);
    font-size:12px;
  }}
  .card-history-row {{
    display:flex; gap:8px; padding:2px 0;
  }}
  .card-history-row .h-date {{ color:var(--muted); min-width:72px; }}
  .card-history-row .h-status {{ font-weight:600; min-width:48px; }}
  .card-history-row .h-name {{ color:var(--text); }}
  .card-history-row a {{ color:var(--text); text-decoration:none; }}
  .card-history-row a:hover {{ text-decoration:underline; }}

  /* ---- Timeline ---- */
  .timeline-section {{
    padding:12px 0; border-bottom:1px solid var(--border);
  }}
  .timeline-label {{
    font-size:11px; font-weight:600; color:var(--muted);
    text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px;
  }}
  .tl-chart {{
    display:flex; align-items:flex-end; gap:2px; height:48px;
    background:#f9fafb;
    border-radius:8px; padding:4px 3px; overflow:hidden;
  }}
  .tl-bar {{
    flex:1; min-width:0; display:flex; flex-direction:column;
    justify-content:flex-end; position:relative; cursor:pointer;
  }}
  .tl-bar .tl-open {{ background:var(--open); border-radius:1px 1px 0 0; }}
  .tl-bar .tl-closed {{ background:var(--closed); }}
  .tl-bar.dim .tl-open, .tl-bar.dim .tl-closed {{ opacity:.15; }}
  .tl-tip {{
    display:none; position:absolute; bottom:100%; left:50%;
    transform:translateX(-50%); background:#333; color:white;
    font-size:10px; padding:3px 6px; border-radius:4px;
    white-space:nowrap; z-index:10; pointer-events:none;
    margin-bottom:2px;
  }}
  .tl-bar:hover .tl-tip {{ display:block; }}

  .tl-range {{
    display:flex; justify-content:space-between;
    font-size:10px; color:var(--muted); margin-top:4px;
  }}
  .dual-slider {{ position:relative; height:20px; margin-top:2px; }}
  .dual-slider input {{
    position:absolute; top:0; left:0; width:100%;
    -webkit-appearance:none; appearance:none;
    background:none; pointer-events:none; margin:0; height:20px;
  }}
  .dual-slider input::-webkit-slider-thumb {{
    -webkit-appearance:none; width:14px; height:14px; border-radius:50%;
    background:var(--text); border:2px solid white;
    box-shadow:0 1px 3px rgba(0,0,0,.3);
    cursor:pointer; pointer-events:auto; margin-top:-5px;
  }}
  .dual-slider input::-webkit-slider-runnable-track {{
    height:4px; background:var(--border); border-radius:2px;
  }}
  .dual-slider input::-moz-range-thumb {{
    width:14px; height:14px; border-radius:50%;
    background:var(--text); border:2px solid white;
    box-shadow:0 1px 3px rgba(0,0,0,.3);
    cursor:pointer; pointer-events:auto;
  }}
  .dual-slider input::-moz-range-track {{
    height:4px; background:var(--border); border-radius:2px;
  }}

  /* ---- Map markers ---- */
  .leaflet-popup-content-wrapper {{
    border-radius:var(--radius) !important;
    box-shadow:var(--shadow-lg) !important;
    font-family:inherit !important;
  }}
  .leaflet-popup-content {{ margin:12px 14px !important; font-size:13px; }}

  /* ---- Footer ---- */
  .panel-footer {{
    padding:12px 20px; border-top:1px solid var(--border);
    font-size:11px; color:var(--muted); flex-shrink:0;
    display:flex; justify-content:space-between; align-items:center;
  }}
  .panel-footer a {{ color:var(--accent); text-decoration:none; }}

  /* ---- Mobile top bar ---- */
  .m-topbar {{
    display:none; position:fixed; top:0; left:0; right:0; z-index:1001;
    height:52px; background:white; box-shadow:0 2px 8px rgba(0,0,0,.1);
    padding:0 14px; align-items:center; gap:10px;
    font-family:inherit;
  }}
  .m-topbar .m-title {{
    flex:1; font-size:15px; font-weight:700; color:var(--text);
  }}
  .m-topbar .m-count {{
    font-size:11px; color:var(--muted);
  }}
  .m-hamburger {{
    background:none; border:none; cursor:pointer; padding:6px;
    display:flex; flex-direction:column; gap:4px;
  }}
  .m-hamburger span {{
    display:block; width:20px; height:2px; background:var(--text); border-radius:1px;
  }}

  /* ---- Mobile filter overlay ---- */
  .m-overlay {{
    display:none; position:fixed; inset:0; z-index:1002;
    background:rgba(0,0,0,.4);
  }}
  .m-overlay.open {{ display:block; }}
  .m-filter-panel {{
    display:none; position:fixed; top:0; left:0; bottom:0; z-index:1003;
    width:min(340px,85vw); background:white; overflow-y:auto;
    padding:16px 20px; transform:translateX(-100%);
    transition:transform .25s ease;
    box-shadow:4px 0 16px rgba(0,0,0,.1);
  }}
  .m-filter-panel.open {{ transform:translateX(0); }}
  .m-filter-close {{
    position:absolute; top:12px; right:12px;
    background:none; border:none; font-size:24px;
    cursor:pointer; color:var(--muted); line-height:1;
  }}

  /* ---- Mobile bottom sheet ---- */
  .m-sheet {{
    display:none; position:fixed; bottom:0; left:0; right:0; z-index:1001;
    background:white; border-radius:16px 16px 0 0;
    box-shadow:0 -4px 20px rgba(0,0,0,.12);
    max-height:45vh; overflow-y:auto;
    padding:0 20px 20px; font-family:inherit;
    transform:translateY(100%);
    transition:transform .25s ease;
  }}
  .m-sheet.open {{ transform:translateY(0); }}
  .m-sheet-handle {{
    display:flex; justify-content:center; padding:10px 0 6px;
    cursor:pointer; position:sticky; top:0; background:white;
    border-radius:16px 16px 0 0;
  }}
  .m-sheet-handle span {{
    display:block; width:36px; height:4px; background:#ddd; border-radius:2px;
  }}
  .m-sheet .card-name {{ font-size:18px; font-weight:700; line-height:1.3; }}
  .m-sheet .card-badge {{ margin-left:0; flex-shrink:0; }}
  .sheet-address, .sheet-city {{
    display:flex; align-items:center; gap:6px;
    font-size:13px; color:var(--muted); margin-top:6px;
  }}
  .sheet-events {{
    margin-top:12px; padding-top:10px; border-top:1px solid var(--border);
  }}
  .sheet-event {{
    display:flex; gap:10px; padding:8px 0;
    border-bottom:1px solid #f5f5f5;
  }}
  .sheet-event:last-child {{ border-bottom:none; }}
  .sheet-event-dot {{
    width:8px; height:8px; border-radius:50%; margin-top:5px; flex-shrink:0;
  }}
  .sheet-event-body {{ flex:1; min-width:0; }}
  .sheet-event-name {{ font-size:14px; font-weight:600; }}
  .sheet-event-meta {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .sheet-event-link {{
    font-size:11px; color:var(--accent); text-decoration:none;
    font-weight:500; margin-top:2px; display:inline-block;
  }}

  /* ---- Responsive ---- */
  @media (max-width:768px) {{
    .panel {{ display:none; }}
    .map-wrap {{ height:100vh; width:100vw; }}
    .m-topbar {{ display:flex; }}
    .m-filter-panel {{ display:block; }}
    .m-sheet {{ display:block; }}
    .leaflet-container {{ margin-top:52px; }}
  }}
</style>
</head>
<body>
<div class="app">
  <div class="panel">
    <div class="panel-header">
      <div class="brand">
        <div class="brand-icon">D</div>
        <div>
          <h1>Denver Restaurant Tracker</h1>
          <div class="brand-sub">Every opening and closing in the Denver metro area, mapped from
            <a href="https://www.westword.com/tag/openings-closings/" target="_blank">Westword</a>
            coverage. Updated weekly.</div>
        </div>
      </div>

      <div class="search-wrap">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
        </svg>
        <input type="text" id="search" class="search-input"
               placeholder="Search restaurants..." oninput="applyFilters()"/>
      </div>

      <div class="chips" id="status-chips">
        <span class="chip active" data-val="" onclick="setChip(this)">All</span>
        <span class="chip open" data-val="opened" onclick="setChip(this)">Opened</span>
        <span class="chip closed" data-val="closed" onclick="setChip(this)">Closed</span>
        <span class="chip" data-val="changed" onclick="setChip(this)">Changed</span>
      </div>

      <div class="city-section">
        <div class="city-label">City</div>
        <div class="city-dropdown" id="city-dd">
          <div class="city-dd-toggle" onclick="toggleCityDd('city-dd')">
            <span id="city-dd-label">All cities</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
          </div>
          <div class="city-dd-list" id="city-dd-list"></div>
        </div>
      </div>

      <div class="timeline-section">
        <div class="timeline-label">Activity</div>
        <div id="tl-chart" class="tl-chart"></div>
        <div class="tl-range">
          <span id="tl-from"></span><span id="tl-to"></span>
        </div>
        <div class="dual-slider">
          <input type="range" id="sl-min" min="0" max="1" value="0" oninput="onSlider('min')"/>
          <input type="range" id="sl-max" min="0" max="1" value="1" oninput="onSlider('max')"/>
        </div>
      </div>

      <div class="results-meta">
        <span id="result-count"></span>
        <a href="#" onclick="resetAll();return false">Reset</a>
      </div>
    </div>

    <div class="panel-expand-bar" id="expand-bar" onclick="expandFilters()">
      Show filters &#9662;
    </div>
    <div class="card-list" id="card-list"></div>

    <div class="panel-footer">
      <span>Data from <a href="https://www.westword.com/tag/openings-closings/"
            target="_blank">Westword</a></span>
      <a href="https://github.com/tcadieux/DenverRestaurant" target="_blank">GitHub</a>
    </div>
  </div>

  <div class="map-wrap">
    <div id="map"></div>
  </div>
</div>

<!-- Mobile top bar -->
<div class="m-topbar">
  <button class="m-hamburger" onclick="toggleMobileFilter()">
    <span></span><span></span><span></span>
  </button>
  <div class="m-title">Denver Restaurant Tracker</div>
  <div class="m-count" id="m-count"></div>
</div>
<div class="m-overlay" id="m-overlay" onclick="toggleMobileFilter()"></div>
<div class="m-filter-panel" id="m-filter-panel">
  <button class="m-filter-close" onclick="toggleMobileFilter()">&times;</button>
  <h2 style="font-size:17px;margin:0 0 4px">Denver Restaurant Tracker</h2>
  <p style="font-size:12px;color:var(--muted);line-height:1.5;margin:0 0 14px">
    Every opening and closing in the Denver metro area, mapped from
    <a href="https://www.westword.com/tag/openings-closings/" target="_blank"
       style="color:var(--accent);text-decoration:none">Westword</a>.
    Updated weekly.
  </p>

  <input type="text" id="m-search" class="search-input" style="margin-bottom:12px"
         placeholder="Search restaurants..." oninput="syncSearch(this);applyFilters()"/>

  <div class="chips" style="margin-bottom:12px">
    <span class="chip active" data-val="" onclick="setChip(this)">All</span>
    <span class="chip open" data-val="opened" onclick="setChip(this)">Opened</span>
    <span class="chip closed" data-val="closed" onclick="setChip(this)">Closed</span>
    <span class="chip" data-val="changed" onclick="setChip(this)">Changed</span>
  </div>

  <div style="margin-bottom:12px">
    <div class="city-label">City</div>
    <div class="city-dropdown" id="m-city-dd">
      <div class="city-dd-toggle" onclick="toggleCityDd('m-city-dd')">
        <span id="m-city-dd-label">All cities</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
      </div>
      <div class="city-dd-list" id="m-city-dd-list"></div>
    </div>
  </div>

  <div style="margin-bottom:12px">
    <div class="timeline-label">Activity</div>
    <div id="m-tl-chart" class="tl-chart"></div>
    <div class="tl-range">
      <span id="m-tl-from"></span><span id="m-tl-to"></span>
    </div>
    <div class="dual-slider">
      <input type="range" id="m-sl-min" min="0" max="1" value="0" oninput="onSlider('min')"/>
      <input type="range" id="m-sl-max" min="0" max="1" value="1" oninput="onSlider('max')"/>
    </div>
  </div>

  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <span id="m-result-count" style="font-size:12px;color:var(--muted)"></span>
    <a href="#" onclick="resetAll();return false" style="font-size:12px;color:var(--accent);text-decoration:none">Reset</a>
  </div>

  <div style="padding-top:12px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)">
    <a href="https://github.com/tcadieux/DenverRestaurant" target="_blank"
       style="color:var(--accent);text-decoration:none">View on GitHub</a>
  </div>
</div>

<!-- Mobile bottom sheet -->
<div class="m-sheet" id="m-sheet">
  <div class="m-sheet-handle" onclick="closeMobileSheet()"><span></span></div>
  <div id="m-sheet-content"></div>
</div>

<script>
var allLocations = {data_json};
var timeline = {timeline_json};
var cities = {cities_json};
var activeStatus = "";
var slMin = 0, slMax = timeline.length - 1;
var map, markers = {{}}, activeCardIdx = null;

// ---- Init ----
(function init() {{
  map = L.map("map", {{zoomControl: true}}).setView([39.7392, -104.9903], 11);
  L.tileLayer("https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png", {{
    attribution: '&copy; OSM &copy; CARTO', maxZoom: 20
  }}).addTo(map);

  // Populate city dropdowns
  ["city-dd-list","m-city-dd-list"].forEach(function(id) {{
    var list = document.getElementById(id);
    if (!list) return;
    cities.forEach(function(c) {{
      var item = document.createElement("label");
      item.className = "city-dd-item";
      item.innerHTML = '<input type="checkbox" value="' + c + '" onchange="onCityCheck()">' + c;
      list.appendChild(item);
    }});
  }});
  // Close dropdown on outside click
  document.addEventListener("click", function(e) {{
    if (!e.target.closest(".city-dropdown")) {{
      document.querySelectorAll(".city-dd-list").forEach(function(l) {{
        l.classList.remove("open");
      }});
    }}
  }});

  // Init sliders (desktop + mobile)
  var mx = timeline.length - 1;
  ["sl-min","m-sl-min"].forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) {{ el.max = mx; el.value = 0; }}
  }});
  ["sl-max","m-sl-max"].forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) {{ el.max = mx; el.value = mx; }}
  }});

  // Close mobile sheet on map tap
  map.on("click", function() {{
    if (window.innerWidth <= 768) closeMobileSheet();
  }});

  renderTimeline();
  applyFilters();
}})();

// ---- Timeline ----
function renderTimeline() {{
  var maxV = 1;
  timeline.forEach(function(t) {{
    var s = t.opened + t.closed;
    if (s > maxV) maxV = s;
  }});
  ["tl-chart","m-tl-chart"].forEach(function(cid) {{
    var el = document.getElementById(cid);
    if (!el) return;
    el.innerHTML = "";
    timeline.forEach(function(t, i) {{
      var oH = Math.round((t.opened / maxV) * 40);
      var cH = Math.round((t.closed / maxV) * 40);
      var dim = (i < slMin || i > slMax) ? " dim" : "";
      var bar = document.createElement("div");
      bar.className = "tl-bar" + dim;
      bar.innerHTML =
        '<div class="tl-tip">' + t.label + ': ' + t.opened + ' opened, ' + t.closed + ' closed</div>' +
        '<div class="tl-open" style="height:' + oH + 'px"></div>' +
        '<div class="tl-closed" style="height:' + cH + 'px"></div>';
      el.appendChild(bar);
    }});
  }});
  if (timeline.length) {{
    ["tl-from","m-tl-from"].forEach(function(id) {{
      var el = document.getElementById(id);
      if (el) el.textContent = timeline[slMin].label;
    }});
    ["tl-to","m-tl-to"].forEach(function(id) {{
      var el = document.getElementById(id);
      if (el) el.textContent = timeline[slMax].label;
    }});
  }}
}}

function onSlider(which) {{
  var isMob = window.innerWidth <= 768;
  var pfx = isMob ? "m-" : "";
  var mn = document.getElementById(pfx + "sl-min");
  var mx = document.getElementById(pfx + "sl-max");
  var lo = parseInt(mn.value), hi = parseInt(mx.value);
  if (which === "min" && lo > hi) mn.value = hi;
  if (which === "max" && hi < lo) mx.value = lo;
  slMin = parseInt(mn.value);
  slMax = parseInt(mx.value);
  // Sync other set
  var opfx = isMob ? "" : "m-";
  var omn = document.getElementById(opfx + "sl-min");
  var omx = document.getElementById(opfx + "sl-max");
  if (omn) omn.value = slMin;
  if (omx) omx.value = slMax;
  renderTimeline();
  applyFilters();
}}

// ---- Filters ----
function setChip(el) {{
  document.querySelectorAll(".chip").forEach(function(c) {{ c.classList.remove("active"); }});
  el.classList.add("active");
  activeStatus = el.dataset.val;
  applyFilters();
}}

function resetAll() {{
  activeStatus = "";
  document.querySelectorAll(".chip").forEach(function(c) {{
    c.classList.toggle("active", c.dataset.val === "");
  }});
  document.getElementById("search").value = "";
  document.querySelectorAll(".city-dd-list input").forEach(function(cb) {{ cb.checked = false; }});
  updateCityLabels();
  slMin = 0; slMax = timeline.length - 1;
  document.getElementById("sl-min").value = 0;
  document.getElementById("sl-max").value = slMax;
  renderTimeline();
  applyFilters();
}}

function applyFilters() {{
  var query = document.getElementById("search").value.toLowerCase().trim();
  var selCities = [];
  document.querySelectorAll("#city-dd-list input:checked, #m-city-dd-list input:checked").forEach(function(cb) {{
    if (selCities.indexOf(cb.value) === -1) selCities.push(cb.value);
  }});
  var ymFrom = timeline.length ? timeline[slMin].ym : "";
  var ymTo = timeline.length ? timeline[slMax].ym + "-31" : "";

  // Clear markers
  Object.keys(markers).forEach(function(k) {{ map.removeLayer(markers[k]); }});
  markers = {{}};
  activeCardIdx = null;

  var list = document.getElementById("card-list");
  list.innerHTML = "";
  var count = 0;

  allLocations.forEach(function(loc, idx) {{
    // Status filter
    if (activeStatus === "changed") {{ if (!loc.changed) return; }}
    else if (activeStatus && loc.current_status !== activeStatus) return;
    // City
    if (selCities.length && selCities.indexOf(loc.city) === -1) return;
    // Timeline
    if (ymFrom) {{
      var inRange = loc.events.some(function(e) {{
        return e.date >= ymFrom && e.date <= ymTo;
      }});
      if (!inRange) return;
    }}
    // Name search
    if (query) {{
      var match = loc.current_name.toLowerCase().includes(query) ||
        loc.events.some(function(e) {{ return e.name.toLowerCase().includes(query); }});
      if (!match) return;
    }}

    count++;

    // Marker
    var color = loc.approx ? "#f59e0b"
              : loc.current_status === "opened" ? "#16a34a" : "#dc2626";
    var m = L.circleMarker([loc.lat, loc.lng], {{
      radius:7, color:color, fillColor:color, fillOpacity:.85, weight:1.5
    }}).addTo(map);
    m.on("click", function(e) {{ L.DomEvent.stopPropagation(e); highlightCard(idx); }});

    var tipRows = loc.events.map(function(e) {{
      var sc = e.status === "opened" ? "color:#16a34a" : "color:#dc2626";
      return '<tr><td style="padding:1px 6px 1px 0;' + sc + '">' + e.date + '</td>' +
        '<td style="padding:1px 6px 1px 0;font-weight:600;' + sc + '">' + e.status + '</td>' +
        '<td style="padding:1px 0"><a href="' + e.url + '" target="_blank" ' +
        'style="color:#333;text-decoration:none">' + e.name + '</a></td></tr>';
    }}).join("");
    m.bindTooltip(
      '<div style="font-family:inherit;font-size:12px;min-width:200px">' +
      '<b>' + loc.address + '</b><br><span style="color:#777">' + loc.city + '</span>' +
      '<hr style="margin:4px 0;border:none;border-top:1px solid #eee">' +
      '<table style="border-collapse:collapse">' + tipRows + '</table></div>',
      {{sticky:false, maxWidth:380}}
    );
    markers[idx] = m;

    // Card
    var card = document.createElement("div");
    card.className = "card card-" + loc.current_status;
    card.dataset.idx = idx;
    card.onclick = function() {{ highlightCard(idx); }};

    var lastEvt = loc.events[loc.events.length - 1];
    var badgeClass = lastEvt.status === "opened" ? "badge-opened" : "badge-closed";
    var badgeText = lastEvt.status === "opened" ? "Open" : "Closed";

    var historyHtml = "";
    if (loc.events.length > 1) {{
      historyHtml = '<div class="card-history">';
      loc.events.forEach(function(e) {{
        var sc = e.status === "opened" ? "color:var(--open)" : "color:var(--closed)";
        historyHtml += '<div class="card-history-row">' +
          '<span class="h-date">' + e.date + '</span>' +
          '<span class="h-status" style="' + sc + '">' + e.status + '</span>' +
          '<a href="' + e.url + '" target="_blank" class="h-name">' + e.name + '</a></div>';
      }});
      historyHtml += '</div>';
    }}

    card.innerHTML =
      '<div class="card-top">' +
        '<div class="card-name">' + loc.current_name + '</div>' +
        '<span class="card-badge ' + badgeClass + '">' + badgeText + '</span>' +
      '</div>' +
      '<div class="card-address">' + loc.address + ', ' + loc.city + '</div>' +
      '<div class="card-date">' + lastEvt.date +
        (loc.events.length > 1 ? ' &middot; ' + loc.events.length + ' events' : '') +
      '</div>' +
      historyHtml;

    list.appendChild(card);
  }});

  var countText = count + " location" + (count !== 1 ? "s" : "");
  document.getElementById("result-count").textContent = countText;
  var mrc = document.getElementById("m-result-count");
  if (mrc) mrc.textContent = countText;
  var mc = document.getElementById("m-count");
  if (mc) mc.textContent = countText;
}}

function collapseFilters() {{
  var hdr = document.querySelector(".panel-header");
  var bar = document.getElementById("expand-bar");
  if (hdr && window.innerWidth > 768) {{
    hdr.classList.add("collapsed");
    bar.classList.add("visible");
  }}
}}

function expandFilters() {{
  var hdr = document.querySelector(".panel-header");
  var bar = document.getElementById("expand-bar");
  hdr.classList.remove("collapsed");
  bar.classList.remove("visible");
}}

function highlightCard(idx) {{
  var loc = allLocations[idx];
  if (!loc) return;

  // Desktop: collapse filters, highlight card
  collapseFilters();
  document.querySelectorAll(".card.active").forEach(function(c) {{
    c.classList.remove("active");
  }});
  var card = document.querySelector('.card[data-idx="' + idx + '"]');
  if (card) {{
    card.classList.add("active");
    card.scrollIntoView({{behavior:"smooth", block:"nearest"}});
  }}

  // Pan map
  var m = markers[idx];
  if (m) {{
    map.setView(m.getLatLng(), Math.max(map.getZoom(), 14), {{animate:true}});
    m.openTooltip();
  }}

  // Mobile: show bottom sheet
  if (window.innerWidth <= 768) {{
    showMobileSheet(loc);
  }}

  activeCardIdx = idx;
}}

function showMobileSheet(loc) {{
  var sheet = document.getElementById("m-sheet");
  var content = document.getElementById("m-sheet-content");

  var lastEvt = loc.events[loc.events.length - 1];
  var badgeClass = lastEvt.status === "opened" ? "badge-opened" : "badge-closed";
  var badgeText = lastEvt.status === "opened" ? "OPEN" : "CLOSED";

  // Build event rows with article links
  var eventsHtml = '<div class="sheet-events">';
  loc.events.forEach(function(e) {{
    var sc = e.status === "opened" ? "var(--open)" : "var(--closed)";
    var notes = e.notes ? ' <span style="color:var(--muted);font-style:italic">(' + e.notes + ')</span>' : '';
    eventsHtml +=
      '<div class="sheet-event">' +
        '<div class="sheet-event-dot" style="background:' + sc + '"></div>' +
        '<div class="sheet-event-body">' +
          '<div class="sheet-event-name">' + e.name + notes + '</div>' +
          '<div class="sheet-event-meta">' +
            '<span style="color:' + sc + ';font-weight:600">' + e.status + '</span>' +
            ' &middot; ' + e.date +
          '</div>' +
          (e.url ? '<a href="' + e.url + '" target="_blank" class="sheet-event-link">View article &#8594;</a>' : '') +
        '</div>' +
      '</div>';
  }});
  eventsHtml += '</div>';

  content.innerHTML =
    '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px">' +
      '<div class="card-name">' + loc.current_name + '</div>' +
      '<span class="card-badge ' + badgeClass + '">' + badgeText + '</span>' +
    '</div>' +
    '<div class="sheet-address">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="2">' +
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>' +
      '</svg> ' +
      loc.address +
    '</div>' +
    '<div class="sheet-city">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="2">' +
        '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22V12h6v10M9 6h.01M15 6h.01M9 10h.01M15 10h.01"/>' +
      '</svg> ' +
      loc.city +
      ' &middot; ' + loc.events.length + ' event' + (loc.events.length !== 1 ? 's' : '') +
    '</div>' +
    eventsHtml;

  sheet.classList.add("open");
}}

function closeMobileSheet() {{
  document.getElementById("m-sheet").classList.remove("open");
}}

function toggleMobileFilter() {{
  document.getElementById("m-overlay").classList.toggle("open");
  document.getElementById("m-filter-panel").classList.toggle("open");
}}

function syncSearch(el) {{
  document.getElementById("search").value = el.value;
}}

function toggleCityDd(id) {{
  var list = document.getElementById(id + "-list");
  list.classList.toggle("open");
}}

function onCityCheck() {{
  // Sync both lists
  var checked = new Set();
  document.querySelectorAll(".city-dd-list input:checked").forEach(function(cb) {{
    checked.add(cb.value);
  }});
  document.querySelectorAll(".city-dd-list input").forEach(function(cb) {{
    cb.checked = checked.has(cb.value);
  }});
  updateCityLabels();
  applyFilters();
}}

function updateCityLabels() {{
  var checked = [];
  document.querySelectorAll("#city-dd-list input:checked").forEach(function(cb) {{
    checked.push(cb.value);
  }});
  var text = checked.length === 0 ? "All cities" : checked.join(", ");
  ["city-dd-label","m-city-dd-label"].forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }});
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=OUTPUT_FILE)
    args = parser.parse_args()

    locations = load_data()
    timeline = build_timeline(locations)
    cities = get_cities(locations)

    html = generate_html(locations, timeline, cities)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    opened = sum(1 for l in locations if l["current_status"] == "opened")
    closed = len(locations) - opened
    print(f"Saved to {args.output}")
    print(f"  {len(locations)} locations — {opened} open, {closed} closed")


if __name__ == "__main__":
    main()
