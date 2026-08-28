"""
Rank the tracked postings into an application shortlist.

Usage:
    python shortlist.py --date 2026-08-09              # -> data/shortlist.csv
    python shortlist.py --date 2026-08-09 --french     # -> data/shortlist_french.csv
    python shortlist.py --date 2026-08-09 --max-age-days 30

Two filters, then a ranking:

1. Freshness -- drops anything published more than --max-age-days ago
   (default 30, matching fetch_jobs.py), *unless* it was last modified within
   --refresh-days (default 15). Rows carrying a `posted_at` are judged on that
   date: it is a real publication date from the source, so "over 30 days old" is
   a fact about the posting rather than an inference. The refresh exception
   exists for evergreen reqs, where publication date and "is anyone still
   hiring for this" have drifted apart -- it only applies where `date_kind` is
   `updated` (Greenhouse), the one source reporting a true last-modified date.

   Rows predating the `posted_at` column fall back to the old rule, which reads
   `updated_at` and is only trustworthy where `date_kind == "updated"`
   (Greenhouse). Ashby and the big-tech career sites return no last-modified
   field, so those legacy rows carry a publication date in `updated_at` and get
   exempted -- ageing them out would throw away live evergreen reqs. Pass
   --strict-age to filter both alike.
2. Seniority -- drops anything with a *known* requirement above
   --max-years (default 2). Postings with a blank `years_experience` are
   KEPT but ranked lower, because blank means "the regex found nothing",
   not "0 years required" (see README).

For the US list it also re-applies `location_is_us` to rows already in the
CSV, so tightening that filter in fetch_jobs.py retroactively cleans the
shortlist instead of only affecting future fetches.

Ranking tiers, best first:
    A  sponsors H-1B + fits the years cap
    B  sponsors H-1B + years unknown
    C  sponsorship unknown + fits the years cap
    D  sponsorship unknown + years unknown

`sponsors_h1b` is a best-effort per-company signal, never a guarantee --
confirm on the posting itself before counting on it.
"""

import argparse
import csv
import os
import re
from datetime import datetime, timedelta, timezone

from companies import unsupported_language_in
from fetch_jobs import (DEFAULT_MAX_AGE_DAYS, DEFAULT_REFRESH_DAYS,
                        YC_MAX_AGE_DAYS, YC_MAX_EXPERIENCE,
                        date_kind_for, location_is_us, refreshed_since)
from mark import DONE_STATUSES

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SOURCE_PATHS = {
    "us": os.path.join(DATA_DIR, "jobs.csv"),
    "french": os.path.join(DATA_DIR, "jobs_french.csv"),
    "eu": os.path.join(DATA_DIR, "jobs_eu.csv"),
    "yc": os.path.join(DATA_DIR, "jobs_yc.csv"),
}
OUTPUT_PATHS = {
    "us": os.path.join(DATA_DIR, "shortlist.csv"),
    "french": os.path.join(DATA_DIR, "shortlist_french.csv"),
    "eu": os.path.join(DATA_DIR, "shortlist_eu.csv"),
    "yc": os.path.join(DATA_DIR, "shortlist_yc.csv"),
}
FIELDS = ["tier", "company", "title", "location", "sponsors_h1b",
          "years_experience", "posted_at", "updated_at", "date_kind", "status",
          "note", "url"]


