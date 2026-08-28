"""
Target company list for the sales job search tool.

Each entry:
  name       - display name
  ats        - which public job-board API to query. One of "greenhouse",
               "ashby", "workday", "oracle", "amazon", "google",
               "smartrecruiters", "yc" (see FETCHERS in fetch_jobs.py).
  slug       - the company's identifier on that ATS. Unused by "google",
               whose feed covers one company only.
  sponsors_h1b - True/False/None (None = unknown, verify manually on myvisajobs.com
                 or h1bgrader.com before relying on it). This is a best-effort signal
                 based on public reputation, NOT a guarantee. Always confirm on the
                 actual job posting (look for "visa sponsorship available" language)
                 or ask the recruiter directly.
  host, site - required by "workday" (the tenant's own subdomain and career-site
               name, both visible in the careers URL) and "oracle" (the HCM host
               and its numeric site id).

Greenhouse/Ashby slugs verified reachable via API test on 2026-08-09; the
big-tech entries on 2026-08-28. Re-run fetch_jobs.py --check-slugs periodically
since companies migrate ATS providers.
"""

import re

COMPANIES = [
    # --- Greenhouse ---
    {"name": "Datadog", "ats": "greenhouse", "slug": "datadog", "sponsors_h1b": True},
    {"name": "MongoDB", "ats": "greenhouse", "slug": "mongodb", "sponsors_h1b": True},
    {"name": "GitLab", "ats": "greenhouse", "slug": "gitlab", "sponsors_h1b": None},
    {"name": "Cloudflare", "ats": "greenhouse", "slug": "cloudflare", "sponsors_h1b": True},
    {"name": "Asana", "ats": "greenhouse", "slug": "asana", "sponsors_h1b": True},
    {"name": "Airtable", "ats": "greenhouse", "slug": "airtable", "sponsors_h1b": None},
    {"name": "Robinhood", "ats": "greenhouse", "slug": "robinhood", "sponsors_h1b": True},
    {"name": "Affirm", "ats": "greenhouse", "slug": "affirm", "sponsors_h1b": True},
    {"name": "Coinbase", "ats": "greenhouse", "slug": "coinbase", "sponsors_h1b": True},
    {"name": "Reddit", "ats": "greenhouse", "slug": "reddit", "sponsors_h1b": True},
    {"name": "Pinterest", "ats": "greenhouse", "slug": "pinterest", "sponsors_h1b": True},
    {"name": "Stripe", "ats": "greenhouse", "slug": "stripe", "sponsors_h1b": True},
    {"name": "Brex", "ats": "greenhouse", "slug": "brex", "sponsors_h1b": None},
    {"name": "Elastic", "ats": "greenhouse", "slug": "elastic", "sponsors_h1b": True},
    {"name": "Okta", "ats": "greenhouse", "slug": "okta", "sponsors_h1b": True},
    {"name": "Zscaler", "ats": "greenhouse", "slug": "zscaler", "sponsors_h1b": True},
    {"name": "Samsara", "ats": "greenhouse", "slug": "samsara", "sponsors_h1b": True},
    {"name": "Gusto", "ats": "greenhouse", "slug": "gusto", "sponsors_h1b": None},
    {"name": "Doximity", "ats": "greenhouse", "slug": "doximity", "sponsors_h1b": None},
    {"name": "Squarespace", "ats": "greenhouse", "slug": "squarespace", "sponsors_h1b": None},
    {"name": "Twilio", "ats": "greenhouse", "slug": "twilio", "sponsors_h1b": True},
    {"name": "ZoomInfo", "ats": "greenhouse", "slug": "zoominfo", "sponsors_h1b": None},
    {"name": "Udemy", "ats": "greenhouse", "slug": "udemy", "sponsors_h1b": None},
    {"name": "Peloton", "ats": "greenhouse", "slug": "peloton", "sponsors_h1b": None},
    {"name": "Instacart", "ats": "greenhouse", "slug": "instacart", "sponsors_h1b": True},
    {"name": "Lyft", "ats": "greenhouse", "slug": "lyft", "sponsors_h1b": True},
    {"name": "Toast", "ats": "greenhouse", "slug": "toast", "sponsors_h1b": True},
    {"name": "Smartsheet", "ats": "greenhouse", "slug": "smartsheet", "sponsors_h1b": True},
    {"name": "Chime", "ats": "greenhouse", "slug": "chime", "sponsors_h1b": None},

    # --- Ashby ---
    {"name": "Snowflake", "ats": "ashby", "slug": "snowflake", "sponsors_h1b": True},
    {"name": "Ramp", "ats": "ashby", "slug": "ramp", "sponsors_h1b": None},
    {"name": "Confluent", "ats": "ashby", "slug": "confluent", "sponsors_h1b": True},
    {"name": "OpenAI", "ats": "ashby", "slug": "openai", "sponsors_h1b": True},
    {"name": "Vanta", "ats": "ashby", "slug": "vanta", "sponsors_h1b": None},
    {"name": "Linear", "ats": "ashby", "slug": "linear", "sponsors_h1b": None},
    {"name": "Notion", "ats": "ashby", "slug": "notion", "sponsors_h1b": True},
    {"name": "Perplexity", "ats": "ashby", "slug": "perplexity", "sponsors_h1b": None},

    # --- Added from AI/dev-tools target list, 2026-08-09 ---
    # sponsors_h1b left as None (unverified) for all of these -- most are
    # young startups without an established public sponsorship record.
    # Greenhouse:
    {"name": "Anthropic", "ats": "greenhouse", "slug": "anthropic", "sponsors_h1b": None},
    {"name": "AssemblyAI", "ats": "greenhouse", "slug": "assemblyai", "sponsors_h1b": None},
    {"name": "Descript", "ats": "greenhouse", "slug": "descript", "sponsors_h1b": None},
    {"name": "Otter.ai", "ats": "greenhouse", "slug": "otter", "sponsors_h1b": None},
    {"name": "Together AI", "ats": "greenhouse", "slug": "togetherai", "sponsors_h1b": None},
    {"name": "Crisp", "ats": "greenhouse", "slug": "crisp", "sponsors_h1b": None},
    {"name": "Vercel", "ats": "greenhouse", "slug": "vercel", "sponsors_h1b": None},
    {"name": "ClickHouse", "ats": "greenhouse", "slug": "clickhouse", "sponsors_h1b": True},
    {"name": "StackBlitz", "ats": "greenhouse", "slug": "stackblitz", "sponsors_h1b": None},
    {"name": "Databricks", "ats": "greenhouse", "slug": "databricks", "sponsors_h1b": True},

    # Ashby:
    {"name": "ElevenLabs", "ats": "ashby", "slug": "elevenlabs", "sponsors_h1b": None},
    {"name": "Midjourney", "ats": "ashby", "slug": "midjourney", "sponsors_h1b": None},
    {"name": "Runway", "ats": "ashby", "slug": "runway", "sponsors_h1b": None},
    {"name": "Cursor", "ats": "ashby", "slug": "cursor", "sponsors_h1b": None},
    {"name": "Replit", "ats": "ashby", "slug": "replit", "sponsors_h1b": None},
    {"name": "Cognition", "ats": "ashby", "slug": "cognition", "sponsors_h1b": None},
    {"name": "Gamma", "ats": "ashby", "slug": "gamma", "sponsors_h1b": None},
    {"name": "Granola", "ats": "ashby", "slug": "granola", "sponsors_h1b": None},
    {"name": "Deepgram", "ats": "ashby", "slug": "deepgram", "sponsors_h1b": None},
    {"name": "Retell AI", "ats": "ashby", "slug": "retell-ai", "sponsors_h1b": None},
    {"name": "Ideogram", "ats": "ashby", "slug": "ideogram", "sponsors_h1b": None},
    {"name": "LangChain", "ats": "ashby", "slug": "langchain", "sponsors_h1b": None},
    {"name": "LlamaIndex", "ats": "ashby", "slug": "llamaindex", "sponsors_h1b": None},
    {"name": "FireCrawl", "ats": "ashby", "slug": "firecrawl", "sponsors_h1b": None},
    {"name": "CodeRabbit", "ats": "ashby", "slug": "coderabbit", "sponsors_h1b": None},
    {"name": "Read AI", "ats": "ashby", "slug": "read-ai", "sponsors_h1b": None},
    {"name": "Photoroom", "ats": "ashby", "slug": "photoroom", "sponsors_h1b": None},
    {"name": "OpusClip", "ats": "ashby", "slug": "opusclip", "sponsors_h1b": None},
    {"name": "Tavus", "ats": "ashby", "slug": "tavus", "sponsors_h1b": None},
    {"name": "Harvey", "ats": "ashby", "slug": "harvey", "sponsors_h1b": None},
    {"name": "Sierra", "ats": "ashby", "slug": "sierra", "sponsors_h1b": None},
    {"name": "Lorikeet", "ats": "ashby", "slug": "lorikeet", "sponsors_h1b": None},
    {"name": "Fyxer.ai", "ats": "ashby", "slug": "fyxer", "sponsors_h1b": None},
    {"name": "Solve Intelligence", "ats": "ashby", "slug": "solveintelligence", "sponsors_h1b": None},
    {"name": "Cluely", "ats": "ashby", "slug": "cluely", "sponsors_h1b": None},
    {"name": "Metaview", "ats": "ashby", "slug": "metaview", "sponsors_h1b": None},
    {"name": "Modal", "ats": "ashby", "slug": "modal", "sponsors_h1b": None},
    {"name": "David AI", "ats": "ashby", "slug": "david-ai", "sponsors_h1b": None},
    {"name": "Decagon", "ats": "ashby", "slug": "decagon", "sponsors_h1b": None},
    {"name": "AVOCA", "ats": "ashby", "slug": "avoca", "sponsors_h1b": None},
    {"name": "Baseten", "ats": "ashby", "slug": "baseten", "sponsors_h1b": None},
    {"name": "E2B", "ats": "ashby", "slug": "e2b", "sponsors_h1b": None},
    {"name": "Turbopuffer", "ats": "ashby", "slug": "turbopuffer", "sponsors_h1b": None},
    {"name": "Exa", "ats": "ashby", "slug": "exa", "sponsors_h1b": None},
    {"name": "OpenRouter", "ats": "ashby", "slug": "openrouter", "sponsors_h1b": None},
    {"name": "Apify", "ats": "ashby", "slug": "apify", "sponsors_h1b": None},
    {"name": "Supabase", "ats": "ashby", "slug": "supabase", "sponsors_h1b": None},
    {"name": "Sentry", "ats": "ashby", "slug": "sentry", "sponsors_h1b": True},
    {"name": "Clerk", "ats": "ashby", "slug": "clerk", "sponsors_h1b": None},
    {"name": "PostHog", "ats": "ashby", "slug": "posthog", "sponsors_h1b": None},
    {"name": "Hex", "ats": "ashby", "slug": "hex", "sponsors_h1b": None},
    {"name": "n8n", "ats": "ashby", "slug": "n8n", "sponsors_h1b": None},
    {"name": "Browserbase", "ats": "ashby", "slug": "browserbase", "sponsors_h1b": None},
    {"name": "Resend", "ats": "ashby", "slug": "resend", "sponsors_h1b": None},
    {"name": "Fathom", "ats": "ashby", "slug": "fathom", "sponsors_h1b": None},
    {"name": "Attio", "ats": "ashby", "slug": "attio", "sponsors_h1b": None},
    # NB: Y Combinator is deliberately NOT in this list -- see YC_SOURCE below.

    # --- Big-tech career sites, added 2026-08-28 ---
    # These run their own ATS rather than Greenhouse/Ashby, so each needs its
    # own fetcher. sponsors_h1b is True across the board: all of them file
    # H-1B petitions in the thousands annually and appear on the public
    # top-sponsor lists, which is a far stronger signal than the reputational
    # guess behind the startup entries above. Still confirm on the posting.
    #
    # Snowflake (Ashby), Databricks and Datadog (Greenhouse) are deliberately
    # NOT repeated here -- they already appear above on their real ATS.
    {"name": "AWS", "ats": "amazon", "slug": "aws", "sponsors_h1b": True},
    {"name": "Google", "ats": "google", "slug": "google", "sponsors_h1b": True},
    {"name": "Oracle", "ats": "oracle", "slug": "CX_45001",
     "host": "eeho.fa.us2.oraclecloud.com", "sponsors_h1b": True},
    {"name": "ServiceNow", "ats": "smartrecruiters", "slug": "ServiceNow",
     "sponsors_h1b": True},

    # Workday-hosted career sites. `slug` is the Workday tenant, `host` its
    # subdomain (the wdN number differs per tenant), `site` the career-site id.
    {"name": "Nvidia", "ats": "workday", "slug": "nvidia",
     "host": "nvidia.wd5", "site": "NVIDIAExternalCareerSite", "sponsors_h1b": True},
    {"name": "Salesforce", "ats": "workday", "slug": "salesforce",
     "host": "salesforce.wd12", "site": "External_Career_Site", "sponsors_h1b": True},
    {"name": "Workday", "ats": "workday", "slug": "workday",
     "host": "workday.wd5", "site": "Workday", "sponsors_h1b": True},
    {"name": "Adobe", "ats": "workday", "slug": "adobe",
     "host": "adobe.wd5", "site": "external_experienced", "sponsors_h1b": True},
    {"name": "HPE", "ats": "workday", "slug": "hpe",
     "host": "hpe.wd5", "site": "Jobsathpe", "sponsors_h1b": True},
]

