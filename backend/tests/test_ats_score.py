"""Unit tests for Module 4: Deterministic 5-Component Scoring & 30-Parameter Audit (backend/tests/test_ats_score.py).

Verifies:
- Section 5.4 Ground-Truth Unit Test Benchmark (Senior Python Developer: Workday = 82.0, Lever = 85.75)
- Platform Weight Matrix (WORKDAY, TALEO, ICIMS, LEVER, GREENHOUSE manual scorecard mode)
- Section 5.5 All 30 Content & Formatting Audit Checklist Parameters
"""

from __future__ import annotations

import pytest

from backend.models.schemas import (
    ATSPlatform,
    AuditStatus,
    CanonicalResume,
    ExtractionResult,
    JDRequirementInput,
    ParsedAddress,
    ParsedEducation,
    ParsedEmployment,
)
from backend.services.ats_score import audit_resume_content, compute_ats_score


def _build_senior_python_developer_benchmark_fixture() -> tuple[CanonicalResume, JDRequirementInput]:
    """Construct the exact Senior Python Developer benchmark inputs from Section 5.4."""
    jd = JDRequirementInput(
        target_title="Senior Python Developer",
        must_have_skills=[
            "Python",
            "Django",
            "PostgreSQL",
            "AWS",
            "Docker",
            "REST APIs",
            "Git",
            "CI/CD",
        ],
        preferred_skills=[
            "Kubernetes",
            "Celery",
            "Redis",
            "microservices architecture",
        ],
    )

    resume = CanonicalResume(
        full_name="Jordan Miller",
        first_name="Jordan",
        last_name="Miller",
        headline="Senior Software Engineer",
        email="jordan.miller@example.com",
        phone="(415) 555-0188",
        phone_e164="+14155550188",
        linkedin_url="https://linkedin.com/in/jordanmiller",
        address=ParsedAddress(city="Austin", region="TX", country="US"),
        summary=(
            "Senior Python Developer with 8 years of experience architecting backend services using Python, Django, and PostgreSQL. "
            "Proven track record scaling cloud infrastructure on AWS with Docker and CI/CD pipelines. "
            "Delivered high-throughput REST APIs for enterprise platforms."
        ),
        employments=[
            ParsedEmployment(
                title="Senior Software Engineer",
                company="CloudScale Systems",
                start_date_raw="Jan 2021",
                end_date_raw="Present",
                start_year=2021,
                start_month=1,
                is_current=True,
                bullets=[
                    "Architected Python and Django backend services with PostgreSQL handling 50,000 requests/sec",
                    "Automated container orchestration deployments on AWS using Docker, Git, and CI/CD pipelines, reducing release time by 40%",
                    "Built REST APIs serving 120 enterprise clients with 99.95% uptime",
                ],
            ),
            ParsedEmployment(
                title="Software Engineer",
                company="DataFlow Corp",
                start_date_raw="Jun 2018",
                end_date_raw="Dec 2020",
                start_year=2018,
                start_month=6,
                end_year=2020,
                end_month=12,
                is_current=False,
                bullets=[
                    "Developed REST APIs (Representational State Transfer Application Programming Interfaces) in Python and PostgreSQL",
                    "Reduced database query latency by 35% across 15 production tables",
                    "Managed Docker build pipelines and Git workflows for a team of 8 engineers",
                ],
            ),
        ],
        educations=[
            ParsedEducation(
                degree="B.S.",
                major="Computer Science",
                school="University of Texas at Austin",
                end_year=2018,
            )
        ],
        skills=[
            "Python",
            "Django",
            "PostgreSQL",
            "AWS",
            "Docker",
            "REST APIs",
            "Git",
            "CI/CD",
            "Search Engine Optimization (SEO)",
        ],
        mandatory_sections_present={
            "Contact Information": True,
            "Work Experience": True,
            "Education": True,
            "Skills": True,
            "Employment Dates": True,
        },
        detected_section_headers={
            "Professional Summary": "Professional Summary",
            "Work Experience": "Work Experience",
            "Education": "Education",
            "Skills": "Skills",
        },
        detected_date_formats=["MONTH_YYYY"],
        mixed_date_formats_detected=False,
        extraction_result=ExtractionResult(
            file_format="pdf",
            ocr_triggered=False,
            confidence_multiplier=1.0,
            detected_fonts=["Calibri", "Arial"],
            body_font_sizes_pt=[11.0],
            heading_font_sizes_pt=[14.0],
        ),
    )
    return resume, jd


