#!/usr/bin/env python3
"""
Map Generator with Interactive Filters
---------------------------------------
Reads westword_enriched.csv and produces a self-contained map.html.
One marker per address; popup shows a full timeline of events at that location.
Marker is green if the most recent event is an opening, red if a closing.

Interactive filters (client-side JS): Status, City, Year, Month, Name search.

Usage:
  python generate_map.py
  python generate_map.py --since 2026-01-01
  python generate_map.py --since 2026-01-01 --until 2026-03-31 --output q1.html
"""

import argparse
import csv
import json
from collections import defaultdict

import folium

INPUT_FILE    = "westword_enriched.csv"
DENVER_CENTER = [39.7392, -104.9903]
COLOR_OPEN    = "#2ecc71"
COLOR_CLOSED  = "#e74c3c"
COLOR_APPROX  = "#f39c12"  # orange — geocode matched after dropping cardinal direction

MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--since",  default="", help="Only load entries on or after YYYY-MM-DD")
    p.add_argument("--until",  default="", help="Only load entries on or before YYYY-MM-DD")
    p.add_argument("--output", default="map.html")
    return p.parse_args()


def load_locations(args):
    raw = defaultdict(list)
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("geocode_status") not in ("ok", "ok_approx"):
                continue
            post_date = row.get("post_date", "")
            if args.since and post_date and post_date < args.since:
                continue
            if args.until and post_date and post_date > args.until:
                continue
            key = (row["address"].strip(), row["city"].strip())
            raw[key].append(row)

    locations = {}
    for key, events in raw.items():
        events.sort(key=lambda r: r.get("post_date") or "")
        locations[key] = events
    return locations


def build_locations_json(locations):
    data = []
    for (address, city), events in locations.items():
        last = events[-1]
        if not last.get("lat") or not last.get("lng"):
            continue
        approx = any(e.get("geocode_status") == "ok_approx" for e in events)
        names = {e.get("restaurant_name", "").strip() for e in events if e.get("restaurant_name")}
        data.append({
            "lat":            float(last["lat"]),
            "lng":            float(last["lng"]),
            "address":        address,
            "city":           city,
            "current_status": last.get("status", ""),
            "current_name":   last.get("restaurant_name", ""),
            "approx":         approx,
            "changed":        len(names) > 1,
            "years":  sorted({e.get("year",  "") for e in events if e.get("year")}),
            "months": [m for m in MONTH_ORDER
                       if any(e.get("month") == m for e in events)],
            "events": [
                {
                    "date":   e.get("post_date", ""),
                    "status": e.get("status", ""),
                    "name":   e.get("restaurant_name", ""),
                    "notes":  e.get("notes", ""),
                    "url":    e.get("article_url", ""),
                }
                for e in events
            ],
        })
    return data


def build_timeline_data(locations_data):
    """Aggregate opened/closed counts by month for the bar chart."""
    from collections import defaultdict
    counts = defaultdict(lambda: {"opened": 0, "closed": 0})
    for loc in locations_data:
        for e in loc["events"]:
            d = e.get("date", "")
            if len(d) >= 7:
                ym = d[:7]  # "2025-01"
                counts[ym][e.get("status", "closed")] += 1
    timeline = []
    for ym in sorted(counts):
        year, month = ym.split("-")
        label = f"{MONTH_ORDER[int(month)-1][:3]} {year}"
        timeline.append({
            "ym": ym,
            "label": label,
            "opened": counts[ym].get("opened", 0),
            "closed": counts[ym].get("closed", 0),
        })
    return timeline


def unique_sorted(data, key, order=None):
    vals = sorted({v for d in data for v in d.get(key, []) if v})
    if order:
        vals = [v for v in order if v in set(vals)]
    return vals