# One source covering hundreds of YC startups rather than a single company, so it
# is kept out of COMPANIES: it feeds its own market (--yc) with its own filters
# -- three weeks instead of 30 days, 0-3 years, and sales *plus* marketing and
# operations -- and the US/EU/French sales runs must not pick it up. Each posting
# carries its own company name and its own sponsorship claim, so the fields here
# are only what the fetcher registry needs.
YC_SOURCE = {"name": "Y Combinator", "ats": "yc", "slug": "yc",
             "sponsors_h1b": True}

SALES_TITLE_KEYWORDS = [
    "sales development",
    "sdr",
    "bdr",
    "business development",
    "account executive",
    "account manager",
    "enterprise sales",
    "sales representative",
    "inside sales",
]

# Titles containing any of these are filtered OUT even if they match a sales
# keyword above -- they require years of closing experience, a management
# track record, or a specialized clearance/vertical Karim doesn't have yet.
# Tune this list based on what still slips through.
SENIOR_EXCLUDE_KEYWORDS = [
    # seniority level
    "senior", "sr.", "sr ", "staff", "principal", "lead ", "iii", " ii ",
    # management / leadership track, not IC
    "director", "vp ", "vp,", "head of", "chief", "manager",
    "vice president", "president",  # spelled-out forms "vp " misses

    # book-of-business / tenure-gated segments
    "enterprise", "strategic", "major account", "majors", "named",
    "global account", "key account",
    # specialized verticals that need clearance or deep domain tenure
    "federal", "fedciv", "public sector", "sled", "government",
]

