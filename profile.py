"""
Application answers used to prefill web forms. Edit these to match your real
answers -- prefill.py fills exactly what's here and nothing else.
"""

import os

PROFILE = {
    "first_name": "Karim",
    "last_name": "Maoui",
    "email": "karim.maoui@outlook.fr",
    "phone": "+33768971161",
    "linkedin": "https://www.linkedin.com/in/karim-maoui-4ab43a212/",
    "github": "https://github.com/KarimMaoui",
    "website": "",  # intentionally blank -- nothing to link publicly yet
    "location": "Paris, France",
    "school": "EM Lyon",
    "degree": "MSc in Data and Economics",
    # Kept inside the repo rather than Downloads, which gets cleared -- a
    # missing file makes prefill.py skip the upload with only a warning.
    "resume_path": os.path.join(os.path.dirname(__file__), "assets", "CV_Karim_MAOUI.pdf"),
    # Answers for common yes/no screening questions. Review these per job --
    # visa sponsorship is the whole reason this tool filters by sponsors_h1b.
    "requires_visa_sponsorship": "Yes",
    "authorized_to_work_us": "No",
}


def resume_file_exists() -> bool:
    return os.path.isfile(PROFILE["resume_path"])
