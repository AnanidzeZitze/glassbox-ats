"""Tests for Structured Recommendations Engine & LaTeX Retest API."""

from fastapi.testclient import TestClient
from backend.main import app
from backend.models.schemas import (
    ATSPlatform,
    CanonicalResume,
    JDRequirementInput,
    ResumeAuditReport,
)
from backend.services.ats_score import audit_resume_content, compute_ats_score
from backend.services.schema_emulators import build_sarah_chen_canonical_fixture
from backend.services.recommendations import generate_structured_recommendations

client = TestClient(app)

SAMPLE_HAZARDOUS_TEX = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.25in]{geometry}
\usepackage{multicol}
\usepackage{fontawesome5}
\begin{document}
\author{Alex Rivera}
\faEnvelope\ alex.rivera@example.com \faPhone\ (555) 019-4242
\begin{multicols}{2}
\section{Experience}
\textbf{Senior Cloud Architect} | CloudOps Inc. \hfill 2021 -- Present
\begin{itemize}
    \item Responsible for managing AWS cloud infrastructure.
\end{itemize}
\section{Skills}
Python, Docker
\end{multicols}
\end{document}"""


def test_structured_recommendations_generation():
    resume = build_sarah_chen_canonical_fixture()
    audit = audit_resume_content(resume)
    jd = JDRequirementInput(
        target_title="Staff Infrastructure Engineer",
        must_have_skills=["Python", "Kubernetes", "Terraform", "Kafka"],
        preferred_skills=["Golang", "Prometheus"],
        required_years_experience=5,
    )

    recs_resp = generate_structured_recommendations(
        current_score=72.0,
        audit_report=audit,
        jd=jd,
        resume=resume,
        latex_source=SAMPLE_HAZARDOUS_TEX,
    )

    assert recs_resp.current_score == 72.0
    assert recs_resp.target_score_estimate > 72.0
    assert len(recs_resp.recommendations) > 0
    # Prompt contains system instructions
    assert "<SYSTEM_INSTRUCTION>" in recs_resp.structured_llm_prompt
    assert "<TARGET_JOB_DESCRIPTION>" in recs_resp.structured_llm_prompt


def test_api_recommendations_endpoint():
    resume = build_sarah_chen_canonical_fixture()
    audit = audit_resume_content(resume)
    jd = JDRequirementInput(
        target_title="Staff Infrastructure Engineer",
        must_have_skills=["Python", "Kubernetes", "AWS"],
        preferred_skills=["Docker"],
        required_years_experience=4,
    )

    payload = {
        "current_score": 75.0,
        "audit_report": audit.model_dump(),
        "jd": jd.model_dump(),
        "resume": resume.model_dump(),
        "latex_source": SAMPLE_HAZARDOUS_TEX,
    }

    resp = client.post("/api/v1/recommendations", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "structured_llm_prompt" in data
    assert "recommendations" in data


def test_api_retest_latex_endpoint():
    jd = JDRequirementInput(
        target_title="Senior Cloud Architect",
        must_have_skills=["Python", "Docker", "AWS"],
        preferred_skills=["Kubernetes"],
        required_years_experience=3,
    )

    payload = {
        "raw_latex": SAMPLE_HAZARDOUS_TEX,
        "jd": jd.model_dump(),
        "target_platform": "WORKDAY",
        "baseline_score": 65.0,
    }

    resp = client.post("/api/v1/retest-latex", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "retested_score" in data
    assert "audit_report" in data
    assert "hazards_detected" in data
    assert len(data["hazards_detected"]) > 0  # detected multicol, fontawesome, margin


def test_api_auto_optimize_latex_endpoint():
    resume = build_sarah_chen_canonical_fixture()
    audit = audit_resume_content(resume)
    jd = JDRequirementInput(
        target_title="Senior Cloud Architect",
        must_have_skills=["Python", "Docker", "Terraform"],
        preferred_skills=["AWS"],
        required_years_experience=3,
    )

    payload = {
        "raw_latex": SAMPLE_HAZARDOUS_TEX,
        "jd": jd.model_dump(),
        "target_platform": "WORKDAY",
        "current_score": 60.0,
        "audit_report": audit.model_dump(),
        "resume": resume.model_dump(),
    }

    resp = client.post("/api/v1/auto-optimize-latex", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["retested_score"] >= 60.0
    # Auto-optimizer should have stripped multicol, fontawesome, and margin hazards
    hazard_types = [h["hazard_type"] for h in data["hazards_detected"]]
    assert "MULTICOLUMN_PACKAGE" not in hazard_types
    assert "ICON_PACKAGE" not in hazard_types
