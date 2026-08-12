"""
Draft a tailored cover letter + suggested resume bullet order for a specific
job posting. This produces a starting DRAFT for you to read, edit, and
personalize -- it is not meant to be sent as-is.

Usage:
    python tailor.py --company Datadog --title "Commercial Account Executive" \\
        --location "Denver, Colorado, USA" --url "https://careers.datadoghq.com/..."
"""

import argparse
import os

from resume_data import CONTACT, EDUCATION, bullets_for

OUT_DIR = os.path.join(os.path.dirname(__file__), "data", "drafts")


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.strip().lower()).strip("_")


def draft_cover_letter(company: str, title: str) -> str:
    bullets = bullets_for(title, n=3)
    bullet_lines = "\n".join(f"- {b['text']}" for b in bullets)
    return f"""Dear {company} Hiring Team,

I'm writing to apply for the {title} role. [ONE SENTENCE HERE ON WHY {company.upper()}
SPECIFICALLY -- e.g. a product you use, a value you admire, someone you know there.
Do not skip this -- generic openers are the #1 reason sales cover letters get ignored.]

A few things from my background that I think are directly relevant:

{bullet_lines}

{EDUCATION}

I'd welcome the chance to talk about how I could contribute to {company}'s sales team.
Thank you for your time and consideration.

Best,
{CONTACT['name']}
{CONTACT['email']} | {CONTACT['phone']} | {CONTACT['linkedin']}
"""


def draft_resume_notes(title: str) -> str:
    bullets = bullets_for(title, n=len(bullets_for(title, n=99)))
    lines = "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(bullets))
    return f"""Suggested bullet order for this application (most relevant first):

{lines}

Reminder: physically reorder these in your resume before applying, don't just
paste the master version.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--location", default="")
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    slug = f"{slugify(args.company)}__{slugify(args.title)}"
    letter_path = os.path.join(OUT_DIR, f"{slug}_cover_letter.txt")
    notes_path = os.path.join(OUT_DIR, f"{slug}_resume_notes.txt")

    with open(letter_path, "w", encoding="utf-8") as f:
        f.write(draft_cover_letter(args.company, args.title))
    with open(notes_path, "w", encoding="utf-8") as f:
        header = f"Job: {args.title} @ {args.company}\nLocation: {args.location}\nURL: {args.url}\n\n"
        f.write(header + draft_resume_notes(args.title))

    print(f"Draft cover letter -> {letter_path}")
    print(f"Resume bullet notes -> {notes_path}")
    print("\nBoth are DRAFTS. Read, personalize the bracketed opener, and check facts before using.")


if __name__ == "__main__":
    main()
