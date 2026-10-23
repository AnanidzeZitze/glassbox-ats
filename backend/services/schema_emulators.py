"""Module 3: Stage 5 Platform JSON Schema Emulators (backend/services/schema_emulators.py).

Implements exact Stage 5 platform JSON schema adapters for:
- 4.1 Greenhouse (Sovren Engine Profile)
- 4.2 Workday (Enterprise ASCII Profile)
- 4.3 Lever (NLP Pattern & Tag-Truncated Profile)
"""

from __future__ import annotations

from typing import Dict, List

from backend.models.schemas import (
    CanonicalResume,
    GreenhouseAddress,
    GreenhouseEducation,
    GreenhouseEmployment,
    GreenhousePhone,
    GreenhouseResume,
    LeverContact,
    LeverPosition,
    LeverResume,
    LeverSchool,
    ParsedAddress,
    ParsedEducation,
    ParsedEmployment,
    WorkdayEducation,
    WorkdayExperience,
    WorkdayResume,
)
from backend.services.nlp_pipeline import (
    format_phone_e164,
    format_phone_us,
    normalize_skill_token,
)


def _collapse_workday_degree_level(degree_raw: str) -> str:
    """Collapse academic degrees into broad Workday degreeLevel tiers ('Master's', 'Bachelor's', 'Doctorate')."""
    d = degree_raw.upper().replace(".", "")
    if any(k in d for k in ("MBA", "MS", "MA", "MENG", "MASTER")):
        return "Master's"
    if any(k in d for k in ("BS", "BA", "BENG", "BACHELOR")):
        return "Bachelor's"
    if any(k in d for k in ("PHD", "MD", "JD", "DOCTOR")):
        return "Doctorate"
    return degree_raw


def emulate_greenhouse(resume: CanonicalResume) -> GreenhouseResume:
    """4.1 Greenhouse JSON Schema (Sovren Engine Profile).

    Behavioral Rules:
    - Splits candidate name into `first_name` and `last_name`.
    - Parses dates into integer `start_month` and `start_year` with boolean `is_current`.
    - Preserves experience bullets as a structured string array `description_bullets`.
    - Separates `degree` and `major` in education.
    - Retains both single-token technical skills and multi-word soft/analytical skills.
    """
    first_name = resume.first_name or (resume.full_name.split()[0] if resume.full_name else "")
    last_name = resume.last_name or (
        " ".join(resume.full_name.split()[1:]) if len(resume.full_name.split()) > 1 else ""
    )

    email_addresses = [resume.email] if resume.email else []
    phone_val = resume.phone_e164 or (format_phone_e164(resume.phone) if resume.phone else "")
    phone_numbers = [GreenhousePhone(value=phone_val, type="mobile")] if phone_val else []

    addresses: List[GreenhouseAddress] = []
    if resume.address:
        addresses.append(
            GreenhouseAddress(
                city=resume.address.city,
                region=resume.address.region,
                country=resume.address.country,
            )
        )

    employments: List[GreenhouseEmployment] = []
    for emp in resume.employments:
        employments.append(
            GreenhouseEmployment(
                title=emp.title,
                company_name=emp.company,
                start_month=emp.start_month,
                start_year=emp.start_year,
                end_month=None if emp.is_current else emp.end_month,
                end_year=None if emp.is_current else emp.end_year,
                is_current=emp.is_current,
                description_bullets=[b.rstrip(".") for b in emp.bullets],
            )
        )

    educations: List[GreenhouseEducation] = []
    for edu in resume.educations:
        educations.append(
            GreenhouseEducation(
                degree=edu.degree,
                major=edu.major,
                school=edu.school,
                end_year=edu.end_year,
            )
        )

    return GreenhouseResume(
        first_name=first_name,
        last_name=last_name,
        email_addresses=email_addresses,
        phone_numbers=phone_numbers,
        addresses=addresses,
        employments=employments,
        educations=educations,
        skills=list(resume.skills),
    )


def emulate_workday(resume: CanonicalResume) -> WorkdayResume:
    """4.2 Workday JSON Schema (Enterprise ASCII Profile).

    Behavioral Rules:
    - Enforces strict ISO-8601 date strings (`YYYY-MM-DD`).
    - Concatenates experience bullet points into a single space-separated paragraph `description`.
    - Collapses degrees into broad `degreeLevel` tiers (`"Master's"`, `"Bachelor's"`), dropping the `major` field.
    - Drops multi-word soft and analytical skill phrases (`"A/B testing"`, `"product analytics"`,
      `"stakeholder management"`, `"OKRs"`), retaining only single-token technical tools.
    """
    experiences: List[WorkdayExperience] = []
    for emp in resume.employments:
        start_iso = f"{emp.start_year:04d}-{emp.start_month:02d}-01"
        end_iso = (
            None
            if emp.is_current or not emp.end_year
            else f"{emp.end_year:04d}-{(emp.end_month or 1):02d}-01"
        )
        # Ensure each bullet ends with a period before joining with a space
        formatted_bullets = [
            b.strip() if b.strip().endswith(".") else f"{b.strip()}."
            for b in emp.bullets
            if b.strip()
        ]
        description_paragraph = " ".join(formatted_bullets)

        experiences.append(
            WorkdayExperience(
                jobTitle=emp.title,
                company=emp.company,
                startDate=start_iso,
                endDate=end_iso,
                currentlyWorkHere=emp.is_current,
                description=description_paragraph,
            )
        )

    educations: List[WorkdayEducation] = []
    for edu in resume.educations:
        educations.append(
            WorkdayEducation(
                degreeLevel=_collapse_workday_degree_level(edu.degree),
                schoolName=edu.school,
                graduationYear=edu.end_year,
            )
        )

    # Filter skills: retain only single-token technical tools/skills, dropping multi-word soft/analytical phrases & OKRs
    workday_skills: List[str] = []
    for sk in resume.skills:
        norm = normalize_skill_token(sk)
        if norm.is_single_token_technical:
            workday_skills.append(sk)

    return WorkdayResume(
        name=resume.full_name,
        email=resume.email or "",
        phone=format_phone_us(resume.phone or ""),
        country=resume.country_full or "United States",
        experience=experiences,
        education=educations,
        skills=workday_skills,
    )


