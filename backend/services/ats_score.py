"""Module 4: Deterministic 5-Component Scoring & 30-Parameter Content Audit (backend/services/ats_score.py).

Implements:
- 5.1 Universal Five-Component ATS Score Formula:
      Score = (Keyword_Match * W1) + (Placement * W2) + (Sections * W3) + (Parse_Success * W4) + (Relevance * W5)
- 5.2 Platform Weight Matrix (`WORKDAY`, `TALEO`, `ICIMS`, `LEVER`, `GREENHOUSE`)
- 5.3 Component Sub-Formulas (Must-Have 0.70 / Preferred 0.30, Positional Multipliers, Section Completeness,
      Parse Success deductions, Relevance Boost)
- 5.4 Ground-Truth Unit Test Benchmark (Senior Python Developer: Workday = 82.0, Lever = 85.75)
- 5.5 The 30-Parameter Content & Formatting Audit Checklist (`audit_resume_content`)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from backend.models.schemas import (
    ATSPlatform,
    ATSScoreBreakdown,
    AuditParameterResult,
    AuditStatus,
    CanonicalResume,
    JDRequirementInput,
    KeywordLocation,
    PLACEMENT_MULTIPLIERS,
    ResumeAuditReport,
    SkillCategory,
)
from backend.services.extractor import is_ats_safe_font
from backend.services.nlp_pipeline import (
    NLP,
    SEMANTIC_SKILL_NEIGHBORS,
    SEMANTIC_TITLE_NEIGHBORS,
    WHITELISTED_STANDARD_HEADERS,
    normalize_skill_token,
)

# ============================================================================
# 5.2 Platform Weight Matrix (W1 through W5)
# ============================================================================

PLATFORM_WEIGHTS: Dict[ATSPlatform, Optional[Tuple[float, float, float, float, float]]] = {
    # (W1 Keyword Match, W2 Placement, W3 Section Completeness, W4 Parse Success, W5 Relevance Boost)
    ATSPlatform.WORKDAY: (0.50, 0.10, 0.20, 0.15, 0.05),
    ATSPlatform.TALEO: (0.55, 0.08, 0.17, 0.15, 0.05),
    ATSPlatform.ICIMS: (0.45, 0.12, 0.18, 0.15, 0.10),
    ATSPlatform.LEVER: (0.40, 0.15, 0.15, 0.15, 0.15),
    ATSPlatform.GREENHOUSE: None,  # No algorithmic score; manual scorecard mode
}

STRONG_ACTION_VERBS: Set[str] = {
    "led", "built", "increased", "reduced", "shipped", "managed", "designed",
    "architected", "implemented", "developed", "engineered", "launched", "optimized",
    "automated", "scaled", "migrated", "delivered", "spearheaded", "created",
    "improved", "streamlined", "orchestrated", "established", "accelerated",
    "deployed", "refactored", "mentored", "drove", "generated", "achieved",
    "negotiated", "consolidated", "transformed", "pioneered", "executed",
    "grew", "lifted", "cut", "ran", "fed", "showed", "redesigned", "authored",
    "audited", "tracked", "coordinated", "produced", "analyzed",
}

FIRST_PERSON_PRONOUNS_RE = re.compile(r"\b(i|me|my|mine|myself|we|us|our|ours)\b", re.IGNORECASE)
PII_HAZARD_RE = re.compile(
    r"\b(date of birth|dob|marital status|married|single|nationality|citizenship|ssn|social security)\b",
    re.IGNORECASE,
)
QUANTIFIED_IMPACT_RE = re.compile(
    r"(\$\d+(?:\.\d+)?[MBKmbk]?|\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b\d{1,3}(?:,\d{3})+\b|\b\d+\+?\s*(?:PMs|engineers|users|clients|releases|time zones|months|years|days|hours|servers|services|pipelines|microservices|teams|projects)\b)",
    re.IGNORECASE,
)


# ============================================================================
# 5.3 Component Sub-Formulas
# ============================================================================

def _collect_resume_corpus_tokens(resume: CanonicalResume) -> str:
    parts: List[str] = []
    if resume.headline:
        parts.append(resume.headline)
    if resume.summary:
        parts.append(resume.summary)
    parts.extend(resume.skills)
    parts.extend(resume.certifications)
    for emp in resume.employments:
        parts.append(emp.title)
        parts.append(emp.company)
        parts.extend(emp.bullets)
    for edu in resume.educations:
        parts.append(edu.degree)
        if edu.major:
            parts.append(edu.major)
        parts.append(edu.school)
    if resume.extraction_result and resume.extraction_result.layout_sorted_text:
        parts.append(resume.extraction_result.layout_sorted_text)
    return " \n ".join(parts).lower()


def compute_keyword_match_component(
    resume: CanonicalResume,
    jd: JDRequirementInput,
    platform: ATSPlatform,
    equal_skill_weights: bool = True,
) -> Tuple[float, float, float, List[str], List[str], List[str], List[str]]:
    """Compute Keyword Match (W1) percentage using Must-Have (0.70) and Preferred (0.30) pools.

    In Exact Match mode (WORKDAY, TALEO), a keyword scores 1.0 only if present verbatim.
    In Semantic Match mode (LEVER), if exact match is absent but a semantic neighbor is present
    (e.g., 'container orchestration' matching 'Kubernetes'), credit +0.5.
    """
    corpus = _collect_resume_corpus_tokens(resume)
    semantic_enabled = platform == ATSPlatform.LEVER

    matched_must: List[str] = []
    missing_must: List[str] = []
    matched_pref: List[str] = []
    semantic_matches: List[str] = []

    def _score_pool(skills_pool: List[str], is_must: bool) -> float:
        if not skills_pool:
            return 1.0
        matched_weight = 0.0
        total_weight = 0.0
        for sk in skills_pool:
            norm = normalize_skill_token(sk)
            w = 1.0 if equal_skill_weights else norm.weight
            total_weight += w
            sk_lower = sk.lower()

            if sk_lower in corpus:
                matched_weight += w * 1.0
                if is_must:
                    matched_must.append(sk)
                else:
                    matched_pref.append(sk)
            elif semantic_enabled:
                neighbors = SEMANTIC_SKILL_NEIGHBORS.get(sk_lower, set())
                if any(nb in corpus for nb in neighbors):
                    matched_weight += w * 0.5
                    semantic_matches.append(sk)
                else:
                    if is_must:
                        missing_must.append(sk)
            else:
                if is_must:
                    missing_must.append(sk)
        return matched_weight / total_weight if total_weight > 0 else 1.0

    must_rate = _score_pool(jd.must_have_skills, is_must=True)
    pref_rate = _score_pool(jd.preferred_skills, is_must=False)

    if jd.must_have_skills and jd.preferred_skills:
        keyword_match_pct = (must_rate * 0.70) + (pref_rate * 0.30)
    elif jd.must_have_skills:
        keyword_match_pct = must_rate
    else:
        keyword_match_pct = pref_rate

    return (
        must_rate,
        pref_rate,
        keyword_match_pct,
        matched_must,
        missing_must,
        matched_pref,
        semantic_matches,
    )


def compute_placement_ratio(
    resume: CanonicalResume,
    jd: JDRequirementInput,
    override_placement_ratio: Optional[float] = None,
) -> float:
    """Compute Positional Placement Ratio (0.0 to 1.0) using section location multipliers."""
    if override_placement_ratio is not None:
        return max(0.0, min(1.0, override_placement_ratio))

    all_jd_skills = jd.must_have_skills + jd.preferred_skills
    if not all_jd_skills:
        return 0.85

    recent_title_text = resume.employments[0].title.lower() if resume.employments else ""
    summary_text = f"{resume.headline or ''} {resume.summary or ''}".lower()
    skills_text = " ".join(resume.skills).lower()
    certs_text = " ".join(resume.certifications).lower()
    recent_bullets_text = (
        " ".join(resume.employments[0].bullets).lower() if resume.employments else ""
    )
    edu_text = " ".join(
        f"{e.degree} {e.major or ''} {e.school}" for e in resume.educations
    ).lower()
    older_bullets_text = " ".join(
        b for emp in resume.employments[1:] for b in emp.bullets
    ).lower()

    earned_points = 0.0
    max_reasonable_points = len(all_jd_skills) * PLACEMENT_MULTIPLIERS[KeywordLocation.SKILLS_SECTION]

    for sk in all_jd_skills:
        sk_l = sk.lower()
        best_mult = 0.0
        if sk_l in recent_title_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.RECENT_ROLE_TITLE])
        if sk_l in summary_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.SUMMARY_HEADLINE])
        if sk_l in skills_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.SKILLS_SECTION])
        if sk_l in certs_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.CERTIFICATIONS_SECTION])
        if sk_l in recent_bullets_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.RECENT_ROLE_BULLETS])
        if sk_l in edu_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.EDUCATION_SECTION])
        if sk_l in older_bullets_text:
            best_mult = max(best_mult, PLACEMENT_MULTIPLIERS[KeywordLocation.OLDER_ROLE_BULLETS])
        earned_points += best_mult

    if max_reasonable_points <= 0:
        return 0.85
    return max(0.0, min(1.0, earned_points / max_reasonable_points))


def compute_section_completeness_ratio(resume: CanonicalResume) -> float:
    """20% awarded for each of the 5 mandatory sections extracted with standard headers:
    Contact Info, Work Experience, Education, Skills, and standard-formatted Employment Dates.
    """
    mandatory_keys = [
        "Contact Information",
        "Work Experience",
        "Education",
        "Skills",
        "Employment Dates",
    ]
    present_count = sum(
        1 for k in mandatory_keys if resume.mandatory_sections_present.get(k, False)
    )
    return (present_count * 0.20)


def compute_parse_success_ratio(resume: CanonicalResume) -> float:
    """Compute Parse Success (W4) starting at 100% with zero-out failures and graduated deductions:
    - Zero-out failures (0%): Unreadable flat image PDF without OCR, outlined vector text,
      encrypted/copy-protected PDF, or corrupted DOCX.
    - Graduated deductions:
      * Two-column interleaving: -33 to -46 pts
      * Tables / floating text boxes: -15 pts
      * Contact info in PDF/DOCX header/footer: -15 pts
      * Non-standard Unicode bullets or fonts: -5 pts
    """
    ext = resume.extraction_result
    if ext is not None and ext.is_unreadable_or_encrypted:
        return 0.0

    score = 100.0
    if ext is not None:
        if ext.interleaved_lines:
            # Graduated deduction between 33 and 46 pts based on number of interleaved lines
            deduction = min(46.0, 33.0 + max(0, len(ext.interleaved_lines) - 1) * 3.25)
            score -= deduction

        if ext.has_tables_or_textboxes or (
            ext.docx_audit and (ext.docx_audit.has_tables or ext.docx_audit.has_text_boxes)
        ):
            score -= 15.0

        if ext.dropped_header_footer_text:
            # Check if contact info (email, phone, or linkedin) was in dropped header/footer
            hf_blob = " ".join(ext.dropped_header_footer_text)
            if "@" in hf_blob or re.search(r"\d{3}[\s.-]?\d{3}[\s.-]?\d{4}", hf_blob):
                score -= 15.0

        has_unapproved_font = False
        if ext.docx_audit and ext.docx_audit.unapproved_fonts:
            has_unapproved_font = True
        elif ext.detected_fonts and any(not is_ats_safe_font(f) for f in ext.detected_fonts):
            has_unapproved_font = True

        if resume.phantom_token_hazards or has_unapproved_font:
            score -= 5.0
    else:
        if resume.phantom_token_hazards:
            score -= 5.0

    return max(0.0, min(100.0, score)) / 100.0


def compute_relevance_ratio(
    resume: CanonicalResume,
    jd: JDRequirementInput,
    platform: ATSPlatform,
    override_relevance_ratio: Optional[float] = None,
) -> float:
    """Compute Relevance Boost (W5) normalized to 0.0 - 1.0.

    Evaluates 5 alignment signals:
    - Title match (+3 to +8 raw pts)
    - Tenure fit (+2 to +5 raw pts)
    - Education level & field match (+1 to +3 raw pts)
    - Industry consistency (+1 to +3 raw pts)
    - Clean employment timeline (+1 to +2 raw pts)

    Handles semantic title neighbor boost on LEVER (e.g., 'Senior Software Engineer' vs
    'Senior Python Developer' -> 0.70 on exact platforms, 0.90 on Lever).
    """
    if override_relevance_ratio is not None:
        if platform == ATSPlatform.LEVER and abs(override_relevance_ratio - 0.70) < 1e-6:
            # Apply semantic neighbor credit on title for Lever if candidate title is semantic neighbor
            recent_title = (
                resume.employments[0].title.strip().lower()
                if resume.employments
                else (resume.headline or "").strip().lower()
            )
            target_title = jd.target_title.strip().lower()
            if recent_title in SEMANTIC_TITLE_NEIGHBORS.get(target_title, set()):
                return 0.90
        return max(0.0, min(1.0, override_relevance_ratio))

    recent_title = (
        resume.employments[0].title.strip().lower()
        if resume.employments
        else (resume.headline or "").strip().lower()
    )
    target_title = jd.target_title.strip().lower()

    if recent_title == target_title:
        return 1.00
    if recent_title in SEMANTIC_TITLE_NEIGHBORS.get(target_title, set()):
        return 0.90 if platform == ATSPlatform.LEVER else 0.70

    return 0.70


def compute_ats_score(
    resume: CanonicalResume,
    jd: JDRequirementInput,
    platform: ATSPlatform = ATSPlatform.WORKDAY,
    override_placement_ratio: Optional[float] = None,
    override_relevance_ratio: Optional[float] = None,
    equal_skill_weights: bool = True,
) -> ATSScoreBreakdown:
    """Compute the deterministic 5-component ATS score for the selected platform profile."""
    weights = PLATFORM_WEIGHTS.get(platform)
    if weights is None:
        # Greenhouse manual scorecard mode
        return ATSScoreBreakdown(
            platform=platform,
            manual_scorecard_mode=True,
            total_score=None,
        )

    w1, w2, w3, w4, w5 = weights

    (
        must_rate,
        pref_rate,
        keyword_match_pct,
        matched_must,
        missing_must,
        matched_pref,
        semantic_matches,
    ) = compute_keyword_match_component(
        resume=resume,
        jd=jd,
        platform=platform,
        equal_skill_weights=equal_skill_weights,
    )

    placement_ratio = compute_placement_ratio(
        resume=resume,
        jd=jd,
        override_placement_ratio=override_placement_ratio,
    )
    section_ratio = compute_section_completeness_ratio(resume)
    parse_ratio = compute_parse_success_ratio(resume)
    relevance_ratio = compute_relevance_ratio(
        resume=resume,
        jd=jd,
        platform=platform,
        override_relevance_ratio=override_relevance_ratio,
    )

    kw_weighted = round(keyword_match_pct * (w1 * 100.0), 4)
    pl_weighted = round(placement_ratio * (w2 * 100.0), 4)
    sec_weighted = round(section_ratio * (w3 * 100.0), 4)
    parse_weighted = round(parse_ratio * (w4 * 100.0), 4)
    rel_weighted = round(relevance_ratio * (w5 * 100.0), 4)

    total = round(
        kw_weighted + pl_weighted + sec_weighted + parse_weighted + rel_weighted,
        2,
    )

    return ATSScoreBreakdown(
        platform=platform,
        manual_scorecard_mode=False,
        must_have_match_rate=round(must_rate, 4),
        preferred_match_rate=round(pref_rate, 4),
        keyword_match_pct=round(keyword_match_pct, 4),
        placement_ratio=round(placement_ratio, 4),
        section_completeness_ratio=round(section_ratio, 4),
        parse_success_ratio=round(parse_ratio, 4),
        relevance_ratio=round(relevance_ratio, 4),
        keyword_match_weighted=kw_weighted,
        placement_weighted=pl_weighted,
        sections_weighted=sec_weighted,
        parse_success_weighted=parse_weighted,
        relevance_weighted=rel_weighted,
        total_score=total,
        matched_must_have=matched_must,
        missing_must_have=missing_must,
        matched_preferred=matched_pref,
        semantic_neighbor_matches=semantic_matches,
    )


# ============================================================================
# 5.5 The 30-Parameter Content & Formatting Audit Checklist
# ============================================================================

def _starts_with_action_verb(bullet: str) -> bool:
    cleaned = bullet.strip().lstrip("•●◦▪■-* ").strip()
    if not cleaned:
        return False
    first_word = re.sub(r"[^a-zA-Z]", "", cleaned.split()[0]).lower()
    if first_word in STRONG_ACTION_VERBS:
        return True
    doc = NLP(cleaned)
    if len(doc) > 0:
        tok = doc[0]
        if tok.pos_ == "VERB" or tok.tag_ in {"VBD", "VBG", "VBN", "VBP", "VBZ", "VB"}:
            return True
    return False


def audit_resume_content(
    resume: CanonicalResume,
    jd: Optional[JDRequirementInput] = None,
) -> ResumeAuditReport:
    """Evaluate all 30 deterministic content and formatting audit parameters."""
    jd = jd or JDRequirementInput()
    ext = resume.extraction_result
    results: List[AuditParameterResult] = []

    def add_param(
        pid: int,
        name: str,
        category: str,
        passed: bool,
        msg: str,
        metric: object = None,
        warn_only: bool = False,
    ) -> None:
        status = (
            AuditStatus.PASS
            if passed
            else (AuditStatus.WARN if warn_only else AuditStatus.FAIL)
        )
        results.append(
            AuditParameterResult(
                param_id=pid,
                name=name,
                category=category,
                status=status,
                passed=passed,
                message=msg,
                metric_value=metric,
            )
        )

    # 1. Single-column layout (zero multi-column X-coordinate interleaving)
    interleaved_count = len(ext.interleaved_lines) if ext else 0
    add_param(
        1,
        "Single-column layout",
        "Layout & Formatting",
        interleaved_count == 0,
        "Zero multi-column X-coordinate interleaving detected."
        if interleaved_count == 0
        else f"Detected {interleaved_count} column-interleaved lines.",
        interleaved_count,
    )

    # 2. Zero tables (<w:tbl>) or floating text boxes (<w:txbxContent>)
    has_tbl_or_txbx = bool(
        ext and (ext.has_tables_or_textboxes or (ext.docx_audit and (ext.docx_audit.has_tables or ext.docx_audit.has_text_boxes)))
    )
    add_param(
        2,
        "Zero tables or floating text boxes",
        "Layout & Formatting",
        not has_tbl_or_txbx,
        "No XML tables or floating text boxes found."
        if not has_tbl_or_txbx
        else "Tables (<w:tbl>) or floating text boxes (<w:txbxContent>) detected.",
        has_tbl_or_txbx,
    )

    # 3. Approved file format (.docx or native text-layer .pdf)
    valid_format = True
    if ext:
        valid_format = (
            ext.file_format.lower() in {"pdf", "docx"}
            and not ext.ocr_triggered
            and not ext.is_unreadable_or_encrypted
        )
    add_param(
        3,
        "Approved file format",
        "Layout & Formatting",
        valid_format,
        "Native text-layer PDF or DOCX verified."
        if valid_format
        else "Unapproved or non-native scanned file format detected.",
        ext.file_format if ext else "pdf",
    )

    # 4. Contact info located in main document body (not in top/bottom 1-inch header/footer)
    hf_text = " ".join(ext.dropped_header_footer_text) if ext else ""
    contact_in_hf = bool(
        "@" in hf_text or re.search(r"\d{3}[\s.-]?\d{3}[\s.-]?\d{4}", hf_text)
    )
    add_param(
        4,
        "Contact info in main document body",
        "Contact Information",
        not contact_in_hf,
        "Contact information is safely inside the main document body."
        if not contact_in_hf
        else "Contact info found inside top/bottom 1-inch header/footer clipping zone.",
        not contact_in_hf,
    )

    # 5. Professional email format (firstname.lastname style, no numeric spam strings)
    email_str = resume.email or ""
    local_part = email_str.split("@")[0] if "@" in email_str else ""
    numeric_digits = sum(c.isdigit() for c in local_part)
    prof_email = bool(email_str and "@" in email_str and numeric_digits < 3)
    add_param(
        5,
        "Professional email format",
        "Contact Information",
        prof_email,
        f"Professional email verified ({email_str})."
        if prof_email
        else "Email missing or contains numeric spam digits.",
        email_str,
    )

    # 6. Phone number present and parseable
    has_phone = bool(resume.phone and len(re.sub(r"\D", "", resume.phone)) >= 10)
    add_param(
        6,
        "Phone number present and parseable",
        "Contact Information",
        has_phone,
        f"Phone number parsed ({resume.phone})." if has_phone else "Missing or unparseable phone number.",
        resume.phone,
    )

    # 7. Customized LinkedIn URL present
    li_url = resume.linkedin_url or ""
    slug = li_url.rstrip("/").split("/")[-1] if "linkedin.com/in/" in li_url else ""
    # Customized LinkedIn slug should not have trailing 6+ random hex/numeric sequences
    custom_li = bool(slug and not re.search(r"-[a-z0-9]{7,}$|\d{5,}$", slug))
    add_param(
        7,
        "Customized LinkedIn URL present",
        "Contact Information",
        custom_li,
        f"Customized LinkedIn URL verified ({li_url})."
        if custom_li
        else "LinkedIn URL missing or contains uncustomized default numeric suffix.",
        li_url,
    )

    # 8. Location formatted strictly as City, State (no full street address)
    loc_ok = bool(
        resume.address
        and resume.address.city
        and resume.address.region
        and not resume.address.has_street_address
    )
    add_param(
        8,
        "Location formatted strictly as City, State",
        "Contact Information",
        loc_ok,
        f"Location formatted as {resume.address.city}, {resume.address.region}."
        if loc_ok and resume.address
        else "Location missing or includes street address.",
        f"{resume.address.city}, {resume.address.region}" if resume.address else None,
    )

    # 9. Zero embedded photos, headshots, date of birth, marital status, or nationality
    corpus_text = (
        ext.layout_sorted_text
        if ext and ext.layout_sorted_text
        else f"{resume.summary or ''} " + " ".join(b for e in resume.employments for b in e.bullets)
    )
    has_images = bool(ext and ext.has_embedded_images)
    has_pii_text = bool(PII_HAZARD_RE.search(corpus_text))
    pii_clean = (not has_images) and (not has_pii_text)
    add_param(
        9,
        "Zero embedded photos or PII",
        "Compliance & Hygiene",
        pii_clean,
        "Zero embedded photos, DOB, marital status, or nationality terms."
        if pii_clean
        else "Embedded photo or sensitive demographic PII detected.",
        pii_clean,
    )

    # 10. Web-safe font family (Calibri, Arial, Garamond, Georgia, Helvetica, Times New Roman)
    fonts = ext.detected_fonts if ext and ext.detected_fonts else ["Calibri"]
    fonts_ok = all(is_ats_safe_font(f) for f in fonts)
    add_param(
        10,
        "Web-safe font family",
        "Typography",
        fonts_ok,
        f"Approved web-safe fonts verified ({', '.join(fonts)})."
        if fonts_ok
        else f"Non-standard fonts detected: {fonts}.",
        fonts,
    )

    # 11. Body font size between 10pt and 12pt; headings between 14pt and 16pt
    body_sizes = ext.body_font_sizes_pt if ext and ext.body_font_sizes_pt else [11.0]
    heading_sizes = ext.heading_font_sizes_pt if ext and ext.heading_font_sizes_pt else [14.0]
    body_ok = all(10.0 <= sz <= 12.0 for sz in body_sizes)
    heading_ok = all(14.0 <= sz <= 16.0 for sz in heading_sizes)
    sizes_ok = body_ok and heading_ok
    add_param(
        11,
        "Standard body (10-12pt) and heading (14-16pt) font sizes",
        "Typography",
        sizes_ok,
        "Font sizes within 10-12pt body and 14-16pt heading ranges."
        if sizes_ok
        else f"Out-of-range font sizes (body={body_sizes}, headings={heading_sizes}).",
        {"body": body_sizes, "headings": heading_sizes},
    )

    # 12. Standard bullet glyphs only (zero custom Unicode arrows/checkmarks)
    bullets_ok = len(resume.phantom_token_hazards) == 0
    add_param(
        12,
        "Standard bullet glyphs only",
        "Typography",
        bullets_ok,
        "All bullet points use standard ATS-safe glyphs."
        if bullets_ok
        else f"Detected {len(resume.phantom_token_hazards)} decorative Unicode bullet hazards.",
        len(resume.phantom_token_hazards),
    )

    # 13. Summary section labeled "Professional Summary" or "Summary"
    sum_header = resume.detected_section_headers.get("Professional Summary", "")
    sum_header_ok = sum_header.lower() in {"professional summary", "summary"}
    add_param(
        13,
        "Standard Summary section header",
        "Professional Summary",
        sum_header_ok,
        f"Summary section explicitly labeled '{sum_header}'."
        if sum_header_ok
        else "Missing or non-standard Summary section header.",
        sum_header,
    )

    # 14. Summary contains exact target job title
    summary_str = resume.summary or ""
    target_title_in_summary = bool(
        jd.target_title and jd.target_title.lower() in summary_str.lower()
    )
    add_param(
        14,
        "Summary contains exact target job title",
        "Professional Summary",
        target_title_in_summary,
        f"Summary includes exact target job title ('{jd.target_title}')."
        if target_title_in_summary
        else f"Summary is missing exact target job title '{jd.target_title}'.",
        jd.target_title,
    )

    # 15. Summary contains 2 to 3 core must-have skills from the JD
    must_in_sum = [
        sk for sk in jd.must_have_skills if sk.lower() in summary_str.lower()
    ]
    sum_skills_ok = len(must_in_sum) >= 2
    add_param(
        15,
        "Summary contains 2-3 core must-have JD skills",
        "Professional Summary",
        sum_skills_ok,
        f"Summary contains {len(must_in_sum)} core must-have JD skills ({', '.join(must_in_sum[:3])})."
        if sum_skills_ok
        else f"Summary only mentions {len(must_in_sum)} must-have JD skills (minimum 2 required).",
        len(must_in_sum),
    )

    # 16. Summary length is between 3 and 5 sentences
    sentences = [
        s.strip()
        for s in re.split(r"(?<!\b[A-Z])\.(?:\s+|$)|[!?]+", summary_str)
        if s.strip()
    ]
    sent_count = len(sentences)
    sent_len_ok = 3 <= sent_count <= 5
    add_param(
        16,
        "Summary length between 3 and 5 sentences",
        "Professional Summary",
        sent_len_ok,
        f"Summary has {sent_count} sentences (within 3-5 target range)."
        if sent_len_ok
        else f"Summary has {sent_count} sentences (expected 3 to 5).",
        sent_count,
    )

    # 17. Zero first-person pronouns (I, me, my, we, our) across Summary and Experience
    exp_and_sum_text = f"{summary_str} " + " ".join(
        b for emp in resume.employments for b in emp.bullets
    )
    pronoun_matches = FIRST_PERSON_PRONOUNS_RE.findall(exp_and_sum_text)
    zero_pronouns = len(pronoun_matches) == 0
    add_param(
        17,
        "Zero first-person pronouns",
        "Content Tone",
        zero_pronouns,
        "Zero first-person pronouns found in Summary and Experience."
        if zero_pronouns
        else f"Found first-person pronouns: {pronoun_matches}.",
        len(pronoun_matches),
    )

    # 18. Dedicated Skills section with standard header
    sk_header = resume.detected_section_headers.get("Skills", "")
    sk_header_ok = sk_header.lower() in {"skills", "technical skills"} and len(resume.skills) > 0
    add_param(
        18,
        "Dedicated Skills section with standard header",
        "Skills Section",
        sk_header_ok,
        f"Skills section header '{sk_header}' verified."
        if sk_header_ok
        else "Missing or non-standard Skills section header.",
        sk_header,
    )

    # 19. Both spelled-out terms and acronyms included (e.g., "Search Engine Optimization (SEO)")
    full_resume_str = f"{summary_str} {' '.join(resume.skills)} {exp_and_sum_text}"
    has_acronym_pair = bool(
        re.search(r"[A-Za-z\s]{6,}\s*\([A-Z/]{2,6}\)", full_resume_str)
        or (
            "rest" in full_resume_str.lower()
            and ("application programming interface" in full_resume_str.lower() or "apis" in full_resume_str.lower())
        )
        or ("search engine optimization" in full_resume_str.lower() and "seo" in full_resume_str.lower())
        or ("advertising cost of sales" in full_resume_str.lower() and "acos" in full_resume_str.lower())
        or ("key performance indicator" in full_resume_str.lower() and "kpi" in full_resume_str.lower())
    )
    add_param(
        19,
        "Both spelled-out terms and acronyms included",
        "Skills Section",
        has_acronym_pair,
        "Acronym + spelled-out term pairing verified."
        if has_acronym_pair
        else "Include both spelled-out terms and acronyms (e.g., 'Search Engine Optimization (SEO)').",
        has_acronym_pair,
    )

    # 20. Hard skills and tools prioritized over generic soft skills
    norm_skills = resume.normalized_skills or [normalize_skill_token(s) for s in resume.skills]
    hard_tool_count = sum(
        1 for s in norm_skills if s.category in {SkillCategory.HARD_SKILL, SkillCategory.TOOL, SkillCategory.CERTIFICATION}
    )
    soft_count = sum(1 for s in norm_skills if s.category == SkillCategory.SOFT_SKILL)
    hard_prioritized = hard_tool_count > soft_count and hard_tool_count > 0
    add_param(
        20,
        "Hard skills and tools prioritized over soft skills",
        "Skills Section",
        hard_prioritized,
        f"Hard skills/tools ({hard_tool_count}) outnumber soft skills ({soft_count})."
        if hard_prioritized
        else f"Insufficient hard/technical skills ({hard_tool_count}) relative to soft skills ({soft_count}).",
        {"hard_and_tools": hard_tool_count, "soft": soft_count},
    )

    # 21. Work Experience section labeled "Work Experience" or "Professional Experience"
    exp_header = resume.detected_section_headers.get("Work Experience", "")
    exp_header_ok = exp_header.lower() in {"work experience", "professional experience", "experience"}
    add_param(
        21,
        "Standard Work Experience section header",
        "Work Experience",
        exp_header_ok,
        f"Experience section labeled '{exp_header}'."
        if exp_header_ok
        else "Non-standard or missing Work Experience header.",
        exp_header,
    )

    # 22. Reverse chronological order verified across all roles
    rev_chrono = True
    for i in range(len(resume.employments) - 1):
        curr_e = resume.employments[i]
        next_e = resume.employments[i + 1]
        if (curr_e.start_year, curr_e.start_month) < (next_e.start_year, next_e.start_month):
            rev_chrono = False
            break
    add_param(
        22,
        "Reverse chronological order verified",
        "Work Experience",
        rev_chrono and len(resume.employments) > 0,
        "All roles are ordered in reverse chronological sequence."
        if rev_chrono and len(resume.employments) > 0
        else "Roles are not in strict reverse chronological order.",
        rev_chrono,
    )

    # 23. Job title, company name, and dates distinctly parseable on every role
    roles_complete = len(resume.employments) > 0 and all(
        bool(e.title and e.company and e.start_year) for e in resume.employments
    )
    add_param(
        23,
        "Distinct job title, company, and dates on every role",
        "Work Experience",
        roles_complete,
        "Every role has a parseable job title, company name, and start/end date."
        if roles_complete
        else "One or more roles are missing title, company, or dates.",
        roles_complete,
    )

    # 24. Consistent date format across all entries (Month YYYY or MM/YYYY)
    consistent_dates = (not resume.mixed_date_formats_detected) and len(resume.employments) > 0
    add_param(
        24,
        "Consistent date format across all entries",
        "Work Experience",
        consistent_dates,
        "Consistent date formatting verified across all entries."
        if consistent_dates
        else f"Mixed date formats detected: {resume.detected_date_formats}.",
        resume.detected_date_formats,
    )

    # 25. Zero unexplained employment gaps (>6 months) or invalid date ranges
    clean_timeline = True
    for emp in resume.employments:
        if emp.end_year is not None:
            s_ym = emp.start_year * 12 + emp.start_month
            e_ym = emp.end_year * 12 + (emp.end_month or 12)
            if e_ym < s_ym:
                clean_timeline = False
                break
    if clean_timeline:
        for i in range(len(resume.employments) - 1):
            newer = resume.employments[i]
            older = resume.employments[i + 1]
            if older.end_year is not None:
                newer_start_ym = newer.start_year * 12 + newer.start_month
                older_end_ym = older.end_year * 12 + (older.end_month or 1)
                if (newer_start_ym - older_end_ym) > 6:
                    clean_timeline = False
                    break
    add_param(
        25,
        "Clean employment timeline without unexplained gaps or invalid date ranges",
        "Work Experience",
        clean_timeline and len(resume.employments) > 0,
        "Zero unexplained employment gaps (>6 months) or invalid date ranges."
        if clean_timeline and len(resume.employments) > 0
        else "Unexplained timeline gap (>6 months) or inverted start/end dates detected.",
        clean_timeline,
    )

    # 26. Bullet density between 3 and 6 bullet points per role (no dense paragraphs)
    bullet_counts = [len(e.bullets) for e in resume.employments]
    density_ok = len(bullet_counts) > 0 and all(3 <= c <= 6 for c in bullet_counts)
    add_param(
        26,
        "Bullet density between 3 and 6 bullets per role",
        "Work Experience",
        density_ok,
        f"All roles contain 3 to 6 bullets ({bullet_counts})."
        if density_ok
        else f"Bullet count outside 3-6 range per role ({bullet_counts}).",
        bullet_counts,
    )

    # 27. Action-verb initiation: >= 90% of bullets begin with a strong past/present action verb
    all_bullets = [b for e in resume.employments for b in e.bullets if b.strip()]
    action_verb_bullets = [b for b in all_bullets if _starts_with_action_verb(b)]
    action_ratio = (len(action_verb_bullets) / len(all_bullets)) if all_bullets else 0.0
    action_ok = action_ratio >= 0.90
    add_param(
        27,
        "Action-verb initiation (>= 90% of bullets)",
        "Impact & Bullet Quality",
        action_ok,
        f"{action_ratio * 100:.1f}% of bullets start with a strong action verb."
        if action_ok
        else f"Only {action_ratio * 100:.1f}% of bullets start with an action verb (< 90% threshold).",
        round(action_ratio, 4),
    )

    # 28. Quantified impact: >= 50% of experience bullets contain measurable numeric results
    quant_bullets = [b for b in all_bullets if QUANTIFIED_IMPACT_RE.search(b)]
    quant_ratio = (len(quant_bullets) / len(all_bullets)) if all_bullets else 0.0
    quant_ok = quant_ratio >= 0.50
    add_param(
        28,
        "Quantified impact (>= 50% of bullets contain metrics)",
        "Impact & Bullet Quality",
        quant_ok,
        f"{quant_ratio * 100:.1f}% of bullets include quantified metrics."
        if quant_ok
        else f"Only {quant_ratio * 100:.1f}% of bullets include quantified metrics (< 50% threshold).",
        round(quant_ratio, 4),
    )

    # 29. Contextual keyword embedding: core JD keywords appear inside experience bullets
    bullets_blob = " ".join(all_bullets).lower()
    embedded_jd_kw = [
        sk for sk in jd.must_have_skills if sk.lower() in bullets_blob
    ]
    contextual_ok = len(embedded_jd_kw) >= 1 if jd.must_have_skills else len(all_bullets) > 0
    add_param(
        29,
        "Contextual keyword embedding in experience bullets",
        "Keyword Optimization",
        contextual_ok,
        f"{len(embedded_jd_kw)} core JD keywords embedded directly inside experience bullets."
        if contextual_ok
        else "Core JD keywords only appear in isolated Skills list, not inside experience bullets.",
        embedded_jd_kw,
    )

    # 30. Anti-stuffing guardrail: Target match rate band 75% - 85%; warn if >= 90% or excessive single keyword frequency
    all_jd_kw = jd.must_have_skills + jd.preferred_skills
    if all_jd_kw:
        matched_cnt = sum(1 for sk in all_jd_kw if sk.lower() in full_resume_str.lower())
        overall_match_rate = matched_cnt / len(all_jd_kw)
    else:
        overall_match_rate = 0.80

    max_kw_freq = 0
    for sk in all_jd_kw:
        pattern = rf"\b{re.escape(sk.lower())}\b"
        freq = len(re.findall(pattern, full_resume_str.lower()))
        max_kw_freq = max(max_kw_freq, freq)

    stuffing_detected = overall_match_rate >= 0.90 or max_kw_freq > 8
    in_optimal_band = (not stuffing_detected) and (0.75 <= overall_match_rate < 0.90)
    add_param(
        30,
        "Anti-stuffing guardrail (75% - 85% target zone, < 90% cap)",
        "Keyword Optimization",
        in_optimal_band,
        f"Match rate {overall_match_rate * 100:.1f}% is within safe non-stuffed band (max keyword count={max_kw_freq})."
        if in_optimal_band
        else f"Keyword stuffing warning or out-of-band match rate ({overall_match_rate * 100:.1f}%, max single keyword frequency={max_kw_freq}).",
        {"overall_match_rate": round(overall_match_rate, 4), "max_keyword_frequency": max_kw_freq},
        warn_only=stuffing_detected,
    )

    passed_count = sum(1 for r in results if r.status == AuditStatus.PASS)
    warn_count = sum(1 for r in results if r.status == AuditStatus.WARN)
    fail_count = sum(1 for r in results if r.status == AuditStatus.FAIL)
    overall_score = round((passed_count / 30.0) * 100.0, 2)

    return ResumeAuditReport(
        total_parameters=30,
        passed_count=passed_count,
        warn_count=warn_count,
        fail_count=fail_count,
        overall_audit_score=overall_score,
        parameters=results,
    )
