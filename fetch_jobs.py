"""
Pull open sales roles (SDR/BDR/AE/etc.) from each target company's public
job-board API and filter to US-based postings.

Usage:
    python fetch_jobs.py --date 2026-08-28              # fetch + print matches
    python fetch_jobs.py --date 2026-08-28 --max-age-days 90
    python fetch_jobs.py --check-slugs                  # verify every company slug is reachable

Only roles published within --max-age-days (default 30) are returned, plus older
ones last modified within --refresh-days (default 15); see "Freshness" below.

Data sources are each company's own public career-site API -- Greenhouse's
boards-api.greenhouse.io, Ashby's api.ashbyhq.com, Workday's CXS endpoint,
Oracle's HCM recruiting API, amazon.jobs' search.json, SmartRecruiters' public
postings API, and the JSON that Google's careers page embeds in its own HTML.
Every one of these is the same feed the company's public "Careers" page uses to
render its listings. No login, no scraping of gated pages, no bypassing of any
access control.

Freshness
---------
Each fetcher returns two dates, because they answer different questions:

  posted_at  - when the req went live. Every source exposes this, so it is what
               the --max-age-days filter uses. "Posted less than 30 days ago" is
               a claim about publication, not about edits.
  updated_at - last modified, where the source exposes it (Greenhouse only).
               Everywhere else this is a copy of posted_at, flagged as such by
               date_kind, so downstream staleness logic knows not to read it as
               "nobody has touched this since".

Publication date alone would throw away evergreen reqs: a req put up 18 months
ago and edited yesterday is old by publication and live by any other reading. So
a posting past the age cutoff is readmitted when updated_at falls inside the
tighter --refresh-days window -- for Greenhouse, the one source that reports a
genuine last-modified date (see refreshed_since).

A posting with neither a readable publication date nor a recent refresh is
dropped, since "unknown age" can't satisfy "under 30 days" -- the count is
reported so the omission is visible rather than silent.
"""

import argparse
import http.client
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from companies import (
    COMPANIES, SALES_TITLE_KEYWORDS, US_LOCATION_KEYWORDS, YC_SOURCE,
    is_qualified, is_french_market, is_eu_market,
)

USER_AGENT = "Mozilla/5.0 (job-search-tool; contact: karim.maoui@edu.em-lyon.com)"

# Google's careers page serves its job data inside the HTML rather than from a
# JSON endpoint, and returns a cut-down page to a non-browser User-Agent.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_MAX_AGE_DAYS = 30

# An evergreen req -- published months ago, still actively maintained -- fails
# the publication-date test but is not cold. A last-modified date inside this
# window readmits it. Deliberately much tighter than MAX_AGE_DAYS: "edited at
# some point" is a weaker signal of a live opening than "put up recently", so it
# has to be a *recent* edit to count.
DEFAULT_REFRESH_DAYS = 15

# Per-company request ceiling for the keyword-search sources (everything except
# Greenhouse and Ashby, which return their whole board in one call). Each page
# is 20-100 postings depending on the API, so this is generous for a sales-title
# search while stopping a runaway crawl of a 20,000-req board like Oracle's.
# fetch_all_matches reports whenever a source hits the cap.
MAX_PAGES_PER_QUERY = 5

# Workday pages at 20 postings and is queried once per company by job category
# rather than once per keyword, so its budget is per-company rather than
# per-keyword: 40 pages covers the largest sales category seen (Salesforce, 779).
WORKDAY_MAX_PAGES = 40

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


# Transient network failures, as opposed to a server answering "no". A run makes
# several hundred sequential requests and a shared public API dropping some of
# them is routine at that volume -- boards-api.greenhouse.io starts timing out
# and hanging up after a few dozen calls in a row.
#
# http.client.HTTPException belongs here because urllib only wraps errors raised
# while *sending* a request in URLError: anything raised while reading the
# response comes back unwrapped, RemoteDisconnected included. Leave it out and a
# single server hanging up mid-response aborts the entire run.
TRANSIENT_ERRORS = (urllib.error.URLError, http.client.HTTPException,
                    ConnectionError, TimeoutError)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def with_retry(fn, attempts: int = 3, backoff: float = 1.5):
    """Run fn(), retrying transient failures with a growing pause between tries.

    An HTTPError is the server answering, so a 404 or a 403 fails immediately
    rather than being asked three times -- only the statuses that mean "busy,
    come back" are worth repeating.
    """
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if last or e.code not in RETRYABLE_STATUS:
                raise
        except TRANSIENT_ERRORS:
            if last:
                raise
        time.sleep(backoff * (attempt + 1))


def http_get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    def once():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return with_retry(once)


def http_post_json(url: str, payload: dict, timeout: int = 20):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST",
    )

    def once():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return with_retry(once)