# Karim works in English and French only. A role gated on any other language
# is out, however the posting phrases it ("German Speaking- SDR", "AE, Dutch
# fluency", "Account Executive - LATAM (Spanish Speaking)").
#
# Rather than enumerating unsupported languages, this names the two supported
# ones and treats every *other* language as disqualifying -- so a language
# nobody thought to list still gets caught.
SUPPORTED_LANGUAGES = {"english", "french"}

# Languages that appear in tech sales postings. Only used to recognize a word
# as a language at all; membership here doesn't imply anything about whether
# Karim speaks it -- SUPPORTED_LANGUAGES decides that.
WORLD_LANGUAGES = {
    "english", "french", "german", "spanish", "portuguese", "italian",
    "dutch", "flemish", "mandarin", "cantonese", "chinese", "japanese",
    "korean", "arabic", "hebrew", "russian", "ukrainian", "polish", "czech",
    "slovak", "hungarian", "romanian", "bulgarian", "greek", "turkish",
    "hindi", "urdu", "bengali", "tamil", "punjabi", "vietnamese", "thai",
    "indonesian", "malay", "tagalog", "filipino", "swedish", "norwegian",
    "danish", "finnish", "icelandic", "estonian", "latvian", "lithuanian",
    "hebrew", "farsi", "persian", "swahili", "afrikaans", "catalan",
    "serbian", "croatian", "slovenian", "hebrew", "nordic",
}

