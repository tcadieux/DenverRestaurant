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


def unique_sorted(data, key, order=None):
    vals = sorted({v for d in data for v in d.get(key, []) if v})
    if order:
        vals = [v for v in order if v in set(vals)]
    return vals


def build_filter_html(cities, years, months):
    def checkboxes(vals):
        items = ""
        for v in vals:
            items += (
                f'<label style="display:block;padding:3px 8px;cursor:pointer;white-space:nowrap">'
                f'<input type="checkbox" value="{v}" onchange="applyFilters()" '
                f'style="margin-right:5px">{v}</label>'
            )
        return items

    return f"""
    <div id="filter-panel" style="
        position:fixed; top:80px; right:12px; z-index:1000;
        background:white; padding:14px 16px; border-radius:8px;
        box-shadow:0 2px 8px rgba(0,0,0,.25); font-family:sans-serif;
        font-size:13px; width:210px;">
      <b style="font-size:14px">Filters</b>
      <div id="filter-count" style="color:#888;font-size:11px;margin-bottom:10px"></div>

      <label style="display:block;margin-bottom:4px;font-weight:600">Status</label>
      <div style="display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap">
        <button class="status-btn active" data-val=""        onclick="setStatus(this)">All</button>
        <button class="status-btn"        data-val="opened"  onclick="setStatus(this)">Open</button>
        <button class="status-btn"        data-val="closed"  onclick="setStatus(this)">Closed</button>
        <button class="status-btn"        data-val="changed" onclick="setStatus(this)">Changed</button>
      </div>

      <label style="display:block;margin-bottom:2px;font-weight:600">City</label>
      <div class="ms-container" id="ms-city">
        <div class="ms-toggle" onclick="toggleMs('ms-city')">
          <span id="ms-city-label">All</span><span style="float:right">▾</span>
        </div>
        <div class="ms-list" id="ms-city-list">
          {checkboxes(cities)}
        </div>
      </div>

      <label style="display:block;margin-bottom:2px;font-weight:600">Year</label>
      <div class="ms-container" id="ms-year">
        <div class="ms-toggle" onclick="toggleMs('ms-year')">
          <span id="ms-year-label">All</span><span style="float:right">▾</span>
        </div>
        <div class="ms-list" id="ms-year-list">
          {checkboxes(years)}
        </div>
      </div>

      <label style="display:block;margin-bottom:2px;font-weight:600">Month</label>
      <div class="ms-container" id="ms-month">
        <div class="ms-toggle" onclick="toggleMs('ms-month')">
          <span id="ms-month-label">All</span><span style="float:right">▾</span>
        </div>
        <div class="ms-list" id="ms-month-list">
          {checkboxes(months)}
        </div>
      </div>

      <label style="display:block;margin-top:8px;margin-bottom:2px;font-weight:600">Name</label>
      <input id="f-name" type="text" placeholder="Search…" oninput="applyFilters()"
             style="width:100%;box-sizing:border-box;padding:4px 6px;border:1px solid #ccc;border-radius:4px"/>

      <button onclick="resetFilters()"
              style="margin-top:10px;width:100%;padding:5px;border:1px solid #ccc;
                     border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:12px">
        Reset
      </button>
    </div>

    <style>
      .status-btn {{
        flex:1; padding:4px 2px; border:1px solid #ccc; border-radius:4px;
        background:#f5f5f5; cursor:pointer; font-size:12px;
      }}
      .status-btn.active {{ background:#333; color:white; border-color:#333; }}
      .ms-container {{ position:relative; margin-bottom:10px; }}
      .ms-toggle {{
        border:1px solid #ccc; border-radius:4px; padding:4px 8px;
        cursor:pointer; background:white; user-select:none; overflow:hidden;
        white-space:nowrap; text-overflow:ellipsis;
      }}
      .ms-toggle:hover {{ background:#f5f5f5; }}
      .ms-list {{
        display:none; position:absolute; top:100%; left:0; right:0;
        background:white; border:1px solid #ccc; border-radius:4px;
        max-height:160px; overflow-y:auto; z-index:1002;
        box-shadow:0 2px 6px rgba(0,0,0,.15);
      }}
      .ms-list label:hover {{ background:#f0f0f0; }}
    </style>
    """


def build_filter_js(locations_data, map_name):
    return f"""
    <script>
    var allLocations = {json.dumps(locations_data)};
    var markerLayer = null;
    var activeStatus = "";

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

    function applyFilters() {{
      if (!markerLayer) {{
        markerLayer = L.layerGroup().addTo({map_name});
      }}
      ["ms-city","ms-year","ms-month"].forEach(updateLabel);
      var cities = getChecked("ms-city-list");
      var years  = getChecked("ms-year-list");
      var months = getChecked("ms-month-list");
      var name   = document.getElementById("f-name").value.toLowerCase().trim();

      markerLayer.clearLayers();
      var count = 0;

      allLocations.forEach(function(loc) {{
        if (activeStatus === "changed") {{ if (!loc.changed) return; }}
        else if (activeStatus && loc.current_status !== activeStatus) return;
        if (cities.length && !cities.includes(loc.city)) return;
        if (years.length  && !loc.years.some(function(y)  {{ return years.includes(y);  }})) return;
        if (months.length && !loc.months.some(function(m) {{ return months.includes(m); }})) return;
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
    }}

    function setStatus(btn) {{
      document.querySelectorAll(".status-btn").forEach(function(b) {{
        b.classList.remove("active");
      }});
      btn.classList.add("active");
      activeStatus = btn.dataset.val;
      applyFilters();
    }}

    function resetFilters() {{
      activeStatus = "";
      document.querySelectorAll(".status-btn").forEach(function(b) {{
        b.classList.toggle("active", b.dataset.val === "");
      }});
      document.querySelectorAll(".ms-list input").forEach(function(cb) {{
        cb.checked = false;
      }});
      ["ms-city","ms-year","ms-month"].forEach(function(id) {{
        document.getElementById(id + "-label").textContent = "All";
      }});
      document.getElementById("f-name").value = "";
      applyFilters();
    }}

    setTimeout(applyFilters, 200);
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

    m = folium.Map(location=DENVER_CENTER, zoom_start=11, tiles="CartoDB positron")
    map_name = m.get_name()

    m.get_root().html.add_child(
        folium.Element(build_filter_html(cities, years, months))
    )
    m.get_root().html.add_child(
        folium.Element(build_filter_js(locations_data, map_name))
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
