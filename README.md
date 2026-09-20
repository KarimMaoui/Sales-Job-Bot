# Sales Job Search Tool

Semi-automated pipeline for finding SDR/BDR/AE roles at US tech companies that
sponsor visas, drafting tailored application materials, and prefilling
application forms. **Every application is submitted by you, manually** —
nothing here auto-clicks Submit or bypasses CAPTCHA/anti-bot checks.

## Setup

### What you need

- **Python 3.9 or newer.** The whole pipeline is standard library only — `csv`,
  `json`, `urllib`, `re`, `argparse`. Nothing to install for steps 1–4 and 6.
- **Playwright + Chromium**, and *only* for step 5 (`prefill.py`, the browser
  form-filler). If you never run that step, you never need it.
- **No API keys, no accounts, no ATS logins.** Every source is the public feed a
  company's own careers page already calls.

### Install

```
git clone https://github.com/KarimMaoui/Sales-Job-Bot.git
cd Sales-Job-Bot
```

Then, for the `prefill.py` step only:

```
# Windows -- py is the launcher, always on PATH once Python is installed
py -m pip install playwright
py -m playwright install chromium

# macOS / Linux
python3 -m pip install playwright
python3 -m playwright install chromium
```

Those are two different things and both are required: the first installs the
Python package, the second downloads the actual Chromium binary (~150 MB) into a
per-user cache (`%LOCALAPPDATA%\ms-playwright` on Windows,
`~/.cache/ms-playwright` on Linux, `~/Library/Caches/ms-playwright` on macOS).
Installing the package alone gets you an import that works and a launch that
fails — see [Troubleshooting](#troubleshooting).

Optional but recommended, to keep Playwright out of your global site-packages:

```
py -m venv .venv                 # python3 -m venv .venv on macOS / Linux
source .venv/Scripts/activate    # Git Bash;  .venv\Scripts\activate on cmd/PowerShell
                                 # source .venv/bin/activate on macOS / Linux
py -m pip install playwright
py -m playwright install chromium
```

The browser cache lives outside the venv, so `playwright install` is needed once
per machine, not once per venv.

### Check it worked

```
py fetch_jobs.py --help        # imports nothing third-party; should print the flags
py prefill.py --help           # ImportError here means Playwright isn't installed
py -m playwright --version     # confirms the package
py fetch_jobs.py --check-slugs # hits every career-site feed, prints a count per company
```

`--check-slugs` is the real end-to-end check: it is the one command that needs no
`--date`, and a company returning `0` means its feed moved (see
[`companies.py`](#editing-your-info)), not that you installed something wrong.

The Workflow section below spells commands as `python script.py`. On Windows read
that as `py script.py` throughout.

### Make it yours

This repo carries a real job search, not just the tooling, so a fresh clone is
somebody else's state. Before your first run:

1. **`profile.py`** — name, email, phone, links, and the screening answers
   (`requires_visa_sponsorship`, `authorized_to_work_us`). `prefill.py` types in
   exactly what is here.
2. **`assets/`** — drop in your own resume PDF and point `profile.py`'s
   `resume_path` at it. A missing file only warns, so the upload silently does
   not happen.
3. **`resume_data.py`** — the bullets `tailor.py` draws from. Keep them in sync
   with the PDF.
4. **`data/*.csv`** — delete the `jobs*.csv` and `shortlist*.csv` files to start
   from an empty history; the next `tracker.py` run recreates the file, header
   included. Keep them and you inherit somebody else's `status` marks.

⚠️ Those same four items are why this repo should not be public with real data in
it: `profile.py` and `assets/` hold a phone number, a personal email and visa
answers, and `data/*.csv` is a record of who was applied to. Making the repo
public means removing them from the **git history**, not just the working tree.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `python: command not found` / `'python' is not recognized` (Windows) | `python` is often absent from PATH even with Python installed, and `python3` may hit the Microsoft Store stub. Use `py`, or the full path: `"C:\Program Files\Python313\python.exe"`. |
| `Executable doesn't exist at ...\ms-playwright\chromium-xxxx\...` | The package is installed but the browser is not. Run `py -m playwright install chromium`. |
| `ModuleNotFoundError: No module named 'playwright'` | Only `prefill.py` needs it. Install it, or activate the venv you installed it into. |
| `error: the following arguments are required: --date` | Every fetching command takes `--date YYYY-MM-DD`; the scripts cannot read the clock. `--check-slugs` is the exception. |
| A run returns far fewer rows than expected | Freshness filter, by design: 30 days by default. Widen with `--max-age-days` / `--refresh-days`. |
| One company returns nothing | Its ATS or slug changed. `py fetch_jobs.py --check-slugs` prints per-company counts; fix the entry in `companies.py`. |

## Workflow

1. **Find matching jobs**
   ```
   python fetch_jobs.py --date 2026-08-28              # entry-level sales roles in the US
   python fetch_jobs.py --date 2026-08-28 --eu         # roles in France, or remote in a scope including France
   python fetch_jobs.py --date 2026-08-28 --french     # French-speaking sales roles anywhere in the world
   python fetch_jobs.py --date 2026-08-28 --yc         # YC startups: sales/marketing/ops, 3 weeks, 0-3y (see below)
   python fetch_jobs.py --date 2026-08-28 --all-levels # skip the seniority/language qualification filter
   python fetch_jobs.py --date 2026-08-28 --max-age-days 60 --refresh-days 30
   ```
   Queries each company in `companies.py` via its public career-site API and
   filters titles to sales roles. `--date` is required because the scripts are
   written blind and can't read the clock; it's the reference point for the
   freshness filter below.

   **Only roles published in the last `--max-age-days` (default 30) are
   returned**, plus older ones **last modified in the last `--refresh-days`
   (default 15)**. Every source exposes a real publication date, recorded in the
   `posted_at` column, and that is what the age test reads — not `updated_at`,
   which on an evergreen Greenhouse req can be *years* later than the day the job
   went up (Datadog has AE reqs published in 2019 and edited yesterday).

   The refresh window is what keeps those: published long ago, but the source
   touched it recently, so somebody is still maintaining the req. It is
   deliberately much tighter than the age window, because "edited at some point"
   is weaker evidence of a live opening than "put up recently". It applies **only
   where `date_kind` is `updated`** — Greenhouse, the one source reporting a
   genuine last-modified date. The other six copy `posted_at` into `updated_at`,
   and without that gate a `--refresh-days` wider than `--max-age-days` would
   readmit their postings on a publication date dressed up as a refresh. Pass
   `--refresh-days 0` to age everything out on publication date alone.

   One caveat on the signal: a company that bulk-edits its whole board resets
   every `updated_at` at once (Datadog's all read the same day), so there a
   recent refresh says less about *that* req than it looks like it does.

   A posting with neither a readable publication date nor a recent refresh is
   dropped, since "unknown age" can't satisfy "under 30 days"; the run prints how
   many that was, and how many the refresh window readmitted, so neither is
   silent.

   Seven sources, one fetcher each in `fetch_jobs.py`:

   | Source | Companies | Publication date from |
   |---|---|---|
   | Greenhouse | Datadog, Databricks, Stripe, Anthropic, … | `first_published` |
   | Ashby | Snowflake, OpenAI, Notion, Cursor, … | `publishedAt` |
   | amazon.jobs | AWS | `posted_date` |
   | Google careers | Google | timestamp in the page's embedded JSON |
   | Oracle HCM | Oracle | `PostedDate` |
   | Workday CXS | Nvidia, Salesforce, Adobe, HPE, Workday | `startDate` (detail endpoint) |
   | SmartRecruiters | ServiceNow | `releasedDate` |
   | YC public board | hundreds of YC startups (`--yc` only) | derived from `createdAt` |

   Two of these need explaining:

   - **Workday** selects by *job category*, not keyword: its `searchText`
     matches descriptions as well as titles and doesn't rank titles first, so a
     keyword crawl both misses real matches and wastes pages on engineering reqs
     that merely mention "account executive". The category ids are opaque
     per-tenant hashes, so they're discovered at runtime by descriptor ("Sales"
     at Nvidia, "Field Sales" at Workday). Workday's list response also dates a
     posting only as ceilinged prose ("Posted 30+ Days Ago"), which can't answer
     a 30-day question, so title matches get one extra detail request each for
     the exact date. Detail is also where multi-city reqs spell out their
     locations — the list collapses them to "6 Locations", which names no place
     and would read as non-US.
   - **Google** has no public JSON endpoint any more (the old
     `careers.google.com/api/v3` returns 404), so its fetcher reads the JSON
     that the careers page embeds in its own HTML. That means positional
     indices, which are brittle by nature: if Google reshapes the payload this
     fetcher returns *nothing* rather than wrong data, because the title index
     would stop holding a string. `--check-slugs` prints a per-company count,
     which is how you notice.

   Four lists, tracked separately because the visa question differs in each:

   - **US** (default) — US locations only, needs H-1B sponsorship.
   - **`--eu`** — the *same US companies*, but roles based in France or
     remote in a scope that includes France. No sponsorship needed as an EU
     citizen. Filters on the remote *scope*, not the word "remote": sampling
     the live feeds showed there is essentially no "remote anywhere" posting
     — it's always bounded ("Remote - France", "Remote (EMEA)", "Remote -
     Texas, USA"). US-scoped and single-country non-France remote are both
     out, since either means relocating.
   - **`--french`** — any role worldwide whose title or location signals
     French (e.g. "Account Executive, French fluency" in Dublin).
   - **`--yc`** — YC startups' public board. Different rules from the three
     above, so it gets its own files (see below).

   `--eu` and `--french` overlap by design: a Paris role appears in both, a
   French-fluency role in Dublin only in `--french`, and an English-language
   Paris role only in `--eu`.

   ### The YC list (`--yc`)

   ```
   python fetch_jobs.py --date 2026-08-28 --yc
   python tracker.py    --date 2026-08-28 --yc --new-only   # -> data/jobs_yc.csv
   python shortlist.py  --date 2026-08-28 --yc              # -> data/shortlist_yc.csv
   ```

   Runs on the board's own bands rather than the sales defaults: **three weeks**
   instead of 30 days, **0–3 years** instead of 0–2, **sales + marketing +
   operations** instead of sales alone, and **no location filter** — YC startups
   hire worldwide, and what makes a posting relevant here is the visa answer, not
   the city. That mix is why it's a separate list: marketing and operations roles
   would be thrown out by the sales title filter the other three lists depend on.

   Two things to know before trusting it.

   **It is not the board you may have in mind.** `workatastartup.com/companies`
   is behind a YC login — a signed-out request redirects to a sign-in page — so
   it's out of scope under the same rule that keeps LinkedIn out. This uses
   `ycombinator.com/jobs/role/{sales,marketing,operations}`, the public mirror,
   which needs no account. The mirror exposes a **subset**: 40 sales / 31
   marketing / 38 operations postings, 109 distinct. `?page=2` returns the same
   ids in a different order, so there is no pagination to crawl — what the mirror
   shows is all it will give, and the full board is bigger. Expect a handful of
   matches per run, not a stream (3 the day it was built, two of them outside the
   US).

   **Sponsorship is per posting here, which is unusually good.** YC states one of
   three values: `US citizen/visa only` (dropped), `Will sponsor`, or
   `US citizenship/visa not required` (both kept — that's what the board's own
   `usVisaNotRequired=true` filter does). Note the last two aren't the same claim:
   one offers to sponsor, the other only says US authorization isn't a
   precondition. Both beat the per-company `sponsors_h1b` guess used elsewhere;
   neither is a guarantee.

   Dates are **derived, not reported**: YC gives an age in prose ("11 days",
   "about 1 month"), so `posted_at` is `--date` minus that age. The prose is
   day-granular below a month and coarse above, which is exactly what a 21-day
   question needs — every value that could land near the boundary is given in
   days, and anything in months or years is unambiguously past it. Prose the
   parser doesn't recognize is dropped as undated rather than guessed at.

   Applying needs a YC account (the Apply button goes to
   `account.ycombinator.com`), so `prefill.py` can't help with these — one
   account, created by you, is fine; that's not what the multiple-accounts limit
   below is about.

2. **Track them over time** (avoids re-seeing the same posting)
   ```
   python tracker.py --date 2026-08-09 --new-only            # -> data/jobs.csv
   python tracker.py --date 2026-08-09 --new-only --eu       # -> data/jobs_eu.csv
   python tracker.py --date 2026-08-09 --new-only --french   # -> data/jobs_french.csv
   python tracker.py --date 2026-08-09 --new-only --yc       # -> data/jobs_yc.csv
   ```
   Appends new postings to a CSV. Run this daily/weekly and pass today's
   actual date (the script can't read the clock itself) — it's written blind,
   so a wrong date lands in `first_seen` and skews the freshness filter.
   It fetches through `fetch_jobs.py`, so the freshness rule applies here too and
   `--max-age-days` / `--refresh-days` work the same way; a posting that fails
   both never enters the CSV in the first place. Rows already tracked keep their place and get
   their dates refreshed rather than aged out — that's `shortlist.py`'s job.
   The four lists get separate files since `sponsors_h1b` only means
   anything for the US list; EU and French roles aren't US visa cases, so
   `shortlist.py` ranks those on years of experience alone (tiers A/B only). The
   YC list is separate for a different reason — its own age, experience and role
   bands, described above.

   Each row includes a `years_experience` column, parsed from the full job
   description (first "N+ years of experience" phrase found). It's a
   best-effort regex match, not guaranteed — leave it blank in your head as
   "unknown" rather than "0 years" when the column is empty, and always
   confirm on the actual posting before ruling a role in or out.

3. **Cut the tracked list down to a ranked shortlist**
   ```
   python shortlist.py --date 2026-08-09            # -> data/shortlist.csv
   python shortlist.py --date 2026-08-09 --french   # -> data/shortlist_french.csv
   python shortlist.py --date 2026-08-09 --yc       # -> data/shortlist_yc.csv
   ```
   Drops postings published more than `--max-age-days` ago (default 30, same as
   `fetch_jobs.py`) unless modified within `--refresh-days` (default 15), and
   those with a *known* requirement above `--max-years`
   (default 2), then ranks what's left into tiers: **A** sponsors + years fit,
   **B** sponsors + years unknown, **C** sponsorship unknown + years fit, **D**
   both unknown. Blank `years_experience` never disqualifies a role — it means
   the regex found nothing, not that the job needs zero experience. `--yc`
   swaps both defaults for the board's own bands (21 days, 3 years), so the
   shortlist doesn't re-filter that list on rules its fetcher never used.

   Rows with a `posted_at` are judged on that date: it's a real publication date
   from the source, so "over 30 days old" is a fact rather than an inference —
   with the evergreen exception above, which readmits one edited in the last 15
   days. Rows predating that column fall back to the old rule, which
   reads `updated_at` and is only trustworthy where `date_kind` is `updated`
   (Greenhouse). Ashby and the big-tech career sites expose no last-modified
   field, so those legacy rows carry a publication date in `updated_at` and get
   exempted: an old publication date says the req went up a while ago, not that
   it went cold, and those APIs only list postings still open on the board.
   Filtering both alike threw away 29 live openings (3 of them tier A) at
   Snowflake, Notion, Harvey, Baseten and others. The run prints how many rows
   each of the two exemptions kept. `--strict-age` ages every row out on its own
   date, dropping both the recently-edited evergreen reqs and these legacy ones.

   Re-running the shortlist is also how the accumulated history gets re-filtered:
   `tracker.py` refreshes rows already in the CSV but never deletes them, so
   tightening `--max-age-days` narrows what gets *added* on the fetch side and
   what survives here.

   It also re-applies the US location filter to rows already in the CSV, so
   tightening `location_is_us` cleans up past rows too rather than only
   future fetches.

   Add `--dedupe` to collapse postings that differ only by city or territory,
   keeping the freshest 2 per role (`--dedupe 1` for one, `--dedupe 5` for
   five). Toast posts the same "Territory Account Executive, SMB" for 100+
   cities; applying to each is pointless — same recruiting team, same form —
   and reads as spam.

   Grouping strips city suffixes after `" - "` and territory parentheticals
   (`(West)`, `(TOLA)`, `(Midwest)`). It deliberately keeps `(Hunter)`,
   `(Grower)`, `(Inbound)` and `(BDR)` distinct — those are different roles
   (new-business vs expansion vs inbound), not the same job in another
   region. Add new territory words to `TERRITORY_WORDS` in `shortlist.py`.

   Dedupe runs *after* ranking, so survivors are each group's highest-tier,
   freshest postings. Nothing is deleted from `data/jobs.csv` — dropping a
   duplicate from the shortlist doesn't lose the posting.

4. **Draft a tailored cover letter + resume bullet order for one job**
   ```
   python tailor.py --company Datadog --title "Commercial Account Executive" \
       --location "Denver, Colorado, USA" --url "https://..."
   ```
   Writes drafts to `data/drafts/`. **Read and personalize the bracketed
   opener before using** — the #1 reason generic cover letters get ignored.

5. **Prefill the application form**
   ```
   python prefill.py --url "https://..."
   ```
   Opens a real browser window, fills name/email/phone/links/resume from
   `profile.py`, and leaves the browser open. You review every field, answer
   screening questions (visa sponsorship, etc.) by hand, paste in your
   personalized cover letter, and click Submit yourself.

6. **Record what you did**
   ```
   python mark.py 8094078 --status applied --date 2026-08-09
   python mark.py 8094078 --status rejected --date 2026-08-20 --note "no sponsorship"
   python mark.py --list                       # everything you've touched
   ```
   The positional argument is any substring of the posting URL — the job id
   from the shortlist is the easy one to paste. An ambiguous match refuses to
   write anything and prints the candidates; `--all` marks them all on
   purpose, which is how you skip a batch of duplicate city postings:
   ```
   python mark.py samsara.com --status skipped --date 2026-08-09 --all
   ```

   Statuses are `new`, `interested`, `drafted` (still on your to-do list) and
   `applied`, `interviewing`, `offer`, `rejected`, `skipped` (done —
   `shortlist.py` hides these unless you pass `--include-done`).

   Marks go to `data/jobs.csv`, the source of truth, and survive later
   `tracker.py` runs. Don't edit `data/shortlist.csv` — it's a derived view
   and gets overwritten on every `shortlist.py` run. Add `--eu`, `--french` or
   `--yc` to mark a row in one of the other lists; each has its own CSV, so a
   mark on the US list doesn't reach a posting tracked elsewhere.

## Editing your info

- `profile.py` — contact info, resume file path, and screening-question
  answers (visa sponsorship status, work authorization). Fields left blank
  are skipped by `prefill.py` rather than filled with an empty value.
- `assets/CV_Karim_MAOUI.pdf` — the resume `prefill.py` uploads. Kept in the repo
  on purpose: pointing at `Downloads/` means a folder cleanup silently breaks
  the upload (you'd only get a warning).
- `resume_data.py` — resume bullets tagged by role type, used by `tailor.py`
  to pick relevant ones per job. **Keep in sync with the PDF** — nothing
  checks that they agree, so an edit to one and not the other is how a cover
  letter ends up claiming something your resume doesn't.
  `TAG_SYNONYMS` maps each tag to the phrasings real postings use ("Sales
  Development Representative" for `sdr`); a tag with no synonym entry only
  matches its own literal text.
- `data/jobs.csv` / `jobs_eu.csv` / `jobs_french.csv` / `jobs_yc.csv` — one per
  list, and the tracker's source of truth,
  including your `status` marks. Safe to edit by hand if you prefer a
  spreadsheet; keep the column order. `posted_at` is when the req went live and
  is comparable across every source — it's the column to read for freshness.
  `updated_at` is last-modified only for Greenhouse (where it's what readmits an
  evergreen req); everywhere else it's a copy
  of `posted_at`, and `date_kind` records which of the two you're looking at
  (`updated` vs `published`). Don't compare them as if they meant the same
  thing. Rows written before `date_kind` existed get backfilled from the
  company's ATS on the next run; rows written before `posted_at` existed keep it
  blank rather than copying `updated_at` into it, since the two can be a year
  apart and copying would invent a publication date the source never gave.
- `companies.py` — target company list, plus the title filters.
  `SUPPORTED_LANGUAGES` is `{english, french}`: a title naming any *other*
  language is dropped however it's phrased ("German Speaking- SDR", "AE,
  Dutch fluency", "Italian Market AE"). It works by naming what you speak and
  rejecting every other language in `WORLD_LANGUAGES`, so a language nobody
  thought to list is still caught — add to `SUPPORTED_LANGUAGES` if that
  changes. `UNSUPPORTED_REGION_KEYWORDS` drops regional desks that are
  language-gated in practice (LATAM, APAC, DACH, Benelux, Iberia, ANZ);
  EMEA is deliberately *not* there, since those roles are routinely
  English-language and are the point of `--eu`.

  The seniority and language filters read the **title only**, so a requirement
  buried in the body still slips through — confirm on the posting. (Descriptions
  *are* fetched, but only to parse `years_experience` out of them.)
  `sponsors_h1b` is a best-effort
  signal (True/False/None), **not a guarantee** — always confirm on the
  actual posting or with the recruiter. Re-run with `--check-slugs` if a
  company stops returning results (they may have switched ATS providers):
  ```
  python fetch_jobs.py --check-slugs
  ```

## What this deliberately does NOT do

- Auto-submit applications
- Solve or bypass CAPTCHA/reCAPTCHA (Greenhouse forms often have one —
  you'll see it in the browser, solve it yourself if it appears)
- Scrape LinkedIn or any other login-gated page — including
  `workatastartup.com`, which is why `--yc` reads YC's public board instead.
  Every other source is the public feed a company's own "Careers" page uses to
  render its listings, including Workday's public job-board endpoint, which
  needs no account. Nothing here authenticates anywhere.
- Create or use multiple accounts on any platform

These are hard limits, not missing features to add later.
