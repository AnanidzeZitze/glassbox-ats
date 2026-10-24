"""Module 2: NLP Pipeline & Taxonomy Normalizer (backend/services/nlp_pipeline.py).

Implements:
- Stage 2: Tokenization (spaCy) & Unicode Glyph Sanitization (`sanitize_and_tokenize`)
- Stage 3: Section Segmentation & Boundary Detection (`segment_sections`) for the 5 Mandatory ATS Sections
           plus non-standard header failure detection (`"My Journey"`, `"What I Bring"`, `"Superpowers"`, `"Toolkit"`, `"Knowledge"`).
- Stage 4: Named Entity Recognition (Deterministic Regex + Statistical NER) & Lightcast Open Skills / ESCO v1.2
           Taxonomy Normalization (`normalize_skills_taxonomy`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import spacy

from backend.models.schemas import (
    CanonicalResume,
    ExtractionResult,
    KeywordLocation,
    NormalizedSkill,
    ParsedAddress,
    ParsedEducation,
    ParsedEmployment,
    PhantomTokenHazard,
    SKILL_CATEGORY_WEIGHTS,
    SectionBoundaryFailure,
    SkillCategory,
)

# Load spaCy pipeline once (with safe fallback to blank("en") if model is missing)
try:
    NLP = spacy.load("en_core_web_md")
except Exception:
    try:
        NLP = spacy.load("en_core_web_sm")
    except Exception:
        NLP = spacy.blank("en")


# ============================================================================
# Stage 2: Bullet Sanitizer & Unicode Glyph Whitelist
# ============================================================================

# Whitelisted bullet characters: solid circles, open circles, squares, ASCII hyphens & asterisks
WHITELISTED_BULLET_CHARS: Set[str] = {
    "•",  # \u2022 solid circle
    "●",  # \u25cf black circle
    "◦",  # \u25e6 white bullet / open circle
    "○",  # \u25cb white circle
    "▪",  # \u25aa black small square
    "■",  # \u25a0 black square
    "-",  # ASCII hyphen
    "*",  # ASCII asterisk
}

# Decorative Unicode symbols that act as phantom token hazards when used as bullets
DECORATIVE_BULLET_HAZARDS: Set[str] = {
    "➢", "➣", "➤", "➔", "➜", "➝", "➞", "⟶", "⇒", "⇛", "▶", "►", "▸",
    "✔", "✓", "☑", "✦", "✧", "★", "☆", "✪", "✫", "❖", "◆", "◇", "◈",
    "—", "–", "»", "›", "☞", "⚡", "🔹", "🔸",
}


def sanitize_and_tokenize(raw_text: str) -> Tuple[str, List[PhantomTokenHazard], List[str]]:
    """Sanitize decorative bullet glyphs and tokenize text via spaCy.

    Flags decorative Unicode symbols (custom arrows, checkmarks, stars, em-dashes
    used as bullets) as `phantom_token_hazards` before normalizing them to `-`.
    """
    hazards: List[PhantomTokenHazard] = []
    sanitized_lines: List[str] = []

    for raw_line in raw_text.splitlines():
        stripped = raw_line.lstrip()
        if not stripped:
            sanitized_lines.append("")
            continue

        first_char = stripped[0]
        leading_ws = raw_line[: len(raw_line) - len(stripped)]

        if first_char in DECORATIVE_BULLET_HAZARDS or (
            ord(first_char) > 127
            and first_char not in WHITELISTED_BULLET_CHARS
            and not first_char.isalnum()
        ):
            hazards.append(
                PhantomTokenHazard(
                    raw_glyph=first_char,
                    codepoint=f"U+{ord(first_char):04X}",
                    line_text=raw_line.strip(),
                    normalized_replacement="-",
                )
            )
            normalized_line = f"{leading_ws}- {stripped[1:].lstrip()}"
            sanitized_lines.append(normalized_line)
        else:
            sanitized_lines.append(raw_line)

    sanitized_text = "\n".join(sanitized_lines)
    doc = NLP(sanitized_text)
    tokens = [t.text for t in doc if not t.is_space]
    return sanitized_text, hazards, tokens


# ============================================================================
# Stage 3: Section Segmentation & Boundary Detection
# ============================================================================

# Exact whitelisted standard headers per Section 3 Stage 3
WHITELISTED_STANDARD_HEADERS: Dict[str, str] = {
    "professional summary": "Professional Summary",
    "summary": "Professional Summary",
    "work experience": "Work Experience",
    "professional experience": "Work Experience",
    "experience": "Work Experience",
    "education": "Education",
    "skills": "Skills",
    "technical skills": "Skills",
    "certifications": "Certifications",
    "projects": "Projects",
    "contact information": "Contact Information",
    "contact": "Contact Information",
}

# Non-standard creative headers that trigger `section_boundary_failure` (Lever unmapped drop)
NON_STANDARD_CREATIVE_HEADERS: Dict[str, str] = {
    "my journey": "Work Experience",
    "career journey": "Work Experience",
    "where i've been": "Work Experience",
    "work history & adventures": "Work Experience",
    "what i bring": "Skills",
    "superpowers": "Skills",
    "toolkit": "Skills",
    "my toolkit": "Skills",
    "knowledge": "Skills",
    "core superpowers": "Skills",
    "academic background": "Education",
    "where i studied": "Education",
}


def classify_section_header(raw_header: str) -> Optional[str]:
    """Classify a section header candidate into a canonical ATS section name."""
    cand = re.sub(r"[:\-–—_#*]+$", "", raw_header).strip().lower()
    if cand in WHITELISTED_STANDARD_HEADERS:
        return WHITELISTED_STANDARD_HEADERS[cand]
    if cand in NON_STANDARD_CREATIVE_HEADERS:
        return NON_STANDARD_CREATIVE_HEADERS[cand]
    return None


def segment_sections(
    sanitized_text: str,
) -> Tuple[Dict[str, List[str]], Dict[str, str], List[SectionBoundaryFailure]]:
    """Segment resume lines into standard ATS sections and detect non-standard headers.

    Also detects headerless opening summary blocks placed directly below the contact block
    (standard in modern executive and single-page resumes).
    """
    sections: Dict[str, List[str]] = {
        "Contact Information": [],
        "Professional Summary": [],
        "Work Experience": [],
        "Education": [],
        "Skills": [],
        "Certifications": [],
        "Projects": [],
    }
    detected_headers: Dict[str, str] = {}
    failures: List[SectionBoundaryFailure] = []

    current_section = "Contact Information"
    lines = sanitized_text.splitlines()

    for line in lines:
        clean = line.strip()
        if not clean:
            continue

        # Normalize potential header line (strip trailing colons or decorative rules)
        header_candidate = re.sub(r"[:\-–—_#*]+$", "", clean).strip()
        lower_cand = header_candidate.lower()

        if lower_cand in WHITELISTED_STANDARD_HEADERS and len(header_candidate.split()) <= 4:
            mapped_sec = WHITELISTED_STANDARD_HEADERS[lower_cand]
            current_section = mapped_sec
            detected_headers[mapped_sec] = header_candidate
            continue

        if lower_cand in NON_STANDARD_CREATIVE_HEADERS and len(header_candidate.split()) <= 5:
            inferred_sec = NON_STANDARD_CREATIVE_HEADERS[lower_cand]
            failures.append(
                SectionBoundaryFailure(
                    header_text=header_candidate,
                    inferred_target_section=inferred_sec,
                    reason=(
                        f"Non-standard creative heading '{header_candidate}' is unmapped by strict ATS "
                        f"parsers (e.g., Lever) and causes '{inferred_sec}' block drop."
                    ),
                )
            )
            current_section = f"UNMAPPED_{inferred_sec}"
            sections.setdefault(current_section, [])
            continue

        # Extract inline 'Certification:' or 'Certifications:' line inside Education/Skills
        if re.match(r"^certifications?\s*:", clean, re.IGNORECASE):
            cert_val = re.sub(r"^certifications?\s*:\s*", "", clean, flags=re.IGNORECASE).strip()
            if cert_val:
                sections["Certifications"].append(cert_val)
                detected_headers.setdefault("Certifications", "Certifications")
            continue

        sections.setdefault(current_section, []).append(clean)

    return sections, detected_headers, failures


# ============================================================================
# Stage 4: Deterministic Regex & Lightcast / ESCO v1.2 Taxonomy Normalization
# ============================================================================

# RFC 5322 compliant email regex
EMAIL_REGEX = re.compile(
    r"\b[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+\b"
)

# US and international phone regex
PHONE_REGEX = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\b\d{3}\b)[\s.-]?\d{3}[\s.-]?\d{4}\b"
)

# LinkedIn profile URL regex
LINKEDIN_REGEX = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?")

# Date span patterns for consistency checking
MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_PATTERNS = {
    "MONTH_YYYY": re.compile(
        rf"\b({MONTH_NAMES})\s+(\d{{4}})\s*[-–—to]+\s*(({MONTH_NAMES})\s+(\d{{4}})|Present|Current)\b",
        re.IGNORECASE,
    ),
    "MM_SLASH_YYYY": re.compile(
        r"\b(0?[1-9]|1[0-2])/(\d{4})\s*[-–—to]+\s*((0?[1-9]|1[0-2])/(\d{4})|Present|Current)\b",
        re.IGNORECASE,
    ),
    "YYYY_DASH_MM": re.compile(
        r"\b(\d{4})-(0[1-9]|1[0-2])\s*[-–—to]+\s*((\d{4})-(0[1-9]|1[0-2])|Present|Current)\b",
        re.IGNORECASE,
    ),
}

MONTH_TO_INT: Dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# Seeded Lightcast Open Skills & ESCO v1.2 Taxonomy Catalog
# Maps lowercase lookup key -> (canonical_id, canonical_name, SkillCategory, hierarchy_cat, hierarchy_subcat, is_single_token_tech)
LIGHTCAST_ESCO_TAXONOMY: Dict[str, Tuple[str, str, SkillCategory, str, str, bool]] = {
    # Hard Skills (Weight 2.0x)
    "python": ("SKILL_ID_402", "Python", SkillCategory.HARD_SKILL, "Information Technology", "Programming Languages", True),
    "py": ("SKILL_ID_402", "Python", SkillCategory.HARD_SKILL, "Information Technology", "Programming Languages", True),
    "sql": ("SKILL_ID_403", "SQL", SkillCategory.HARD_SKILL, "Information Technology", "Database & Query Languages", True),
    "django": ("SKILL_ID_404", "Django", SkillCategory.HARD_SKILL, "Information Technology", "Web Frameworks", True),
    "postgresql": ("SKILL_ID_405", "PostgreSQL", SkillCategory.HARD_SKILL, "Information Technology", "Databases", True),
    "postgres": ("SKILL_ID_405", "PostgreSQL", SkillCategory.HARD_SKILL, "Information Technology", "Databases", True),
    "rest apis": ("SKILL_ID_406", "REST APIs", SkillCategory.HARD_SKILL, "Information Technology", "API Architecture", False),
    "restful apis": ("SKILL_ID_406", "REST APIs", SkillCategory.HARD_SKILL, "Information Technology", "API Architecture", False),
    "rest api": ("SKILL_ID_406", "REST APIs", SkillCategory.HARD_SKILL, "Information Technology", "API Architecture", False),
    "ci/cd": ("SKILL_ID_407", "CI/CD", SkillCategory.HARD_SKILL, "Information Technology", "DevOps", True),
    "microservices architecture": ("SKILL_ID_408", "microservices architecture", SkillCategory.HARD_SKILL, "Information Technology", "System Architecture", False),
    "microservices": ("SKILL_ID_408", "microservices architecture", SkillCategory.HARD_SKILL, "Information Technology", "System Architecture", True),
    "a/b testing": ("SKILL_ID_409", "A/B testing", SkillCategory.HARD_SKILL, "Analysis", "Experimentation", False),
    "product analytics": ("SKILL_ID_410", "product analytics", SkillCategory.HARD_SKILL, "Business", "Product Management", False),
    "okrs": ("SKILL_ID_411", "OKRs", SkillCategory.HARD_SKILL, "Business", "Strategic Planning", False),
    "objectives and key results": ("SKILL_ID_411", "OKRs", SkillCategory.HARD_SKILL, "Business", "Strategic Planning", False),
    "search engine optimization": ("SKILL_ID_412", "Search Engine Optimization (SEO)", SkillCategory.HARD_SKILL, "Marketing", "Digital Marketing", False),
    "seo": ("SKILL_ID_412", "Search Engine Optimization (SEO)", SkillCategory.HARD_SKILL, "Marketing", "Digital Marketing", True),
    "fastapi": ("SKILL_ID_413", "FastAPI", SkillCategory.HARD_SKILL, "Information Technology", "Web Frameworks", True),
    "typescript": ("SKILL_ID_414", "TypeScript", SkillCategory.HARD_SKILL, "Information Technology", "Programming Languages", True),
    "javascript": ("SKILL_ID_415", "JavaScript", SkillCategory.HARD_SKILL, "Information Technology", "Programming Languages", True),
    "react": ("SKILL_ID_416", "React", SkillCategory.HARD_SKILL, "Information Technology", "Frontend Frameworks", True),
    "machine learning": ("SKILL_ID_417", "Machine Learning", SkillCategory.HARD_SKILL, "Artificial Intelligence", "Machine Learning", False),
    "container orchestration": ("SKILL_ID_418", "Container Orchestration", SkillCategory.HARD_SKILL, "Information Technology", "Cloud Native", False),
    "project management": ("SKILL_ID_419", "Project Management", SkillCategory.HARD_SKILL, "Business", "Project Management", False),
    "process redesign": ("SKILL_ID_420", "Process Redesign", SkillCategory.HARD_SKILL, "Business", "Operations", False),
    "budget and spend tracking": ("SKILL_ID_421", "Budget & Spend Tracking", SkillCategory.HARD_SKILL, "Business", "Financial Operations", False),
    "content calendars": ("SKILL_ID_422", "Content Calendars", SkillCategory.HARD_SKILL, "Marketing", "Campaign Operations", False),
    "creative briefs": ("SKILL_ID_423", "Creative Briefs", SkillCategory.HARD_SKILL, "Marketing", "Creative Operations", False),
    "creative briefs for designers": ("SKILL_ID_423", "Creative Briefs", SkillCategory.HARD_SKILL, "Marketing", "Creative Operations", False),
    "business analytics": ("SKILL_ID_424", "Business Analytics", SkillCategory.HARD_SKILL, "Analysis", "Analytics", False),
    "quantitative finance": ("SKILL_ID_425", "Quantitative Finance", SkillCategory.HARD_SKILL, "Finance", "Quantitative Analysis", False),

    # Tools (Weight 1.5x)
    "aws": ("SKILL_ID_501", "AWS", SkillCategory.TOOL, "Cloud Computing", "Cloud Platforms", True),
    "amazon web services": ("SKILL_ID_501", "AWS", SkillCategory.TOOL, "Cloud Computing", "Cloud Platforms", True),
    "docker": ("SKILL_ID_502", "Docker", SkillCategory.TOOL, "Information Technology", "Containerization", True),
    "git": ("SKILL_ID_503", "Git", SkillCategory.TOOL, "Information Technology", "Version Control", True),
    "kubernetes": ("SKILL_ID_504", "Kubernetes", SkillCategory.TOOL, "Information Technology", "Container Orchestration", True),
    "k8s": ("SKILL_ID_504", "Kubernetes", SkillCategory.TOOL, "Information Technology", "Container Orchestration", True),
    "celery": ("SKILL_ID_505", "Celery", SkillCategory.TOOL, "Information Technology", "Task Queues", True),
    "redis": ("SKILL_ID_506", "Redis", SkillCategory.TOOL, "Information Technology", "In-Memory Databases", True),
    "tableau": ("SKILL_ID_507", "Tableau", SkillCategory.TOOL, "Business Intelligence", "Data Visualization", True),
    "jira": ("SKILL_ID_508", "Jira", SkillCategory.TOOL, "Project Management", "Issue Tracking", True),
    "confluence": ("SKILL_ID_509", "Confluence", SkillCategory.TOOL, "Collaboration", "Documentation Tools", True),
    "figma": ("SKILL_ID_510", "Figma", SkillCategory.TOOL, "Design", "UI/UX Tools", True),
    "advanced excel": ("SKILL_ID_511", "Advanced Excel", SkillCategory.TOOL, "Business Intelligence", "Spreadsheets", False),
    "excel": ("SKILL_ID_511", "Microsoft Excel", SkillCategory.TOOL, "Business Intelligence", "Spreadsheets", True),
    "google analytics 4": ("SKILL_ID_512", "Google Analytics 4 (GA4)", SkillCategory.TOOL, "Marketing", "Web Analytics", False),
    "ga4": ("SKILL_ID_512", "Google Analytics 4 (GA4)", SkillCategory.TOOL, "Marketing", "Web Analytics", True),
    "mailchimp": ("SKILL_ID_513", "Mailchimp", SkillCategory.TOOL, "Marketing", "Email Marketing", True),
    "lifecycle email (mailchimp)": ("SKILL_ID_513", "Lifecycle Email (Mailchimp)", SkillCategory.TOOL, "Marketing", "Email Marketing", False),
    "wordpress": ("SKILL_ID_514", "WordPress", SkillCategory.TOOL, "Information Technology", "CMS", True),
    "woocommerce": ("SKILL_ID_515", "WooCommerce", SkillCategory.TOOL, "E-Commerce", "Platforms", True),
    "hubspot": ("SKILL_ID_516", "HubSpot", SkillCategory.TOOL, "Marketing", "CRM", True),
    "salesforce": ("SKILL_ID_517", "Salesforce", SkillCategory.TOOL, "Sales", "CRM", True),
    "google ads": ("SKILL_ID_518", "Google Ads", SkillCategory.TOOL, "Marketing", "Paid Search", False),
    "meta ads manager": ("SKILL_ID_519", "Meta Ads Manager", SkillCategory.TOOL, "Marketing", "Paid Social", False),

    # Certifications (Weight 2.0x)
    "aws certified solutions architect": ("SKILL_ID_601", "AWS Certified Solutions Architect", SkillCategory.CERTIFICATION, "Cloud Computing", "Certifications", False),
    "pmp": ("SKILL_ID_602", "Project Management Professional (PMP)", SkillCategory.CERTIFICATION, "Business", "Certifications", True),
    "project management professional": ("SKILL_ID_602", "Project Management Professional (PMP)", SkillCategory.CERTIFICATION, "Business", "Certifications", False),
    "cka": ("SKILL_ID_603", "Certified Kubernetes Administrator (CKA)", SkillCategory.CERTIFICATION, "Information Technology", "Certifications", True),
    "google ai professional certificate": ("SKILL_ID_604", "Google AI Professional Certificate", SkillCategory.CERTIFICATION, "Artificial Intelligence", "Certifications", False),

    # Soft Skills (Weight 0.5x)
    "stakeholder management": ("SKILL_ID_701", "stakeholder management", SkillCategory.SOFT_SKILL, "Interpersonal", "Leadership", False),
    "leadership": ("SKILL_ID_702", "Leadership", SkillCategory.SOFT_SKILL, "Interpersonal", "Leadership", False),
    "communication": ("SKILL_ID_703", "Communication", SkillCategory.SOFT_SKILL, "Interpersonal", "Communication", False),
    "cross-functional collaboration": ("SKILL_ID_704", "Cross-Functional Collaboration", SkillCategory.SOFT_SKILL, "Interpersonal", "Teamwork", False),
    "agile": ("SKILL_ID_705", "Agile", SkillCategory.SOFT_SKILL, "Methodology", "Agile Delivery", False),
}

# Semantic neighbor graph for Lever embedding similarity (+0.5 neighbor credit)
SEMANTIC_SKILL_NEIGHBORS: Dict[str, Set[str]] = {
    "kubernetes": {"container orchestration", "docker swarm", "eks", "gke", "helm", "k8s"},
    "container orchestration": {"kubernetes", "k8s", "ecs", "nomad"},
    "postgresql": {"relational database", "rds", "sql", "aurora"},
    "aws": {"cloud infrastructure", "ec2", "s3", "gcp", "azure"},
    "celery": {"distributed task queue", "background workers", "rabbitmq"},
    "redis": {"in-memory cache", "memcached", "caching"},
    "microservices architecture": {"distributed systems", "service-oriented architecture", "soa"},
    "ci/cd": {"github actions", "jenkins", "gitlab ci", "continuous integration"},
}

SEMANTIC_TITLE_NEIGHBORS: Dict[str, Set[str]] = {
    "senior python developer": {
        "senior software engineer",
        "senior backend engineer",
        "lead python engineer",
        "staff python developer",
    },
    "senior software engineer": {
        "senior python developer",
        "senior backend engineer",
        "software engineer iii",
    },
    "senior product manager": {
        "lead product manager",
        "group product manager",
        "principal product manager",
    },
    "marketing coordinator": {
        "marketing operations analyst",
        "marketing lead",
        "growth analyst",
        "project coordinator",
    },
    "marketing operations analyst": {
        "marketing coordinator",
        "marketing lead",
        "growth analyst",
    },
}

GENERIC_SOFT_SKILL_TERMS: Set[str] = {
    "communication",
    "leadership",
    "teamwork",
    "collaboration",
    "cross-functional collaboration",
    "stakeholder management",
    "problem solving",
    "time management",
    "adaptability",
    "empathy",
    "work ethic",
    "interpersonal skills",
}


def normalize_skill_token(raw_skill: str) -> NormalizedSkill:
    """Map a skill token or phrase to its Lightcast/ESCO canonical ID and weighted category."""
    cleaned = raw_skill.strip()
    key = cleaned.lower()

    if key in LIGHTCAST_ESCO_TAXONOMY:
        cid, cname, cat, h_cat, h_subcat, is_single_tech = LIGHTCAST_ESCO_TAXONOMY[key]
        return NormalizedSkill(
            raw_text=cleaned,
            canonical_id=cid,
            canonical_name=cname,
            category=cat,
            weight=SKILL_CATEGORY_WEIGHTS[cat],
            hierarchy_category=h_cat,
            hierarchy_subcategory=h_subcat,
            is_single_token_technical=is_single_tech,
        )

    # Heuristic classification for unknown skills: only classify as SOFT_SKILL if it matches interpersonal/soft terms
    is_single = len(cleaned.split()) == 1 and key != "okrs"
    is_soft = key in GENERIC_SOFT_SKILL_TERMS or any(s in key for s in ("interpersonal", "teamwork", "empathy"))
    cat = SkillCategory.SOFT_SKILL if is_soft else SkillCategory.HARD_SKILL
    synth_id = f"SKILL_ID_SYNTH_{abs(hash(key)) % 9000 + 1000}"
    return NormalizedSkill(
        raw_text=cleaned,
        canonical_id=synth_id,
        canonical_name=cleaned,
        category=cat,
        weight=SKILL_CATEGORY_WEIGHTS[cat],
        is_single_token_technical=is_single,
    )


def format_phone_e164(raw_phone: str) -> str:
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else raw_phone


def format_phone_us(raw_phone: str) -> str:
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw_phone


def detect_date_formats(text: str) -> Tuple[List[str], bool]:
    """Check all date spans in text and flag if mixed date formats are used."""
    found_formats: List[str] = []
    for fmt_name, pattern in DATE_PATTERNS.items():
        if pattern.search(text):
            found_formats.append(fmt_name)
    return found_formats, len(found_formats) > 1


def _parse_single_date(date_str: str) -> Tuple[Optional[int], Optional[int], bool]:
    """Return (year, month, is_current) from a date substring."""
    clean = date_str.strip()
    if clean.lower() in {"present", "current", "now"}:
        return None, None, True

    # Check Month YYYY
    m_month = re.match(rf"^({MONTH_NAMES})\.?\s+(\d{{4}})$", clean, re.IGNORECASE)
    if m_month:
        m_str = m_month.group(1).lower()[:3]
        year = int(m_month.group(2))
        return year, MONTH_TO_INT.get(m_str, 1), False

    # Check MM/YYYY
    m_slash = re.match(r"^(0?[1-9]|1[0-2])/(\d{4})$", clean)
    if m_slash:
        return int(m_slash.group(2)), int(m_slash.group(1)), False

    # Check YYYY-MM
    m_iso = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", clean)
    if m_iso:
        return int(m_iso.group(1)), int(m_iso.group(2)), False

    # Check bare YYYY
    m_year = re.match(r"^(\d{4})$", clean)
    if m_year:
        return int(m_year.group(1)), 1, False

    return None, None, False


_LOCATION_LOOKING_RE = re.compile(
    r"^(?:[A-Z][a-zA-Z\s.]+,\s*(?:[A-Z]{2}|[A-Z][a-zA-Z\s]+)|Remote|Hybrid)$"
)
_COMPANY_HINT_RE = re.compile(
    r"\b(?:inc\.?|llc|ltd\.?|pvt\.?|corp(?:oration)?|company|co\.|foundation|university|"
    r"college|institute|school|systems|technologies|labs?|group|partners|bank|hospital|studio|agency)\b",
    re.IGNORECASE,
)


def _split_role_header_parts(header_chunks: List[str]) -> Tuple[str, str]:
    """Given 1 to 3 non-date header strings for a role, identify (title, company) and ignore pure location strings."""
    tokens: List[str] = []
    for chunk in header_chunks:
        for part in re.split(r"\s*\|\s*", chunk):
            p = part.strip(" ,-–—()")
            if not p:
                continue
            if _LOCATION_LOOKING_RE.match(p):
                continue
            if p not in tokens:
                tokens.append(p)

    if not tokens:
        raw_first = header_chunks[0].split("|")[0].strip() if header_chunks else "Role"
        return raw_first, "Organization"
    if len(tokens) == 1:
        # Try splitting on ' at ' or ' - ' or ','
        sub = [s.strip() for s in re.split(r"\s+(?:at|@|—|–|-)\s+", tokens[0]) if s.strip()]
        if len(sub) >= 2:
            return sub[0], sub[1]
        return tokens[0], "Organization"

    # If the first token looks like a company and the second does not, swap or keep standard Title | Company order
    t0, t1 = tokens[0], tokens[1]
    role_word_re = re.compile(
        r"\b(engineer|developer|manager|analyst|coordinator|specialist|director|architect|"
        r"designer|lead|scientist|consultant|intern|associate|president|vp|head|founder|officer|assistant|researcher)\b",
        re.IGNORECASE,
    )
    if _COMPANY_HINT_RE.search(t0) and role_word_re.search(t1) and not role_word_re.search(t0):
        return t1, t0
    return t0, t1


def _parse_employments_from_lines(lines: List[str]) -> List[ParsedEmployment]:
    """Parse work experience lines into structured ParsedEmployment objects.

    Supports:
    - Single-line headers: `Senior Product Manager | Zendex Inc. | Mar 2022 - Present`
    - Two-line headers:
        Line 1: `Marketing Operations Analyst | Boston, Massachusetts`
        Line 2: `Grimes King Foundation Inc. | Aug 2025 -- Present`
    - Multi-block `\\hfill` headers split by Stream B into 3-4 consecutive short lines:
        Line 1: `Marketing Operations Analyst`
        Line 2: `Boston, Massachusetts`
        Line 3: `Grimes King Foundation Inc.`
        Line 4: `Aug 2025 -- Present`
    """
    employments: List[ParsedEmployment] = []
    current_emp: Optional[ParsedEmployment] = None

    date_span_re = re.compile(
        rf"((?:{MONTH_NAMES}\.?\s+\d{{4}})|(?:\d{{1,2}}/\d{{4}})|(?:\d{{4}}-\d{{2}})|(?:\b(?:19|20)\d{{2}}\b))\s*[-–—to]+\s*"
        rf"((?:{MONTH_NAMES}\.?\s+\d{{4}})|(?:\d{{1,2}}/\d{{4}})|(?:\d{{4}}-\d{{2}})|(?:\b(?:19|20)\d{{2}}\b)|Present|Current)",
        re.IGNORECASE,
    )

    cleaned_lines = [ln.strip() for ln in lines if ln.strip()]
    idx = 0
    n = len(cleaned_lines)

    def _is_bullet(s: str) -> bool:
        return bool(s) and s[0] in WHITELISTED_BULLET_CHARS

    def _is_short_header_line(s: str) -> bool:
        return (not _is_bullet(s)) and len(s) <= 85 and not s.endswith(".")

    while idx < n:
        stripped = cleaned_lines[idx]

        # 1. Bullet line
        if _is_bullet(stripped):
            bullet_text = stripped[1:].strip()
            if current_emp is not None and bullet_text:
                current_emp.bullets.append(bullet_text)
            idx += 1
            continue

        # 2. Look ahead up to 3 lines for a date span across short non-bullet header lines
        m_date_curr = date_span_re.search(stripped)
        if m_date_curr:
            start_raw, end_raw = m_date_curr.group(1), m_date_curr.group(2)
            s_year, s_month, _ = _parse_single_date(start_raw)
            e_year, e_month, is_curr = _parse_single_date(end_raw)

            prefix = stripped[: m_date_curr.start()].strip(" |,-–—()")
            header_chunks = [prefix] if prefix else []
            title, company = _split_role_header_parts(header_chunks)

            current_emp = ParsedEmployment(
                title=title,
                company=company,
                start_date_raw=start_raw,
                end_date_raw=end_raw,
                start_year=s_year or 2020,
                start_month=s_month or 1,
                end_year=e_year,
                end_month=e_month,
                is_current=is_curr,
                bullets=[],
            )
            employments.append(current_emp)
            idx += 1
            continue

        if _is_short_header_line(stripped):
            date_offset: Optional[int] = None
            m_date_found: Optional[re.Match[str]] = None
            for offset in (1, 2, 3):
                if idx + offset >= n:
                    break
                cand_line = cleaned_lines[idx + offset]
                if not _is_short_header_line(cand_line):
                    break
                m_cand = date_span_re.search(cand_line)
                if m_cand:
                    date_offset = offset
                    m_date_found = m_cand
                    break

            if date_offset is not None and m_date_found is not None:
                start_raw, end_raw = m_date_found.group(1), m_date_found.group(2)
                s_year, s_month, _ = _parse_single_date(start_raw)
                e_year, e_month, is_curr = _parse_single_date(end_raw)

                header_chunks = [cleaned_lines[idx + k] for k in range(date_offset)]
                date_line_prefix = cleaned_lines[idx + date_offset][: m_date_found.start()].strip(" |,-–—()")
                if date_line_prefix:
                    header_chunks.append(date_line_prefix)

                title, company = _split_role_header_parts(header_chunks)
                current_emp = ParsedEmployment(
                    title=title,
                    company=company,
                    start_date_raw=start_raw,
                    end_date_raw=end_raw,
                    start_year=s_year or 2020,
                    start_month=s_month or 1,
                    end_year=e_year,
                    end_month=e_month,
                    is_current=is_curr,
                    bullets=[],
                )
                employments.append(current_emp)
                idx += date_offset + 1
                continue

        # 3. Secondary line or wrapped bullet continuation
        if current_emp is not None and not current_emp.bullets and "|" in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip() and not _LOCATION_LOOKING_RE.match(p.strip())]
            if parts and current_emp.company in ("Company", "Organization"):
                current_emp.company = parts[0]
        elif current_emp is not None:
            if current_emp.bullets and not current_emp.bullets[-1].endswith("."):
                current_emp.bullets[-1] = f"{current_emp.bullets[-1]} {stripped}"
            else:
                current_emp.bullets.append(stripped)
        idx += 1

    return employments


def _parse_educations_from_lines(lines: List[str]) -> List[ParsedEducation]:
    """Parse education lines into ParsedEducation records (supporting 1-line, 2-line, and 4-block hfill entries)."""
    educations: List[ParsedEducation] = []
    cleaned_lines: List[str] = []
    for line in lines:
        stripped = line.strip().lstrip("•●◦-* ").strip()
        if not stripped:
            continue
        if re.match(r"^(relevant coursework|coursework|gpa|honors|activities|dean's list)\s*:", stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(stripped)

    idx = 0
    n = len(cleaned_lines)
    degree_keywords_re = re.compile(
        r"\b(b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?b\.?a\.?|ph\.?d\.?|bachelor(?:'s)?|master(?:'s)?|associate(?:'s)?|doctorate|diploma)\b",
        re.IGNORECASE,
    )
    school_keywords_re = re.compile(
        r"\b(university|college|institute|school|academy|polytechnic)\b",
        re.IGNORECASE,
    )
    year_re = re.compile(r"\b(19\d{2}|20\d{2})\b")

    while idx < n:
        curr = cleaned_lines[idx]
        curr_years = year_re.findall(curr)

        # Case 1: Single line already contains both a year and either pipes or degree/school
        if curr_years and ("|" in curr or degree_keywords_re.search(curr) or school_keywords_re.search(curr)):
            end_year = int(curr_years[-1])
            without_year = re.sub(
                rf"[,|()\s-]*(?:{MONTH_NAMES}\.?\s+)?(19\d{{2}}|20\d{{2}})(?:\s*[-–—to]+\s*(?:{MONTH_NAMES}\.?\s+)?(?:19\d{{2}}|20\d{{2}}|Present))?[,|()\s-]*",
                " | ",
                curr,
                flags=re.IGNORECASE,
            ).strip(" |")
            parts = [
                p.strip()
                for p in re.split(r"\s*\|\s*", without_year)
                if p.strip() and not _LOCATION_LOOKING_RE.match(p.strip())
            ]
            if len(parts) == 1:
                parts = [p.strip() for p in re.split(r"\s*[—–-]\s*", parts[0]) if p.strip()]

            degree_part = parts[0] if parts else curr
            school_part = parts[1] if len(parts) > 1 else "University"
            if school_keywords_re.search(degree_part) and not degree_keywords_re.search(degree_part) and len(parts) > 1:
                degree_part, school_part = parts[1], parts[0]

            degree = degree_part
            major: Optional[str] = None
            if " in " in degree_part:
                d_split = degree_part.split(" in ", 1)
                degree, major = d_split[0].strip(), d_split[1].strip()
            elif "," in degree_part and not school_keywords_re.search(degree_part):
                d_split = degree_part.split(",", 1)
                degree, major = d_split[0].strip(), d_split[1].strip()

            educations.append(
                ParsedEducation(
                    degree=degree,
                    major=major,
                    school=school_part,
                    end_year=end_year,
                )
            )
            idx += 1
            continue

        # Case 2: Multi-line / hfill Education block (collect up to 4 lines until we hit a line with a graduation year)
        block_lines = [curr]
        consumed = 1
        found_years = list(curr_years)
        while consumed < 4 and (idx + consumed) < n:
            nxt_ln = cleaned_lines[idx + consumed]
            # Stop if next line starts a brand new School after we already saw a degree or year
            if found_years:
                break
            block_lines.append(nxt_ln)
            yr_matches = year_re.findall(nxt_ln)
            if yr_matches:
                found_years.extend(yr_matches)
                consumed += 1
                break
            consumed += 1

        end_year = int(found_years[-1]) if found_years else 2020
        school_val = "University"
        degree_raw = ""

        for bl in block_lines:
            bl_no_yr = re.sub(
                rf"[,|()\s-]*(?:{MONTH_NAMES}\.?\s+)?(19\d{{2}}|20\d{{2}})(?:\s*[-–—to]+\s*(?:{MONTH_NAMES}\.?\s+)?(?:19\d{{2}}|20\d{{2}}|Present))?[,|()\s-]*",
                " ",
                bl,
                flags=re.IGNORECASE,
            ).strip(" |-–—")
            if not bl_no_yr or _LOCATION_LOOKING_RE.match(bl_no_yr):
                continue
            for seg in [s.strip() for s in bl_no_yr.split("|") if s.strip()]:
                if _LOCATION_LOOKING_RE.match(seg):
                    continue
                if degree_keywords_re.search(seg):
                    degree_raw = seg
                elif school_keywords_re.search(seg) or school_val == "University":
                    school_val = seg
                elif not degree_raw:
                    degree_raw = seg

        if not degree_raw:
            degree_raw = block_lines[0].split("|")[0].strip()

        degree = degree_raw
        major = None
        if " in " in degree_raw:
            d_split = degree_raw.split(" in ", 1)
            degree, major = d_split[0].strip(), d_split[1].strip()
        elif " - " in degree_raw:
            d_split = degree_raw.split(" - ", 1)
            degree, major = d_split[0].strip(), d_split[1].strip()
        elif "," in degree_raw:
            d_split = degree_raw.split(",", 1)
            degree, major = d_split[0].strip(), d_split[1].strip()

        educations.append(
            ParsedEducation(
                degree=degree,
                major=major,
                school=school_val,
                end_year=end_year,
            )
        )
        idx += consumed

    return educations


def parse_resume_text(
    raw_text: str,
    extraction_result: Optional[ExtractionResult] = None,
) -> CanonicalResume:
    """Execute Stage 2, Stage 3, and Stage 4 NLP pipeline to produce a CanonicalResume."""
    sanitized_text, hazards, _ = sanitize_and_tokenize(raw_text)
    section_lines, detected_headers, boundary_failures = segment_sections(sanitized_text)

    # Extract deterministic regex entities across full text
    email_match = EMAIL_REGEX.search(sanitized_text)
    phone_match = PHONE_REGEX.search(sanitized_text)
    linkedin_match = LINKEDIN_REGEX.search(sanitized_text)
    date_formats, mixed_dates = detect_date_formats(sanitized_text)

    email = email_match.group(0) if email_match else None
    phone_raw = phone_match.group(0) if phone_match else None
    phone_us = format_phone_us(phone_raw) if phone_raw else None
    phone_e164 = format_phone_e164(phone_raw) if phone_raw else None

    linkedin_url: Optional[str] = None
    if linkedin_match:
        raw_li = linkedin_match.group(0).rstrip("/")
        if not raw_li.startswith("http"):
            linkedin_url = f"https://{raw_li}"
        else:
            linkedin_url = raw_li

    # Extract candidate name, address, and any headerless opening summary from Contact Information lines
    raw_contact_lines = section_lines.get("Contact Information", [])
    contact_lines: List[str] = []
    implicit_summary_lines: List[str] = []

    for idx_c, c_ln in enumerate(raw_contact_lines):
        if idx_c == 0:
            contact_lines.append(c_ln)
            continue
        has_contact_signal = bool(
            EMAIL_REGEX.search(c_ln)
            or PHONE_REGEX.search(c_ln)
            or LINKEDIN_REGEX.search(c_ln)
            or "|" in c_ln
            or len(c_ln) <= 55
        )
        if has_contact_signal and not implicit_summary_lines:
            contact_lines.append(c_ln)
        else:
            implicit_summary_lines.append(c_ln)

    full_name = "Candidate Name"
    if contact_lines:
        first_line = contact_lines[0].strip()
        full_name = first_line.split("|")[0].strip()

    name_tokens = full_name.split()
    first_name = name_tokens[0] if name_tokens else "Candidate"
    last_name = " ".join(name_tokens[1:]) if len(name_tokens) > 1 else ""

    # Parse City, State location
    address: Optional[ParsedAddress] = None
    street_regex = re.compile(
        r"\b\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln)\b",
        re.IGNORECASE,
    )
    city_state_regex = re.compile(
        r"\b([A-Z][a-zA-Z\s.]+),\s*([A-Z]{2}|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|"
        r"Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|"
        r"Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|"
        r"New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
        r"South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b"
    )
    for c_line in contact_lines:
        has_street = bool(street_regex.search(c_line))
        m_cs = city_state_regex.search(c_line)
        if m_cs:
            address = ParsedAddress(
                city=m_cs.group(1).strip(),
                region=m_cs.group(2).strip(),
                country="US",
                full_location_raw=c_line.strip(),
                has_street_address=has_street,
            )
            break

    # Parse Summary (explicit Professional Summary section or implicit opening summary block)
    summary_lines = section_lines.get("Professional Summary", []) or implicit_summary_lines
    summary = " ".join(summary_lines).strip() if summary_lines else None

    # Parse Work Experience
    employments = _parse_employments_from_lines(section_lines.get("Work Experience", []))
    headline = employments[0].title if employments else None

    # Parse Education
    educations = _parse_educations_from_lines(section_lines.get("Education", []))

    # Parse Skills
    skills_raw_list: List[str] = []
    for s_line in section_lines.get("Skills", []):
        if ":" in s_line:
            s_line = s_line.split(":", 1)[1]
        for token in re.split(r"[,;|•●◦]+", s_line):
            clean_tok = token.strip().lstrip("-* ").strip().rstrip(".")
            if clean_tok and clean_tok not in skills_raw_list:
                skills_raw_list.append(clean_tok)

    # Also detect taxonomy skills present in the resume text if Skills section was unmapped or sparse
    if len(skills_raw_list) < 3:
        text_lower = sanitized_text.lower()
        for key, (_, cname, _, _, _, _) in LIGHTCAST_ESCO_TAXONOMY.items():
            if len(key) <= 2 and key != "py":
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", text_lower):
                disp = cname.split("(")[0].strip() if "(" in cname and key != "seo" else cname
                if disp not in skills_raw_list:
                    skills_raw_list.append(disp)

    normalized_skills: List[NormalizedSkill] = []
    for sk in skills_raw_list:
        norm_sk = normalize_skill_token(sk)
        norm_sk.locations.append(KeywordLocation.SKILLS_SECTION)
        normalized_skills.append(norm_sk)

    # Check mandatory 5 sections presence
    has_contact = bool(email and phone_raw)
    has_experience = "Work Experience" in detected_headers and len(employments) > 0
    has_education = "Education" in detected_headers and len(educations) > 0
    has_skills = "Skills" in detected_headers and len(skills_raw_list) > 0
    has_dates = len(date_formats) > 0 and not mixed_dates

    mandatory_present = {
        "Contact Information": has_contact,
        "Work Experience": has_experience,
        "Education": has_education,
        "Skills": has_skills,
        "Employment Dates": has_dates,
    }

    return CanonicalResume(
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        headline=headline,
        email=email,
        phone=phone_us,
        phone_e164=phone_e164,
        linkedin_url=linkedin_url,
        address=address,
        country_full="United States",
        summary=summary,
        employments=employments,
        educations=educations,
        skills=skills_raw_list,
        normalized_skills=normalized_skills,
        certifications=section_lines.get("Certifications", []),
        projects=section_lines.get("Projects", []),
        mandatory_sections_present=mandatory_present,
        detected_section_headers=detected_headers,
        section_boundary_failures=boundary_failures,
        phantom_token_hazards=hazards,
        mixed_date_formats_detected=mixed_dates,
        detected_date_formats=date_formats,
        extraction_result=extraction_result,
    )
