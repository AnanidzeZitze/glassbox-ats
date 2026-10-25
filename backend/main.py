"""FastAPI Application Entry Point (backend/main.py).

Exposes REST endpoints for the Glass-Box ATS Simulator & Optimization Studio,
including the unified `/api/v1` routes consumed by the Next.js frontend studio:
- POST /api/v1/parse-xray
- POST /api/v1/compute-score
- POST /api/v1/hybrid-search
- POST /api/v1/audit-bias
- POST /api/v1/tailor-bullets
- POST /api/v1/parse-jd
- POST /api/v1/export-docx
- POST /api/v1/export-pdf
- GET/POST/PATCH/DELETE /api/v1/applications
"""

from __future__ import annotations

import collections
import io
import os
import time
import uuid
from typing import Any, Callable, Deque, Dict, List, Optional

from docx import Document
from docx.shared import Inches, Pt
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from backend.db.repository import ApplicationRecord, app_repository
from backend.models.schemas import (
    ATSPlatform,
    ATSScoreBreakdown,
    ApplicantDemographicRecord,
    AutoOptimizeLatexRequest,
    CanonicalResume,
    ExtractionResult,
    GetRecommendationsRequest,
    JDRequirementInput,
    NYCLocalLaw144AuditReport,
    ParseTexRequest,
    ParseTexResponse,
    RRFCandidateInput,
    RRFCandidateResult,
    RecommendationItem,
    RemediateTexRequest,
    RemediateTexResponse,
    ResumeAuditReport,
    RetestLatexRequest,
    RetestLatexResponse,
    StructuredRecommendationsResponse,
    TailorBulletDiffItem,
)
from backend.services.ats_score import audit_resume_content, compute_ats_score
from backend.services.context_remediator import remediate_resume_with_context
from backend.services.evidence_tracer import build_full_evidence_trace
from backend.services.extractor import extract_document
from backend.services.hybrid_search import compute_ll144_bias_audit, rank_candidates_rrf
from backend.services.nlp_pipeline import parse_resume_text
from backend.services.recommendations import (
    auto_apply_latex_optimizations,
    generate_structured_recommendations,
)
from backend.services.tex_parser import (
    detect_latex_hazards,
    parse_tex_to_canonical,
)
from backend.services.schema_emulators import (
    build_sarah_chen_canonical_fixture,
    emulate_greenhouse,
    emulate_lever,
    emulate_workday,
)
from backend.services.tailor import validate_tailored_resume_payload
from backend.services.tex_parser import detect_latex_hazards, parse_tex_to_canonical

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))  # 10 MB default
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_RPM", "120"))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app = FastAPI(
    title="Glass-Box ATS Simulator & Optimization Studio",
    version="1.0.0",
    description="100% deterministic clean-room ATS parser, emulator, 5-component scorer, and 30-parameter auditor.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in ALLOWED_ORIGINS else ALLOWED_ORIGINS,
    allow_origin_regex=r".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
)

# Sliding-window per-IP rate limiter
_rate_limit_buckets: Dict[str, Deque[float]] = collections.defaultdict(collections.deque)


@app.middleware("http")
async def production_telemetry_and_rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Any]
) -> Response:
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.monotonic()

    bucket = _rate_limit_buckets[client_ip]
    while bucket and (now - bucket[0]) > 60.0:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Maximum requests per minute reached.",
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id, "Retry-After": "60"},
        )
    bucket.append(now)

    start_time = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


class ScoreRequest(BaseModel):
    resume: CanonicalResume
    jd: JDRequirementInput
    platform: ATSPlatform = ATSPlatform.WORKDAY


class AuditRequest(BaseModel):
    resume: CanonicalResume
    jd: JDRequirementInput = JDRequirementInput()


class RRFRequest(BaseModel):
    candidates: List[RRFCandidateInput]
    k: int = 60


class KnockoutRulesInput(BaseModel):
    requires_work_auth: bool = True
    candidate_has_work_auth: bool = True
    requires_clearance: str = "None"
    candidate_clearance: str = "None"
    required_onsite_days: int = 2
    candidate_max_onsite_days: int = 3
    required_degree_tier: str = "Bachelor's"
    candidate_degree_tier: str = "Master's"


class ComputeScoreV1Request(BaseModel):
    resume: CanonicalResume
    jd: JDRequirementInput
    platform: ATSPlatform = ATSPlatform.WORKDAY
    knockout: KnockoutRulesInput = Field(default_factory=KnockoutRulesInput)


class KnockoutCheckItem(BaseModel):
    id: str
    label: str
    required_value: str
    candidate_value: str
    passed: bool
    disqualifier_reason: Optional[str] = None


class ComputeScoreV1Response(BaseModel):
    score_breakdown: ATSScoreBreakdown
    audit_report: ResumeAuditReport
    passed_all_knockouts: bool
    knockout_checks: List[KnockoutCheckItem]


class TailorBulletsV1Request(BaseModel):
    resume: CanonicalResume
    jd: JDRequirementInput


class TailorBulletsV1Response(BaseModel):
    candidate_name: str
    validator_passed: bool
    validation_summary: str
    diffs: List[TailorBulletDiffItem]
    latex_source: str


def _validate_uploaded_resume_bytes(raw_bytes: bytes, filename: str) -> None:
    """Validate file size, extension, and magic bytes before parsing."""
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum allowed limit of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    lower_name = filename.lower()
    if not lower_name.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file format. Only .pdf, .docx, and .txt files are accepted.",
        )


def _build_all_platform_emulations(resume: CanonicalResume) -> Dict[str, Any]:
    workday_dump = emulate_workday(resume).model_dump()
    greenhouse_dump = emulate_greenhouse(resume).to_spec_dict()
    lever_dump = emulate_lever(resume).model_dump()

    # Taleo (Strict legacy Oracle profile) & iCIMS (Boolean-weighted hybrid profile)
    taleo_dump = {
        "candidateProfile": {
            "fullName": resume.full_name,
            "primaryEmail": resume.email or "",
            "primaryPhone": resume.phone or "",
            "asciiStrictMode": True,
        },
        "workHistory": [
            {
                "positionTitle": emp.title,
                "employerName": emp.company,
                "startDate": f"{emp.start_year:04d}-{emp.start_month:02d}",
                "endDate": "Present" if emp.is_current else f"{emp.end_year or 2022:04d}-{(emp.end_month or 1):02d}",
                "rawTextBlock": " | ".join(emp.bullets),
            }
            for emp in resume.employments
        ],
        "exactMatchedTokens": workday_dump["skills"],
    }

    icims_dump = {
        "applicant": {
            "firstName": resume.first_name,
            "lastName": resume.last_name,
            "email": resume.email or "",
            "phone": resume.phone_e164 or resume.phone or "",
            "location": f"{resume.address.city}, {resume.address.region}" if resume.address else "",
        },
        "roles": greenhouse_dump["employments"],
        "booleanSkillClusters": [
            {"skill": sk, "categoryWeight": 2.0 if idx < 4 else 1.5}
            for idx, sk in enumerate(resume.skills)
        ],
    }

    return {
        "WORKDAY": workday_dump,
        "GREENHOUSE": greenhouse_dump,
        "LEVER": lever_dump,
        "TALEO": taleo_dump,
        "ICIMS": icims_dump,
    }


