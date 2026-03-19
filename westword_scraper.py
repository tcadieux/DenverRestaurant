#!/usr/bin/env python3
"""
Westword Restaurant Openings & Closings Scraper
------------------------------------------------
Crawls https://www.westword.com/tag/openings-closings/ and scrapes
each article for structured opening/closing data.

Output: westword_openings_closings.csv
Columns: post_date, month, year, date_precision, article_title, article_url,
         status, restaurant_name, address, city, notes, source_urls
"""

import csv
import logging
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("westword_scraper.log"),
        logging.StreamHandler(),
    ],
)

# ---- Config -----------------------------------------------------------------
TAG_URL       = "https://www.westword.com/tag/openings-closings/"
OUTPUT_FILE   = "westword_openings_closings.csv"
REQUEST_DELAY = 1.5
MAX_PAGES     = None  # None = all pages; set to an int to limit
USER_AGENT    = "Mozilla/5.0 (compatible; WestwordScraper/1.0)"
HEADERS       = {"User-Agent": USER_AGENT}

KNOWN_CITIES = {
    "aurora", "englewood", "thornton", "littleton", "lakewood",
    "arvada", "westminster", "broomfield", "centennial", "parker",
    "greenwood village", "highlands ranch", "lone tree", "northglenn",
    "commerce city", "federal heights", "wheat ridge", "edgewater",
    "boulder", "longmont", "louisville", "lafayette", "loveland",
    "castle rock", "morrison", "hudson", "niwot", "lyons", "evergreen",
    "golden", "glendale", "pine",
}



