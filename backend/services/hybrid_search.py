"""Module 5: PostgreSQL + pgvector Hybrid RRF & Bias Audit (backend/services/hybrid_search.py).

Implements:
- 6.1 Production Database Schema & Reciprocal Rank Fusion (k = 60) SQL + deterministic Python evaluator
- 6.2 3-Candidate RRF Mathematical Tournament at k = 60:
      * Candidate A (Keyword Stuffer): bm25_rank = 1, ann_rank = 50 -> 1/61 + 1/110 = 0.02548 (Rank 3)
      * Candidate B (Consensus Match): bm25_rank = 3, ann_rank = 3 -> 1/63 + 1/63 = 0.03175 (Rank 1 Winner)
      * Candidate C (Semantic Outlier): bm25_rank = 10, ann_rank = 1 -> 1/70 + 1/61 = 0.03068 (Rank 2)
- 6.3 NYC Local Law 144 Bias Audit Telemetry:
      Scoring_Rate(group_g) = count(d in group_g where Score(d) > Median(All_Applicants)) / total_applicants(group_g)
      Impact_Ratio(group_g) = Scoring_Rate(group_g) / max_over_all_groups(Scoring_Rate)
      Flag adverse_impact_detected = True if Impact_Ratio(group_g) < 0.80 (EEOC Four-Fifths Rule).
"""

from __future__ import annotations

import statistics
from typing import Dict, List

from backend.models.schemas import (
    ApplicantDemographicRecord,
    CohortBiasMetric,
    NYCLocalLaw144AuditReport,
    RRFCandidateInput,
    RRFCandidateResult,
)

RRF_DEFAULT_K = 60
EEOC_FOUR_FIFTHS_THRESHOLD = 0.80

