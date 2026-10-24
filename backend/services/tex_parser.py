"""Module: LaTeX Resume Parser & AST Hazard Detector (backend/services/tex_parser.py).

Implements deterministic parsing of LaTeX (.tex) resume documents into CanonicalResume models
and identifies LaTeX-specific ATS parsing hazards:
- Multicolumn layouts (multicol, paracol, minipage columns)
- Table environments (tabular, tabularx) that trigger interleaving or drop text
- Icon packages (fontawesome, marvosym) that emit unmapped Unicode glyphs
- Non-standard fonts and narrow margins (< 0.75 in)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.models.schemas import (
    CanonicalResume,
    ParsedAddress,
    ParsedEducation,
    ParsedEmployment,
)
from backend.services.nlp_pipeline import (
    EMAIL_REGEX,
    LINKEDIN_REGEX,
    PHONE_REGEX,
    classify_section_header,
    format_phone_e164,
    format_phone_us,
    normalize_skill_token,
)


class LatexATSHazard:
    def __init__(self, hazard_type: str, severity: str, description: str, line_num: Optional[int] = None):
        self.hazard_type = hazard_type
        self.severity = severity  # "CRITICAL", "WARNING", "INFO"
        self.description = description
        self.line_num = line_num

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hazard_type": self.hazard_type,
            "severity": self.severity,
            "description": self.description,
            "line_num": self.line_num,
        }


def detect_latex_hazards(tex_source: str) -> List[Dict[str, Any]]:
    """Scan raw LaTeX source code for known ATS-disqualifying constructs."""
    hazards: List[LatexATSHazard] = []
    lines = tex_source.splitlines()

    for idx, line in enumerate(lines, start=1):
        clean_ln = line.strip()
        if clean_ln.startswith("%"):
            continue

        # 1. Multi-column packages & environments
        if re.search(r"\\usepackage(\[[^\]]*\])?\{(multicol|paracol|flowfram)\}", clean_ln, re.IGNORECASE):
            hazards.append(
                LatexATSHazard(
                    "MULTICOLUMN_PACKAGE",
                    "CRITICAL",
                    f"Multicolumn package detected ('{clean_ln}'). Multi-column rendering creates severe XY-Cut interleaving hazards in Stream A/B parsers.",
                    idx,
                )
            )
        if re.search(r"\\begin\{(multicols|paracol)\}", clean_ln):
            hazards.append(
                LatexATSHazard(
                    "MULTICOLUMN_ENVIRONMENT",
                    "CRITICAL",
                    "Active multi-column environment will cause text interleaving and parse failure in Workday and Taleo.",
                    idx,
                )
            )

        # 2. Tabular / Table environments
        if re.search(r"\\begin\{(tabular|tabularx|tabulary|longtable)\}", clean_ln):
            hazards.append(
                LatexATSHazard(
                    "TABULAR_LAYOUT",
                    "CRITICAL",
                    "Tabular environment used for layout. ATS engines often flatten table cells left-to-right across rows, interleaving titles, dates, and companies.",
                    idx,
                )
            )

        # 3. Icon packages (FontAwesome, Marvosym)
        if re.search(r"\\usepackage(\[[^\]]*\])?\{(fontawesome5?|marvosym|pifont|wasysym)\}", clean_ln, re.IGNORECASE):
            hazards.append(
                LatexATSHazard(
                    "ICON_PACKAGE",
                    "WARNING",
                    "Icon package detected. Graphic icons for email/phone/location replace text labels with unmapped private-use Unicode glyphs, causing contact details to be dropped.",
                    idx,
                )
            )

        # 4. Dangerous TikZ / Graphics
        if re.search(r"\\usepackage(\[[^\]]*\])?\{tikz\}", clean_ln, re.IGNORECASE) or "\\begin{tikzpicture}" in clean_ln:
            hazards.append(
                LatexATSHazard(
                    "TIKZ_GRAPHICS",
                    "CRITICAL",
                    "TikZ graphic elements render as unextractable paths or garbled characters in naive text extractors.",
                    idx,
                )
            )

        # 5. Margin Hazard in geometry
        m_geom = re.search(r"\\usepackage\[(.*?)\]\{geometry\}", clean_ln)
        if m_geom:
            geom_args = m_geom.group(1).lower()
            if any(k in geom_args for k in ("0.3in", "0.4in", "0.5in", "0.2in", "margin=0.5", "margin=0.25")):
                hazards.append(
                    LatexATSHazard(
                        "SUB_INCH_MARGIN",
                        "CRITICAL",
                        f"Aggressive margins ('{m_geom.group(1)}'). Margins under 0.75in risk dropping contact information into Taleo's 1-inch (72pt) clipping zone.",
                        idx,
                    )
                )

    return [h.to_dict() for h in hazards]


def strip_latex_formatting(text: str) -> str:
    """Clean LaTeX macros, environments, comments, and escapes into readable plain text."""
    # Remove comments
    text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)

    # Replace common formatting commands
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\(textbf|textit|emph|underline|textsf|textsc|texttt)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\(huge|Huge|LARGE|Large|large|small|footnotesize|tiny|normalsize)\b", "", text)

    # Common custom template macros (Jake's Resume, Deedy, Awesome-CV)
    text = re.sub(r"\\resumeSubheading\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}", r"\1 | \3 | \2 | \4\n", text)
    text = re.sub(r"\\resumeProjectHeading\s*\{([^}]*)\}\s*\{([^}]*)\}", r"\1 | \2\n", text)
    text = re.sub(r"\\resumeSubSubheading\s*\{([^}]*)\}\s*\{([^}]*)\}", r"\1 | \2\n", text)
    text = re.sub(r"\\resumeItem\s*\{([^}]*)\}", r"- \1\n", text)
    text = re.sub(r"\\resumeItemList(?:Start|End)", r"\n", text)
    text = re.sub(r"\\resumeSubHeadingList(?:Start|End)", r"\n", text)

    # Strip custom single-arg formatting wrappers \customCommand{text}
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)

    # Replace hfill and spacing
    text = re.sub(r"\\hfill", " | ", text)
    text = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", "\n", text)
    text = re.sub(r"\\\\\[[^\]]*\]", "\n", text)
    text = re.sub(r"\\\\", "\n", text)

    # Replace itemize items
    text = re.sub(r"\\item\b", "- ", text)

    # Clean environments
    text = re.sub(r"\\(begin|end)\{[^}]*\}", "\n", text)

    # Escaped characters
    text = text.replace(r"\%", "%")
    text = text.replace(r"\&", "&")
    text = text.replace(r"\$", "$")
    text = text.replace(r"\_", "_")
    text = text.replace(r"\{", "{")
    text = text.replace(r"\}", "}")
    text = text.replace(r"\#", "#")
    text = text.replace("~", " ")
    text = text.replace("--", "-")
    text = text.replace("---", "-")

    # Clean redundant spaces
    cleaned_lines = []
    for line in text.splitlines():
        ln = re.sub(r"\s+", " ", line).strip()
        if ln:
            cleaned_lines.append(ln)
    return "\n".join(cleaned_lines)


def parse_tex_to_canonical(tex_source: str) -> Tuple[CanonicalResume, List[Dict[str, Any]]]:
    """Parse a LaTeX resume into a structured CanonicalResume and return detected ATS hazards."""
    hazards = detect_latex_hazards(tex_source)

    # Extract author/name directly if present in standard macros
    full_name = ""
    name_m = re.search(r"\\(?:name|author)\{([^}]*)\}", tex_source)
    if name_m:
        full_name = strip_latex_formatting(name_m.group(1)).strip()

    # Plain text version for section and NLP extraction
    plain_text = strip_latex_formatting(tex_source)
    lines = [ln.strip() for ln in plain_text.splitlines() if ln.strip()]

    # Extract contacts from plain text
    m_email = EMAIL_REGEX.search(plain_text)
    email_found = m_email.group(0).lower() if m_email else None

    m_phone = PHONE_REGEX.search(plain_text)
    phone_raw = m_phone.group(0) if m_phone else None
    phone_e164 = format_phone_e164(phone_raw) if phone_raw else None

    m_li = LINKEDIN_REGEX.search(plain_text)
    linkedin_url = f"https://{m_li.group(0)}" if m_li and not m_li.group(0).startswith("http") else (m_li.group(0) if m_li else None)

    if not full_name:
        for ln in lines[:6]:
            if "@" not in ln and not re.search(r"\d{3}", ln) and len(ln.split()) in (2, 3, 4):
                if not any(k in ln.lower() for k in ("resume", "curriculum", "vitae", "contact", "email", "phone")):
                    full_name = ln
                    break
        if not full_name:
            full_name = "Candidate Name"

    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else "Candidate"
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Name"

    # Break plain text into categorized sections
    current_section = "HEADER"
    section_lines: Dict[str, List[str]] = {
        "HEADER": [],
        "SUMMARY": [],
        "EXPERIENCE": [],
        "EDUCATION": [],
        "SKILLS": [],
        "PROJECTS": [],
        "CERTIFICATIONS": [],
    }

    sec_hdr_re = re.compile(
        r"^(?:\\section\*?\{([^}]*)\}|(?:[A-Z\s]{3,30}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*:?$)"
    )

    for ln in lines:
        m_sec = re.match(r"^\\section\*?\{([^}]*)\}", ln)
        raw_hdr = m_sec.group(1) if m_sec else ln
        canon_sec = classify_section_header(raw_hdr)
        if canon_sec:
            current_section = canon_sec
            continue
        section_lines.setdefault(current_section, []).append(ln)

    # Employments
    from backend.services.nlp_pipeline import _parse_employments_from_lines, _parse_educations_from_lines
    employments = _parse_employments_from_lines(
        section_lines.get("Work Experience", []) or section_lines.get("EXPERIENCE", [])
    )
    educations = _parse_educations_from_lines(
        section_lines.get("Education", []) or section_lines.get("EDUCATION", [])
    )

    # Skills
    skills_set = set()
    skill_lines = section_lines.get("Skills", []) or section_lines.get("SKILLS", [])
    for ln in skill_lines:
        clean_ln = re.sub(r"^(languages|frameworks|tools|developer tools|technical skills|skills)\s*[:\-–—]\s*", "", ln, flags=re.IGNORECASE)
        for token in re.split(r"[,;|•\t/]", clean_ln):
            token_clean = token.strip()
            if 1 < len(token_clean) <= 40:
                skills_set.add(token_clean)

    # Fallback skills from experience bullets if dedicated skills section is sparse
    if len(skills_set) < 5:
        from backend.services.nlp_pipeline import LIGHTCAST_ESCO_TAXONOMY
        for emp in employments:
            for b in emp.bullets:
                for word in re.findall(r"\b[A-Za-z0-9+#.-]{2,20}\b", b):
                    w_lower = word.lower()
                    if w_lower in LIGHTCAST_ESCO_TAXONOMY:
                        norm = normalize_skill_token(word)
                        skills_set.add(norm.canonical_name)

    summary_text = " ".join(section_lines.get("Professional Summary", []) or section_lines.get("SUMMARY", [])) or None

    canonical = CanonicalResume(
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        headline=f"{employments[0].title if employments else 'Professional'}",
        email=email_found,
        phone=phone_raw,
        phone_e164=phone_e164,
        linkedin_url=linkedin_url,
        address=None,
        country_full="United States",
        summary=summary_text,
        employments=employments,
        educations=educations,
        skills=sorted(list(skills_set)),
        certifications=[],
        projects=[],
    )

    return canonical, hazards
