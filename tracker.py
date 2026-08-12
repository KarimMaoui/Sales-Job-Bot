"""
Persist matched job postings to a local CSV, deduplicated across runs.

Usage:
    python tracker.py                    # fetch latest US matches, append new ones to data/jobs.csv
    python tracker.py --french           # fetch French-speaking roles worldwide -> data/jobs_french.csv
    python tracker.py --eu               # fetch France / remote-incl-France roles -> data/jobs_eu.csv
    python tracker.py --new-only         # print only rows added in this run
"""

import argparse
import csv
import os

from fetch_jobs import date_kind_for, fetch_all_matches

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATHS = {
    "us": os.path.join(DATA_DIR, "jobs.csv"),
    "french": os.path.join(DATA_DIR, "jobs_french.csv"),
    "eu": os.path.join(DATA_DIR, "jobs_eu.csv"),
}
FIELDS = ["company", "title", "location", "url", "sponsors_h1b",
          "years_experience", "updated_at", "date_kind", "status",
          "first_seen", "status_updated", "note"]


def load_existing(csv_path):
    if not os.path.exists(csv_path):
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = {row["url"]: row for row in csv.DictReader(f)}
    # Older CSVs predate the years_experience column, the status_updated/note
    # columns that mark.py writes, and date_kind.
    for row in rows.values():
        row.setdefault("years_experience", "")
        row.setdefault("status_updated", "")
        row.setdefault("note", "")
        if not row.get("date_kind"):
            row["date_kind"] = date_kind_for(row["company"], row["url"])
    return rows


def save_all(csv_path, rows_by_url):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows_by_url.values():
            writer.writerow(row)


def sync(today: str, qualified_only: bool = True, market: str = "us"):
    csv_path = CSV_PATHS[market]
    existing = load_existing(csv_path)
    matches = fetch_all_matches(qualified_only=qualified_only, market=market)
    new_rows = []

    for m in matches:
        years = m["years_experience"] if m["years_experience"] is not None else ""
        if m["url"] in existing:
            existing[m["url"]]["updated_at"] = m["updated_at"]
            existing[m["url"]]["date_kind"] = m["date_kind"]
            existing[m["url"]]["years_experience"] = years
            continue
        row = {
            "company": m["company"],
            "title": m["title"],
            "location": m["location"],
            "url": m["url"],
            "sponsors_h1b": m["sponsors_h1b"],
            "years_experience": years,
            "updated_at": m["updated_at"],
            "date_kind": m["date_kind"],
            "status": "new",
            "first_seen": today,
            "status_updated": "",
            "note": "",
        }
        existing[m["url"]] = row
        new_rows.append(row)

    save_all(csv_path, existing)
    return new_rows, len(existing)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--date", required=True,
                         help="today's date as YYYY-MM-DD (script cannot read the clock itself)")
    parser.add_argument("--all-levels", action="store_true",
                         help="include senior/management/specialized/foreign-language roles (off by default)")
    parser.add_argument("--french", action="store_true",
                         help="track French-speaking roles worldwide in data/jobs_french.csv instead")
    parser.add_argument("--eu", action="store_true",
                         help="track France / remote-inclusive-of-France roles in data/jobs_eu.csv instead")
    args = parser.parse_args()

    market = "french" if args.french else ("eu" if args.eu else "us")
    new_rows, total = sync(args.date, qualified_only=not args.all_levels, market=market)

    if args.new_only:
        for r in new_rows:
            print(f"{r['company']:<15} {r['title']:<45} {r['location']:<20} {r['url']}")
        print(f"\n{len(new_rows)} new rows (tracker now has {total} total).")
    else:
        print(f"Synced. {len(new_rows)} new rows added, {total} total in {CSV_PATHS[market]}.")


if __name__ == "__main__":
    main()
