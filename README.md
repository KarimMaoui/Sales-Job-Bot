# Sales Job Search Tool

Semi-automated pipeline for finding SDR/BDR/AE roles at US tech companies that
sponsor visas, drafting tailored application materials, and prefilling
application forms. **Every application is submitted by you, manually** —
nothing here auto-clicks Submit or bypasses CAPTCHA/anti-bot checks.

## Setup (already done in this environment)

```
pip install playwright
python -m playwright install chromium
```

## Workflow

1. **Find matching jobs**
   ```
   python fetch_jobs.py            # entry-level sales roles in the US
   python fetch_jobs.py --eu       # roles in France, or remote in a scope including France
   python fetch_jobs.py --french   # French-speaking sales roles anywhere in the world
   python fetch_jobs.py --all-levels  # skip the seniority/language qualification filter
   ```
   Queries each company in `companies.py` via its public career-site API
   (Greenhouse/Ashby), filters titles to sales roles. Three markets, tracked
   separately because the visa question differs in each:

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

   `--eu` and `--french` overlap by design: a Paris role appears in both, a
   French-fluency role in Dublin only in `--french`, and an English-language
   Paris role only in `--eu`.

2. **Track them over time** (avoids re-seeing the same posting)
   ```
   python tracker.py --date 2026-08-09 --new-only            # -> data/jobs.csv
   python tracker.py --date 2026-08-09 --new-only --eu       # -> data/jobs_eu.csv
   python tracker.py --date 2026-08-09 --new-only --french   # -> data/jobs_french.csv
   ```
   Appends new postings to a CSV. Run this daily/weekly and pass today's
   actual date (the script can't read the clock itself) — it's written blind,
   so a wrong date lands in `first_seen` and skews the freshness filter.
   The three markets get separate files since `sponsors_h1b` only means
   anything for the US list; EU and French roles aren't US visa cases, so
   `shortlist.py` ranks those on years of experience alone (tiers A/B only).

   Each row includes a `years_experience` column, parsed from the full job
   description (first "N+ years of experience" phrase found). It's a
   best-effort regex match, not guaranteed — leave it blank in your head as
   "unknown" rather than "0 years" when the column is empty, and always
   confirm on the actual posting before ruling a role in or out.

3. **Cut the tracked list down to a ranked shortlist**
   ```
   python shortlist.py --date 2026-08-09            # -> data/shortlist.csv
   python shortlist.py --date 2026-08-09 --french   # -> data/shortlist_french.csv
   ```
   Drops postings not updated in the last `--max-age-days` (default 90) and
   those with a *known* requirement above `--max-years` (default 2), then
   ranks what's left into tiers: **A** sponsors + years fit, **B** sponsors +
   years unknown, **C** sponsorship unknown + years fit, **D** both unknown.
   Blank `years_experience` never disqualifies a role — it means the regex
   found nothing, not that the job needs zero experience.

   The age filter only applies to rows whose `date_kind` is `updated`. Ashby's
   public API returns no last-modified field, only `publishedAt`, so those rows
   are tagged `published` and exempted: an old publication date says the req
   went up a while ago, not that it went cold, and the API only lists postings
   still open on the board. Filtering both alike threw away 29 live openings
   (3 of them tier A) at Snowflake, Notion, Harvey, Baseten and others. The run
   prints how many rows the exemption kept; `--strict-age` restores the blunt
   behaviour and ages out both kinds.

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
   and gets overwritten on every `shortlist.py` run.

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
- `data/jobs.csv` / `jobs_french.csv` — the tracker's source of truth,
  including your `status` marks. Safe to edit by hand if you prefer a
  spreadsheet; keep the column order. `date_kind` records what `updated_at`
  actually measures for that row — `updated` (Greenhouse's real last-modified
  timestamp) or `published` (Ashby, which exposes no update field). Don't
  compare the two as if they meant the same thing; `shortlist.py`'s age filter
  keys off this column. Rows written before it existed get backfilled from the
  company's ATS on the next run.
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

  Only the **title** is checked (the fetch skips full descriptions for
  speed), so a language requirement buried in the body still slips through —
  confirm on the posting. `sponsors_h1b` is a best-effort
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
- Scrape LinkedIn, Workday, or other login-gated pages
- Create or use multiple accounts on any platform

These are hard limits, not missing features to add later.