# Regional desks that are almost always gated on a regional language even when
# the title doesn't spell one out. EMEA is deliberately absent -- those roles
# are routinely English-language and are the point of --eu mode.
UNSUPPORTED_REGION_KEYWORDS = {"latam", "apac", "anz", "benelux", "dach", "iberia"}


def unsupported_language_in(title: str):
    """Return the name of a language the title requires that Karim doesn't
    speak, or None.

    Any language word in the title counts as a requirement -- postings phrase
    it too many ways ("German Speaking- SDR", "AE, Dutch fluency", "Italian
    Market AE") to match on "speaking"/"fluency" alone. English and French
    are ignored, so "Account Executive, French fluency" stays in.
    """
    words = _location_words(title)  # same lowercase word split works on titles
    for word in words:
        if word in WORLD_LANGUAGES and word not in SUPPORTED_LANGUAGES:
            return word
    for word in words:
        if word in UNSUPPORTED_REGION_KEYWORDS:
            return word
    return None


def is_qualified(title: str) -> bool:
    """True if the title doesn't trip the seniority or language exclusions.
    Note: this only sees the job TITLE (fetch_jobs.py requests content=false
    for speed), so a language/seniority requirement buried in the full job
    description rather than the title won't be caught -- always confirm on
    the actual posting."""
    t = title.lower()
    if any(kw in t for kw in SENIOR_EXCLUDE_KEYWORDS):
        return False
    return unsupported_language_in(title) is None