def parse_updated_at(value: str):
    """Both ATS feeds emit ISO-8601, but with different shapes (Greenhouse
    uses -04:00 offsets, Ashby uses fractional seconds + Z). Returns None on
    anything unparseable so a malformed row degrades to "unknown age"
    instead of crashing the run."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_years(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Parenthetical suffixes that mark a *territory*, not a distinct job. Removed
# when grouping duplicates. Deliberately NOT listed: (Hunter), (Grower),
# (Inbound), (BDR) -- those are genuinely different roles at the same company
# (new-business vs expansion vs inbound), and collapsing them would hide a
# real opening behind a near-identical title.
TERRITORY_WORDS = {
    "east", "west", "north", "south", "northeast", "northwest",
    "southeast", "southwest", "midwest", "central", "tola", "emea",
    "amer", "us", "usa", "remote eligible", "remote",
}

# "Territory Account Executive, Retail - Appleton, WI" -> everything from the
# " - " onward is the city. Anchored on the dash-space form so it can't eat a
# hyphenated role name ("Mid-Market").
CITY_SUFFIX_RE = re.compile(r"\s+[-–]\s*.+$")


def role_key(company: str, title: str) -> tuple:
    """Group key for near-duplicate postings: same company, same underlying
    role, differing only by city or territory.

    Toast alone posts the same "Territory Account Executive, SMB" for 100+
    cities. Applying to each is pointless -- same recruiting team, same form --
    and reads as spam, so the shortlist collapses them to the freshest few.
    """
    t = title.lower().replace("\t", " ")
    # Drop territory parentheticals, keep role-defining ones
    def strip_paren(match):
        inner = match.group(1).strip().lower()
        return "" if inner in TERRITORY_WORDS else match.group(0)
    t = re.sub(r"\(([^)]*)\)", strip_paren, t)
    t = CITY_SUFFIX_RE.sub("", t)
    # Normalize spacing quirks ("Executive ,  SMB" vs "Executive, SMB")
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\s+", " ", t).strip().strip(",").strip()
    return (company.lower(), t)


def dedupe(rows, keep_per_role: int = 2):
    """Keep at most `keep_per_role` postings per (company, role) group.

    Assumes `rows` is already sorted best-first, so the survivors are the
    highest-tier / freshest of each group. Returns (kept, dropped_count).
    """
    seen = {}
    kept = []
    dropped = 0
    for row in rows:
        key = role_key(row["company"], row["title"])
        count = seen.get(key, 0)
        if count >= keep_per_role:
            dropped += 1
            continue
        seen[key] = count + 1
        kept.append(row)
    return kept, dropped


def tier_for(sponsors: str, years, max_years: int,
             sponsorship_moot: bool = False) -> str:
    """Rank a row A (best) to D.

    sponsorship_moot: for the EU/French lists, where Karim needs no visa and
    sponsors_h1b carries no signal. Ranking then depends on years alone, so
    only A and B are used -- otherwise every EU row would land in C/D and
    look worse than a US row purely because of an irrelevant column.
    """
    years_ok = years is not None and years <= max_years
    if sponsorship_moot:
        return "A" if years_ok else "B"
    if sponsors == "True":
        return "A" if years_ok else "B"
    return "C" if years_ok else "D"


def sort_date(row):
    """The date to rank freshness on: the real publication date where the row
    has one, else whatever `updated_at` holds. Never None, so a row with two
    unreadable dates sorts last instead of crashing the sort."""
    return (parse_updated_at(row.get("posted_at"))
            or parse_updated_at(row.get("updated_at"))
            or datetime.min.replace(tzinfo=timezone.utc))


def build(today: str, market: str = "us",
          max_age_days: int = DEFAULT_MAX_AGE_DAYS,
          max_years: int = 2, include_done: bool = False,
          keep_per_role: int = None, strict_age: bool = False,
          refresh_days: int = DEFAULT_REFRESH_DAYS):
    source = SOURCE_PATHS[market]
    with open(source, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.setdefault("status_updated", "")
        row.setdefault("note", "")
        row.setdefault("posted_at", "")
        if not row.get("date_kind"):
            row["date_kind"] = date_kind_for(row["company"], row["url"])

    reference = datetime.fromisoformat(today).replace(tzinfo=timezone.utc)
    cutoff = reference - timedelta(days=max_age_days)
    # --strict-age means "age every row out on its own date", so it switches off
    # the evergreen readmission as well as the legacy exemption below.
    refresh_cutoff = (None if strict_age or refresh_days <= 0
                      else reference - timedelta(days=refresh_days))

    kept = []
    dropped_stale = dropped_senior = dropped_unparsed = dropped_non_us = 0
    dropped_done = dropped_language = 0
    for row in rows:
        if not include_done and row["status"] in DONE_STATUSES:
            dropped_done += 1
            continue
        # Re-applied to already-tracked rows, so tightening the language rule
        # cleans up past fetches too instead of only future ones.
        if unsupported_language_in(row["title"]):
            dropped_language += 1
            continue
        if market == "us" and not location_is_us(row["location"]):
            dropped_non_us += 1
            continue
        posted = parse_updated_at(row["posted_at"])
        if posted is not None:
            # A real publication date from the source: "published over N days
            # ago" is simply true or false, with none of the ambiguity below.
            # A recent edit still readmits an old req -- the evergreen case,
            # where publication date and "is this live" have drifted apart.
            if posted < cutoff and not refreshed_since(
                    row["date_kind"], row["updated_at"], refresh_cutoff):
                dropped_stale += 1
                continue
        else:
            # Legacy row, written before posted_at existed. All we have is
            # updated_at, and a "published" date there can't answer the question
            # this filter asks: Ashby and the big-tech sites expose no
            # last-modified field, so an old date means the req went up a while
            # ago, not that it went cold -- and those APIs only return postings
            # still listed on the board. Dropping them discards live openings,
            # so exempt them and let the ranking below push them down instead.
            updated = parse_updated_at(row["updated_at"])
            if updated is None:
                dropped_unparsed += 1
                continue
            if updated < cutoff and (strict_age or row["date_kind"] != "published"):
                dropped_stale += 1
                continue
        years = parse_years(row["years_experience"])
        if years is not None and years > max_years:
            dropped_senior += 1
            continue
        kept.append({
            "tier": tier_for(row["sponsors_h1b"], years, max_years,
                             sponsorship_moot=market in ("eu", "french")),
            "company": row["company"],
            "title": row["title"],
            "location": row["location"],
            "sponsors_h1b": row["sponsors_h1b"],
            "years_experience": row["years_experience"],
            "posted_at": row["posted_at"],
            "updated_at": row["updated_at"],
            "date_kind": row["date_kind"],
            "status": row["status"],
            "note": row["note"],
            "url": row["url"],
        })

    # Within a tier, freshest first -- a posting put up yesterday is more
    # likely to still be taking applications than one from 40 days ago.
    kept.sort(key=lambda r: (r["tier"], -sort_date(r).timestamp()))

    # Dedupe after sorting so each group's survivors are its best-ranked,
    # freshest postings rather than whichever happened to come first in the CSV.
    dropped_duplicate = 0
    if keep_per_role:
        kept, dropped_duplicate = dedupe(kept, keep_per_role)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATHS[market], "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(kept)

    return kept, {
        "total": len(rows),
        "stale": dropped_stale,
        "too_senior": dropped_senior,
        "unparsed_date": dropped_unparsed,
        "non_us": dropped_non_us,
        "done": dropped_done,
        "duplicate": dropped_duplicate,
        "language": dropped_language,
        # Recounted against the final list so the number matches what's in the
        # CSV -- an exempted row can still lose its slot to the deduper. Only
        # legacy rows (no posted_at) can be exempt; anything with a real
        # publication date was aged out on it above.
        "age_exempt": sum(1 for r in kept
                          if not r["posted_at"]
                          and r["date_kind"] == "published"
                          and (parse_updated_at(r["updated_at"]) or cutoff) < cutoff),
        # Same reason for recounting: rows readmitted by a recent edit despite an
        # old publication date -- the evergreen reqs. Worth showing separately
        # from age_exempt, which is about rows with no publication date at all.
        "refreshed": sum(1 for r in kept
                         if r["posted_at"]
                         and (parse_updated_at(r["posted_at"]) or reference) < cutoff
                         and refreshed_since(r["date_kind"], r["updated_at"],
                                             refresh_cutoff)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True,
                        help="today's date as YYYY-MM-DD (script cannot read the clock itself)")
    parser.add_argument("--french", action="store_true",
                        help="shortlist data/jobs_french.csv instead of the US list")
    parser.add_argument("--eu", action="store_true",
                        help="shortlist data/jobs_eu.csv instead of the US list")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help=f"drop roles published more than this many days ago "
                             f"(default {DEFAULT_MAX_AGE_DAYS}, or "
                             f"{YC_MAX_AGE_DAYS} with --yc, same as fetch_jobs.py)")
    parser.add_argument("--refresh-days", type=int, default=DEFAULT_REFRESH_DAYS,
                        help=f"keep a role published before the cutoff if it was "
                             f"last modified within this many days (default "
                             f"{DEFAULT_REFRESH_DAYS}, same as fetch_jobs.py). "
                             f"Pass 0 to age out evergreen reqs on publication "
                             f"date alone.")
    parser.add_argument("--strict-age", action="store_true",
                        help="age every row out on its own date: drops both the "
                             "recently-edited evergreen reqs and the legacy rows "
                             "whose only date is a publication date standing in "
                             "for a last-modified one. Off by default because it "
                             "drops still-listed openings.")
    parser.add_argument("--yc", action="store_true",
                        help="shortlist data/jobs_yc.csv (YC startups' "
                             "sales/marketing/operations roles) instead")
    parser.add_argument("--max-years", type=int, default=None,
                        help=f"drop roles with a known requirement above this "
                             f"many years (default 2, or {YC_MAX_EXPERIENCE} "
                             f"with --yc, matching the YC board's own band)")
    parser.add_argument("--limit", type=int, default=None,
                        help="only print the first N rows (the CSV always gets all of them)")
    parser.add_argument("--include-done", action="store_true",
                        help="also include rows already applied/rejected/skipped "
                             "(hidden by default so the shortlist is your to-do list)")
    parser.add_argument("--dedupe", nargs="?", type=int, const=2, default=None,
                        metavar="N",
                        help="collapse postings that differ only by city/territory, "
                             "keeping the freshest N per role (default 2)")
    args = parser.parse_args()

    market = ("yc" if args.yc else
              "french" if args.french else ("eu" if args.eu else "us"))
    # The YC list runs on the board's own bands rather than the sales defaults:
    # three weeks instead of 30 days, and 0-3 years instead of 0-2.
    if args.max_age_days is None:
        args.max_age_days = (YC_MAX_AGE_DAYS if market == "yc"
                             else DEFAULT_MAX_AGE_DAYS)
    if args.max_years is None:
        args.max_years = YC_MAX_EXPERIENCE if market == "yc" else 2

    kept, stats = build(args.date, market, args.max_age_days, args.max_years,
                        include_done=args.include_done,
                        keep_per_role=args.dedupe,
                        strict_age=args.strict_age,
                        refresh_days=args.refresh_days)

    dupe_note = (f"{stats['duplicate']} duplicate city/territory postings, "
                 if args.dedupe else "")
    print(f"{stats['total']} tracked -> {len(kept)} shortlisted "
          f"(dropped {dupe_note}"
          f"{stats['stale']} stale >{args.max_age_days}d, "
          f"{stats['too_senior']} needing >{args.max_years}y, "
          f"{stats['non_us']} non-US, "
          f"{stats['language']} needing another language, "
          f"{stats['done']} already handled, "
          f"{stats['unparsed_date']} with unreadable dates)")

    # Called out rather than folded silently into the total: these rows are
    # older than the cutoff and only survive because their date can't be read
    # as staleness. Worth an eyeball before applying.
    if stats["refreshed"]:
        print(f"  {stats['refreshed']} kept despite being published "
              f">{args.max_age_days}d ago, last modified within "
              f"{args.refresh_days}d (evergreen reqs still being maintained)")
    if stats["age_exempt"]:
        print(f"  {stats['age_exempt']} kept despite a >{args.max_age_days}d "
              f"date (legacy rows with no publication date recorded; "
              f"--strict-age drops them)")
    print()

    counts = {}
    for r in kept:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    print("  ".join(f"{t}:{counts.get(t, 0)}" for t in "ABCD"), "\n")

    for r in (kept[:args.limit] if args.limit else kept):
        yoe = f"{r['years_experience']}y" if r["years_experience"] else " ?"
        # "new" is the default and adds no information; anything else is a
        # deliberate mark worth seeing at a glance.
        flag = "" if r["status"] == "new" else f" <{r['status']}>"
        print(f"[{r['tier']}] [{yoe:>3}] {r['company']:<14} "
              f"{r['title'][:42]:<42} {r['location'][:26]:<26} "
              f"{r['url']}{flag}")

    print(f"\nWritten to {OUTPUT_PATHS[market]}")


if __name__ == "__main__":
    main()
