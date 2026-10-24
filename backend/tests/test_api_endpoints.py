"""End-to-End FastAPI Endpoint Integration Tests (backend/tests/test_api_endpoints.py).

Tests all production `/api/v1` endpoints, telemetry/security headers, upload validation
guardrails, PDF/DOCX round-trip re-ingestion, JD parsing, RRF search, LL144 bias auditing,
and Kanban application CRUD persistence.
"""

from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.schema_emulators import build_sarah_chen_canonical_fixture

client = TestClient(app)


def test_health_and_security_telemetry_headers() -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "engine": "glassbox-ats-clean-room"}
    assert "x-request-id" in resp.headers
    assert "x-process-time-ms" in resp.headers
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


def test_parse_xray_upload_guardrails() -> None:
    # 1. Reject empty file (400)
    resp_empty = client.post(
        "/api/v1/parse-xray",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp_empty.status_code == 400

    # 2. Reject unsupported file extension (415)
    resp_bad_ext = client.post(
        "/api/v1/parse-xray",
        files={"file": ("malicious.exe", b"MZ-binary-payload", "application/octet-stream")},
    )
    assert resp_bad_ext.status_code == 415


def test_export_pdf_and_docx_roundtrip_reingestion() -> None:
    fixture = build_sarah_chen_canonical_fixture()

    # 1. Export ATS-safe PDF
    pdf_resp = client.post("/api/v1/export-pdf", json=fixture.model_dump())
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    pdf_bytes = pdf_resp.content
    assert pdf_bytes.startswith(b"%PDF-")

    # 2. Re-ingest exported PDF into /api/v1/parse-xray and verify 0 dropped header lines & 0 interleaved lines
    xray_pdf = client.post(
        "/api/v1/parse-xray",
        files={"file": ("exported_sarah_chen.pdf", pdf_bytes, "application/pdf")},
    )
    assert xray_pdf.status_code == 200
    data_pdf = xray_pdf.json()
    assert data_pdf[" extraction" if " extraction" in data_pdf else "extraction"]["dropped_header_footer_text"] == []
    assert data_pdf["extraction"]["interleaved_lines"] == []
    assert "WORKDAY" in data_pdf["emulators"]
    assert "GREENHOUSE" in data_pdf["emulators"]
    assert "LEVER" in data_pdf["emulators"]

    # 3. Export ATS-safe DOCX
    docx_resp = client.post("/api/v1/export-docx", json=fixture.model_dump())
    assert docx_resp.status_code == 200
    docx_bytes = docx_resp.content
    assert len(docx_bytes) > 1000

    # 4. Re-ingest exported DOCX into /api/v1/parse-xray and verify zero XML tables or textboxes
    xray_docx = client.post(
        "/api/v1/parse-xray",
        files={
            "file": (
                "exported_sarah_chen.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert xray_docx.status_code == 200
    data_docx = xray_docx.json()
    assert data_docx["extraction"]["has_tables_or_textboxes"] is False


def test_parse_jd_and_compute_score_v1_endpoints() -> None:
    jd_resp = client.post(
        "/api/v1/parse-jd",
        json={
            "raw_jd_text": (
                "Job Title: Senior Python Developer\n"
                "Must Have: 5+ years of experience in Python, Django, PostgreSQL, AWS, Docker, REST APIs, Git, and SQL.\n"
                "Preferred Qualifications: Kubernetes, Celery, Redis, and CI/CD."
            )
        },
    )
    assert jd_resp.status_code == 200
    parsed_jd = jd_resp.json()
    assert parsed_jd["target_title"] == "Senior Python Developer"
    assert "Python" in parsed_jd["must_have_skills"]
    assert "Kubernetes" in parsed_jd["preferred_skills"]
    assert parsed_jd["required_years_experience"] == 5

    # Verify arbitrary non-engineering JD extraction (no default Python fallback)
    mkt_resp = client.post(
        "/api/v1/parse-jd",
        json={
            "raw_jd_text": (
                "Growth Marketing & Analytics Manager\n"
                "We are looking for a Growth Marketing & Analytics Manager with 4+ years of experience in "
                "HubSpot, Klaviyo, Google Analytics 4, SEO, and Financial Modeling.\n"
                "Nice to have: Looker, Shopify, and A/B testing."
            )
        },
    )
    assert mkt_resp.status_code == 200
    mkt_jd = mkt_resp.json()
    assert mkt_jd["target_title"] == "Growth Marketing & Analytics Manager"
    assert "HubSpot" in mkt_jd["must_have_skills"]
    assert "Klaviyo" in mkt_jd["must_have_skills"]
    assert "Python" not in mkt_jd["must_have_skills"]
    assert "Looker" in mkt_jd["preferred_skills"]
    assert mkt_jd["required_years_experience"] == 4

    fixture = build_sarah_chen_canonical_fixture()
    score_resp = client.post(
        "/api/v1/compute-score",
        json={
            "resume": fixture.model_dump(),
            "jd": parsed_jd,
            "platform": "WORKDAY",
        },
    )
    assert score_resp.status_code == 200
    score_data = score_resp.json()
    assert score_data["passed_all_knockouts"] is True
    assert score_data["score_breakdown"]["parse_success_ratio"] == 1.0
    assert score_data["audit_report"]["total_parameters"] == 30


def test_tailor_bullets_and_kanban_applications_crud() -> None:
    fixture = build_sarah_chen_canonical_fixture()
    tailor_resp = client.post(
        "/api/v1/tailor-bullets",
        json={
            "resume": fixture.model_dump(),
            "jd": {
                "target_title": "Senior Python Developer",
                "must_have_skills": ["Python", "PostgreSQL", "AWS"],
                "preferred_skills": ["Kubernetes"],
            },
        },
    )
    assert tailor_resp.status_code == 200
    t_data = tailor_resp.json()
    assert t_data["validator_passed"] is True
    assert len(t_data["diffs"]) > 0
    assert "\\usepackage[top=1.0in,bottom=1.0in" in t_data["latex_source"]

    # Test Kanban Applications CRUD
    create_resp = client.post(
        "/api/v1/applications",
        json={
            "id": "test-app-999",
            "company": "OpenAI",
            "role": "Senior Systems Engineer",
            "platform": "GREENHOUSE",
            "ats_score": 89.5,
            "jd_match_pct": 84.0,
            "stage": "APPLIED",
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["company"] == "OpenAI"

    patch_resp = client.patch(
        "/api/v1/applications/test-app-999",
        json={"stage": "INTERVIEW"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["stage"] == "INTERVIEW"

    del_resp = client.delete("/api/v1/applications/test-app-999")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_uploaded_real_pdf_resume_end_to_end_zero_presets() -> None:
    # 1. Parse custom JD
    jd_resp = client.post(
        "/api/v1/parse-jd",
        json={
            "raw_jd_text": (
                "Role: Product & Program Operations Manager\n"
                "Responsibilities:\n"
                "- Lead cross-functional product operations, KPI dashboards, and Jira/Confluence workflows.\n"
                "- Partner with stakeholders on SQL data analysis, Python automation, and roadmap execution.\n"
                "Preferred Qualifications:\n"
                "- Experience with Tableau, Agile, Scrum, and Lean Six Sigma."
            )
        },
    )
    assert jd_resp.status_code == 200
    jd_data = jd_resp.json()
    assert "Senior Python Developer" not in jd_data["target_title"]
    assert "Jira" in jd_data["must_have_skills"]
    assert "SQL" in jd_data["must_have_skills"]
    assert "Tableau" in jd_data["preferred_skills"]

    # 2. Upload real PDF resume (GBN_Resume_ATS_Optimized.pdf)
    with open("backend/data/GBN_Resume_ATS_Optimized.pdf", "rb") as f:
        xray_resp = client.post(
            "/api/v1/parse-xray",
            files={"file": ("GBN_Resume_ATS_Optimized.pdf", f.read(), "application/pdf")},
        )
    assert xray_resp.status_code == 200
    xray_data = xray_resp.json()
    canon = xray_data["canonical"]
    assert "Sarah Chen" not in canon["full_name"]
    assert canon["email"] != "sarah.chen@example.com"
    assert len(canon["employments"]) >= 3
    for emp in canon["employments"]:
        assert emp["company"] != "Zendex Inc."

    # 3. Compute ATS Score & 30-Point Audit for the uploaded resume and custom JD
    score_resp = client.post(
        "/api/v1/compute-score",
        json={
            "platform": "WORKDAY",
            "resume": canon,
            "extraction": xray_data["extraction"],
            "jd": jd_data,
        },
    )
    assert score_resp.status_code == 200
    score_data = score_resp.json()
    assert score_data["audit_report"]["total_parameters"] == 30
    for param in score_data["audit_report"]["parameters"]:
        assert "sarah.chen@example.com" not in param["message"]

    # 4. Tailor bullets for the uploaded resume and custom JD
    tailor_resp = client.post(
        "/api/v1/tailor-bullets",
        json={"resume": canon, "jd": jd_data},
    )
    assert tailor_resp.status_code == 200
    tailor_data = tailor_resp.json()
    assert len(tailor_data["diffs"]) > 0
    for diff in tailor_data["diffs"]:
        assert "Sarah Chen" not in tailor_data["latex_source"]
    assert "sarah.chen@example.com" not in tailor_data["latex_source"]


def test_tex_remediation_and_evidence_tracer_endpoints() -> None:
    # 1. Sample LaTeX resume with hazards (multicol, tabular, fontawesome)
    sample_tex = r"""
    \documentclass[10pt]{article}
    \usepackage{geometry}
    \usepackage{fontawesome5}
    \usepackage{multicol}
    \begin{document}
    \author{Alex Rivera}
    \section{Experience}
    \textbf{Senior Cloud Architect} | CloudOps Inc. \hfill 2021 -- Present
    \begin{itemize}
        \item Directed cloud migration on AWS infrastructure using Terraform and Docker.
    \end{itemize}
    \section{Education}
    \textbf{B.S. Computer Science} | MIT \hfill 2020
    \section{Skills}
    Python, AWS, Docker, Terraform
    \end{document}
    """

    # Test /api/v1/parse-tex
    tex_resp = client.post("/api/v1/parse-tex", json={"raw_tex": sample_tex})
    assert tex_resp.status_code == 200
    tex_data = tex_resp.json()
    assert tex_data["canonical"]["full_name"] == "Alex Rivera"
    assert "Python" in tex_data["canonical"]["skills"]
    assert any(h["hazard_type"] == "MULTICOLUMN_PACKAGE" for h in tex_data["hazards"])
    assert any(h["hazard_type"] == "ICON_PACKAGE" for h in tex_data["hazards"])

    # Test /api/v1/evidence-trace
    ev_resp = client.post("/api/v1/evidence-trace", json={"resume": tex_data["canonical"]})
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert "workday" in ev_data
    assert "greenhouse" in ev_data
    assert "lever" in ev_data
    assert "taleo" in ev_data
    assert "icims" in ev_data

    # Test /api/v1/remediate-tex-md
    sample_md = """# Alex Rivera - Master Background Profile
    ## Work History
    At CloudOps Inc., I led the migration of 40+ microservices to Kubernetes and orchestrated Kafka event streams.
    Additionally, I authored automated CI/CD deployment pipelines with GitHub Actions.
    """
    sample_jd = (
        "Job Title: Lead Cloud Infrastructure Engineer\n"
        "Must Have: AWS, Kubernetes, Terraform, Docker, Kafka\n"
        "Preferred: GitHub Actions"
    )

    rem_resp = client.post(
        "/api/v1/remediate-tex-md",
        json={
            "resume_tex": sample_tex,
            "master_profile_md": sample_md,
            "raw_jd_text": sample_jd,
            "platform": "WORKDAY",
        },
    )
    assert rem_resp.status_code == 200
    rem_data = rem_resp.json()
    assert rem_data["remediated_score"] >= rem_data["baseline_score"]
    assert "Kubernetes" in rem_data["newly_added_skills"] or "Kafka" in rem_data["newly_added_skills"]
    assert len(rem_data["diffs"]) > 0
    assert r"\documentclass[10pt,letterpaper]{article}" in rem_data["updated_tex"]
    assert "geometry" in rem_data["updated_tex"]


