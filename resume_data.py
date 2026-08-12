"""
Structured version of Karim's resume, used by tailor.py to pick the most
relevant bullets per job and draft a cover letter. Keep in sync with
assets/CV_Karim_MAOUI.pdf if the resume changes.
"""

CONTACT = {
    "name": "Karim Maoui",
    "phone": "+33 768-971-161",
    "email": "karim.maoui@outlook.fr",
    "linkedin": "https://www.linkedin.com/in/karim-maoui-4ab43a212/",
    "github": "https://github.com/KarimMaoui",
}

# Each bullet is tagged with the role types it's most relevant for, so tailor.py
# can select the right subset per job posting. Order here follows the resume;
# bullets_for() reorders by relevance without rewriting the text.
BULLETS = [
    {
        "text": "Co-led the $1M Mechanism for AGS EMEA at AWS, an AI-powered deal qualification and "
                "acceleration mechanism serving 140+ enterprise account managers across $175M of "
                "qualified pipeline, and re-architected its data pipeline into an agentic ETL that "
                "replaced a manual weekly refresh.",
        "tags": ["ae", "account executive", "enterprise", "demand generation", "cloud",
                 "technical", "saas"],
    },
    {
        "text": "Selected by a Senior GenAI GTM Tech BDM at AWS to build an AI matching agent pairing "
                "frontier-model AI startups with AWS enterprise customers -- a partnership model "
                "landing startups their first reference customers.",
        "tags": ["sdr", "bdr", "outreach", "business development", "partnerships",
                 "demand generation", "cloud"],
    },
    {
        "text": "Served as primary point of contact for onboarding and scaling a B2B FinTech SaaS "
                "platform to 30+ institutional users (CACIB, BNP, Goldman Sachs), contributing to "
                "EUR 7M in revenue.",
        "tags": ["ae", "account executive", "account manager", "enterprise", "fintech",
                 "customer success", "saas"],
    },
    {
        "text": "Partnered with product and engineering teams to translate enterprise client needs into "
                "product improvements, driving a 35% increase in client satisfaction and a 300% revenue "
                "increase within three months.",
        "tags": ["ae", "account manager", "customer success", "enterprise"],
    },
    {
        "text": "Led go-to-market strategy (pricing, branding, B2B/B2C outreach) as co-founder of an "
                "EdTech startup, achieving a 20% outreach-to-client conversion rate and converting "
                "1,300+ prospects into clients.",
        "tags": ["sdr", "bdr", "business development", "ae", "founder", "outreach", "startup"],
    },
    {
        "text": "Built a VBA-based tool for government bond brokers across France, Italy and Spain that "
                "drove a 5% increase in executed deals, generating EUR 1.5M in annual revenue -- "
                "comfortable pairing sales execution with technical tooling.",
        "tags": ["ae", "sdr", "technical", "sales engineering", "fintech"],
    },
    {
        "text": "Shipped a spaced-repetition study app (1,100+ questions) adopted by 25+ AWS interns as "
                "the cohort's official certification revision tool, and secured buy-in from AWS Tech "
                "University to integrate it into their internal training platform.",
        "tags": ["sdr", "bdr", "technical", "founder", "startup", "cloud"],
    },
    {
        "text": "AWS Certified Solutions Architect (SAA-C03) and AWS Certified AI Practitioner (AIF-C01); "
                "proficient in Python, SQL and Excel/VBA -- able to self-serve on pipeline reporting, "
                "prospecting list-building and CRM data hygiene without waiting on RevOps.",
        "tags": ["sdr", "bdr", "ae", "technical", "sales engineering", "cloud", "saas"],
    },
]

EDUCATION = (
    "MSc in Data and Economics, EM Lyon (2021-2026) -- coursework in Sales Excellence, Business "
    "Analytics, Corporate Strategy, and Economics of Digital Platforms, after two years of "
    "Classe Preparatoire in maths and geopolitics at Lycee du Parc."
)

LANGUAGES = "English (fluent), French (native), German (intermediate)"


# Real job titles spell out what the tags abbreviate -- a posting says
# "Sales Development Representative", never "SDR". Without this expansion every
# bullet scores 0 on such titles and selection silently degrades to resume
# order, which is how this went unnoticed at first.
TAG_SYNONYMS = {
    "sdr": ["sales development representative", "sales development", "sdr"],
    "bdr": ["business development representative", "bdr"],
    "ae": ["account executive", "ae"],
    "account executive": ["account executive"],
    "account manager": ["account manager", "customer growth"],
    "business development": ["business development", "partnerships"],
    "enterprise": ["enterprise", "mid market", "mid-market", "strategic", "commercial"],
    "customer success": ["customer success", "customer growth", "retention"],
    "sales engineering": ["sales engineer", "solutions engineer", "solutions architect"],
    "cloud": ["cloud", "aws", "infrastructure", "platform"],
    "saas": ["saas", "software"],
    "outreach": ["outbound", "prospecting", "outreach"],
    "startup": ["startup", "founding", "smb", "small business"],
    "fintech": ["fintech", "financial", "payments"],
    "demand generation": ["demand generation", "growth", "pipeline"],
    "technical": ["technical", "engineer"],
    "founder": ["founding", "founder"],
    "partnerships": ["partner", "channel", "alliances"],
}


def bullets_for(title: str, n: int = 3):
    """Return the n bullets whose tags best match the job title.

    Ties keep resume order, so an untagged or unusual title still falls back
    to the strongest general bullets (AWS first) rather than an arbitrary set.
    """
    t = title.lower()
    scored = []
    for index, b in enumerate(BULLETS):
        score = 0
        for tag in b["tags"]:
            phrases = TAG_SYNONYMS.get(tag, [tag])
            if any(phrase in t for phrase in phrases):
                score += 1
        scored.append((-score, index, b))
    scored.sort(key=lambda triple: (triple[0], triple[1]))
    return [b for _, _, b in scored[:n]]
