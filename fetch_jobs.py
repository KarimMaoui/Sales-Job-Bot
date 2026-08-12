"""
Pull open sales roles (SDR/BDR/AE/etc.) from each target company's public
job-board API and filter to US-based postings.

Usage:
    python fetch_jobs.py                  # fetch + print matches
    python fetch_jobs.py --check-slugs    # just verify every company slug is reachable

Data sources are each company's own public career-site API (Greenhouse's
boards-api.greenhouse.io, Ashby's posting-api.ashbyhq.com) -- the same JSON
feed their public "Careers" page uses to render listings. No login, no
scraping of gated pages, no bypassing of any access control.
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

from companies import (
    COMPANIES, SALES_TITLE_KEYWORDS, US_LOCATION_KEYWORDS, is_qualified,
    is_french_market, is_eu_market,
)

USER_AGENT = "Mozilla/5.0 (job-search-tool; contact: karim.maoui@edu.em-lyon.com)"

# Matches phrasing like "5+ years of experience", "3-5 years of sales
# experience", "1 year of relevant experience", "5+ years closing
# experience", "3+ years in a Sales Engineering role". Allows up to 3 filler
# words between "years" and "experience"/"role"/"in a ... role" since job
# posts phrase this in many ways ("years of X Y experience", "years X
# closing experience", etc). Takes the first match in the description --
# job posts occasionally repeat the requirement in a summary and again in a
# bullet list, and the first mention is consistently the headline
# requirement in every posting sampled while building this.
YEARS_EXPERIENCE_RE = re.compile(
    r"(\d+)\s*(?:-\s*\d+\s*)?\+?\s*years?\s*"
    r"(?:of\s+)?(?:\w+\s+){0,3}?"
    r"(?:experience|closing|quota)",
    re.IGNORECASE,
)


def extract_years_experience(text: str, return_match_text: bool = False):
    if not text:
        return (None, None) if return_match_text else None
    match = YEARS_EXPERIENCE_RE.search(text)
    if not match:
        return (None, None) if return_match_text else None
    years = int(match.group(1))
    return (years, match.group(0)) if return_match_text else years


def http_get_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# What the `updated_at` column actually measures, per ATS. Greenhouse returns a
# real last-modified timestamp; Ashby's public posting API exposes only
# `publishedAt` and no update field at all, so an old Ashby date means "this req
# went up a while ago", NOT "nobody has touched it since". Evergreen reqs stay
# listed for years -- Hex's 2024 AE postings are still `isListed` today -- so
# downstream freshness filters have to know which kind of date they're reading.
DATE_KIND_BY_ATS = {"greenhouse": "updated", "ashby": "published"}


def date_kind_for(company: str, url: str = "") -> str:
    """Backfill `date_kind` for CSV rows written before the column existed.

    Resolves by company name against COMPANIES, since Greenhouse postings are
    served from each company's own domain and can't be identified by URL. Falls
    back to the Ashby URL host (the one host that is identifiable), then to
    "updated" -- the conservative answer, because it keeps the pre-existing
    filter behaviour for any row we can't place.
    """
    for c in COMPANIES:
        if c["name"] == company:
            return DATE_KIND_BY_ATS[c["ats"]]
    if "ashbyhq.com" in (url or ""):
        return "published"
    return "updated"


def fetch_greenhouse(slug: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = http_get_json(url)
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "updated_at": j.get("updated_at", ""),
            "date_kind": DATE_KIND_BY_ATS["greenhouse"],
            "years_experience": extract_years_experience(j.get("content", "")),
        })
    return jobs


def fetch_ashby(slug: str):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = http_get_json(url)
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("jobUrl", ""),
            "updated_at": j.get("publishedAt", ""),
            "date_kind": DATE_KIND_BY_ATS["ashby"],
            "years_experience": extract_years_experience(j.get("descriptionPlain", "")),
        })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
}


def title_matches_sales(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in SALES_TITLE_KEYWORDS)


NON_US_KEYWORDS = [
    "uk", "united kingdom", "canada", "ontario", "quebec", "vancouver",
    "toronto", "montreal", "mexico", "brazil", "france", "germany",
    "ireland", "australia", "india", "singapore", "japan", "netherlands",
    ", bc", ", on", ", ab", ", ns",  # Canadian province abbreviations
    # Foreign cities whose country suffix collides with a US state
    # abbreviation -- "Munich, DE" is Germany, not Delaware. Matching the
    # city name is safer than dropping DE/IN/OR/LA from the state list,
    # which would throw out real Delaware/Indiana/Oregon/Louisiana roles.
    "munich", "berlin", "hamburg", "frankfurt", "dusseldorf", "cologne",
    "stuttgart", "milan", "milano", "rome", "turin", "naples",
    "chennai", "bangalore", "bengaluru", "mumbai", "hyderabad", "pune",
]

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}


def location_is_us(location: str) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False
    if any(kw in loc for kw in NON_US_KEYWORDS):
        return False
    if any(kw in loc for kw in US_LOCATION_KEYWORDS):
        return True
    import re
    for match in re.findall(r",\s*([A-Z]{2})\b", location or ""):
        if match in US_STATE_ABBREVIATIONS:
            return True
    return False


def check_slugs():
    ok, fail = [], []
    for c in COMPANIES:
        fetcher = FETCHERS[c["ats"]]
        try:
            fetcher(c["slug"])
            ok.append(c["name"])
        except Exception as e:
            fail.append((c["name"], str(e)))
        time.sleep(0.3)
    print(f"OK ({len(ok)}): {', '.join(ok)}")
    if fail:
        print(f"\nFAIL ({len(fail)}):")
        for name, err in fail:
            print(f"  {name}: {err}")


def fetch_all_matches(qualified_only: bool = True, market: str = "us"):
    """market: "us" (default) filters to US-based roles and applies the
    seniority + language qualification filter (visa sponsorship matters here).
    "french" instead looks for roles anywhere that explicitly require French,
    skipping the US location filter and the unsupported-language exclusion
    (French roles obviously don't get excluded for requiring French).
    "eu" keeps roles based in France or remote in a scope that includes France
    (EMEA/Europe-wide) -- jobs takeable from Paris with no sponsorship, since
    a French citizen needs none in the EU."""
    matches = []
    for c in COMPANIES:
        fetcher = FETCHERS[c["ats"]]
        try:
            jobs = fetcher(c["slug"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  [warn] {c['name']}: fetch failed ({e})", file=sys.stderr)
            continue
        for j in jobs:
            if not title_matches_sales(j["title"]):
                continue
            if market == "french":
                if not is_french_market(j["title"], j["location"]):
                    continue
            elif market == "eu":
                if not is_eu_market(j["title"], j["location"]):
                    continue
            else:
                if not location_is_us(j["location"]):
                    continue
            if qualified_only and not is_qualified(j["title"]):
                continue
            matches.append({
                    "company": c["name"],
                    "sponsors_h1b": c["sponsors_h1b"] if market == "us" else None,
                    "title": j["title"],
                    "location": j["location"],
                    "url": j["url"],
                    "updated_at": j["updated_at"],
                    "date_kind": j["date_kind"],
                    "years_experience": j.get("years_experience"),
                })
        time.sleep(0.3)  # be polite to shared public APIs
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-slugs", action="store_true")
    parser.add_argument("--all-levels", action="store_true",
                         help="include senior/management/specialized/foreign-language roles (off by default)")
    parser.add_argument("--french", action="store_true",
                         help="search French-speaking roles worldwide instead of US roles (no visa filter)")
    parser.add_argument("--eu", action="store_true",
                         help="search roles in France or remote-inclusive-of-France "
                              "at the same US companies (no visa needed as an EU citizen)")
    args = parser.parse_args()

    if args.check_slugs:
        check_slugs()
        return

    market = "french" if args.french else ("eu" if args.eu else "us")
    matches = fetch_all_matches(qualified_only=not args.all_levels, market=market)
    matches.sort(key=lambda m: (m["sponsors_h1b"] is not True, m["company"]))
    scope = {"french": "French-speaking roles worldwide",
             "eu": "based in France or remote-inclusive-of-France",
             "us": "in the US"}[market]
    label = "matching sales roles" if args.all_levels else "qualified entry-level sales roles"
    print(f"\nFound {len(matches)} {label} {scope}:\n")
    for m in matches:
        sponsor_flag = {True: "sponsors", False: "no-sponsor", None: "unknown"}[m["sponsors_h1b"]]
        yoe = f"{m['years_experience']}y" if m["years_experience"] is not None else "?y"
        print(f"[{sponsor_flag:>10}] [{yoe:>3}] {m['company']:<15} {m['title']:<40} {m['location']:<20} {m['url']}")


if __name__ == "__main__":
    main()