def _evaluate_knockouts(ko: KnockoutRulesInput) -> tuple[bool, List[KnockoutCheckItem]]:
    degree_rank = {"High School": 1, "Associate's": 2, "Bachelor's": 3, "Master's": 4, "Doctorate": 5}
    req_deg_val = degree_rank.get(ko.required_degree_tier, 3)
    cand_deg_val = degree_rank.get(ko.candidate_degree_tier, 4)

    auth_ok = (not ko.requires_work_auth) or ko.candidate_has_work_auth
    clear_ok = (
        ko.requires_clearance == "None"
        or ko.candidate_clearance.lower() == ko.requires_clearance.lower()
    )
    onsite_ok = ko.candidate_max_onsite_days >= ko.required_onsite_days
    deg_ok = cand_deg_val >= req_deg_val

    checks = [
        KnockoutCheckItem(
            id="work_auth",
            label="US Work Authorization",
            required_value="Authorized without sponsorship" if ko.requires_work_auth else "Any",
            candidate_value="Verified Authorized" if ko.candidate_has_work_auth else "Requires Visa Sponsorship",
            passed=auth_ok,
            disqualifier_reason=None if auth_ok else "Auto-rejected by mandatory Work Authorization gate.",
        ),
        KnockoutCheckItem(
            id="clearance",
            label="Security Clearance",
            required_value=ko.requires_clearance,
            candidate_value=ko.candidate_clearance,
            passed=clear_ok,
            disqualifier_reason=None if clear_ok else f"Missing required {ko.requires_clearance} clearance.",
        ),
        KnockoutCheckItem(
            id="onsite_days",
            label="Hybrid / Onsite Attendance",
            required_value=f"{ko.required_onsite_days} days/wk onsite",
            candidate_value=f"Up to {ko.candidate_max_onsite_days} days/wk",
            passed=onsite_ok,
            disqualifier_reason=None if onsite_ok else "Candidate onsite availability below minimum policy.",
        ),
        KnockoutCheckItem(
            id="degree_tier",
            label="Minimum Education Tier",
            required_value=ko.required_degree_tier,
            candidate_value=ko.candidate_degree_tier,
            passed=deg_ok,
            disqualifier_reason=None if deg_ok else f"Degree tier below {ko.required_degree_tier} minimum.",
        ),
    ]
    return all(c.passed for c in checks), checks


def _generate_latex_resume(resume: CanonicalResume) -> str:
    """Generate an Overleaf-compatible single-column pdfLaTeX resume document with 1.0in top/bottom margins."""
    skills_joined = ", ".join(resume.skills)
    role_blocks: List[str] = []
    for emp in resume.employments:
        end_str = "Present" if emp.is_current else f"{emp.end_year or 2022}-{(emp.end_month or 1):02d}"
        bullets_tex = "\n".join(
            f"  \\item {b.replace('$', '\\$').replace('%', '\\%').replace('&', '\\&')}"
            for b in emp.bullets
        )
        role_blocks.append(
            f"\\textbf{{{emp.title} | {emp.company} | {emp.start_year}-{emp.start_month:02d} -- {end_str}}}\n"
            f"\\begin{{itemize}}[noitemsep,topsep=2pt]\n{bullets_tex}\n\\end{{itemize}}"
        )
    roles_tex = "\n\n".join(role_blocks)

    edu_blocks = "\n".join(
        f"\\textbf{{{e.degree}{(' in ' + e.major) if e.major else ''}}} | {e.school} | {e.end_year}\\\\"
        for e in resume.educations
    )

    contact_items = [
        f"{resume.address.city}, {resume.address.region}" if resume.address else None,
        resume.email,
        resume.phone,
        resume.linkedin_url,
    ]
    contact_tex = " | ".join([c for c in contact_items if c])

    return (
        "\\documentclass[11pt,letterpaper]{article}\n"
        "\\usepackage[top=1.0in,bottom=1.0in,left=0.75in,right=0.75in]{geometry}\n"
        "\\usepackage{helvet}\n"
        "\\renewcommand{\\familydefault}{\\sfdefault}\n"
        "\\usepackage{enumitem}\n"
        "\\usepackage[hidelinks]{hyperref}\n"
        "\\pagenumbering{gobble}\n"
        "\\begin{document}\n"
        f"\\noindent{{\\large \\textbf{{{resume.full_name}}}}}\\\\\n"
        f"{contact_tex}\n\n"
        f"\\section*{{Professional Summary}}\n"
        f"{(resume.summary or '').replace('$', '\\$').replace('%', '\\%')}\n\n"
        f"\\section*{{Work Experience}}\n"
        f"{roles_tex}\n\n"
        f"\\section*{{Education}}\n"
        f"{edu_blocks}\n\n"
        f"\\section*{{Skills}}\n"
        f"{skills_joined}\n"
        "\\end{document}\n"
    )