def build_filter_html(cities, years, months, timeline):
    def checkboxes(vals):
        items = ""
        for v in vals:
            items += (
                f'<label class="cb-label">'
                f'<input type="checkbox" value="{v}" onchange="applyFilters()">{v}</label>'
            )
        return items

    return f"""
    <!-- Desktop sidebar -->
    <div id="sidebar">
      <div class="sidebar-scroll">
        <div class="sidebar-header">
          <h1>Denver Restaurant Tracker</h1>
          <p class="subtitle">Every opening and closing in the Denver metro area, mapped from
            <a href="https://www.westword.com/tag/openings-closings/" target="_blank">Westword</a>
            coverage. Updated weekly.</p>
          <div id="filter-count" class="count-label"></div>
        </div>

        <div class="sidebar-section">
          <div class="filter-label">Status</div>
          <div class="status-buttons">
            <button class="status-btn active" data-val=""        onclick="setStatus(this)">All</button>
            <button class="status-btn"        data-val="opened"  onclick="setStatus(this)">Open</button>
            <button class="status-btn"        data-val="closed"  onclick="setStatus(this)">Closed</button>
            <button class="status-btn"        data-val="changed" onclick="setStatus(this)">Changed</button>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="filter-label">Name</div>
          <input id="f-name" type="text" placeholder="Search restaurants…" oninput="applyFilters()" class="name-input"/>
        </div>

        <div class="sidebar-section">
          <div class="filter-label">City</div>
          <div class="ms-container" id="ms-city">
            <div class="ms-toggle" onclick="toggleMs('ms-city')">
              <span id="ms-city-label">All</span><span class="ms-arrow">&#9662;</span>
            </div>
            <div class="ms-list" id="ms-city-list">{checkboxes(cities)}</div>
          </div>
        </div>

        <div class="sidebar-row">
          <div class="sidebar-section" style="flex:1">
            <div class="filter-label">Year</div>
            <div class="ms-container" id="ms-year">
              <div class="ms-toggle" onclick="toggleMs('ms-year')">
                <span id="ms-year-label">All</span><span class="ms-arrow">&#9662;</span>
              </div>
              <div class="ms-list" id="ms-year-list">{checkboxes(years)}</div>
            </div>
          </div>
          <div class="sidebar-section" style="flex:1">
            <div class="filter-label">Month</div>
            <div class="ms-container" id="ms-month">
              <div class="ms-toggle" onclick="toggleMs('ms-month')">
                <span id="ms-month-label">All</span><span class="ms-arrow">&#9662;</span>
              </div>
              <div class="ms-list" id="ms-month-list">{checkboxes(months)}</div>
            </div>
          </div>
        </div>

        <button onclick="resetFilters()" class="reset-btn">Reset Filters</button>

        <div class="sidebar-section" style="margin-top:16px">
          <div class="filter-label">Timeline</div>
          <div id="timeline-chart" class="timeline-chart"></div>
          <div class="range-row">
            <span id="range-from" class="range-label"></span>
            <span id="range-to" class="range-label"></span>
          </div>
          <div class="dual-range">
            <input type="range" id="range-min" min="0" max="1" value="0"
                   oninput="syncRange('min')" class="range-input"/>
            <input type="range" id="range-max" min="0" max="1" value="1"
                   oninput="syncRange('max')" class="range-input"/>
          </div>
        </div>

        <div class="sidebar-footer">
          <div class="legend">
            <span class="legend-dot" style="background:#2ecc71"></span> Open
            <span class="legend-dot" style="background:#e74c3c"></span> Closed
            <span class="legend-dot" style="background:#f39c12"></span> Approx. location
          </div>
          <p class="footer-text">
            Hover a marker for details. Click to pin the popup.
            <br><br>
            Data sourced from <a href="https://www.westword.com/tag/openings-closings/" target="_blank">Westword</a>.
            Built with Python, Folium &amp; OpenStreetMap.
            <br>
            <a href="https://github.com/tcadieux/DenverRestaurant" target="_blank">View on GitHub</a>
          </p>
        </div>
      </div>
    </div>

    <!-- Mobile: top bar + hamburger menu -->
    <div id="mobile-bar">
      <button id="hamburger" onclick="toggleDrawer()" aria-label="Menu">
        <span></span><span></span><span></span>
      </button>
      <div class="bar-title">Denver Restaurant Tracker</div>
      <div id="filter-count-bar" class="bar-count"></div>
    </div>
    <div id="mobile-overlay" onclick="toggleDrawer()"></div>
    <div id="mobile-menu">
      <div class="menu-header">
        <h2>Denver Restaurant Tracker</h2>
        <button onclick="toggleDrawer()" class="close-btn">&times;</button>
      </div>
      <p class="menu-desc">Every opening and closing in the Denver metro area, mapped from
        <a href="https://www.westword.com/tag/openings-closings/" target="_blank">Westword</a>.
        Updated weekly.</p>
      <div class="drawer-count"></div>

      <div class="mobile-section">
        <div class="filter-label">Status</div>
        <div class="status-buttons">
          <button class="status-btn-m active" data-val=""        onclick="setStatus(this)">All</button>
          <button class="status-btn-m"        data-val="opened"  onclick="setStatus(this)">Open</button>
          <button class="status-btn-m"        data-val="closed"  onclick="setStatus(this)">Closed</button>
          <button class="status-btn-m"        data-val="changed" onclick="setStatus(this)">Changed</button>
        </div>
      </div>

      <div class="mobile-section">
        <div class="filter-label">Name</div>
        <input id="f-name-m" type="text" placeholder="Search restaurants…"
               oninput="syncName(this);applyFilters()" class="name-input"/>
      </div>

      <div class="mobile-section">
        <div class="filter-label">City</div>
        <div class="ms-container" id="ms-city-m">
          <div class="ms-toggle" onclick="toggleMs('ms-city-m')">
            <span id="ms-city-m-label">All</span><span class="ms-arrow">&#9662;</span>
          </div>
          <div class="ms-list" id="ms-city-m-list">{checkboxes(cities)}</div>
        </div>
      </div>

      <div class="mobile-row">
        <div class="mobile-section" style="flex:1">
          <div class="filter-label">Year</div>
          <div class="ms-container" id="ms-year-m">
            <div class="ms-toggle" onclick="toggleMs('ms-year-m')">
              <span id="ms-year-m-label">All</span><span class="ms-arrow">&#9662;</span>
            </div>
            <div class="ms-list" id="ms-year-m-list">{checkboxes(years)}</div>
          </div>
        </div>
        <div class="mobile-section" style="flex:1">
          <div class="filter-label">Month</div>
          <div class="ms-container" id="ms-month-m">
            <div class="ms-toggle" onclick="toggleMs('ms-month-m')">
              <span id="ms-month-m-label">All</span><span class="ms-arrow">&#9662;</span>
            </div>
            <div class="ms-list" id="ms-month-m-list">{checkboxes(months)}</div>
          </div>
        </div>
      </div>

      <div class="mobile-section">
        <div class="filter-label">Timeline</div>
        <div id="timeline-chart-m" class="timeline-chart"></div>
        <div class="range-row">
          <span id="range-from-m" class="range-label"></span>
          <span id="range-to-m" class="range-label"></span>
        </div>
        <div class="dual-range">
          <input type="range" id="range-min-m" min="0" max="1" value="0"
                 oninput="syncRange('min')" class="range-input"/>
          <input type="range" id="range-max-m" min="0" max="1" value="1"
                 oninput="syncRange('max')" class="range-input"/>
        </div>
      </div>

      <button onclick="resetFilters()" class="reset-btn">Reset Filters</button>

      <div class="menu-footer">
        <div class="legend">
          <span class="legend-dot" style="background:#2ecc71"></span> Open
          <span class="legend-dot" style="background:#e74c3c"></span> Closed
          <span class="legend-dot" style="background:#f39c12"></span> Approx.
        </div>
        <p class="footer-text">
          Tap a marker for details.
          <a href="https://github.com/tcadieux/DenverRestaurant" target="_blank">GitHub</a>
        </p>
      </div>
    </div>

    <style>
      * {{ box-sizing: border-box; }}
      body {{ margin:0; padding:0; }}

      /* ---- Desktop sidebar ---- */
      #sidebar {{
        display:none; position:fixed; top:0; left:0; bottom:0;
        width:320px; z-index:1000; background:#fff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size:13px; box-shadow:2px 0 12px rgba(0,0,0,.1);
      }}
      .sidebar-scroll {{
        height:100%; overflow-y:auto; padding:20px;
      }}
      .sidebar-header h1 {{
        font-size:18px; margin:0 0 8px 0; color:#222;
      }}
      .subtitle {{
        color:#666; font-size:13px; line-height:1.5; margin:0 0 12px 0;
      }}
      .subtitle a {{ color:#2563eb; text-decoration:none; }}
      .subtitle a:hover {{ text-decoration:underline; }}
      .count-label {{
        font-size:13px; color:#888; margin-bottom:16px;
        padding-bottom:12px; border-bottom:1px solid #eee;
      }}

      .sidebar-section {{ margin-bottom:14px; }}
      .sidebar-row {{ display:flex; gap:10px; margin-bottom:14px; }}

      .sidebar-footer {{
        margin-top:20px; padding-top:14px; border-top:1px solid #eee;
      }}
      .legend {{
        display:flex; align-items:center; gap:6px;
        font-size:12px; color:#555; margin-bottom:10px; flex-wrap:wrap;
      }}
      .legend-dot {{
        display:inline-block; width:10px; height:10px; border-radius:50%;
        margin-left:6px;
      }}
      .legend-dot:first-child {{ margin-left:0; }}
      .footer-text {{
        font-size:11px; color:#999; line-height:1.6; margin:0;
      }}
      .footer-text a {{ color:#2563eb; text-decoration:none; }}
      .footer-text a:hover {{ text-decoration:underline; }}

      /* ---- Shared filter styles ---- */
      .filter-label {{
        font-weight:600; font-size:11px; margin-bottom:4px;
        color:#555; text-transform:uppercase; letter-spacing:.5px;
      }}
      .status-buttons {{ display:flex; gap:4px; flex-wrap:wrap; }}
      .status-btn, .status-btn-m {{
        padding:6px 10px; border:1px solid #ddd; border-radius:6px;
        background:#f7f7f7; cursor:pointer; font-size:12px;
        white-space:nowrap; transition:all .15s;
      }}
      .status-btn:hover, .status-btn-m:hover {{ background:#eee; }}
      .status-btn.active, .status-btn-m.active {{
        background:#333; color:white; border-color:#333;
      }}
      .name-input {{
        width:100%; padding:6px 10px; border:1px solid #ddd;
        border-radius:6px; font-size:12px;
      }}
      .name-input:focus {{ outline:none; border-color:#2563eb; }}

      .ms-container {{ position:relative; }}
      .ms-toggle {{
        border:1px solid #ddd; border-radius:6px; padding:6px 10px;
        cursor:pointer; background:white; user-select:none;
        overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
        display:flex; justify-content:space-between; align-items:center;
        font-size:12px; transition:border-color .15s;
      }}
      .ms-toggle:hover {{ border-color:#999; }}
      .ms-arrow {{ font-size:10px; margin-left:6px; color:#999; }}
      .ms-list {{
        display:none; position:absolute; left:0; right:0;
        min-width:100%; width:max-content;
        background:white; border:1px solid #ddd; border-radius:6px;
        max-height:200px; overflow-y:auto; z-index:1002;
        box-shadow:0 4px 12px rgba(0,0,0,.12);
      }}
      /* Desktop: dropdowns open downward */
      #sidebar .ms-list {{ top:100%; margin-top:2px; }}
      /* Mobile: dropdowns open upward */
      #filter-drawer .ms-list {{ bottom:100%; margin-bottom:2px; }}
      .cb-label {{
        display:block; padding:5px 10px; cursor:pointer;
        white-space:nowrap; font-size:12px;
      }}
      .cb-label:hover {{ background:#f5f5f5; }}
      .cb-label input {{ margin-right:6px; }}

      .reset-btn {{
        width:100%; padding:8px; border:1px solid #ddd; border-radius:6px;
        background:#f7f7f7; cursor:pointer; font-size:12px;
        transition:background .15s;
      }}
      .reset-btn:hover {{ background:#eee; }}

      /* ---- Mobile top bar + menu ---- */
      #mobile-bar {{
        position:fixed; top:0; left:0; right:0; z-index:1001;
        background:#333; color:white; padding:0 14px;
        height:48px; display:flex; align-items:center; gap:10px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        box-shadow:0 2px 8px rgba(0,0,0,.2);
      }}
      .bar-title {{
        font-size:15px; font-weight:600; flex:1;
        white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
      }}
      .bar-count {{ font-size:11px; color:#aaa; white-space:nowrap; }}

      #hamburger {{
        background:none; border:none; cursor:pointer;
        padding:4px 2px; display:flex; flex-direction:column; gap:4px;
      }}
      #hamburger span {{
        display:block; width:20px; height:2px; background:white;
        border-radius:1px; transition:all .2s;
      }}
      #hamburger.open span:nth-child(1) {{ transform:rotate(45deg) translate(4px,4px); }}
      #hamburger.open span:nth-child(2) {{ opacity:0; }}
      #hamburger.open span:nth-child(3) {{ transform:rotate(-45deg) translate(4px,-4px); }}

      #mobile-overlay {{
        display:none; position:fixed; inset:0; z-index:1001;
        background:rgba(0,0,0,.4);
      }}
      #mobile-overlay.open {{ display:block; }}

      #mobile-menu {{
        position:fixed; top:0; left:0; bottom:0; z-index:1002;
        width:min(320px, 85vw); background:white;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size:13px; overflow-y:auto; padding:16px 20px;
        transform:translateX(-100%); transition:transform .25s ease;
        box-shadow:2px 0 16px rgba(0,0,0,.15);
      }}
      #mobile-menu.open {{ transform:translateX(0); }}

      .menu-header {{
        display:flex; justify-content:space-between; align-items:flex-start;
        margin-bottom:6px;
      }}
      .menu-header h2 {{ font-size:17px; margin:0; color:#222; }}
      .close-btn {{
        background:none; border:none; font-size:24px;
        cursor:pointer; color:#999; padding:0; line-height:1;
      }}
      .close-btn:hover {{ color:#333; }}
      .menu-desc {{
        color:#666; font-size:12px; line-height:1.5; margin:0 0 8px 0;
      }}
      .menu-desc a {{ color:#2563eb; text-decoration:none; }}
      .drawer-count {{
        color:#888; font-size:12px; margin-bottom:14px;
        padding-bottom:10px; border-bottom:1px solid #eee;
      }}

      .mobile-section {{ margin-bottom:14px; }}
      .mobile-row {{ display:flex; gap:10px; }}

      .menu-footer {{
        margin-top:16px; padding-top:12px; border-top:1px solid #eee;
      }}

      /* ---- Timeline chart + slider ---- */
      .timeline-chart {{
        display:flex; align-items:flex-end; gap:1px;
        height:80px; background:#fafafa; border:1px solid #eee;
        border-radius:6px; padding:4px 2px; overflow:hidden;
      }}
      .tbar {{
        flex:1; min-width:0; display:flex; flex-direction:column;
        justify-content:flex-end; cursor:pointer; position:relative;
      }}
      .tbar-open {{
        background:{COLOR_OPEN}; border-radius:2px 2px 0 0;
        min-height:0;
      }}
      .tbar-closed {{
        background:{COLOR_CLOSED}; border-radius:0;
        min-height:0;
      }}
      .tbar.dimmed .tbar-open {{ opacity:.2; }}
      .tbar.dimmed .tbar-closed {{ opacity:.2; }}
      .tbar-tip {{
        display:none; position:absolute; bottom:100%; left:50%;
        transform:translateX(-50%); background:#333; color:white;
        font-size:10px; padding:3px 6px; border-radius:4px;
        white-space:nowrap; z-index:10; pointer-events:none;
      }}
      .tbar:hover .tbar-tip {{ display:block; }}

      .range-row {{
        display:flex; justify-content:space-between;
        margin-top:4px; margin-bottom:0;
      }}
      .range-label {{ font-size:11px; color:#888; }}

      .dual-range {{
        position:relative; height:24px;
      }}
      .range-input {{
        position:absolute; top:0; left:0; width:100%;
        -webkit-appearance:none; appearance:none;
        background:none; pointer-events:none; margin:0;
        height:24px;
      }}
      .range-input::-webkit-slider-thumb {{
        -webkit-appearance:none; appearance:none;
        width:16px; height:16px; border-radius:50%;
        background:#333; border:2px solid white;
        box-shadow:0 1px 3px rgba(0,0,0,.3);
        cursor:pointer; pointer-events:auto;
        margin-top:-6px;
      }}
      .range-input::-webkit-slider-runnable-track {{
        height:4px; background:#ddd; border-radius:2px;
      }}
      .range-input::-moz-range-thumb {{
        width:16px; height:16px; border-radius:50%;
        background:#333; border:2px solid white;
        box-shadow:0 1px 3px rgba(0,0,0,.3);
        cursor:pointer; pointer-events:auto;
      }}
      .range-input::-moz-range-track {{
        height:4px; background:#ddd; border-radius:2px;
      }}

      /* ---- Responsive ---- */
      @media (min-width:769px) {{
        #sidebar {{ display:block; }}
        #mobile-bar {{ display:none; }}
        #mobile-overlay {{ display:none !important; }}
        #mobile-menu {{ display:none; }}
        .leaflet-container {{ margin-left:320px; }}
      }}
      @media (max-width:768px) {{
        #sidebar {{ display:none; }}
        .leaflet-container {{ margin-top:48px; }}
      }}
    </style>
    """