def http_get_text(url: str, timeout: int = 25, accept: str = None) -> str:
    """`accept` is not cosmetic for every host: ycombinator.com answers a
    request without an Accept header with 406 Not Acceptable."""
    headers = {"User-Agent": BROWSER_USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)

    def once():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    return with_retry(once)


def parse_date(value):
    """Parse any of the date shapes the seven sources emit, into an aware
    datetime. Returns None on anything unreadable, so a malformed posting
    degrades to "unknown age" instead of crashing the run.

    Handles ISO-8601 in its several flavours (Greenhouse's -04:00 offsets,
    Ashby's fractional seconds + Z, Oracle's bare YYYY-MM-DD) and the
    "August 27, 2026" long form amazon.jobs returns.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            # amazon.jobs: "August 27, 2026", sometimes with the day padded by
            # a second space ("July  6, 2026").
            try:
                parsed = datetime.strptime(re.sub(r"\s+", " ", text), "%B %d, %Y")
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso_from_epoch(seconds) -> str:
    if not seconds:
        return ""
    return datetime.fromtimestamp(int(seconds), timezone.utc).isoformat()


def title_matches_sales(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in SALES_TITLE_KEYWORDS)


# What the `updated_at` column actually measures, per ATS. Greenhouse returns a
# real last-modified timestamp; every other source exposes only a publication
# date, so an old date there means "this req went up a while ago", NOT "nobody
# has touched it since". Evergreen reqs stay listed for years -- Hex's 2024 AE
# postings are still `isListed` today -- so downstream freshness filters have to
# know which kind of date they're reading. `posted_at` is unambiguous everywhere
# and is what the age filter in fetch_all_matches uses.
DATE_KIND_BY_ATS = {
    "greenhouse": "updated",
    "ashby": "published",
    "workday": "published",
    "oracle": "published",
    "amazon": "published",
    "google": "published",
    "smartrecruiters": "published",
    # YC reports an age in prose, from which posted_at is derived. There is no
    # last-modified date at all, so there is nothing for the refresh rule to
    # read -- YC postings are judged on publication age alone.
    "yc": "published",
}


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
    if "ashbyhq.com" in (url or "") or "ycombinator.com" in (url or ""):
        return "published"
    return "updated"


def _iso_or_blank(value) -> str:
    """Normalize a source's date to ISO-8601, or "" if it can't be read.

    Every date reaches the CSV through here so the column holds one format
    regardless of source. This matters downstream: shortlist.py reads dates with
    datetime.fromisoformat, which would reject amazon.jobs' "August 27, 2026"
    outright and quietly treat every AWS row as undated.
    """
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def _posting(title, location, url, posted_at, ats, description="",
             updated_at=None):
    """Build one normalized posting. `updated_at` defaults to posted_at for the
    six sources that expose no last-modified field (see DATE_KIND_BY_ATS)."""
    return {
        "title": title or "",
        "location": location or "",
        "url": url or "",
        "posted_at": _iso_or_blank(posted_at),
        "updated_at": _iso_or_blank(
            updated_at if updated_at is not None else posted_at),
        "date_kind": DATE_KIND_BY_ATS[ats],
        "years_experience": extract_years_experience(description),
    }


def fetch_greenhouse(company: dict):
    slug = company["slug"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = http_get_json(url)
    return [
        _posting(
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            # first_published is the real "this went live" date and is present
            # on every posting sampled; updated_at can be a year later on an
            # evergreen req, which is why the age filter uses this one.
            posted_at=j.get("first_published") or j.get("updated_at", ""),
            updated_at=j.get("updated_at", ""),
            ats="greenhouse",
            description=j.get("content", ""),
        )
        for j in data.get("jobs", [])
    ]


def fetch_ashby(company: dict):
    slug = company["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = http_get_json(url)
    return [
        _posting(
            title=j.get("title", ""),
            location=j.get("location", ""),
            url=j.get("jobUrl", ""),
            posted_at=j.get("publishedAt", ""),
            ats="ashby",
            description=j.get("descriptionPlain", ""),
        )
        for j in data.get("jobs", [])
    ]


def fetch_amazon(company: dict):
    """amazon.jobs search.json -- the feed behind the public careers site.

    Covers AWS along with the rest of Amazon; the sales-title filter downstream
    is what narrows it to the roles worth looking at.
    """
    postings, seen = [], set()
    for keyword in SALES_TITLE_KEYWORDS:
        for page in range(MAX_PAGES_PER_QUERY):
            query = urllib.parse.urlencode({
                "base_query": keyword,
                "result_limit": 100,
                "offset": page * 100,
                "sort": "recent",
            })
            data = http_get_json(f"https://www.amazon.jobs/en/search.json?{query}")
            jobs = data.get("jobs", [])
            for j in jobs:
                path = j.get("job_path", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                postings.append(_posting(
                    title=j.get("title", ""),
                    location=j.get("normalized_location", ""),
                    url=f"https://www.amazon.jobs{path}",
                    posted_at=j.get("posted_date", ""),
                    ats="amazon",
                    description=" ".join(filter(None, [
                        j.get("basic_qualifications", ""),
                        j.get("description", ""),
                    ])),
                ))
            if len(jobs) < 100:
                break
            time.sleep(0.3)
    return postings


def fetch_google(company: dict):
    """Google's careers page embeds its results as JSON in an
    AF_initDataCallback block; there is no public JSON endpoint (the old
    careers.google.com/api/v3 one now 404s).

    The positional indices below are read off that structure. They are
    inherently brittle -- if Google reshapes the payload this fetcher will start
    returning nothing rather than wrong data, because the title index would no
    longer hold a string and the sales-title filter would reject everything.
    --check-slugs is the way to notice.
    """
    postings, seen = [], set()
    for keyword in SALES_TITLE_KEYWORDS:
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            # sort_by=date makes the page-cap harmless: what gets cut is the
            # oldest end of the list, which the age filter would drop anyway.
            query = urllib.parse.urlencode({
                "q": f'"{keyword}"', "page": page, "sort_by": "date",
            })
            body = http_get_text(
                "https://www.google.com/about/careers/applications/jobs/results?"
                + query
            )
            match = re.search(
                r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel",
                body, re.DOTALL,
            )
            if not match:
                break
            try:
                block = json.loads(match.group(1))
            except ValueError:
                break
            jobs = block[0] if block and isinstance(block[0], list) else []
            for j in jobs:
                if not isinstance(j, list) or len(j) < 13:
                    continue
                job_id = j[0]
                if not isinstance(job_id, str) or job_id in seen:
                    continue
                seen.add(job_id)
                # j[9] is a list of locations, each a list whose first element
                # is the display string. Joined with "; " and read as
                # alternatives by location_is_us.
                locations = "; ".join(
                    loc[0] for loc in (j[9] or [])
                    if isinstance(loc, list) and loc and isinstance(loc[0], str)
                )
                # j[4] holds the minimum-qualifications HTML ("8 years of
                # experience in advertising sales..."), j[3] the
                # responsibilities. Both are [None, "<html>"] pairs.
                description = " ".join(
                    part[1] for part in (j[3], j[4], j[19] if len(j) > 19 else None)
                    if isinstance(part, list) and len(part) > 1
                    and isinstance(part[1], str)
                )
                postings.append(_posting(
                    title=j[1] if isinstance(j[1], str) else "",
                    location=locations,
                    url=f"https://www.google.com/about/careers/applications/jobs/results/{job_id}",
                    posted_at=_iso_from_epoch(
                        j[12][0] if isinstance(j[12], list) and j[12] else None),
                    ats="google",
                    description=description,
                ))
            # block[2] is the total match count, block[3] the page size.
            total = block[2] if len(block) > 2 and isinstance(block[2], int) else 0
            page_size = block[3] if len(block) > 3 and isinstance(block[3], int) else 20
            if page * page_size >= total:
                break
            time.sleep(0.3)
    return postings


def fetch_oracle(company: dict):
    """Oracle's HCM recruiting API, the feed behind careers.oracle.com.

    `slug` is the numeric site id (CX_45001) and `host` the tenant's HCM host,
    both visible in the careers-site network calls.
    """
    host = company["host"]
    site = company["slug"]
    postings, seen = [], set()
    for keyword in SALES_TITLE_KEYWORDS:
        for page in range(MAX_PAGES_PER_QUERY):
            finder = (
                f"findReqs;siteNumber={site},"
                f"keyword={urllib.parse.quote(keyword)},"
                f"limit=200,offset={page * 200},sortBy=POSTING_DATES_DESC"
            )
            # `expand` is load-bearing, not an optimization: without it the
            # response still returns HTTP 200 with a populated TotalJobsCount
            # but omits requisitionList entirely, so the fetch silently yields
            # nothing.
            url = (f"https://{host}/hcmRestApi/resources/latest/"
                   f"recruitingCEJobRequisitions?onlyData=true"
                   f"&expand=requisitionList.secondaryLocations&finder={finder}")
            data = http_get_json(url, timeout=30)
            items = data.get("items", [])
            reqs = items[0].get("requisitionList", []) if items else []
            for j in reqs:
                job_id = j.get("Id")
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                postings.append(_posting(
                    title=j.get("Title", ""),
                    location=j.get("PrimaryLocation", ""),
                    url=("https://careers.oracle.com/jobs/#en/sites/jobsearch/"
                         f"job/{job_id}"),
                    posted_at=j.get("PostedDate", ""),
                    ats="oracle",
                    # ShortDescriptionStr is the only description the list
                    # response populates -- ExternalQualificationsStr, where the
                    # years-of-experience line normally lives, comes back null
                    # here. So years_experience is often blank for Oracle, which
                    # downstream reads as "unknown" rather than "0 years".
                    description=j.get("ShortDescriptionStr") or "",
                ))
            if len(reqs) < 200:
                break
            time.sleep(0.3)
    return postings


def fetch_smartrecruiters(company: dict):
    """SmartRecruiters' public postings API. `releasedDate` is the publication
    date, so no per-posting detail call is needed.

    The list endpoint carries no job description, so years_experience stays
    blank for these -- which the downstream filter treats as "unknown" and ranks
    lower, rather than as "0 years required".
    """
    slug = company["slug"]
    postings, seen = [], set()
    for keyword in SALES_TITLE_KEYWORDS:
        for page in range(MAX_PAGES_PER_QUERY):
            query = urllib.parse.urlencode({
                "q": keyword, "limit": 100, "offset": page * 100,
            })
            data = http_get_json(
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?{query}")
            content = data.get("content", [])
            for j in content:
                job_id = j.get("id")
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                loc = j.get("location") or {}
                country = (loc.get("country") or "").upper()
                parts = [loc.get("city"), (loc.get("region") or "").upper(),
                         "USA" if country == "US" else country]
                postings.append(_posting(
                    title=j.get("name", ""),
                    location=", ".join(p for p in parts if p),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{job_id}",
                    posted_at=j.get("releasedDate", ""),
                    ats="smartrecruiters",
                ))
            if len(content) < 100:
                break
            time.sleep(0.3)
    return postings


def _workday_sales_facets(facets) -> list:
    """The tenant's own ids for its sales job categories.

    Workday's `jobFamilyGroup` facet ids are opaque per-tenant hashes, so they
    have to be discovered by descriptor at runtime. The descriptors differ too
    ("Sales" at Nvidia, "Field Sales" at Workday, "Business Development /
    Alliances"), hence substring matching. "Sales Operations" is excluded: it is
    a back-office family whose titles never pass the sales-title filter, so
    including it would only buy extra pages to crawl.
    """
    ids = []
    for facet in facets or []:
        if facet.get("facetParameter") != "jobFamilyGroup":
            continue
        for value in facet.get("values", []):
            label = (value.get("descriptor") or "").lower()
            if "operation" in label:
                continue
            if "sales" in label or "business development" in label:
                ids.append(value["id"])
    return ids


def fetch_workday(company: dict):
    """Workday's CXS endpoint, the feed behind every *.myworkdayjobs.com site.

    Selects by job category rather than by keyword. Workday's `searchText`
    matches descriptions as well as titles and does not rank titles first, so a
    keyword crawl both misses real matches and wastes pages on engineering reqs
    that merely mention "account executive". Filtering to the Sales categories
    returns every selling role the tenant has, which is what the title filter
    then narrows.

    The list response only dates a posting in relative, ceilinged prose
    ("Posted 30+ Days Ago"), which cannot answer a 45-day question. The exact
    `startDate` lives on the per-posting detail endpoint, so this fetches detail
    for the sales-title matches only -- a fraction of the category -- rather
    than one request per req on the whole board.
    """
    base = (f"https://{company['host']}.myworkdayjobs.com/wday/cxs/"
            f"{company['slug']}/{company['site']}")
    probe = http_post_json(base + "/jobs", {
        "appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "",
    })
    facet_ids = _workday_sales_facets(probe.get("facets"))
    if not facet_ids:
        print(f"  [warn] {company['name']}: no sales job-category facet found, "
              f"falling back to keyword search", file=sys.stderr)
    applied = {"jobFamilyGroup": facet_ids} if facet_ids else {}
    # One category query has the reach that nine keyword queries had, so it gets
    # a correspondingly larger page budget.
    queries = [("", WORKDAY_MAX_PAGES)] if facet_ids else \
        [(kw, MAX_PAGES_PER_QUERY) for kw in SALES_TITLE_KEYWORDS]

    found, seen = [], set()
    for search_text, max_pages in queries:
        for page in range(max_pages):
            data = http_post_json(base + "/jobs", {
                "appliedFacets": applied, "limit": 20, "offset": page * 20,
                "searchText": search_text,
            })
            page_jobs = data.get("jobPostings", [])
            for j in page_jobs:
                path = j.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                # Only title matches earn a detail request.
                if title_matches_sales(j.get("title", "")):
                    found.append(j)
            if len(page_jobs) < 20:
                break
            time.sleep(0.3)
        else:
            total = data.get("total")
            if total and total > max_pages * 20:
                print(f"  [warn] {company['name']}: stopped at {max_pages * 20} "
                      f"of {total} postings (page cap); some roles not seen",
                      file=sys.stderr)

    postings = []
    for j in found:
        path = j["externalPath"]
        public_url = (f"https://{company['host']}.myworkdayjobs.com/en-US/"
                      f"{company['site']}{path}")
        posted_at, description = "", ""
        # The list response collapses a multi-city req to "6 Locations", which
        # names no place at all and would read as non-US. Detail spells the
        # cities out, so prefer it and keep locationsText only as a fallback.
        location = j.get("locationsText", "")
        try:
            info = (http_get_json(base + path) or {}).get("jobPostingInfo", {})
            posted_at = info.get("startDate", "")
            description = info.get("jobDescription", "")
            public_url = info.get("externalUrl") or public_url
            spelled_out = list(dict.fromkeys(
                [info.get("location")] + list(info.get("additionalLocations") or [])))
            if any(spelled_out):
                location = "; ".join(x for x in spelled_out if x)
        except TRANSIENT_ERRORS + (ValueError,):
            # Leaving posted_at blank makes the age filter drop this posting and
            # count it as undated, which is reported -- better than guessing a
            # date from the ceilinged "30+ Days Ago" string.
            pass
        postings.append(_posting(
            title=j.get("title", ""),
            location=location,
            url=public_url,
            posted_at=posted_at,
            ats="workday",
            description=description,
        ))
        time.sleep(0.2)
    return postings


# --- Y Combinator ----------------------------------------------------------
# workatastartup.com/companies -- the board itself -- sits behind a YC login and
# redirects a signed-out request to a sign-in page, so it is out of scope by the
# same rule that keeps LinkedIn out. ycombinator.com/jobs is the public mirror of
# the same postings, needs no account, and carries the three fields this needs:
# `visa`, `createdAt` and `minExperience`.
#
# Two limits, both measured rather than assumed:
#   - It exposes a *subset*, not the whole board: 40 sales / 31 marketing /
#     38 operations postings. `?page=2` returns the same set of ids in a
#     different order, so there is no pagination to crawl -- what you see is all
#     the public mirror will give.
#   - The list order is randomised per request, so it is not "newest first" and
#     every posting has to be read to find the recent ones. That is fine at 109.
YC_ROLES = ("sales", "marketing", "operations")

# YC's own visa vocabulary, taken from the live payload. "US citizen/visa only"
# is the value that rules Karim out; the other two are exactly what the board's
# usVisaNotRequired=true filter keeps. Note they are not the same claim:
# "Will sponsor" is an offer to sponsor, while "US citizenship/visa not
# required" only means US work authorization isn't a precondition. Both are
# worth seeing, neither is a guarantee -- confirm on the posting.
YC_VISA_OK = {"Will sponsor", "US citizenship/visa not required"}

# Karim's band. YC states this per posting as "3+ years" / "Any (new grads ok)".
YC_MAX_EXPERIENCE = 3

# Three weeks. Applied through the normal age filter, not inside the fetcher, so
# the drop counts get reported the same way as every other source.
YC_MAX_AGE_DAYS = 21

_YC_RELATIVE_RE = re.compile(
    r"^(?:about|over|almost)?\s*(\d+)\s+(hour|day|week|month|year)s?$")
_YC_UNIT_DAYS = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30.5,
                 "year": 365}


def _yc_age_days(created_at: str):
    """YC reports age as prose ("11 days", "about 1 month"), never a date.

    The prose is granular in days below one month and coarse above it, which is
    the shape a 21-day question happens to need: every value that could fall
    near the boundary is given in days, and anything expressed in months or
    years is unambiguously past it. So the month/year multipliers below only
    ever decide *how far* past the cutoff a posting is, never whether it is --
    they are not precision this data has.

    Returns None on prose this doesn't recognize, which the age filter reads as
    "unknown age" and drops rather than guessing at.
    """
    match = _YC_RELATIVE_RE.match((created_at or "").strip().lower())
    if not match:
        return None
    return int(match.group(1)) * _YC_UNIT_DAYS[match.group(2)]


def _yc_years(min_experience: str):
    """"3+ years" -> 3, "Any (new grads ok)" -> 0, missing -> None (unknown).

    None matters: it means YC's field was empty, which downstream reads as
    "unknown" and keeps, rather than as "0 years required".
    """
    if not min_experience:
        return None
    match = re.search(r"(\d+)", min_experience)
    if match:
        return int(match.group(1))
    return 0 if "any" in min_experience.lower() else None


def fetch_yc(company: dict):
    """Postings from YC startups across the sales/marketing/operations roles.

    Unlike the other fetchers this returns postings from *many* companies, so
    each one carries its own `company` and `sponsors_h1b` for fetch_all_matches
    to use instead of the config entry's.

    Applies YC's two structured filters at the source, mirroring the board's own
    query: drops anything demanding existing US authorization, and anything
    above YC_MAX_EXPERIENCE years. The age cut is left to the shared age filter.
    """
    reference = parse_date(company.get("reference_date"))
    postings, seen = [], set()
    for role in YC_ROLES:
        page = http_get_text(
            f"https://www.ycombinator.com/jobs/role/{role}",
            accept="text/html,application/xhtml+xml")
        # The page is server-rendered Inertia.js: its whole dataset sits in one
        # HTML-escaped JSON attribute. Asking for the JSON directly with an
        # X-Inertia header does not work -- the server ignores it and serves
        # HTML anyway -- so this parses the attribute out.
        match = re.search(r'data-page="(.*?)"\s*>', page, re.S)
        if not match:
            continue
        payload = json.loads(html.unescape(match.group(1)))
        for j in payload.get("props", {}).get("jobPostings", []):
            if j.get("id") in seen:
                continue          # a posting can be tagged with several roles
            seen.add(j.get("id"))
            if j.get("visa") not in YC_VISA_OK:
                continue
            years = _yc_years(j.get("minExperience"))
            if years is not None and years > YC_MAX_EXPERIENCE:
                continue
            age = _yc_age_days(j.get("createdAt"))
            # Derived, not reported: YC gives an age, so the date it implies is
            # only as good as the reference date passed in. Left blank when
            # there is no reference date (check_slugs) or unreadable prose, and
            # the age filter drops those rather than inventing a date.
            posted_at = ""
            if reference is not None and age is not None:
                posted_at = (reference - timedelta(days=age)).isoformat()
            posting = _posting(
                title=j.get("title", ""),
                location=j.get("location", ""),
                url="https://www.ycombinator.com" + (j.get("url") or ""),
                posted_at=posted_at,
                ats="yc",
            )
            posting["company"] = j.get("companyName") or "YC startup"
            # A real per-posting claim from the employer, which beats the
            # per-company guess the rest of COMPANIES carries.
            posting["sponsors_h1b"] = True
            posting["years_experience"] = years
            postings.append(posting)
    return postings


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
    "workday": fetch_workday,
    "oracle": fetch_oracle,
    "amazon": fetch_amazon,
    "google": fetch_google,
    "smartrecruiters": fetch_smartrecruiters,
    "yc": fetch_yc,
}


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


def _matches_non_us(loc: str) -> bool:
    """Whether a lowercased single location names somewhere outside the US.

    Single-word keywords are matched as whole words, not substrings: "US, IN,
    Indianapolis" (Workday's format, and "Indianapolis, IN" on Greenhouse)
    contains "india", and substring matching silently dropped every Indianapolis
    role as Indian. Multi-word keywords ("united kingdom") and the anchored
    province abbreviations (", bc") stay substring matches, since neither can
    collide with a city name the same way.
    """
    words = set(w for w in re.split(r"[^a-z]+", loc) if w)
    for kw in NON_US_KEYWORDS:
        if " " in kw or "," in kw or "." in kw:
            if kw in loc:
                return True
        elif kw in words:
            return True
    return False


def _single_location_is_us(location: str) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False
    if _matches_non_us(loc):
        return False
    if any(kw in loc for kw in US_LOCATION_KEYWORDS):
        return True
    for match in re.findall(r",\s*([A-Z]{2})\b", location or ""):
        if match in US_STATE_ABBREVIATIONS:
            return True
    return False


def location_is_us(location: str) -> bool:
    """True if the posting can be worked from the US.

    A ";"-separated location is a list of alternatives, not one place: Google
    posts a single req against several cities ("Chicago, IL, USA; London, UK").
    Each segment is judged on its own so one foreign alternative doesn't
    disqualify a role that is also open in the US.
    """
    return any(_single_location_is_us(part) for part in (location or "").split(";"))


def check_slugs():
    ok, fail = [], []
    for c in COMPANIES:
        fetcher = FETCHERS[c["ats"]]
        try:
            jobs = fetcher(c)
            # A reachable source that yields nothing is worth flagging too: it
            # usually means a changed payload shape rather than a real "no sales
            # roles open", especially for the positional Google parser.
            ok.append(f"{c['name']}({len(jobs)})")
        except Exception as e:
            fail.append((c["name"], str(e)))
        time.sleep(0.3)
    print(f"OK ({len(ok)}): {', '.join(ok)}")
    if fail:
        print(f"\nFAIL ({len(fail)}):")
        for name, err in fail:
            print(f"  {name}: {err}")


def refreshed_since(date_kind: str, updated_at, refresh_cutoff) -> bool:
    """Was this posting last modified on or after `refresh_cutoff`?

    Gated on date_kind == "updated" on purpose. Only Greenhouse reports a real
    last-modified date; the other six sources copy posted_at into updated_at, so
    without the gate a refresh window *wider* than the age window would readmit
    their postings on a publication date dressed up as a refresh -- turning
    --refresh-days into a silent second --max-age-days for most of the list.
    Shared with shortlist.py so both stages answer this the same way.
    A None cutoff means the rule is switched off (--refresh-days 0).
    """
    if refresh_cutoff is None or date_kind != "updated":
        return False
    updated = parse_date(updated_at)
    return updated is not None and updated >= refresh_cutoff


def fetch_all_matches(qualified_only: bool = True, market: str = "us",
                      today: str = None,
                      max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                      refresh_days: int = DEFAULT_REFRESH_DAYS):
    """market: "us" (default) filters to US-based roles and applies the
    seniority + language qualification filter (visa sponsorship matters here).
    "french" instead looks for roles anywhere that explicitly require French,
    skipping the US location filter and the unsupported-language exclusion
    (French roles obviously don't get excluded for requiring French).
    "eu" keeps roles based in France or remote in a scope that includes France
    (EMEA/Europe-wide) -- jobs takeable from Paris with no sponsorship, since
    a French citizen needs none in the EU.
    "yc" is the odd one out: a single source (YC's public board) rather than a
    slice of COMPANIES, covering sales *plus* marketing and operations, with no
    location filter -- YC startups hire worldwide and the board's own visa filter
    is what makes a posting relevant rather than where it sits.

    today: YYYY-MM-DD, the reference point for the age filter. Passed in rather
    than read from the clock, matching tracker.py and shortlist.py. Omitting it
    disables the age filter and warns, since without a reference date there is
    no way to tell what "30 days" means.

    refresh_days: a posting published before the cutoff is still kept if its
    last-modified date falls inside this window (see refreshed_since).
    """
    cutoff = refresh_cutoff = None
    if today:
        reference = datetime.fromisoformat(today).replace(tzinfo=timezone.utc)
        cutoff = reference - timedelta(days=max_age_days)
        if refresh_days > 0:
            refresh_cutoff = reference - timedelta(days=refresh_days)
    else:
        print("  [warn] no reference date given: age filter disabled",
              file=sys.stderr)

    matches = []
    dropped_stale = dropped_undated = kept_refreshed = 0
    # The YC market is one source of its own, not a slice of the company list:
    # its postings span hundreds of startups and three role families, so mixing
    # it into the US/EU/French runs would put marketing and operations roles into
    # sales-tuned lists.
    sources = [YC_SOURCE] if market == "yc" else COMPANIES
    for c in sources:
        fetcher = FETCHERS[c["ats"]]
        try:
            # reference_date is ignored by every fetcher but YC's, which is given
            # an age in prose rather than a date and needs a point to count back
            # from. Injected here so no fetcher signature has to change.
            jobs = fetcher({**c, "reference_date": today})
        except TRANSIENT_ERRORS + (ValueError, KeyError, IndexError) as e:
            # One unreachable company must never cost the other hundred-odd: a
            # run takes minutes and writes nothing until it returns, so an
            # escaping exception here throws away all of it.
            print(f"  [warn] {c['name']}: fetch failed ({e})", file=sys.stderr)
            continue
        for j in jobs:
            # YC is queried by role, so its own filter has already decided the
            # posting is sales/marketing/operations. Re-checking sales title
            # keywords here would throw the marketing and operations ones away.
            if market != "yc" and not title_matches_sales(j["title"]):
                continue
            if market == "french":
                if not is_french_market(j["title"], j["location"]):
                    continue
            elif market == "eu":
                if not is_eu_market(j["title"], j["location"]):
                    continue
            elif market == "yc":
                pass    # no location filter: YC startups hire worldwide
            else:
                if not location_is_us(j["location"]):
                    continue
            # is_qualified reads the *title* for seniority and language. YC states
            # required experience as a structured field instead, which the fetcher
            # has already filtered on, and a title-based guess would only override
            # it with something weaker ("Chief of Staff" tagged "new grads ok").
            if qualified_only and market != "yc" and not is_qualified(j["title"]):
                continue
            if cutoff is not None:
                posted = parse_date(j["posted_at"])
                fresh = posted is not None and posted >= cutoff
                refreshed = refreshed_since(j["date_kind"], j["updated_at"],
                                            refresh_cutoff)
                if not fresh and not refreshed:
                    # Undated and stale are counted apart: one is a gap in what
                    # the source told us, the other is a fact about the posting.
                    if posted is None:
                        dropped_undated += 1
                    else:
                        dropped_stale += 1
                    continue
                if not fresh:
                    kept_refreshed += 1
            matches.append({
                # A posting may name its own employer and its own sponsorship
                # claim: YC's feed spans hundreds of startups, so the config
                # entry's name would label every row "Y Combinator" and its
                # sponsors_h1b would replace a real per-posting statement with a
                # blanket guess.
                "company": j.get("company") or c["name"],
                "sponsors_h1b": j.get(
                    "sponsors_h1b",
                    c["sponsors_h1b"] if market == "us" else None),
                "title": j["title"],
                "location": j["location"],
                "url": j["url"],
                "posted_at": j["posted_at"],
                "updated_at": j["updated_at"],
                "date_kind": j["date_kind"],
                "years_experience": j.get("years_experience"),
            })
        time.sleep(0.3)  # be polite to shared public APIs

    if cutoff is not None:
        print(f"  [info] age filter: dropped {dropped_stale} published over "
              f"{max_age_days}d ago, {dropped_undated} with no readable "
              f"publication date; kept {kept_refreshed} older ones last "
              f"modified within {refresh_days}d", file=sys.stderr)
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-slugs", action="store_true")
    parser.add_argument("--date",
                        help="today's date as YYYY-MM-DD (script cannot read the "
                             "clock itself). Required unless --check-slugs.")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help=f"only keep roles published within this many days "
                             f"(default {DEFAULT_MAX_AGE_DAYS}, or "
                             f"{YC_MAX_AGE_DAYS} with --yc)")
    parser.add_argument("--refresh-days", type=int, default=DEFAULT_REFRESH_DAYS,
                        help=f"also keep an older role whose last-modified date "
                             f"is within this many days -- an evergreen req that "
                             f"is still being maintained (default "
                             f"{DEFAULT_REFRESH_DAYS}; Greenhouse only, the "
                             f"other sources report no last-modified date). "
                             f"Pass 0 to disable.")
    parser.add_argument("--all-levels", action="store_true",
                         help="include senior/management/specialized/foreign-language roles (off by default)")
    parser.add_argument("--french", action="store_true",
                         help="search French-speaking roles worldwide instead of US roles (no visa filter)")
    parser.add_argument("--eu", action="store_true",
                         help="search roles in France or remote-inclusive-of-France "
                              "at the same US companies (no visa needed as an EU citizen)")
    parser.add_argument("--yc", action="store_true",
                         help=f"search YC startups' public board instead: sales, "
                              f"marketing and operations roles that don't require "
                              f"existing US authorization, 0-{YC_MAX_EXPERIENCE}y, "
                              f"worldwide, published within {YC_MAX_AGE_DAYS} days")
    args = parser.parse_args()

    if args.check_slugs:
        check_slugs()
        return
    if not args.date:
        parser.error("--date is required (or pass --check-slugs)")

    market = ("yc" if args.yc else
              "french" if args.french else ("eu" if args.eu else "us"))
    # Three weeks for YC rather than 30 days, per its own much faster churn.
    if args.max_age_days is None:
        args.max_age_days = (YC_MAX_AGE_DAYS if market == "yc"
                             else DEFAULT_MAX_AGE_DAYS)
    matches = fetch_all_matches(qualified_only=not args.all_levels, market=market,
                                today=args.date, max_age_days=args.max_age_days,
                                refresh_days=args.refresh_days)
    matches.sort(key=lambda m: (m["sponsors_h1b"] is not True, m["company"]))
    scope = {"french": "French-speaking roles worldwide",
             "eu": "based in France or remote-inclusive-of-France",
             "yc": "at YC startups, worldwide, no US authorization required",
             "us": "in the US"}[market]
    label = ("sales/marketing/operations roles" if market == "yc" else
             "matching sales roles" if args.all_levels
             else "qualified entry-level sales roles")
    # The refresh clause is only worth naming where a source reports a
    # last-modified date; YC reports none, so it could never apply there.
    refresh_note = ("" if market == "yc"
                    else f" (or modified in the last {args.refresh_days})")
    print(f"\nFound {len(matches)} {label} {scope}, "
          f"published in the last {args.max_age_days} days"
          f"{refresh_note}:\n")
    for m in matches:
        sponsor_flag = {True: "sponsors", False: "no-sponsor", None: "unknown"}[m["sponsors_h1b"]]
        yoe = f"{m['years_experience']}y" if m["years_experience"] is not None else "?y"
        posted = (m["posted_at"] or "")[:10]
        print(f"[{sponsor_flag:>10}] [{yoe:>3}] [{posted:>10}] {m['company']:<15} "
              f"{m['title']:<40} {m['location']:<20} {m['url']}")


if __name__ == "__main__":
    main()
