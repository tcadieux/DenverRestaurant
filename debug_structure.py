#!/usr/bin/env python3
"""
Run this once to show the actual HTML structure of the tag page
so we can fix the scraper selectors.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WestwordDebug/1.0)"}
URL = "https://www.westword.com/tag/openings-closings/"

soup = BeautifulSoup(requests.get(URL, headers=HEADERS, timeout=15).text, "html.parser")

print("=" * 60)
print("ALL <a> tags whose href contains /food-drink/")
print("=" * 60)
for a in soup.find_all("a", href=True):
    if "/food-drink/" in a["href"] and a.get_text(strip=True):
        print(f"  href : {a['href'][:80]}")
        print(f"  text : {a.get_text(strip=True)[:60]}")
        # Show parent chain
        parents = []
        p = a.parent
        while p and p.name not in ("[document]", "body"):
            cls = " ".join(p.get("class", []))
            parents.append(f"<{p.name} class='{cls}'>")
            p = p.parent
            if len(parents) > 4:
                break
        print(f"  path : {' > '.join(reversed(parents))}")
        print()

print("=" * 60)
print("ALL elements with 'article' in their class name")
print("=" * 60)
import re
for tag in soup.find_all(class_=re.compile(r"article", re.I)):
    cls = " ".join(tag.get("class", []))
    print(f"  <{tag.name} class='{cls}'>  text[:60]: {tag.get_text(strip=True)[:60]}")

print("\n" + "=" * 60)
print("SAMPLE: first 3000 chars of <main> or <body> inner HTML")
print("=" * 60)
main = soup.find("main") or soup.find("div", id="primary") or soup.body
if main:
    print(str(main)[:3000])