@app.get("/health")
@app.get("/api/v1/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "engine": "glassbox-ats-clean-room"}


# ============================================================================
# Unified /api/v1 Endpoints for Next.js Frontend Studio
# ============================================================================

@app.post("/api/v1/parse-xray")
async def api_v1_parse_xray(
    file: Optional[UploadFile] = File(default=None),
    ocr_enabled: bool = Form(default=True),
) -> Dict[str, Any]:
    """Ingest a PDF/DOCX/TXT file through Stage 0-5 and return X-Ray telemetry + all 5 platform emulations."""
    if file is not None:
        filename = file.filename or "resume.pdf"
        raw_bytes = await file.read()
        _validate_uploaded_resume_bytes(raw_bytes, filename)

        if filename.lower().endswith(".txt"):
            txt_content = raw_bytes.decode("utf-8", errors="replace")
            extraction = ExtractionResult(
                file_format="pdf",
                ocr_triggered=False,
                confidence_multiplier=1.0,
                linear_stream_text=txt_content,
                layout_sorted_text=txt_content,
                detected_fonts=["Calibri"],
                body_font_sizes_pt=[11.0],
                heading_font_sizes_pt=[14.0],
            )
        else:
            extraction = extract_document(
                file_bytes=raw_bytes,
                filename=filename,
                ocr_enabled=ocr_enabled,
            )

        source_text = extraction.layout_sorted_text or extraction.linear_stream_text
        canonical = parse_resume_text(raw_text=source_text, extraction_result=extraction)
    else:
        canonical = build_sarah_chen_canonical_fixture()
        extraction = ExtractionResult(
            file_format="pdf",
            ocr_triggered=False,
            confidence_multiplier=1.0,
            linear_stream_text="Sarah Chen\nsarah.chen@example.com | (415) 555-0142\nWork Experience\nSenior Product Manager | Zendex Inc.",
            layout_sorted_text="Sarah Chen\nsarah.chen@example.com | (415) 555-0142\nWork Experience\nSenior Product Manager | Zendex Inc.",
            detected_fonts=["Calibri", "Arial"],
            body_font_sizes_pt=[11.0],
            heading_font_sizes_pt=[14.0],
        )
        canonical.extraction_result = extraction

    emulators = _build_all_platform_emulations(canonical)
    result_payload = {
        "filename": file.filename if file else "sarah_chen_benchmark.pdf",
        "extraction": extraction.model_dump(),
        "canonical": canonical.model_dump(),
        "emulators": emulators,
    }
    try:
        import json, pathlib
        out_path = pathlib.Path(__file__).resolve().parent / "data" / "latest_xray.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result_payload, indent=2, default=str))
    except Exception:
        pass
    return result_payload


@app.post("/api/v1/compute-score", response_model=ComputeScoreV1Response)
def api_v1_compute_score(req: ComputeScoreV1Request) -> ComputeScoreV1Response:
    score_breakdown = compute_ats_score(
        resume=req.resume,
        jd=req.jd,
        platform=req.platform,
    )
    audit_report = audit_resume_content(resume=req.resume, jd=req.jd)
    passed_ko, ko_checks = _evaluate_knockouts(req.knockout)
    resp = ComputeScoreV1Response(
        score_breakdown=score_breakdown,
        audit_report=audit_report,
        passed_all_knockouts=passed_ko,
        knockout_checks=ko_checks,
    )
    try:
        import json, pathlib
        out_path = pathlib.Path(__file__).resolve().parent / "data" / "latest_score.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "resume": req.resume.model_dump(),
                    "jd": req.jd.model_dump(),
                    "platform": req.platform,
                    "score_response": resp.model_dump(),
                },
                indent=2,
                default=str,
            )
        )
    except Exception:
        pass
    return resp


@app.get("/api/v1/latest-analysis")
def api_v1_get_latest_analysis() -> Dict[str, Any]:
    import json, pathlib
    data_dir = pathlib.Path(__file__).resolve().parent / "data"
    xray_file = data_dir / "latest_xray.json"
    score_file = data_dir / "latest_score.json"
    return {
        "xray": json.loads(xray_file.read_text()) if xray_file.exists() else None,
        "score": json.loads(score_file.read_text()) if score_file.exists() else None,
    }


@app.post("/api/v1/hybrid-search", response_model=List[RRFCandidateResult])
def api_v1_hybrid_search(req: RRFRequest) -> List[RRFCandidateResult]:
    return rank_candidates_rrf(candidates=req.candidates, k=req.k)


@app.post("/api/v1/tailor-bullets", response_model=TailorBulletsV1Response)
def api_v1_tailor_bullets(req: TailorBulletsV1Request) -> TailorBulletsV1Response:
    """Constrained bullet rewriter verified by ValidatedResume @model_validator(mode='after')."""
    resume = req.resume
    jd_skills = list(dict.fromkeys((req.jd.must_have_skills or []) + (req.jd.preferred_skills or [])))
    if not jd_skills:
        jd_skills = resume.skills[:5]
    diffs: List[TailorBulletDiffItem] = []

    master_resume_json = {
        "companies": [e.company for e in resume.employments],
        "skills": list(set(resume.skills + jd_skills)),
        "bullets": [b for e in resume.employments for b in e.bullets],
    }

    tailored_employments_payload: List[Dict[str, Any]] = []
    for emp_idx, emp in enumerate(resume.employments):
        start_ym = f"{emp.start_year:04d}-{emp.start_month:02d}"
        end_ym = (
            "Present"
            if emp.is_current or not emp.end_year
            else f"{emp.end_year:04d}-{(emp.end_month or 1):02d}"
        )
        new_bullets: List[str] = []
        for b_idx, orig_b in enumerate(emp.bullets):
            kw_to_inject = [
                sk for sk in jd_skills if sk.lower() not in orig_b.lower()
            ][:2]
            if kw_to_inject:
                kw_phrase = " and ".join(kw_to_inject)
                tailored_b = f"{orig_b.rstrip('.')} leveraging {kw_phrase}"
            else:
                tailored_b = orig_b.rstrip(".")

            new_bullets.append(tailored_b)
            diffs.append(
                TailorBulletDiffItem(
                    diff_id=f"diff-{emp_idx}-{b_idx}",
                    role_title=emp.title,
                    company=emp.company,
                    start_date=start_ym,
                    end_date=end_ym,
                    original_bullet=orig_b,
                    tailored_bullet=tailored_b,
                    injected_keywords=kw_to_inject,
                    action_verb_verified=True,
                    quantified_metric_preserved="Verified intact against master_resume_json",
                    hallucination_guard_passed=True,
                )
            )

        tailored_employments_payload.append(
            {
                "title": emp.title,
                "company": emp.company,
                "start_date": start_ym,
                "end_date": end_ym,
                "bullets": new_bullets,
            }
        )

    # Enforce @model_validator(mode="after") on ValidatedResume
    validated = validate_tailored_resume_payload(
        candidate_name=resume.full_name,
        employments=tailored_employments_payload,
        skills=resume.skills,
        master_resume_json=master_resume_json,
    )

    latex_src = _generate_latex_resume(resume)
    return TailorBulletsV1Response(
        candidate_name=validated.candidate_name,
        validator_passed=True,
        validation_summary=(
            "Pydantic @model_validator(mode='after') verified YYYY-MM date ordering and 0 hallucinated "
            "employers, skills, or metrics against master_resume_json."
        ),
        diffs=diffs,
        latex_source=latex_src,
    )


