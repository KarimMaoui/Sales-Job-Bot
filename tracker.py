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

from fetch_jobs import (DEFAULT_MAX_AGE_DAYS, DEFAULT_REFRESH_DAYS,
                        YC_MAX_AGE_DAYS, date_kind_for, fetch_all_matches)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATHS = {
    "us": os.path.join(DATA_DIR, "jobs.csv"),
    "french": os.path.join(DATA_DIR, "jobs_french.csv"),
    "eu": os.path.join(DATA_DIR, "jobs_eu.csv"),
    "yc": os.path.join(DATA_DIR, "jobs_yc.csv"),
}
FIELDS = ["company", "title", "location", "url", "sponsors_h1b",
          "years_experience", "posted_at", "updated_at", "date_kind", "status",
          "first_seen", "status_updated", "note"]


def load_existing(csv_path):
    if not os.path.exists(csv_path):
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = {row["url"]: row for row in csv.DictReader(f)}
    # Older CSVs predate the years_experience column, the status_updated/note
    # columns that mark.py writes, date_kind, and posted_at. posted_at stays
    # blank for those rows rather than being backfilled from updated_at: the two
    # can be a year apart on an evergreen req, so copying one into the other
    # would invent a publication date the source never gave us.
    for row in rows.values():
        row.setdefault("years_experience", "")
        row.setdefault("status_updated", "")
        row.setdefault("note", "")
        row.setdefault("posted_at", "")
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


def sync(today: str, qualified_only: bool = True, market: str = "us",
         max_age_days: int = DEFAULT_MAX_AGE_DAYS,
         refresh_days: int = DEFAULT_REFRESH_DAYS):
    csv_path = CSV_PATHS[market]
    existing = load_existing(csv_path)
    # Rows already in the CSV are refreshed but never dropped, so tightening
    # max_age_days only narrows what gets *added* -- shortlist.py is where the
    # accumulated history gets re-filtered.
    matches = fetch_all_matches(qualified_only=qualified_only, market=market,
                                today=today, max_age_days=max_age_days,
                                refresh_days=refresh_days)
    new_rows = []

    for m in matches:
        years = m["years_experience"] if m["years_experience"] is not None else ""
        if m["url"] in existing:
            existing[m["url"]]["posted_at"] = m["posted_at"]
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
            "posted_at": m["posted_at"],
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
    parser.add_argument("--yc", action="store_true",
                         help="track YC startups' sales/marketing/operations "
                              "roles in data/jobs_yc.csv instead")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help=f"only track roles published within this many days "
                             f"(default {DEFAULT_MAX_AGE_DAYS}, or "
                             f"{YC_MAX_AGE_DAYS} with --yc)")
    parser.add_argument("--refresh-days", type=int, default=DEFAULT_REFRESH_DAYS,
                        help=f"also track an older role last modified within this "
                             f"many days -- an evergreen req still being "
                             f"maintained (default {DEFAULT_REFRESH_DAYS}; "
                             f"Greenhouse only). Pass 0 to disable.")
    args = parser.parse_args()

    market = ("yc" if args.yc else
              "french" if args.french else ("eu" if args.eu else "us"))
    if args.max_age_days is None:
        args.max_age_days = (YC_MAX_AGE_DAYS if market == "yc"
                             else DEFAULT_MAX_AGE_DAYS)
    new_rows, total = sync(args.date, qualified_only=not args.all_levels,
                           market=market, max_age_days=args.max_age_days,
                           refresh_days=args.refresh_days)

    if args.new_only:
        for r in new_rows:
            print(f"{r['company']:<15} {r['title']:<45} {r['location']:<20} {r['url']}")
        print(f"\n{len(new_rows)} new rows (tracker now has {total} total).")
    else:
        print(f"Synced. {len(new_rows)} new rows added, {total} total in {CSV_PATHS[market]}.")


if __name__ == "__main__":
    main()