def test_senior_python_developer_workday_ground_truth_benchmark():
    """Verify Section 5.4 Expected Workday Output:
    - Keyword Match: ((1.00 * 0.70) + (0.00 * 0.30)) * 50 = 35.0
    - Placement: 0.85 * 10 = 8.5
    - Sections: 1.00 * 20 = 20.0
    - Parse Success: 1.00 * 15 = 15.0
    - Relevance: 0.70 * 5 = 3.5
    - Total Workday Score: 82.0 / 100
    """
    resume, jd = _build_senior_python_developer_benchmark_fixture()
    score = compute_ats_score(
        resume=resume,
        jd=jd,
        platform=ATSPlatform.WORKDAY,
        override_placement_ratio=0.85,
        override_relevance_ratio=0.70,
        equal_skill_weights=True,
    )

    assert score.must_have_match_rate == pytest.approx(1.00)
    assert score.preferred_match_rate == pytest.approx(0.00)
    assert score.keyword_match_weighted == pytest.approx(35.0)
    assert score.placement_weighted == pytest.approx(8.5)
    assert score.sections_weighted == pytest.approx(20.0)
    assert score.parse_success_weighted == pytest.approx(15.0)
    assert score.relevance_weighted == pytest.approx(3.5)
    assert score.total_score == pytest.approx(82.0)


def test_senior_python_developer_lever_ground_truth_benchmark():
    """Verify Section 5.4 Expected Lever Output:
    - Keyword Match: ((1.00 * 0.70) + (0.125 * 0.30)) * 40 = 0.7375 * 40 = 29.5
    - Placement: 0.85 * 15 = 12.75
    - Sections: 1.00 * 15 = 15.0
    - Parse Success: 1.00 * 15 = 15.0
    - Relevance: 0.90 * 15 = 13.5 (semantic neighbor credit on title)
    - Total Lever Score: 29.5 + 12.75 + 15.0 + 15.0 + 13.5 = 85.75 / 100
    """
    resume, jd = _build_senior_python_developer_benchmark_fixture()
    score = compute_ats_score(
        resume=resume,
        jd=jd,
        platform=ATSPlatform.LEVER,
        override_placement_ratio=0.85,
        override_relevance_ratio=0.70,
        equal_skill_weights=True,
    )

    assert score.must_have_match_rate == pytest.approx(1.00)
    assert score.preferred_match_rate == pytest.approx(0.125)
    assert "Kubernetes" in score.semantic_neighbor_matches
    assert score.keyword_match_pct == pytest.approx(0.7375)
    assert score.keyword_match_weighted == pytest.approx(29.5)
    assert score.placement_weighted == pytest.approx(12.75)
    assert score.sections_weighted == pytest.approx(15.0)
    assert score.parse_success_weighted == pytest.approx(15.0)
    assert score.relevance_weighted == pytest.approx(13.5)
    assert score.total_score == pytest.approx(85.75)


def test_greenhouse_manual_scorecard_mode():
    resume, jd = _build_senior_python_developer_benchmark_fixture()
    score = compute_ats_score(resume=resume, jd=jd, platform=ATSPlatform.GREENHOUSE)
    assert score.manual_scorecard_mode is True
    assert score.total_score is None


def test_30_parameter_content_and_formatting_audit_checklist():
    """Verify all 30 parameters in `audit_resume_content()` pass on a compliant gold-standard resume."""
    resume, jd = _build_senior_python_developer_benchmark_fixture()
    # Adjust preferred skills so total JD skills = 10 and 8 are matched (80% match rate inside 75%-85% band)
    jd_80_band = JDRequirementInput(
        target_title="Senior Python Developer",
        must_have_skills=["Python", "Django", "PostgreSQL", "AWS", "Docker", "REST APIs", "Git", "CI/CD"],
        preferred_skills=["Kubernetes", "Celery"],
    )

    report = audit_resume_content(resume=resume, jd=jd_80_band)
    assert report.total_parameters == 30
    assert len(report.parameters) == 30
    failed_params = [p for p in report.parameters if p.status != AuditStatus.PASS]
    assert failed_params == [], f"Unexpected failed parameters: {failed_params}"
    assert report.passed_count == 30
    assert report.overall_audit_score == 100.0