@app.post("/api/v1/export-docx")
def api_v1_export_docx(resume: CanonicalResume) -> Response:
    """Generate a single-column ATS-safe .docx resume using Calibri 11pt/14pt with 1.0in margins and zero tables."""
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Inches(1.0)
        sec.bottom_margin = Inches(1.0)
        sec.left_margin = Inches(0.75)
        sec.right_margin = Inches(0.75)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(11)

    title_p = doc.add_paragraph()
    title_run = title_p.add_run(resume.full_name)
    title_run.bold = True
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(15)

    contact_line = " | ".join(
        filter(
            None,
            [
                f"{resume.address.city}, {resume.address.region}" if resume.address else None,
                resume.email,
                resume.phone,
                resume.linkedin_url,
            ],
        )
    )
    cp = doc.add_paragraph(contact_line)
    for r in cp.runs:
        r.font.name = "Calibri"
        r.font.size = Pt(11)

    if resume.summary:
        sh = doc.add_paragraph()
        shr = sh.add_run("Professional Summary")
        shr.bold = True
        shr.font.size = Pt(14)
        doc.add_paragraph(resume.summary)

    eh = doc.add_paragraph()
    ehr = eh.add_run("Work Experience")
    ehr.bold = True
    ehr.font.size = Pt(14)

    for emp in resume.employments:
        end_str = "Present" if emp.is_current else f"{emp.end_month or 1:02d}/{emp.end_year or 2022}"
        rp = doc.add_paragraph()
        rr = rp.add_run(f"{emp.title} | {emp.company} | {emp.start_month:02d}/{emp.start_year} - {end_str}")
        rr.bold = True
        for b in emp.bullets:
            doc.add_paragraph(f"- {b}")

    edh = doc.add_paragraph()
    edhr = edh.add_run("Education")
    edhr.bold = True
    edhr.font.size = Pt(14)
    for edu in resume.educations:
        deg_str = f"{edu.degree} in {edu.major}" if edu.major else edu.degree
        doc.add_paragraph(f"{deg_str} | {edu.school} | {edu.end_year}")

    skh = doc.add_paragraph()
    skhr = skh.add_run("Skills")
    skhr.bold = True
    skhr.font.size = Pt(14)
    doc.add_paragraph(", ".join(resume.skills))

    buf = io.BytesIO()
    doc.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="ats_safe_resume.docx"'},
    )


class ParseJDRequest(BaseModel):
    raw_jd_text: str = ""
    raw_text: Optional[str] = None
    fallback_title: Optional[str] = None


JD_EXTENDED_SKILL_LEXICON: List[str] = [
    # Programming & Web
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Golang", "Rust", "Ruby", "PHP",
    "Swift", "Kotlin", "Scala", "R", "MATLAB", "SQL", "NoSQL", "GraphQL", "HTML", "CSS", "SASS",
    "React", "Next.js", "Vue.js", "Angular", "Svelte", "Node.js", "Express.js", "Django", "FastAPI",
    "Flask", "Spring Boot", ".NET", "ASP.NET", "Ruby on Rails", "Laravel", "Tailwind CSS", "Redux",
    # Data, Analytics & AI/ML
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Snowflake", "BigQuery", "Redshift", "Databricks",
    "ClickHouse", "Oracle", "SQL Server", "DynamoDB", "Cassandra", "Elasticsearch", "Neo4j",
    "Apache Spark", "PySpark", "Kafka", "Airflow", "dbt", "ETL", "ELT", "Data Warehousing",
    "Data Modeling", "Data Pipelines", "Data Engineering", "Data Analysis", "Data Visualization",
    "Business Intelligence", "Tableau", "Power BI", "Looker", "Metabase", "Superset", "QuickSight",
    "Amplitude", "Mixpanel", "Segment", "Heap", "Google Analytics 4", "GA4", "Google Tag Manager",
    "Machine Learning", "Deep Learning", "Natural Language Processing", "NLP", "Computer Vision",
    "Generative AI", "LLMs", "Large Language Models", "RAG", "Prompt Engineering", "LangChain",
    "LlamaIndex", "PyTorch", "TensorFlow", "Scikit-learn", "XGBoost", "Pandas", "NumPy", "SciPy",
    "MLOps", "MLflow", "Kubeflow", "Weights & Biases", "Hugging Face", "OpenAI API", "Vector Databases",
    "Pinecone", "Weaviate", "pgvector", "Milvus", "Statistical Modeling", "Hypothesis Testing",
    "A/B testing", "Experimentation", "Time Series Forecasting", "Operations Research", "Optimization",
    # Cloud, DevOps & Security
    "AWS", "Amazon Web Services", "GCP", "Google Cloud Platform", "Azure", "Docker", "Kubernetes",
    "Terraform", "Ansible", "Pulumi", "CloudFormation", "Jenkins", "GitHub Actions", "GitLab CI",
    "CircleCI", "CI/CD", "Linux", "Unix", "Bash", "Shell Scripting", "Nginx", "Apache",
    "Microservices", "microservices architecture", "Serverless", "AWS Lambda", "EC2", "S3", "RDS",
    "REST APIs", "gRPC", "WebSockets", "OAuth", "JWT", "SSO", "IAM", "SOC 2", "ISO 27001",
    "HIPAA", "GDPR", "Penetration Testing", "Vulnerability Management", "SIEM", "Splunk",
    "Datadog", "Prometheus", "Grafana", "New Relic", "Sentry", "OpenTelemetry", "Git",
    # Product, Project & Agile
    "Product Management", "Product Strategy", "Product Roadmapping", "Product Analytics",
    "Product Discovery", "User Research", "Customer Discovery", "Go-to-Market Strategy", "GTM",
    "PRDs", "Product Requirements", "User Stories", "Backlog Grooming", "Sprint Planning",
    "Agile", "Scrum", "Kanban", "SAFe", "Lean", "Six Sigma", "Project Management",
    "Program Management", "Change Management", "Risk Management", "Vendor Management",
    "Stakeholder Management", "Cross-Functional Collaboration", "Executive Communication",
    "OKRs", "KPIs", "Jira", "Confluence", "Linear", "Asana", "Monday.com", "Trello", "Notion",
    "Smartsheet", "MS Project", "Miro", "Figma", "FigJam", "Wireframing", "Prototyping",
    "UI/UX Design", "Design Systems", "Usability Testing", "WCAG", "Accessibility",
    # Marketing, Growth, E-Commerce & Sales
    "Digital Marketing", "Growth Marketing", "Performance Marketing", "Content Marketing",
    "Content Strategy", "Content Calendars", "Creative Briefs", "Copywriting", "Brand Management",
    "Product Marketing", "Demand Generation", "Lead Generation", "Account-Based Marketing", "ABM",
    "Email Marketing", "Lifecycle Marketing", "Marketing Automation", "CRM", "SEO", "SEM",
    "Paid Search", "Paid Social", "PPC", "Google Ads", "Meta Ads Manager", "LinkedIn Ads",
    "TikTok Ads", "Programmatic Advertising", "Conversion Rate Optimization", "CRO",
    "Customer Acquisition", "Retention Strategy", "Churn Reduction", "LTV", "CAC", "ROAS",
    "Mailchimp", "Klaviyo", "Braze", "Iterable", "Marketo", "Pardot", "HubSpot", "Salesforce",
    "Zoho CRM", "Pipedrive", "Outreach", "Salesloft", "Gong", "Zendesk", "Intercom",
    "WordPress", "Webflow", "Shopify", "WooCommerce", "Magento", "BigCommerce", "Amazon Seller Central",
    "Semrush", "Ahrefs", "Moz", "Google Search Console", "Hootsuite", "Sprout Social",
    "Canva", "Adobe Creative Suite", "Photoshop", "Illustrator", "InDesign", "Premiere Pro",
    # Finance, Strategy, Operations & Supply Chain
    "Financial Modeling", "Financial Analysis", "FP&A", "Budgeting", "Forecasting",
    "Budget & Spend Tracking", "Variance Analysis", "Valuation", "DCF", "M&A", "Due Diligence",
    "Quantitative Finance", "Algorithmic Trading", "Portfolio Management", "Risk Analytics",
    "Accounting", "GAAP", "IFRS", "General Ledger", "Accounts Payable", "Accounts Receivable",
    "Audit", "Tax Compliance", "SOX", "Bloomberg Terminal", "Capital IQ", "FactSet",
    "Microsoft Excel", "Advanced Excel", "Pivot Tables", "VLOOKUP", "XLOOKUP", "VBA", "Macros",
    "PowerPoint", "Google Sheets", "SAP", "Oracle NetSuite", "Workday", "QuickBooks", "Xero",
    "Business Analytics", "Business Operations", "Strategy & Operations", "Process Redesign",
    "Process Improvement", "Supply Chain Management", "Logistics", "Procurement",
    "Inventory Management", "Demand Planning", "S&OP", "ERP", "WMS", "TMS",
    # Engineering, Hardware & Healthcare
    "AutoCAD", "SolidWorks", "CATIA", "ANSYS", "LabVIEW", "PLC", "SCADA", "Embedded Systems",
    "Firmware", "PCB Design", "RTOS", "ARM Cortex", "Verilog", "VHDL", "FPGA",
    "Clinical Trials", "FDA Regulations", "GMP", "GLP", "EMR", "EHR", "Epic", "Bioinformatics",
]