def build_filter_js(locations_data, map_name, timeline=None):
    return f"""
    <script>
    var allLocations = {json.dumps(locations_data)};
    var timelineData = {json.dumps(timeline or [])};
    var markerLayer = null;
    var activeStatus = "";
    var rangeMin = 0;
    var rangeMax = timelineData.length - 1;

    function popupHtml(loc) {{
      var rows = loc.events.map(function(e) {{
        var color = e.status === "opened" ? "{COLOR_OPEN}" : "{COLOR_CLOSED}";
        var notes = e.notes ? " <i>(" + e.notes + ")</i>" : "";
        return "<tr>" +
          "<td style='color:" + color + ";padding:2px 8px 2px 0;white-space:nowrap'>" + e.date + "</td>" +
          "<td style='color:" + color + ";padding:2px 8px 2px 0'>" + e.status + "</td>" +
          "<td style='padding:2px 0'><a href='" + e.url + "' target='_blank' " +
            "style='color:#333;text-decoration:none'><b>" + e.name + "</b></a>" + notes + "</td>" +
          "</tr>";
      }}).join("");
      var approxNote = loc.approx
        ? "<div style='margin-top:6px;font-size:11px;color:{COLOR_APPROX}'>⚠ Location approximate — street number matched after removing cardinal direction</div>"
        : "";
      return "<div style='font-family:sans-serif;font-size:12px;min-width:260px'>" +
        "<b style='font-size:13px'>" + loc.address + "</b><br>" +
        "<span style='color:#666'>" + loc.city + "</span>" +
        "<hr style='margin:6px 0'>" +
        "<table style='border-collapse:collapse'>" + rows + "</table>" +
        approxNote + "</div>";
    }}

    function getChecked(listId) {{
      var vals = [];
      document.querySelectorAll("#" + listId + " input:checked").forEach(function(cb) {{
        vals.push(cb.value);
      }});
      return vals;
    }}

    function updateLabel(msId) {{
      var checked = getChecked(msId + "-list");
      var label = document.getElementById(msId + "-label");
      label.textContent = checked.length === 0 ? "All" : checked.join(", ");
    }}

    function toggleMs(msId) {{
      var list = document.getElementById(msId + "-list");
      var isOpen = list.style.display === "block";
      document.querySelectorAll(".ms-list").forEach(function(el) {{
        el.style.display = "none";
      }});
      if (!isOpen) list.style.display = "block";
    }}

    document.addEventListener("click", function(e) {{
      if (!e.target.closest(".ms-container")) {{
        document.querySelectorAll(".ms-list").forEach(function(el) {{
          el.style.display = "none";
        }});
      }}
    }});

    function isMobile() {{
      return window.innerWidth <= 768;
    }}

    function toggleDrawer() {{
      document.getElementById("hamburger").classList.toggle("open");
      document.getElementById("mobile-overlay").classList.toggle("open");
      document.getElementById("mobile-menu").classList.toggle("open");
    }}

    function syncName(el) {{
      var other = el.id === "f-name" ? "f-name-m" : "f-name";
      document.getElementById(other).value = el.value;
    }}

    function renderTimeline() {{
      if (!timelineData.length) return;
      var maxVal = 0;
      timelineData.forEach(function(t) {{
        var total = t.opened + t.closed;
        if (total > maxVal) maxVal = total;
      }});
      if (!maxVal) maxVal = 1;

      ["timeline-chart", "timeline-chart-m"].forEach(function(containerId) {{
        var el = document.getElementById(containerId);
        if (!el) return;
        el.innerHTML = "";
        timelineData.forEach(function(t, i) {{
          var openH  = Math.round((t.opened / maxVal) * 68);
          var closeH = Math.round((t.closed / maxVal) * 68);
          var dimmed = (i < rangeMin || i > rangeMax) ? " dimmed" : "";
          var bar = document.createElement("div");
          bar.className = "tbar" + dimmed;
          bar.innerHTML =
            '<div class="tbar-tip">' + t.label + '<br>' +
              t.opened + ' opened, ' + t.closed + ' closed</div>' +
            '<div class="tbar-open" style="height:' + openH + 'px"></div>' +
            '<div class="tbar-closed" style="height:' + closeH + 'px"></div>';
          el.appendChild(bar);
        }});
      }});
    }}

    function initSliders() {{
      if (!timelineData.length) return;
      var maxIdx = timelineData.length - 1;
      ["", "-m"].forEach(function(sfx) {{
        var mn = document.getElementById("range-min" + sfx);
        var mx = document.getElementById("range-max" + sfx);
        if (!mn || !mx) return;
        mn.max = maxIdx; mn.value = 0;
        mx.max = maxIdx; mx.value = maxIdx;
      }});
      updateRangeLabels();
    }}

    function syncRange(which) {{
      var sfx = isMobile() ? "-m" : "";
      var mn = document.getElementById("range-min" + sfx);
      var mx = document.getElementById("range-max" + sfx);
      var lo = parseInt(mn.value), hi = parseInt(mx.value);
      if (which === "min" && lo > hi) mn.value = hi;
      if (which === "max" && hi < lo) mx.value = lo;
      rangeMin = parseInt(mn.value);
      rangeMax = parseInt(mx.value);
      // sync other set
      var osfx = sfx === "-m" ? "" : "-m";
      var omn = document.getElementById("range-min" + osfx);
      var omx = document.getElementById("range-max" + osfx);
      if (omn) omn.value = rangeMin;
      if (omx) omx.value = rangeMax;
      updateRangeLabels();
      renderTimeline();
      applyFilters();
    }}

    function updateRangeLabels() {{
      if (!timelineData.length) return;
      var fromLabel = timelineData[rangeMin].label;
      var toLabel   = timelineData[rangeMax].label;
      ["", "-m"].forEach(function(sfx) {{
        var f = document.getElementById("range-from" + sfx);
        var t = document.getElementById("range-to" + sfx);
        if (f) f.textContent = fromLabel;
        if (t) t.textContent = toLabel;
      }});
    }}

    function applyFilters() {{
      if (!markerLayer) {{
        markerLayer = L.layerGroup().addTo({map_name});
      }}
      var sfx = isMobile() ? "-m" : "";
      ["ms-city","ms-year","ms-month"].forEach(function(id) {{
        updateLabel(id + sfx);
      }});
      var cities = getChecked("ms-city" + sfx + "-list");
      var years  = getChecked("ms-year" + sfx + "-list");
      var months = getChecked("ms-month" + sfx + "-list");
      var nameEl = document.getElementById("f-name" + (sfx ? "-m" : ""));
      var name   = nameEl ? nameEl.value.toLowerCase().trim() : "";

      markerLayer.clearLayers();
      var count = 0;
      var ymFrom = timelineData.length ? timelineData[rangeMin].ym : "";
      var ymTo   = timelineData.length ? timelineData[rangeMax].ym + "-31" : "";

      allLocations.forEach(function(loc) {{
        if (activeStatus === "changed") {{ if (!loc.changed) return; }}
        else if (activeStatus && loc.current_status !== activeStatus) return;
        if (cities.length && !cities.includes(loc.city)) return;
        if (years.length  && !loc.years.some(function(y)  {{ return years.includes(y);  }})) return;
        if (months.length && !loc.months.some(function(m) {{ return months.includes(m); }})) return;
        if (ymFrom) {{
          var inRange = loc.events.some(function(e) {{
            return e.date >= ymFrom && e.date <= ymTo;
          }});
          if (!inRange) return;
        }}
        if (name) {{
          var nameMatch = loc.current_name.toLowerCase().includes(name) ||
            loc.events.some(function(e) {{ return e.name.toLowerCase().includes(name); }});
          if (!nameMatch) return;
        }}

        var color = loc.approx ? "{COLOR_APPROX}"
                  : loc.current_status === "opened" ? "{COLOR_OPEN}" : "{COLOR_CLOSED}";
        var marker = L.circleMarker([loc.lat, loc.lng], {{
          radius: 7, color: color, fillColor: color,
          fillOpacity: 0.85, weight: 1.5
        }});
        marker.bindTooltip(popupHtml(loc), {{maxWidth: 400, sticky: false}});
        marker.bindPopup(popupHtml(loc), {{maxWidth: 420}});
        markerLayer.addLayer(marker);
        count++;
      }});

      var label = count + " location" + (count !== 1 ? "s" : "");
      document.getElementById("filter-count").textContent = label;
      document.getElementById("filter-count-bar").textContent = "Filters — " + label;
      var dc = document.querySelector(".drawer-count");
      if (dc) dc.textContent = label;
    }}

    function setStatus(btn) {{
      activeStatus = btn.dataset.val;
      document.querySelectorAll(".status-btn,.status-btn-m").forEach(function(b) {{
        b.classList.toggle("active", b.dataset.val === activeStatus);
      }});
      applyFilters();
    }}

    function resetFilters() {{
      activeStatus = "";
      document.querySelectorAll(".status-btn,.status-btn-m").forEach(function(b) {{
        b.classList.toggle("active", b.dataset.val === "");
      }});
      document.querySelectorAll(".ms-list input").forEach(function(cb) {{
        cb.checked = false;
      }});
      ["ms-city","ms-year","ms-month","ms-city-m","ms-year-m","ms-month-m"].forEach(function(id) {{
        var el = document.getElementById(id + "-label");
        if (el) el.textContent = "All";
      }});
      document.getElementById("f-name").value = "";
      document.getElementById("f-name-m").value = "";
      rangeMin = 0;
      rangeMax = timelineData.length - 1;
      initSliders();
      renderTimeline();
      applyFilters();
    }}

    setTimeout(function() {{
      initSliders();
      renderTimeline();
      applyFilters();
    }}, 200);
    </script>
    """


def main():
    args = parse_args()
    locations = load_locations(args)

    if not locations:
        print("No data loaded.")
        return

    locations_data = build_locations_json(locations)

    cities = sorted({d["city"] for d in locations_data if d.get("city")})
    years  = unique_sorted(locations_data, "years")
    months = unique_sorted(locations_data, "months", order=MONTH_ORDER)

    timeline = build_timeline_data(locations_data)

    m = folium.Map(location=DENVER_CENTER, zoom_start=11, tiles="CartoDB positron")
    map_name = m.get_name()

    m.get_root().html.add_child(
        folium.Element(build_filter_html(cities, years, months, timeline))
    )
    m.get_root().html.add_child(
        folium.Element(build_filter_js(locations_data, map_name, timeline))
    )

    m.save(args.output)
    print_summary(args.output, locations_data)


def print_summary(output, locations_data):
    n_open   = sum(1 for d in locations_data if d["current_status"] == "opened")
    n_closed = sum(1 for d in locations_data if d["current_status"] == "closed")
    print(f"Saved to {output}")
    print(f"  {len(locations_data)} locations — {n_open} open, {n_closed} closed")


if __name__ == "__main__":
    main()