PRODUCTION_POSTGRES_PGVECTOR_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    location_city VARCHAR(100),
    location_region VARCHAR(100),
    linkedin_url TEXT,
    demographic_cohort JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parsed_resumes (
    resume_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    raw_file_format VARCHAR(20) NOT NULL,
    linear_raw_text TEXT NOT NULL,
    layout_sorted_text TEXT NOT NULL,
    canonical_json JSONB NOT NULL,
    greenhouse_json JSONB NOT NULL,
    workday_json JSONB NOT NULL,
    lever_json JSONB NOT NULL,
    parse_success_score NUMERIC(5,2) NOT NULL,
    section_completeness_score NUMERIC(5,2) NOT NULL,
    content_audit_metrics JSONB NOT NULL,
    lexical_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', layout_sorted_text)) STORED,
    dense_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_resumes_lexical_bm25 ON parsed_resumes USING GIN (lexical_tsv);
CREATE INDEX idx_resumes_dense_hnsw ON parsed_resumes USING hnsw (dense_embedding vector_cosine_ops);
"""

HYBRID_RRF_SQL_QUERY = """
WITH bm25_ranked AS (
    SELECT 
        resume_id,
        ROW_NUMBER() OVER (ORDER BY ts_rank_cd(lexical_tsv, plainto_tsquery('english', $1)) DESC) AS bm25_rank
    FROM parsed_resumes
    WHERE lexical_tsv @@ plainto_tsquery('english', $1)
    LIMIT 100
),
vector_ranked AS (
    SELECT 
        resume_id,
        ROW_NUMBER() OVER (ORDER BY (dense_embedding <=> $2::vector) ASC) AS ann_rank
    FROM parsed_resumes
    ORDER BY (dense_embedding <=> $2::vector) ASC
    LIMIT 100
)
SELECT 
    COALESCE(b.resume_id, v.resume_id) AS resume_id,
    b.bm25_rank,
    v.ann_rank,
    (COALESCE(1.0 / (60 + b.bm25_rank), 0.0) + COALESCE(1.0 / (60 + v.ann_rank), 0.0)) AS rrf_score
FROM bm25_ranked b
FULL OUTER JOIN vector_ranked v ON b.resume_id = v.resume_id
ORDER BY rrf_score DESC
LIMIT 25;
"""


def compute_rrf_score(
    bm25_rank: int | None,
    ann_rank: int | None,
    k: int = RRF_DEFAULT_K,
) -> float:
    """Compute Reciprocal Rank Fusion score: 1/(k + bm25_rank) + 1/(k + ann_rank)."""
    lexical_part = (1.0 / (k + bm25_rank)) if bm25_rank is not None and bm25_rank > 0 else 0.0
    vector_part = (1.0 / (k + ann_rank)) if ann_rank is not None and ann_rank > 0 else 0.0
    return round(lexical_part + vector_part, 5)


def rank_candidates_rrf(
    candidates: List[RRFCandidateInput],
    k: int = RRF_DEFAULT_K,
) -> List[RRFCandidateResult]:
    """Rank a candidate pool using Reciprocal Rank Fusion (k = 60)."""
    scored: List[RRFCandidateResult] = []
    for cand in candidates:
        score = compute_rrf_score(cand.bm25_rank, cand.ann_rank, k=k)
        scored.append(
            RRFCandidateResult(
                candidate_id=cand.candidate_id,
                candidate_name=cand.candidate_name,
                bm25_rank=cand.bm25_rank,
                ann_rank=cand.ann_rank,
                rrf_score=score,
                final_rank=0,
            )
        )

    scored.sort(key=lambda c: c.rrf_score, reverse=True)
    for idx, item in enumerate(scored, start=1):
        item.final_rank = idx
    return scored


def compute_ll144_bias_audit(
    applicants: List[ApplicantDemographicRecord],
) -> NYCLocalLaw144AuditReport:
    """Compute NYC Local Law 144 Bias Audit Telemetry across demographic cohorts.

    Formulas:
      Scoring_Rate(group_g) = count(d in group_g where Score(d) > Median(All_Applicants)) / total_applicants(group_g)
      Impact_Ratio(group_g) = Scoring_Rate(group_g) / max_over_all_groups(Scoring_Rate)
      Flag `adverse_impact_detected = True` if `Impact_Ratio(group_g) < 0.80` (EEOC Four-Fifths Rule).
    """
    if not applicants:
        return NYCLocalLaw144AuditReport(
            median_score=0.0,
            max_scoring_rate=0.0,
            adverse_impact_detected=False,
            cohorts=[],
        )

    all_scores = [a.score for a in applicants]
    median_score = float(statistics.median(all_scores))

    by_cohort: Dict[str, List[ApplicantDemographicRecord]] = {}
    for app in applicants:
        by_cohort.setdefault(app.cohort_group, []).append(app)

    raw_cohort_rates: List[Tuple[str, int, int, float]] = []
    for group_name, members in by_cohort.items():
        total = len(members)
        above_med = sum(1 for m in members if m.score > median_score)
        rate = (above_med / total) if total > 0 else 0.0
        raw_cohort_rates.append((group_name, total, above_med, rate))

    max_rate = max((r[3] for r in raw_cohort_rates), default=0.0)

    cohorts_report: List[CohortBiasMetric] = []
    any_adverse = False

    for group_name, total, above_med, rate in raw_cohort_rates:
        impact_ratio = (rate / max_rate) if max_rate > 0 else 1.0
        adverse = impact_ratio < EEOC_FOUR_FIFTHS_THRESHOLD
        if adverse:
            any_adverse = True
        cohorts_report.append(
            CohortBiasMetric(
                cohort_group=group_name,
                total_applicants=total,
                above_median_count=above_med,
                scoring_rate=round(rate, 4),
                impact_ratio=round(impact_ratio, 4),
                adverse_impact_detected=adverse,
            )
        )

    return NYCLocalLaw144AuditReport(
        median_score=round(median_score, 4),
        max_scoring_rate=round(max_rate, 4),
        adverse_impact_detected=any_adverse,
        cohorts=cohorts_report,
    )