US_LOCATION_KEYWORDS = [
    "united states", "usa", "u.s.", "remote - us", "remote (us)",
    "new york", "san francisco", "austin", "chicago", "boston",
    "seattle", "denver", "atlanta", "los angeles", "dallas",
]

# For --french mode: matches roles at the same target companies that are
# explicitly French-speaking, wherever in the world they're based. No visa
# question here (these aren't US roles), so sponsors_h1b is irrelevant for
# this mode -- fetch_jobs.py reports it as None regardless of the value in
# COMPANIES.
FRENCH_TITLE_KEYWORDS = [
    "french speaking", "french speaker", "french fluency", "french fluent",
    "francophone", "(french)", "- french", "french market",
]

FRENCH_LOCATION_KEYWORDS = [
    "france", "paris", "lyon", "marseille", "toulouse", "nantes",
    "belgium", "brussels", "geneva", "lausanne",  # French-speaking Switzerland only -- Zurich/Bern/Basel are German-speaking
    "quebec", "montreal", "luxembourg",
]


def is_french_market(title: str, location: str) -> bool:
    t = title.lower()
    loc = (location or "").lower()
    return any(kw in t for kw in FRENCH_TITLE_KEYWORDS) or any(kw in loc for kw in FRENCH_LOCATION_KEYWORDS)


# For --eu mode: roles at these US companies that Karim could actually take
# from Paris. As a French (EU) citizen he needs no sponsorship anywhere in the
# EU, so sponsors_h1b is irrelevant here -- the constraint is whether the
# posting's location includes France.
#
# Sampling the live feeds showed there is essentially no "remote anywhere"
# posting: remote is always scoped to a country or region ("Remote - France",
# "Remote (EMEA)", "Remote - California, USA"). So this filters on that scope
# rather than on the word "remote".
FRANCE_LOCATION_KEYWORDS = [
    "france", "paris", "lyon", "marseille", "toulouse", "bordeaux",
    "nantes", "lille",
    "fra", "fr",  # "Ville de Paris, FRA", "FR-Paris"
]

# Region scopes that include France even without naming it.
EU_WIDE_KEYWORDS = [
    "emea", "europe", "european union", "eu",
]

# Matched on whole words, not substrings: "fra" must not hit San *Fra*ncisco
# or *Fra*nkfort, and "eu" must not hit S*eu*l or Br*eu*kelen. Word bounds
# treat "/", "-" and "," as separators, so "FR-Paris" and "Ville de Paris,
# FRA" still match.
_WORD_SPLIT_RE = re.compile(r"[^a-z]+")


def _location_words(location: str) -> set:
    return {w for w in _WORD_SPLIT_RE.split((location or "").lower()) if w}

def is_eu_market(title: str, location: str) -> bool:
    """True if the posting is in France, or remote in a scope that includes
    France (EMEA/Europe-wide, or a multi-country list naming France).

    Everything else is out -- including US-scoped remote ("Remote - Texas,
    USA") and single-country non-France remote ("Remote, Germany"). The
    latter is legally open to an EU citizen but still means living there, so
    it's not a job you can take from Paris.
    """
    words = _location_words(location)
    if not words:
        return False
    return bool(words & set(FRANCE_LOCATION_KEYWORDS)
                or words & set(EU_WIDE_KEYWORDS))