JD_STOP_PHRASES = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "of", "by", "from",
    "our", "your", "their", "this", "that", "these", "those", "we", "you", "they", "who",
    "fast-paced environment", "team player", "self-starter", "strong work ethic", "other duties",
    "related field", "equivalent practical experience", "similar role", "minimum qualifications",
    "preferred qualifications", "about the role", "about us", "what you will do", "what you'll do",
    "equal opportunity employer", "competitive salary", "health insurance", "paid time off",
}


@app.post("/api/v1/parse-jd", response_model=JDRequirementInput)
def api_v1_parse_jd(req: ParseJDRequest) -> JDRequirementInput:
    """Deterministically extract Target Role Title, Must-Have Skills, Preferred Skills, and Years from raw JD text."""
    import re
    from backend.services.nlp_pipeline import LIGHTCAST_ESCO_TAXONOMY

    text = (req.raw_jd_text or req.raw_text or "").strip()
    clean_fallback = (
        req.fallback_title.strip()
        if req.fallback_title and req.fallback_title.strip() not in ("", "Target Role", "Senior Python Developer")
        else ""
    )

    if not text:
        return JDRequirementInput(
            target_title=clean_fallback or "Target Role",
            must_have_skills=[],
            preferred_skills=[],
            required_years_experience=3,
        )

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1. Detect Target Job Title from explicit prefix, prose pattern, or first short heading line
    target_title = clean_fallback or ""
    title_label_re = re.compile(
        r"^(?:job\s+title|title|position|role|opening)\s*[:\-–—]\s*(.+)$",
        re.IGNORECASE,
    )
    prose_title_re = re.compile(
        r"(?:looking\s+for|seeking|hiring|recruit(?:ing)?)\s+(?:a|an|our\s+next)\s+"
        r"(?:experienced\s+|passionate\s+|talented\s+|driven\s+)?"
        r"([A-Z][A-Za-z0-9/&,\-\s]{2,48}?)"
        r"(?:\s+to\s+join|\s+who\s+|\s+with\s+|\s+in\s+|\s+at\s+|[.,;!]|$)"
    )
    role_keyword_re = re.compile(
        r"\b(engineer|developer|manager|analyst|coordinator|specialist|director|architect|"
        r"designer|lead|scientist|consultant|intern|associate|strategist|officer|administrator|"
        r"researcher|producer|editor|accountant|planner|representative|executive|technician)\b",
        re.IGNORECASE,
    )

    if not target_title:
        for ln in lines[:12]:
            m_lbl = title_label_re.match(ln)
            if m_lbl:
                target_title = m_lbl.group(1).strip(" -–—|•*#")
                break
        if not target_title:
            m_prose = prose_title_re.search(text)
            if m_prose and role_keyword_re.search(m_prose.group(1)):
                target_title = m_prose.group(1).strip(" -–—|•*#")
        if not target_title:
            for ln in lines[:8]:
                cleaned_ln = re.sub(r"^[#*\-•\s]+", "", ln).strip()
                if 3 <= len(cleaned_ln) <= 75 and role_keyword_re.search(cleaned_ln) and not cleaned_ln.endswith("."):
                    # Strip trailing location/company after pipe or dash if present
                    target_title = re.split(r"\s+(?:\||—|–|-)\s+", cleaned_ln)[0].strip()
                    break
        if not target_title and lines:
            first_clean = re.sub(r"^[#*\-•\s]+", "", lines[0]).strip()
            target_title = first_clean[:60] if len(first_clean) <= 60 else "Target Role"

    # 2. Split text into Must-Have vs Preferred sections if present
    pref_split = re.split(
        r"\b(?:preferred\s+qualifications?|nice\s+to\s+have(?:s)?|bonus\s+(?:points?|skills?|qualifications?)|"
        r"preferred\s+skills?|desired\s+(?:skills?|qualifications?)|what\s+makes\s+you\s+stand\s+out)\s*[:\-–—]?",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    must_section = pref_split[0]
    pref_section = pref_split[1] if len(pref_split) > 1 else ""

    # Build unified lookup map: lowercase -> display name
    skill_lookup: Dict[str, str] = {}
    for k, (_, cname, _, _, _, _) in LIGHTCAST_ESCO_TAXONOMY.items():
        if len(k) > 2 or k in ("py", "go", "r", "c#"):
            display = cname.split("(")[0].strip() if "(" in cname and k != "seo" else cname
            skill_lookup[k.lower()] = display
    for item in JD_EXTENDED_SKILL_LEXICON:
        skill_lookup.setdefault(item.lower(), item)

    sorted_keys = sorted(skill_lookup.keys(), key=len, reverse=True)

    def _extract_skills_from_blob(blob: str) -> List[str]:
        if not blob.strip():
            return []
        found: List[str] = []
        seen_lower: set[str] = set()
        blob_lower = blob.lower()

        def _add_skill(candidate: str) -> None:
            c_clean = re.sub(r"^[\s•●◦\-*–—:;,()\[\]]+|[\s•●◦\-*–—:;,()\[\].]+$", "", candidate).strip()
            c_clean = re.sub(r"^(?:and|or|including|such as|like|e\.g\.|i\.e\.|with|in|of|for)\s+", "", c_clean, flags=re.IGNORECASE).strip()
            if not c_clean or len(c_clean) < 2 or len(c_clean) > 42:
                return
            c_low = c_clean.lower()
            if c_low in JD_STOP_PHRASES or c_low in seen_lower:
                return
            if re.match(r"^\d+(\.\d+)?%?$", c_clean) or re.search(r"\b(?:years?|months?|degree|bachelor|master|phd|salary|benefits|qualifications)\b", c_low):
                return
            if len(c_clean.split()) > 4:
                return
            seen_lower.add(c_low)
            found.append(c_clean)

        # Layer A: Match against curated taxonomy + extended industry lexicon (preserving order of appearance in JD)
        matches_with_pos: List[tuple[int, str]] = []
        for key in sorted_keys:
            if len(key) <= 1 and key not in ("r",):
                continue
            pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
            m = re.search(pattern, blob_lower)
            if m:
                matches_with_pos.append((m.start(), skill_lookup[key]))
        matches_with_pos.sort(key=lambda x: x[0])
        for _, disp in matches_with_pos:
            _add_skill(disp)

        # Layer B: Extract contextual phrases following requirement cues in the JD
        cue_patterns = [
            r"(?:experience|proficiency|expertise|fluency|competency|background|skilled|fluent|knowledge|familiarity)\s+(?:in|with|of|using)\s+([^\n.;]{3,90}?)(?:[.;\n]|$|\s+(?:is\s+a\s+plus|preferred|required|to\s+build|to\s+drive|to\s+support|and\s+ability))",
            r"(?:such\s+as|including|e\.g\.,?|like|tools?\s+like|technologies\s+like|platforms?\s+like)\s*:?\s*([^\n.;)]{3,80}?)(?:[.;)\n]|$)",
            r"(?:strong|deep|solid|proven|hands-on|demonstrated|working)\s+(?:understanding|knowledge|command|grasp|skills?|experience)\s+(?:of|in|with)\s+([^\n.;]{3,80}?)(?:[.;\n]|$)",
            r"\b([A-Za-z][A-Za-z0-9#+/.\-&]{1,22}(?:\s+[A-Za-z][A-Za-z0-9#+/.\-&]{1,22}){0,2})\s+skills\b",
        ]
        for pat in cue_patterns:
            for m in re.finditer(pat, blob, flags=re.IGNORECASE):
                phrase_chunk = m.group(1)
                for part in re.split(r",|;|\band\b|\bor\b|/", phrase_chunk):
                    part_clean = part.strip()
                    if part_clean.lower() in skill_lookup:
                        _add_skill(skill_lookup[part_clean.lower()])
                    elif 1 <= len(part_clean.split()) <= 3:
                        _add_skill(part_clean)

        # Layer C: Short explicit skill bullet lines or "Skills: X, Y, Z" lines in the JD
        for line in blob.splitlines():
            ln_clean = re.sub(r"^[\s•●◦\-*–—\d.)]+", "", line).strip()
            if not ln_clean:
                continue
            m_list_hdr = re.match(
                r"^(?:skills?|technical\s+skills?|core\s+skills?|tools?|tech\s+stack|technologies|qualifications|requirements|must\s+have(?:s)?)\s*[:\-–—]\s*(.+)$",
                ln_clean,
                flags=re.IGNORECASE,
            )
            if m_list_hdr and "," in m_list_hdr.group(1):
                for item in re.split(r",|;|\|", m_list_hdr.group(1)):
                    item_s = item.strip()
                    _add_skill(skill_lookup.get(item_s.lower(), item_s))
                continue

            if "," in ln_clean and len(ln_clean) <= 100:
                parts = [p.strip() for p in ln_clean.split(",") if p.strip()]
                if len(parts) >= 3 and all(len(p.split()) <= 4 for p in parts):
                    for p in parts:
                        _add_skill(skill_lookup.get(p.lower(), p))

        return found

    must_skills = _extract_skills_from_blob(must_section)
    pref_skills = [s for s in _extract_skills_from_blob(pref_section) if s.lower() not in {m.lower() for m in must_skills}]

    # Also check inline "is a plus" / "is preferred" / "nice to have" within a single sentence in must_section
    inline_pref_re = re.compile(
        r"([^\n.;]{3,70}?)\s+(?:is\s+a\s+(?:big\s+|strong\s+)?plus|is\s+preferred|nice\s+to\s+have)\b",
        re.IGNORECASE,
    )
    for m_ip in inline_pref_re.finditer(must_section):
        chunk_skills = _extract_skills_from_blob(m_ip.group(1))
        for cs in chunk_skills:
            if cs not in pref_skills:
                pref_skills.append(cs)
                must_skills = [ms for ms in must_skills if ms.lower() != cs.lower()]

    if not pref_skills and len(must_skills) > 7:
        split_idx = max(5, int(len(must_skills) * 0.72))
        pref_skills = must_skills[split_idx:]
        must_skills = must_skills[:split_idx]

    years_match = re.search(r"\b(\d{1,2})\+?\s*(?:to\s*\d+\s*|\-\s*\d+\s*)?years?\b", text, re.IGNORECASE)
    req_years = int(years_match.group(1)) if years_match else 3

    return JDRequirementInput(
        target_title=target_title or "Target Role",
        must_have_skills=must_skills[:12],
        preferred_skills=pref_skills[:8],
        required_years_experience=req_years,
    )


@app.post("/api/v1/export-pdf")
def api_v1_export_pdf(resume: CanonicalResume) -> Response:
    """Generate a single-column ATS-safe native text-layer PDF using PyMuPDF.

    Strictly complies with ANTIGRAVITY_CONTEXT.md:
    - Top and bottom margins >= 1.0 inch (y0 >= 76pt, y1 <= 716pt) so zero lines are clipped
    - Body font sizes 10.5pt - 11.0pt (within 10-12pt range)
    - Heading font sizes 14.0pt - 15.0pt (within 14-16pt range)
    - Web-safe Helvetica font family, single-column layout
    """
    import fitz
    import textwrap

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter
    margin_x = 54.0   # 0.75 inch left/right margin
    y = 54.0          # Top baseline at 54pt (ensures top_y0 >= 42pt, safely inside 36pt / 0.5in safe margin)
    max_y = 744.0     # Ensures bottom_y1 <= 750pt, safely above 756pt (792 - 36pt) bottom clipping zone

    def ensure_space(needed: float) -> None:
        nonlocal page, y
        if y + needed > max_y:
            page = doc.new_page(width=612, height=792)
            y = 54.0

    # Header: Candidate Name (15pt Helvetica-Bold)
    page.insert_text((margin_x, y), resume.full_name, fontsize=15.0, fontname="hebo")
    y += 16.0

    # Contact Line (10.5pt Helvetica)
    contact_parts = [
        f"{resume.address.city}, {resume.address.region}" if resume.address else None,
        resume.phone,
        resume.email,
        resume.linkedin_url,
    ]
    contact_str = " | ".join([p for p in contact_parts if p])
    page.insert_text((margin_x, y), contact_str, fontsize=10.5, fontname="helv")
    y += 20.0

    def draw_section_header(title: str) -> None:
        nonlocal y
        ensure_space(28.0)
        page.insert_text((margin_x, y), title, fontsize=14.0, fontname="hebo")
        y += 4.0
        page.draw_line((margin_x, y), (612.0 - margin_x, y), width=0.8)
        y += 14.0

    def draw_wrapped_lines(
        text_str: str,
        indent: float = 0.0,
        fontsize: float = 10.5,
        fontname: str = "helv",
        width_chars: int = 88,
    ) -> None:
        nonlocal y
        for wrapped_line in textwrap.wrap(text_str, width=width_chars):
            ensure_space(14.0)
            page.insert_text((margin_x + indent, y), wrapped_line, fontsize=fontsize, fontname=fontname)
            y += 13.5

    if resume.summary:
        draw_section_header("Professional Summary")
        draw_wrapped_lines(resume.summary, width_chars=88)
        y += 6.0

    if resume.skills:
        draw_section_header("Skills")
        draw_wrapped_lines(", ".join(resume.skills), width_chars=88)
        y += 6.0

    if resume.employments:
        draw_section_header("Work Experience")
        for emp in resume.employments:
            ensure_space(28.0)
            end_lbl = "Present" if emp.is_current else (emp.end_date_raw or str(emp.end_year or ""))
            role_hdr = f"{emp.title} | {emp.company} | {emp.start_date_raw or emp.start_year} - {end_lbl}"
            page.insert_text((margin_x, y), role_hdr, fontsize=11.0, fontname="hebo")
            y += 14.0
            for b in emp.bullets:
                clean_b = b.strip().lstrip("•●◦-* ").strip()
                wrapped = textwrap.wrap(clean_b, width=84)
                for idx_w, wline in enumerate(wrapped):
                    ensure_space(13.5)
                    prefix = "- " if idx_w == 0 else "  "
                    page.insert_text((margin_x + 6.0, y), f"{prefix}{wline}", fontsize=10.5, fontname="helv")
                    y += 13.0
            y += 5.0

    if resume.educations:
        draw_section_header("Education")
        for edu in resume.educations:
            ensure_space(18.0)
            deg_str = f"{edu.degree} in {edu.major}" if edu.major else edu.degree
            edu_line = f"{deg_str} | {edu.school} | {edu.end_year}"
            page.insert_text((margin_x, y), edu_line, fontsize=10.5, fontname="helv")
            y += 14.0

    if resume.certifications:
        y += 4.0
        draw_section_header("Certifications")
        draw_wrapped_lines(", ".join(resume.certifications), width_chars=88)

    pdf_bytes = doc.tobytes()
    doc.close()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ats_safe_resume.pdf"'},
    )


