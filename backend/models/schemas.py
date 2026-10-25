"""Canonical, Platform Emulator, Scoring, Audit, RRF, and Tailoring Pydantic Schemas.

Strictly implements the data models defined in specs/SPECIFICATION.md.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Enums & Constants
# ============================================================================

class ATSPlatform(str, Enum):
    WORKDAY = "WORKDAY"
    TALEO = "TALEO"
    ICIMS = "ICIMS"
    LEVER = "LEVER"
    GREENHOUSE = "GREENHOUSE"


class SkillCategory(str, Enum):
    HARD_SKILL = "HARD_SKILL"        # Weight: 2.0x
    CERTIFICATION = "CERTIFICATION"  # Weight: 2.0x
    TOOL = "TOOL"                    # Weight: 1.5x
    SOFT_SKILL = "SOFT_SKILL"        # Weight: 0.5x


SKILL_CATEGORY_WEIGHTS: Dict[SkillCategory, float] = {
    SkillCategory.HARD_SKILL: 2.0,
    SkillCategory.CERTIFICATION: 2.0,
    SkillCategory.TOOL: 1.5,
    SkillCategory.SOFT_SKILL: 0.5,
}


class KeywordLocation(str, Enum):
    RECENT_ROLE_TITLE = "RECENT_ROLE_TITLE"          # 3.0x
    SUMMARY_HEADLINE = "SUMMARY_HEADLINE"            # 2.5x
    SKILLS_SECTION = "SKILLS_SECTION"                # 2.0x
    CERTIFICATIONS_SECTION = "CERTIFICATIONS_SECTION"# 2.0x
    RECENT_ROLE_BULLETS = "RECENT_ROLE_BULLETS"      # 1.5x
    EDUCATION_SECTION = "EDUCATION_SECTION"          # 1.0x
    OLDER_ROLE_BULLETS = "OLDER_ROLE_BULLETS"        # 0.7x


PLACEMENT_MULTIPLIERS: Dict[KeywordLocation, float] = {
    KeywordLocation.RECENT_ROLE_TITLE: 3.0,
    KeywordLocation.SUMMARY_HEADLINE: 2.5,
    KeywordLocation.SKILLS_SECTION: 2.0,
    KeywordLocation.CERTIFICATIONS_SECTION: 2.0,
    KeywordLocation.RECENT_ROLE_BULLETS: 1.5,
    KeywordLocation.EDUCATION_SECTION: 1.0,
    KeywordLocation.OLDER_ROLE_BULLETS: 0.7,
}


class AuditStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


# ============================================================================
# Module 1: Ingestion & Layout Models
# ============================================================================

class BoundingBoxBlock(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_no: int = 0
    page_no: int = 0
    font_name: Optional[str] = None
    font_size: Optional[float] = None


class InterleavedLineFlag(BaseModel):
    line_text: str
    left_block_text: str
    right_block_text: str
    horizontal_gap_pt: float
    page_no: int = 0


class DocxAuditReport(BaseModel):
    has_tables: bool = False
    table_count: int = 0
    has_text_boxes: bool = False
    text_box_count: int = 0
    header_footer_text: List[str] = Field(default_factory=list)
    unapproved_fonts: List[str] = Field(default_factory=list)
    approved_fonts: List[str] = Field(default_factory=list)
    body_font_sizes_pt: List[float] = Field(default_factory=list)
    heading_font_sizes_pt: List[float] = Field(default_factory=list)
    has_embedded_images: bool = False


class ExtractionResult(BaseModel):
    file_format: str = "pdf"
    ocr_triggered: bool = False
    ocr_enabled_by_profile: bool = True
    confidence_multiplier: float = 1.0
    is_unreadable_or_encrypted: bool = False
    linear_stream_text: str = ""
    layout_sorted_text: str = ""
    dropped_header_footer_text: List[str] = Field(default_factory=list)
    interleaved_lines: List[InterleavedLineFlag] = Field(default_factory=list)
    blocks: List[BoundingBoxBlock] = Field(default_factory=list)
    docx_audit: Optional[DocxAuditReport] = None
    detected_fonts: List[str] = Field(default_factory=list)
    body_font_sizes_pt: List[float] = Field(default_factory=list)
    heading_font_sizes_pt: List[float] = Field(default_factory=list)
    has_tables_or_textboxes: bool = False
    has_embedded_images: bool = False


# ============================================================================
# Module 2: NLP & Taxonomy Models
# ============================================================================

class PhantomTokenHazard(BaseModel):
    raw_glyph: str
    codepoint: str
    line_text: str
    normalized_replacement: str = "-"


class SectionBoundaryFailure(BaseModel):
    header_text: str
    inferred_target_section: str
    reason: str


class NormalizedSkill(BaseModel):
    raw_text: str
    canonical_id: str
    canonical_name: str
    category: SkillCategory
    weight: float
    hierarchy_category: str = "Technology"
    hierarchy_subcategory: str = "Software Development"
    locations: List[KeywordLocation] = Field(default_factory=list)
    is_single_token_technical: bool = True


class ParsedAddress(BaseModel):
    city: str
    region: str
    country: str = "US"
    full_location_raw: Optional[str] = None
    has_street_address: bool = False


class ParsedEmployment(BaseModel):
    title: str
    company: str
    start_date_raw: str = ""
    end_date_raw: Optional[str] = None
    start_year: int
    start_month: int = 1
    end_year: Optional[int] = None
    end_month: Optional[int] = None
    is_current: bool = False
    bullets: List[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    degree: str
    major: Optional[str] = None
    school: str
    end_year: int


class CanonicalResume(BaseModel):
    full_name: str
    first_name: str
    last_name: str
    headline: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_e164: Optional[str] = None
    linkedin_url: Optional[str] = None
    address: Optional[ParsedAddress] = None
    country_full: str = "United States"
    summary: Optional[str] = None
    employments: List[ParsedEmployment] = Field(default_factory=list)
    educations: List[ParsedEducation] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    normalized_skills: List[NormalizedSkill] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    mandatory_sections_present: Dict[str, bool] = Field(
        default_factory=lambda: {
            "Contact Information": False,
            "Work Experience": False,
            "Education": False,
            "Skills": False,
            "Employment Dates": False,
        }
    )
    detected_section_headers: Dict[str, str] = Field(default_factory=dict)
    section_boundary_failures: List[SectionBoundaryFailure] = Field(default_factory=list)
    phantom_token_hazards: List[PhantomTokenHazard] = Field(default_factory=list)
    mixed_date_formats_detected: bool = False
    detected_date_formats: List[str] = Field(default_factory=list)
    extraction_result: Optional[ExtractionResult] = None


# ============================================================================
# Module 3: Stage 5 Platform JSON Schema Emulators (Exact Spec Structure)
# ============================================================================

# --- 4.1 Greenhouse Schema ---
class GreenhousePhone(BaseModel):
    value: str
    type: str = "mobile"


class GreenhouseAddress(BaseModel):
    city: str
    region: str
    country: str = "US"


class GreenhouseEmployment(BaseModel):
    title: str
    company_name: str
    start_month: int
    start_year: int
    end_month: Optional[int] = None
    end_year: Optional[int] = None
    is_current: bool
    description_bullets: List[str]


class GreenhouseEducation(BaseModel):
    degree: str
    major: Optional[str] = None
    school: str
    end_year: int

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        # Omit major if None to match exact Greenhouse JSON spec in Section 4.1
        data = super().model_dump(**kwargs)
        if data.get("major") is None and "major" in data:
            del data["major"]
        return data


class GreenhouseResume(BaseModel):
    first_name: str
    last_name: str
    email_addresses: List[str]
    phone_numbers: List[GreenhousePhone]
    addresses: List[GreenhouseAddress]
    employments: List[GreenhouseEmployment]
    educations: List[GreenhouseEducation]
    skills: List[str]

    def to_spec_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["educations"] = [edu.model_dump() for edu in self.educations]
        return data


# --- 4.2 Workday Schema ---
class WorkdayExperience(BaseModel):
    jobTitle: str
    company: str
    startDate: str
    endDate: Optional[str] = None
    currentlyWorkHere: bool
    description: str


class WorkdayEducation(BaseModel):
    degreeLevel: str
    schoolName: str
    graduationYear: int


class WorkdayResume(BaseModel):
    name: str
    email: str
    phone: str
    country: str = "United States"
    experience: List[WorkdayExperience]
    education: List[WorkdayEducation]
    skills: List[str]


# --- 4.3 Lever Schema ---
class LeverContact(BaseModel):
    email: str
    phone: str
    links: List[str]


class LeverPosition(BaseModel):
    title: str
    org: str
    start: str
    end: str
    summary: str


class LeverSchool(BaseModel):
    name: str
    degree: str
    end: str


class LeverResume(BaseModel):
    name: str
    contact: LeverContact
    headline: str
    positions: List[LeverPosition]
    schools: List[LeverSchool]
    tags: List[str]


# ============================================================================
# Module 4: Deterministic 5-Component Scoring & 30-Parameter Audit Schemas
# ============================================================================

class JDRequirementInput(BaseModel):
    target_title: str = "Senior Python Developer"
    must_have_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    required_years_experience: Optional[int] = None
    required_degree_level: Optional[str] = None
    target_industry: Optional[str] = None


class ATSScoreBreakdown(BaseModel):
    platform: ATSPlatform
    manual_scorecard_mode: bool = False
    must_have_match_rate: float = 0.0
    preferred_match_rate: float = 0.0
    keyword_match_pct: float = 0.0
    placement_ratio: float = 0.0
    section_completeness_ratio: float = 0.0
    parse_success_ratio: float = 0.0
    relevance_ratio: float = 0.0
    keyword_match_weighted: float = 0.0
    placement_weighted: float = 0.0
    sections_weighted: float = 0.0
    parse_success_weighted: float = 0.0
    relevance_weighted: float = 0.0
    total_score: Optional[float] = None
    matched_must_have: List[str] = Field(default_factory=list)
    missing_must_have: List[str] = Field(default_factory=list)
    matched_preferred: List[str] = Field(default_factory=list)
    semantic_neighbor_matches: List[str] = Field(default_factory=list)


class AuditParameterResult(BaseModel):
    param_id: int
    name: str
    category: str
    status: AuditStatus
    passed: bool
    message: str
    metric_value: Optional[Any] = None


class ResumeAuditReport(BaseModel):
    total_parameters: int = 30
    passed_count: int
    warn_count: int
    fail_count: int
    overall_audit_score: float
    parameters: List[AuditParameterResult]


# ============================================================================
# Module 5: Hybrid RRF Search & NYC LL144 Bias Audit Schemas
# ============================================================================

class RRFCandidateInput(BaseModel):
    candidate_id: str
    candidate_name: str
    bm25_rank: Optional[int] = None
    ann_rank: Optional[int] = None


class RRFCandidateResult(BaseModel):
    candidate_id: str
    candidate_name: str
    bm25_rank: Optional[int] = None
    ann_rank: Optional[int] = None
    rrf_score: float
    final_rank: int


class ApplicantDemographicRecord(BaseModel):
    applicant_id: str
    score: float
    cohort_group: str  # e.g. race/ethnicity or sex group


class CohortBiasMetric(BaseModel):
    cohort_group: str
    total_applicants: int
    above_median_count: int
    scoring_rate: float
    impact_ratio: float
    adverse_impact_detected: bool


class NYCLocalLaw144AuditReport(BaseModel):
    median_score: float
    max_scoring_rate: float
    adverse_impact_detected: bool
    cohorts: List[CohortBiasMetric]


# ============================================================================
# Module 6: Constrained AI Tailoring & Zero-Hallucination Validator
# ============================================================================

DATE_YYYY_MM_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class TailoredEmploymentEntry(BaseModel):
    title: str
    company: str
    start_date: str
    end_date: str = "Present"
    bullets: List[str]


class ValidatedResume(BaseModel):
    """Enforces @model_validator(mode='after') for zero-hallucination tailoring."""

    candidate_name: str
    employments: List[TailoredEmploymentEntry]
    skills: List[str] = Field(default_factory=list)
    master_resume_json: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates_and_zero_hallucinations(self) -> "ValidatedResume":
        # 1. Normalize and validate all employment dates against ^\d{4}-\d{2}$ or "Present"
        # and verify start_date <= end_date
        for emp in self.employments:
            if not DATE_YYYY_MM_REGEX.match(emp.start_date):
                raise ValueError(
                    f"Invalid start_date '{emp.start_date}'. Must match YYYY-MM (e.g. '2022-03')."
                )
            if emp.end_date != "Present":
                if not DATE_YYYY_MM_REGEX.match(emp.end_date):
                    raise ValueError(
                        f"Invalid end_date '{emp.end_date}'. Must match YYYY-MM or 'Present'."
                    )
                if emp.start_date > emp.end_date:
                    raise ValueError(
                        f"Chronological violation: start_date ({emp.start_date}) > end_date ({emp.end_date})."
                    )

        # 2. Cross-check every skill, employer, and metric against master_resume_json
        if self.master_resume_json:
            allowed_companies = {
                str(c).strip().lower()
                for c in self.master_resume_json.get("companies", [])
            }
            for emp_obj in self.master_resume_json.get("employments", []):
                if isinstance(emp_obj, dict) and emp_obj.get("company"):
                    allowed_companies.add(str(emp_obj["company"]).strip().lower())

            allowed_skills = {
                str(s).strip().lower()
                for s in self.master_resume_json.get("skills", [])
            }
            master_text_corpus = str(self.master_resume_json).lower()

            # Check employers
            if allowed_companies:
                for emp in self.employments:
                    if emp.company.strip().lower() not in allowed_companies:
                        raise ValueError(
                            f"Hallucinated employer detected: '{emp.company}' is not in master_resume_json."
                        )

            # Check skills
            if allowed_skills:
                for skill in self.skills:
                    if skill.strip().lower() not in allowed_skills:
                        raise ValueError(
                            f"Hallucinated skill/tool detected: '{skill}' is not in master_resume_json."
                        )

            # Check numeric metrics in bullets against master resume metrics
            metric_pattern = re.compile(r"\$\d+(?:\.\d+)?[MBKmbk]?|\d+(?:\.\d+)?%|\b\d{2,}\b")
            allowed_metrics = set(metric_pattern.findall(master_text_corpus))
            for emp in self.employments:
                for bullet in emp.bullets:
                    bullet_metrics = metric_pattern.findall(bullet.lower())
                    for metric in bullet_metrics:
                        if metric not in allowed_metrics:
                            raise ValueError(
                                f"Hallucinated metric '{metric}' in bullet '{bullet}' is not present in master_resume_json."
                            )

        return self


# ============================================================================
# Module 7: Reverse-Engineering & LaTeX Remediation Schemas
# ============================================================================

class ParseTexRequest(BaseModel):
    raw_tex: str


class ParseTexResponse(BaseModel):
    canonical: CanonicalResume
    hazards: List[Dict[str, Any]]


class TailorBulletDiffItem(BaseModel):
    diff_id: str
    role_title: str
    company: str
    start_date: str = ""
    end_date: str = "Present"
    original_bullet: str
    tailored_bullet: str
    injected_keywords: List[str] = Field(default_factory=list)
    action_verb_verified: bool = True
    quantified_metric_preserved: str = ""
    hallucination_guard_passed: bool = True


class RemediateTexRequest(BaseModel):
    resume_tex: str
    master_profile_md: str
    raw_jd_text: str
    platform: ATSPlatform = "WORKDAY"


class RemediateTexResponse(BaseModel):
    baseline_score: float
    remediated_score: float
    target_platform: ATSPlatform
    updated_tex: str
    diffs: List[TailorBulletDiffItem]
    newly_added_skills: List[str]
    hazards_detected: List[Dict[str, Any]]
    evidence_trace: Dict[str, Any]
    updated_canonical: CanonicalResume


# ============================================================================
# Module 8: Structured Recommendations & LaTeX LLM Optimizer Schemas
# ============================================================================

class RecommendationItem(BaseModel):
    id: str
    category: str  # "CRITICAL_ATS_HAZARD" | "KEYWORD_MUST_HAVE" | "KEYWORD_PREFERRED" | "BULLET_QUANTIFICATION" | "FORMAT_STRUCTURE"
    title: str
    problem_statement: str
    actionable_instruction: str
    score_impact_estimate: str
    priority: str  # "CRITICAL" | "HIGH" | "MEDIUM"


class StructuredRecommendationsResponse(BaseModel):
    current_score: float
    target_score_estimate: float
    must_have_missing: List[str]
    preferred_missing: List[str]
    failed_audit_params: List[Dict[str, Any]]
    recommendations: List[RecommendationItem]
    structured_llm_prompt: str


class GetRecommendationsRequest(BaseModel):
    current_score: float
    audit_report: ResumeAuditReport
    jd: JDRequirementInput
    resume: CanonicalResume
    latex_source: Optional[str] = None


class RetestLatexRequest(BaseModel):
    raw_latex: str
    jd: JDRequirementInput
    target_platform: ATSPlatform = "WORKDAY"
    baseline_score: Optional[float] = None


class RetestLatexResponse(BaseModel):
    retested_score: float
    baseline_score: Optional[float] = None
    score_delta: float
    audit_report: ResumeAuditReport
    hazards_detected: List[Dict[str, Any]]
    canonical_resume: CanonicalResume
    summary_message: str


class AutoOptimizeLatexRequest(BaseModel):
    raw_latex: str
    jd: JDRequirementInput
    target_platform: ATSPlatform = "WORKDAY"
    current_score: float
    audit_report: ResumeAuditReport
    resume: CanonicalResume