def emulate_lever(resume: CanonicalResume, format_markdown_links: bool = False) -> LeverResume:
    """4.3 Lever JSON Schema (NLP Pattern & Tag-Truncated Profile).

    Behavioral Rules:
    - Extracts top-level `headline`.
    - Formats dates as `YYYY-MM` and stores `"Present"` as a literal string for active roles.
    - Compresses bullets into a newline-delimited (`\n`) string under `summary`.
    - Concatenates degree and major into a single `degree` string.
    - Truncates extracted skills under `tags` to the **first 4 tokens only** (`tags[:4]`),
      and drops secondary multi-column sidebars entirely.
    """
    links: List[str] = []
    if resume.linkedin_url:
        if format_markdown_links:
            links.append(f"[{resume.linkedin_url}]({resume.linkedin_url})")
        else:
            links.append(resume.linkedin_url)

    contact = LeverContact(
        email=resume.email or "",
        phone=format_phone_us(resume.phone or ""),
        links=links,
    )

    headline = resume.headline or (
        resume.employments[0].title if resume.employments else ""
    )

    positions: List[LeverPosition] = []
    for emp in resume.employments:
        start_ym = f"{emp.start_year:04d}-{emp.start_month:02d}"
        end_ym = (
            "Present"
            if emp.is_current or not emp.end_year
            else f"{emp.end_year:04d}-{(emp.end_month or 1):02d}"
        )
        clean_bullets = [b.rstrip(".") for b in emp.bullets if b.strip()]
        positions.append(
            LeverPosition(
                title=emp.title,
                org=emp.company,
                start=start_ym,
                end=end_ym,
                summary="\n".join(clean_bullets),
            )
        )

    schools: List[LeverSchool] = []
    for edu in resume.educations:
        combined_degree = f"{edu.degree} {edu.major}".strip() if edu.major else edu.degree
        schools.append(
            LeverSchool(
                name=edu.school,
                degree=combined_degree,
                end=str(edu.end_year),
            )
        )

    # Truncate tags to the first 4 tokens only (tags[:4])
    truncated_tags = list(resume.skills[:4])

    return LeverResume(
        name=resume.full_name,
        contact=contact,
        headline=headline,
        positions=positions,
        schools=schools,
        tags=truncated_tags,
    )


def build_sarah_chen_canonical_fixture() -> CanonicalResume:
    """Construct the Benchmark Candidate Sarah Chen CanonicalResume defined in Section 4."""
    return CanonicalResume(
        full_name="Sarah Chen",
        first_name="Sarah",
        last_name="Chen",
        headline="Senior Product Manager",
        email="sarah.chen@example.com",
        phone="(415) 555-0142",
        phone_e164="+14155550142",
        linkedin_url="https://linkedin.com/in/sarahchen",
        address=ParsedAddress(city="San Francisco", region="CA", country="US"),
        country_full="United States",
        employments=[
            ParsedEmployment(
                title="Senior Product Manager",
                company="Zendex Inc.",
                start_date_raw="Mar 2022",
                end_date_raw="Present",
                start_year=2022,
                start_month=3,
                end_year=None,
                end_month=None,
                is_current=True,
                bullets=[
                    "Led roadmap for enterprise analytics suite, $8M ARR in year one",
                    "Managed team of 4 PMs and 18 engineers across 3 time zones",
                    "Shipped 14 major releases with 99.2% on-time delivery",
                ],
            )
        ],
        educations=[
            ParsedEducation(
                degree="M.B.A.",
                major=None,
                school="Stanford Graduate School of Business",
                end_year=2019,
            ),
            ParsedEducation(
                degree="B.S.",
                major="Computer Science",
                school="UC Berkeley",
                end_year=2015,
            ),
        ],
        skills=[
            "SQL",
            "Python",
            "Tableau",
            "Jira",
            "Confluence",
            "Figma",
            "A/B testing",
            "product analytics",
            "stakeholder management",
            "OKRs",
        ],
        mandatory_sections_present={
            "Contact Information": True,
            "Work Experience": True,
            "Education": True,
            "Skills": True,
            "Employment Dates": True,
        },
    )
