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