# ---- HTTP -------------------------------------------------------------------
def get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ---- Tag-page crawl ---------------------------------------------------------
def parse_tag_page(page_num):
    url = TAG_URL if page_num == 1 else f"{TAG_URL}?paged={page_num}"
    soup = get_soup(url)
    articles = []

    for article in soup.select("div.archive-results article"):
        link = article.select_one("h2.entry-title a, h3.entry-title a")
        if not link:
            continue
        href = link.get("href", "")
        if not href.startswith("http"):
            continue
        title = link.get_text(strip=True)
        if not title:
            continue

        date_str = ""
        time_tag = article.find("time")
        if time_tag:
            dt = time_tag.get("datetime", "")
            if dt:
                try:
                    date_str = datetime.fromisoformat(
                        dt.replace("Z", "+00:00")
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    date_str = dt[:10]
            else:
                date_str = time_tag.get_text(strip=True)

        articles.append({
            "title":     title,
            "url":       href,
            "post_date": date_str,
        })

    has_next = bool(soup.select_one("a.next, nav.pagination a[href*='paged=']"))
    return articles, has_next


# ---- Article parsing --------------------------------------------------------
# Only these exact headings (case-insensitive) trigger entry collection.
OPENINGS_HEADING_RE = re.compile(r"^openings?$", re.IGNORECASE)
CLOSURES_HEADING_RE = re.compile(r"^(closures?|closed?)$", re.IGNORECASE)


def parse_article(url, fallback_date, article_title=""):
    soup = get_soup(url)
    rows = []
    ctx = {"url": url, "title": article_title}

    # -- Date: OpenGraph meta is the most reliable source ---------------------
    post_date = fallback_date
    og = soup.find("meta", {"property": "article:published_time"})
    if og and og.get("content"):
        try:
            post_date = datetime.fromisoformat(
                og["content"].replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass
    if not post_date:
        time_tag = soup.find("time")
        if time_tag:
            dt = time_tag.get("datetime", "")
            if dt:
                try:
                    post_date = datetime.fromisoformat(
                        dt.replace("Z", "+00:00")
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    post_date = dt[:10]
            elif time_tag.get_text(strip=True):
                try:
                    post_date = datetime.strptime(
                        time_tag.get_text(strip=True), "%B %d, %Y"
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    post_date = time_tag.get_text(strip=True)

    ctx["date"] = post_date

    body = (
        soup.find("div", class_=re.compile(
            r"article-body|entry-content|post-content|body"
        ))
        or soup.find("article")
    )
    if not body:
        return post_date, [], []

    sidecar_rows = []  # location sub-header entries (e.g. DIA) written separately

    # Walk tags. We ONLY collect entries after an exact "Openings" or
    # "Closures" heading is found. Every tag before that heading is ignored
    # - no prose leaks through, and individual story articles (which never
    # have those headings) produce zero rows intentionally.
    section = None         # current list section, or None
    in_list = False        # True once we have seen at least one list heading
    pending_name = None    # restaurant name from "Name, N locations:" sub-header
    pending_address = None # shared address from "New at Location, sub-loc:" sub-header

    for tag in body.find_all(["h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(strip=True)
        text = " ".join(text.split())  # collapse all whitespace incl. \xa0, \u200b, etc.
        norm = text.strip()

        if tag.name in ("h2", "h3", "h4"):
            if OPENINGS_HEADING_RE.match(norm):
                section = "opened"
                in_list = True
                pending_name = pending_address = None
                continue
            if CLOSURES_HEADING_RE.match(norm):
                section = "closed"
                in_list = True
                pending_name = pending_address = None
                continue
            # Any other heading after we are in the list resets the section.
            # We keep scanning in case another Openings/Closures follows.
            if in_list:
                section = None
                pending_name = pending_address = None
            continue

        # Skip everything that precedes the first list heading
        if not in_list or section is None:
            continue

        # The "or earlier" footnote marks the definitive end of the list
        if re.match(r"^\*?\s*or\s+earlier", norm, re.IGNORECASE):
            break

        # Collect entry lines from this tag
        lines = []
        if tag.name in ("p", "li"):
            raw_html = tag.decode_contents()
            for part in re.split(r"<br\s*/?>", raw_html, flags=re.IGNORECASE):
                clean = BeautifulSoup(part, "html.parser").get_text(strip=True)
                if clean:
                    lines.append(clean)

        for line in lines:
            entry = parse_entry_line(line, section, ctx)
            if entry:
                pending_name = pending_address = None
                rows.append(entry)
            elif line.endswith(":") and "," in line:
                # Sub-header with a comma — two possible formats:
                #   "Name, N locations:"      → sub-entries are addresses (Sanitas pattern)
                #   "New at Location, sub-loc:" → sub-entries are names (DIA pattern)
                # Distinguish by checking whether the part before the first comma
                # looks like an address/location keyword.
                header = line.rstrip(":").strip()
                first_part = header.split(",", 1)[0].strip().strip("*").strip()
                if ADDRESS_RE.search(first_part):
                    # Location header: sub-entries are restaurant names
                    pending_address = re.sub(r"^new at\s+", "", header, flags=re.IGNORECASE)
                    pending_name = None
                else:
                    # Restaurant header: sub-entries are addresses
                    pending_name = first_part
                    pending_address = None
            elif pending_name:
                # Address-only line following a "Name, N locations:" sub-header
                entry = parse_entry_line(f"{pending_name}, {line}", section, ctx)
                if entry:
                    rows.append(entry)
                else:
                    logging.warning(
                        "Could not parse sub-entry %r (pending name: %r) | %s | %s | %s",
                        line, pending_name, ctx["date"], ctx["title"], ctx["url"],
                    )
            elif pending_address:
                if re.search(r"airport", pending_address, re.IGNORECASE):
                    # Airport entry: use fixed DIA address, concourse → notes
                    name = line.strip().strip("*").strip()
                    notes = ""
                    note_match = NOTE_SUFFIX_RE.search(name)
                    if note_match:
                        notes = note_match.group(1).strip()
                        name = name[: note_match.start()].strip().strip("*").strip()
                    addr_parts = pending_address.split(",", 1)
                    concourse = addr_parts[1].strip().title() if len(addr_parts) > 1 else ""
                    if concourse:
                        notes = f"{concourse}; {notes}".strip("; ") if notes else concourse
                    if name:
                        rows.append({
                            "status":          section,
                            "restaurant_name": name,
                            "address":         "8500 Peña Boulevard",
                            "city":            "Denver",
                            "notes":           notes,
                        })
                else:
                    # Other location sub-headers — write to sidecar for review
                    sidecar_rows.append({
                        "post_date":       ctx["date"],
                        "article_title":   ctx["title"],
                        "article_url":     ctx["url"],
                        "status":          section,
                        "location":        pending_address,
                        "restaurant_name": line.strip().strip("*").strip(),
                    })

    return post_date, rows, sidecar_rows


# ---- Entry-line parsing -----------------------------------------------------
NOTE_SUFFIX_RE = re.compile(r"\s*\(([^)]*)\)\s*$")

ADDRESS_RE = re.compile(
    r"\d|airport|avenue|street|blvd|boulevard|road|way|drive|lane|"
    r"place|court|plaza|pkwy|parkway|hwy|highway|concourse|mall|"
    r"mainstreet|broadway|federal|colfax|larimer|wazee|wynkoop|"
    r"market|walnut|blake|delgany|platte|tejon|navajo|zuni|pecos|"
    r"champa|hampden|mississippi|evans|alameda|wadsworth|sheridan",
    re.IGNORECASE,
)


def parse_entry_line(line, status, ctx=None):
    # Strip leading />  artifacts left by <br> splitting
    line = re.sub(r"^[\s/>*]+", "", line).strip()
    if not line or len(line) < 6:
        return None

    # A line ending with ":" is a sub-heading (e.g. "New at DIA, Concourse B:")
    if line.endswith(":"):
        return None

    # Every valid entry is "Name, Address" -- no comma means not an entry
    if "," not in line:
        return None

    parts = line.split(",", 1)
    if len(parts) < 2:
        return None

    name = parts[0].strip().strip("*").strip()
    address = parts[1].strip()

    # Extract trailing parenthetical note -- check name first, then address
    notes = ""
    note_match = NOTE_SUFFIX_RE.search(name)
    if note_match:
        notes = note_match.group(1).strip()
        name = name[: note_match.start()].strip().strip("*").strip()
    else:
        note_match = NOTE_SUFFIX_RE.search(address)
        if note_match:
            notes = note_match.group(1).strip()
            address = address[: note_match.start()].strip()

    # Name: non-empty, not too long, no URLs or email addresses
    if not name or len(name) > 120:
        return None
    if re.search(r"https?://|@", name):
        return None

    # Address must look like an address (contain a digit or street keyword)
    if not ADDRESS_RE.search(address):
        ctx = ctx or {}
        logging.warning(
            "Rejected address %r — from line: %r | %s | %s | %s",
            address, line,
            ctx.get("date", ""), ctx.get("title", ""), ctx.get("url", ""),
        )
        return None
    if len(address) > 200:
        return None

    # Parse city from last address segment; default to Denver if none found
    city = ""
    addr_parts = [p.strip() for p in address.split(",")]
    if len(addr_parts) >= 2:
        last = addr_parts[-1].lower().strip()
        if last in KNOWN_CITIES:
            city = addr_parts[-1].strip()
            address = ", ".join(addr_parts[:-1]).strip()
    if not city:
        city = "Denver"

    return {
        "status":          status,
        "restaurant_name": name,
        "address":         address,
        "city":            city,
        "notes":           notes,
    }


# ---- Deduplication ----------------------------------------------------------
def deduplicate(all_rows):
    """
    Deduplicate on (restaurant_name, address, status).
    Week-precision entries win over month-precision; accumulate source_urls.
    """
    # Sort so week entries come before month entries (week=0, month=1)
    all_rows.sort(key=lambda r: (
        r["post_date"] or "9999-99-99",
        0 if r.get("date_precision") == "week" else 1,
    ))

    seen = {}
    duplicates = []
    for row in all_rows:
        key = (
            row["restaurant_name"].lower().strip(),
            row["address"].lower().strip(),
            row["status"],
            row.get("year", ""),
            row.get("month", ""),
        )
        if key not in seen:
            seen[key] = dict(row)
        else:
            existing = seen[key]
            # Record this row as a duplicate before merging
            dup = dict(row)
            dup["merged_into_url"] = existing["article_url"]
            if existing.get("date_precision") != row.get("date_precision"):
                dup["duplicate_reason"] = "same event in weekly and monthly article"
            else:
                dup["duplicate_reason"] = "same event reported in multiple articles"
            duplicates.append(dup)
            # Accumulate source URLs from both articles
            existing_urls = existing["source_urls"].split(" | ")
            if row["article_url"] not in existing_urls:
                existing["source_urls"] += " | " + row["article_url"]
            # If we now have a weekly entry for something previously only monthly, upgrade it
            if existing.get("date_precision") == "month" and row.get("date_precision") == "week":
                existing["post_date"] = row["post_date"]
                existing["month"] = row["month"]
                existing["year"] = row["year"]
                existing["article_title"] = row["article_title"]
                existing["article_url"] = row["article_url"]
                existing["date_precision"] = "week"
            # Fill in any missing enrichment fields
            for field in ("notes", "city"):
                if not existing.get(field) and row.get(field):
                    existing[field] = row[field]

    deduped = list(seen.values())
    deduped.sort(key=lambda r: r["post_date"] or "")
    return deduped, duplicates


# ---- Main -------------------------------------------------------------------
FIELDNAMES = [
    "post_date", "month", "year", "date_precision", "article_title", "article_url", "status",
    "restaurant_name", "address", "city",
    "notes", "source_urls",
]


def load_existing():
    """
    Read the existing CSV (if any) and return:
      - existing_rows: list of row dicts already saved
      - seen_urls:     set of article_url values already scraped
    """
    import os
    if not os.path.exists(OUTPUT_FILE):
        return [], set()

    existing_rows = []
    seen_urls = set()
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing_rows.append(row)
            # source_urls may contain multiple pipe-separated URLs
            for url in row.get("source_urls", "").split(" | "):
                if url.strip():
                    seen_urls.add(url.strip())
    return existing_rows, seen_urls


def main():
    existing_rows, seen_urls = load_existing()
    if existing_rows:
        print(f"Loaded {len(existing_rows)} existing records ({len(seen_urls)} article URLs already scraped)")
    else:
        print("No existing data found -- full scrape")

    new_rows = []
    sidecar_rows = []
    page = 1
    stop_early = False  # set True once we hit a page of all-already-seen articles

    while True:
        print(f"  Tag page {page}...", end=" ", flush=True)
        try:
            articles, has_next = parse_tag_page(page)
        except Exception as e:
            print(f"ERROR: {e}")
            break

        # Filter to articles not yet scraped
        fresh = [a for a in articles if a["url"] not in seen_urls]
        skipped = len(articles) - len(fresh)
        print(f"{len(articles)} articles ({skipped} already scraped, {len(fresh)} new)")

        # If every article on this page has been seen before, we've caught up
        if articles and not fresh:
            print("  All caught up -- stopping early")
            stop_early = True
            break

        for art in fresh:
            print(f"    -> {art['url'][:80]}", end=" ... ", flush=True)
            try:
                time.sleep(REQUEST_DELAY)
                post_date, entries, art_sidecar = parse_article(art["url"], art["post_date"], art["title"])
                sidecar_rows.extend(art_sidecar)
                if not post_date:
                    logging.warning("Missing post_date for %s", art["url"])
                try:
                    month = datetime.strptime(post_date, "%Y-%m-%d").strftime("%B") if post_date else ""
                    year  = datetime.strptime(post_date, "%Y-%m-%d").strftime("%Y") if post_date else ""
                except ValueError:
                    logging.warning("Unparseable post_date %r for %s", post_date, art["url"])
                    month, year = "", ""
                precision = "week" if re.search(r"\bweek\b", art["title"], re.IGNORECASE) else "month"
                print(f"{len(entries)} entries")
                for entry in entries:
                    new_rows.append({
                        "post_date":       post_date,
                        "month":           month,
                        "year":            year,
                        "date_precision":  precision,
                        "article_title":   art["title"],
                        "article_url":     art["url"],
                        "status":          entry["status"],
                        "restaurant_name": entry["restaurant_name"],
                        "address":         entry["address"],
                        "city":            entry.get("city", ""),
                        "notes":           entry.get("notes", ""),
                        "source_urls":     art["url"],
                    })
            except Exception as e:
                logging.warning("SKIP %s — %s: %s", art["url"], type(e).__name__, e)

        if not has_next or (MAX_PAGES and page >= MAX_PAGES):
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    if not new_rows:
        print(f"\nNothing new to add. {len(existing_rows)} records unchanged.")
        return

    # Merge new rows with existing, then deduplicate the combined set
    all_rows = []
    # Re-parse existing rows back into the expected dict shape
    for row in existing_rows:
        all_rows.append(dict(row))
    all_rows.extend(new_rows)

    deduped, duplicates = deduplicate(all_rows)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deduped)

    if duplicates:
        dup_file = "westword_duplicates.csv"
        dup_fields = FIELDNAMES + ["duplicate_reason", "merged_into_url"]
        with open(dup_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=dup_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(duplicates)
        logging.info("  Duplicates: %d → %s", len(duplicates), dup_file)

    if sidecar_rows:
        sidecar_file = "westword_location_entries.csv"
        sidecar_fields = ["post_date", "article_title", "article_url", "status", "location", "restaurant_name"]
        write_header = not __import__("os").path.exists(sidecar_file)
        with open(sidecar_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sidecar_fields)
            if write_header:
                writer.writeheader()
            writer.writerows(sidecar_rows)
        logging.info("  Location entries (e.g. DIA): %d → %s", len(sidecar_rows), sidecar_file)

    print(f"\nDone.")
    print(f"  New entries scraped:  {len(new_rows)}")
    print(f"  Duplicates merged:    {len(duplicates)}")
    print(f"  Total after dedup:    {len(deduped)}")
    print(f"  Saved to:             {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
