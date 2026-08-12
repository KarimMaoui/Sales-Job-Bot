"""
Open a job application page in a real, visible browser window and prefill the
standard fields (name, email, phone, links, resume upload) from profile.py.

The browser is left open on the filled-in form for you to review, fix
anything the heuristics got wrong, answer any remaining questions, and click
Submit yourself. This script NEVER submits the form -- there is no code path
in here that clicks a submit/apply button.

Usage:
    python prefill.py --url "https://boards.greenhouse.io/company/jobs/12345"

Requires: pip install playwright && playwright install chromium (already done
in this project's setup).
"""

import argparse
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from profile import PROFILE, resume_file_exists

# label text -> profile key. Matched case-insensitively against <label> text,
# aria-label, and placeholder. Forms vary a lot between companies, so this is
# best-effort: whatever isn't matched, you fill in by hand in the open browser.
FIELD_LABEL_MAP = [
    (["first name"], "first_name"),
    (["last name"], "last_name"),
    (["email"], "email"),
    (["phone"], "phone"),
    (["linkedin"], "linkedin"),
    (["github"], "github"),
    (["website", "portfolio"], "website"),
    (["location", "current location", "city"], "location"),
]

RESUME_LABEL_HINTS = ["resume", "cv", "upload resume", "attach resume"]


def application_frames(page):
    """Job application forms are frequently embedded in an iframe (Greenhouse,
    Ashby, Lever all do this). Return the main page plus every same-site frame
    so field lookups can search all of them."""
    return [page] + list(page.frames)


def try_fill_text_fields(page):
    filled = []
    for hints, profile_key in FIELD_LABEL_MAP:
        value = PROFILE.get(profile_key, "")
        if not value:
            continue
        for frame in application_frames(page):
            matched = False
            for hint in hints:
                try:
                    locator = frame.get_by_label(hint, exact=False)
                    if locator.count() > 0:
                        locator.first.fill(value, timeout=3000)
                        filled.append(profile_key)
                        matched = True
                        break
                except Exception:
                    continue
            if matched:
                break
    return filled


def try_upload_resume(page):
    if not resume_file_exists():
        print(f"  [warn] resume file not found at {PROFILE['resume_path']}, skipping upload",
              file=sys.stderr)
        return False
    for frame in application_frames(page):
        try:
            file_inputs = frame.locator("input[type=file]")
            count = file_inputs.count()
        except Exception:
            continue
        if count == 0:
            continue
        target = file_inputs.first
        for i in range(count):
            el = file_inputs.nth(i)
            try:
                name_attr = (el.get_attribute("name") or "").lower()
                id_attr = (el.get_attribute("id") or "").lower()
            except Exception:
                continue
            if any(h in name_attr or h in id_attr for h in ["resume", "cv"]):
                target = el
                break
        try:
            target.set_input_files(PROFILE["resume_path"])
            return True
        except Exception as e:
            print(f"  [warn] resume upload failed in frame {frame.url}: {e}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        print(f"Opening {args.url} ...")
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)  # let JS-rendered forms (Ashby/Greenhouse embeds) settle

        filled = try_fill_text_fields(page)
        uploaded = try_upload_resume(page)

        print(f"\nAuto-filled fields: {filled or '(none matched)'}")
        print(f"Resume uploaded: {uploaded}")
        print("\nBrowser is open and left on the form. Review every field, answer any "
              "screening questions by hand, personalize the cover letter, and click "
              "Submit yourself when ready.")
        print("This script will not close the browser or touch Submit -- close the "
              "window when you're done.")

        # Keep the script alive so the browser (and its process) stays open
        # until the user closes the window manually.
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass


if __name__ == "__main__":
    main()