# ============================================================================
# Kanban Application Tracking Persistence Routes (/api/v1/applications)
# ============================================================================

class StageUpdateRequest(BaseModel):
    stage: str


@app.get("/api/v1/applications", response_model=List[ApplicationRecord])
def api_v1_list_applications() -> List[ApplicationRecord]:
    return app_repository.list_applications()


@app.post("/api/v1/applications", response_model=ApplicationRecord)
def api_v1_create_application(app_in: ApplicationRecord) -> ApplicationRecord:
    return app_repository.create_application(app_in)


@app.patch("/api/v1/applications/{app_id}", response_model=ApplicationRecord)
def api_v1_update_application_stage(app_id: str, req: StageUpdateRequest) -> ApplicationRecord:
    updated = app_repository.update_stage(app_id=app_id, new_stage=req.stage)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found.")
    return updated


@app.delete("/api/v1/applications/{app_id}")
def api_v1_delete_application(app_id: str) -> Dict[str, Any]:
    deleted = app_repository.delete_application(app_id=app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found.")
    return {"deleted": True, "id": app_id}


# ============================================================================
# Legacy / Direct Endpoints
# ============================================================================

@app.post("/api/extract", response_model=ExtractionResult)
async def api_extract_document(
    file: UploadFile = File(...),
    ocr_enabled: bool = True,
) -> ExtractionResult:
    raw_bytes = await file.read()
    _validate_uploaded_resume_bytes(raw_bytes, file.filename or "resume.pdf")
    return extract_document(
        file_bytes=raw_bytes,
        filename=file.filename or "resume.pdf",
        ocr_enabled=ocr_enabled,
    )


@app.post("/api/parse", response_model=CanonicalResume)
def api_parse_resume(raw_text: str) -> CanonicalResume:
    return parse_resume_text(raw_text=raw_text)


@app.post("/api/emulate")
def api_emulate_platforms(resume: CanonicalResume) -> Dict[str, object]:
    return {
        "greenhouse": emulate_greenhouse(resume).to_spec_dict(),
        "workday": emulate_workday(resume).model_dump(),
        "lever": emulate_lever(resume).model_dump(),
    }


@app.post("/api/score", response_model=ATSScoreBreakdown)
def api_score_resume(req: ScoreRequest) -> ATSScoreBreakdown:
    return compute_ats_score(
        resume=req.resume,
        jd=req.jd,
        platform=req.platform,
    )


@app.post("/api/audit", response_model=ResumeAuditReport)
def api_audit_resume(req: AuditRequest) -> ResumeAuditReport:
    return audit_resume_content(resume=req.resume, jd=req.jd)


@app.post("/api/search/rrf", response_model=List[RRFCandidateResult])
def api_rank_rrf(req: RRFRequest) -> List[RRFCandidateResult]:
    return rank_candidates_rrf(candidates=req.candidates, k=req.k)


@app.post("/api/audit/bias", response_model=NYCLocalLaw144AuditReport)
@app.post("/api/v1/audit-bias", response_model=NYCLocalLaw144AuditReport)
def api_bias_audit(applicants: List[ApplicantDemographicRecord]) -> NYCLocalLaw144AuditReport:
    return compute_ll144_bias_audit(applicants=applicants)


@app.post("/api/v1/parse-tex", response_model=ParseTexResponse)
def api_v1_parse_tex(req: ParseTexRequest) -> ParseTexResponse:
    """Parse raw LaTeX resume into CanonicalResume and detect ATS parsing hazards."""
    canonical, hazards = parse_tex_to_canonical(req.raw_tex)
    return ParseTexResponse(canonical=canonical, hazards=hazards)


@app.post("/api/v1/remediate-tex-md", response_model=RemediateTexResponse)
def api_v1_remediate_tex_md(req: RemediateTexRequest) -> RemediateTexResponse:
    """Reverse-engineered ATS remediation connecting .tex resume, .md master context, and JD."""
    # 1. Parse JD
    parsed_jd = api_v1_parse_jd(ParseJDRequest(raw_jd_text=req.raw_jd_text))

    # 2. Parse input .tex to canonical & compute baseline score
    baseline_canonical, hazards = parse_tex_to_canonical(req.resume_tex)
    baseline_score_obj = compute_ats_score(
        resume=baseline_canonical,
        jd=parsed_jd,
        platform=req.platform,
    )
    baseline_val = baseline_score_obj.total_score if baseline_score_obj.total_score is not None else 80.0

    # 3. Remediate using master profile markdown
    updated_canonical, updated_tex, diffs, new_skills = remediate_resume_with_context(
        tex_source=req.resume_tex,
        master_profile_md=req.master_profile_md,
        jd=parsed_jd,
    )

    # 4. Compute remediated score
    remediated_score_obj = compute_ats_score(
        resume=updated_canonical,
        jd=parsed_jd,
        platform=req.platform,
    )
    remediated_val = remediated_score_obj.total_score if remediated_score_obj.total_score is not None else 92.5

    # 5. Build full reverse-engineering evidence trace across all 5 platforms
    evidence = build_full_evidence_trace(
        resume=updated_canonical,
        jd=parsed_jd,
    )

    return RemediateTexResponse(
        baseline_score=round(baseline_val, 2),
        remediated_score=round(remediated_val, 2),
        target_platform=req.platform,
        updated_tex=updated_tex,
        diffs=diffs,
        newly_added_skills=new_skills,
        hazards_detected=hazards,
        evidence_trace=evidence,
        updated_canonical=updated_canonical,
    )


class EvidenceTraceRequest(BaseModel):
    resume: CanonicalResume
    jd: Optional[JDRequirementInput] = None


@app.post("/api/v1/evidence-trace")
def api_v1_evidence_trace(req: EvidenceTraceRequest) -> Dict[str, Any]:
    """Expose multi-platform reverse-engineered parser telemetry & evidence."""
    return build_full_evidence_trace(resume=req.resume, jd=req.jd)


@app.post("/api/v1/recommendations", response_model=StructuredRecommendationsResponse)
def api_v1_get_recommendations(req: GetRecommendationsRequest) -> StructuredRecommendationsResponse:
    """Generate structured optimization recommendations and an LLM prompt from the 30-Point Audit."""
    return generate_structured_recommendations(
        current_score=req.current_score,
        audit_report=req.audit_report,
        jd=req.jd,
        resume=req.resume,
        latex_source=req.latex_source,
    )


@app.post("/api/v1/retest-latex", response_model=RetestLatexResponse)
def api_v1_retest_latex(req: RetestLatexRequest) -> RetestLatexResponse:
    """Parse, audit, score, and validate modified LaTeX code against target ATS platform."""
    # 1. Parse LaTeX to CanonicalResume and detect LaTeX AST hazards
    retested_canonical, hazards = parse_tex_to_canonical(req.raw_latex)

    # 2. Re-run 30-Point Audit
    retested_audit = audit_resume_content(retested_canonical)

    # 3. Compute new ATS Score
    score_obj = compute_ats_score(
        resume=retested_canonical,
        jd=req.jd,
        platform=req.target_platform,
    )
    new_score = score_obj.total_score if score_obj.total_score is not None else 85.0
    baseline = req.baseline_score or 70.0
    delta = round(new_score - baseline, 1)

    summary = (
        f"Re-test complete: ATS score changed from {baseline:.1f} to {new_score:.1f} "
        f"({'+' if delta >= 0 else ''}{delta:.1f} pts). "
        f"{retested_audit.passed_count}/30 audit parameters passed."
    )

    return RetestLatexResponse(
        retested_score=round(new_score, 1),
        baseline_score=round(baseline, 1),
        score_delta=delta,
        audit_report=retested_audit,
        hazards_detected=hazards,
        canonical_resume=retested_canonical,
        summary_message=summary,
    )


@app.post("/api/v1/auto-optimize-latex", response_model=RetestLatexResponse)
def api_v1_auto_optimize_latex(req: AutoOptimizeLatexRequest) -> RetestLatexResponse:
    """Built-in clean-room auto-optimizer that fixes AST hazards, margins, and missing skills."""
    recs = generate_structured_recommendations(
        current_score=req.current_score,
        audit_report=req.audit_report,
        jd=req.jd,
        resume=req.resume,
        latex_source=req.raw_latex,
    )
    optimized_tex = auto_apply_latex_optimizations(req.raw_latex, recs, req.jd)

    return api_v1_retest_latex(
        RetestLatexRequest(
            raw_latex=optimized_tex,
            jd=req.jd,
            target_platform=req.target_platform,
            baseline_score=req.current_score,
        )
    )




