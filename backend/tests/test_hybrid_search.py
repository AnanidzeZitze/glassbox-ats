"""Unit tests for Module 5 (Hybrid RRF Search & NYC LL144 Bias Audit) and Module 6 (Zero-Hallucination Tailor)."""

from __future__ import annotations

import pytest

from backend.models.schemas import (
    ApplicantDemographicRecord,
    RRFCandidateInput,
)
from backend.services.hybrid_search import (
    compute_ll144_bias_audit,
    rank_candidates_rrf,
)
from backend.services.tailor import (
    run_constrained_tailor_with_retries,
    validate_tailored_resume_payload,
)


def test_rrf_3_candidate_tournament_benchmark():
    """Verify Section 6.2 3-candidate RRF tournament at k = 60:
    - Candidate A (Keyword Stuffer): bm25_rank = 1, ann_rank = 50 -> 1/61 + 1/110 = 0.02548 (Rank 3)
    - Candidate B (Consensus Match): bm25_rank = 3, ann_rank = 3 -> 1/63 + 1/63 = 0.03175 (Rank 1 Winner)
    - Candidate C (Semantic Outlier): bm25_rank = 10, ann_rank = 1 -> 1/70 + 1/61 = 0.03068 (Rank 2)
    """
    candidates = [
        RRFCandidateInput(
            candidate_id="cand_a",
            candidate_name="Candidate A (Keyword Stuffer)",
            bm25_rank=1,
            ann_rank=50,
        ),
        RRFCandidateInput(
            candidate_id="cand_b",
            candidate_name="Candidate B (Consensus Match)",
            bm25_rank=3,
            ann_rank=3,
        ),
        RRFCandidateInput(
            candidate_id="cand_c",
            candidate_name="Candidate C (Semantic Outlier)",
            bm25_rank=10,
            ann_rank=1,
        ),
    ]

    ranked = rank_candidates_rrf(candidates, k=60)

    # Winner: Candidate B
    assert ranked[0].candidate_id == "cand_b"
    assert ranked[0].final_rank == 1
    assert ranked[0].rrf_score == pytest.approx(0.03175, abs=1e-5)

    # Runner-up: Candidate C
    assert ranked[1].candidate_id == "cand_c"
    assert ranked[1].final_rank == 2
    assert ranked[1].rrf_score == pytest.approx(0.03068, abs=1e-5)

    # Third place: Candidate A
    assert ranked[2].candidate_id == "cand_a"
    assert ranked[2].final_rank == 3
    assert ranked[2].rrf_score == pytest.approx(0.02548, abs=1e-5)


def test_nyc_local_law_144_bias_audit_four_fifths_rule():
    """Verify Section 6.3 NYC Local Law 144 Scoring Rate, Impact Ratio, and < 0.80 adverse impact detection."""
    applicants = [
        # Group A: 4 of 5 score above overall median -> Scoring Rate = 0.80
        ApplicantDemographicRecord(applicant_id="a1", score=92.0, cohort_group="Group_A"),
        ApplicantDemographicRecord(applicant_id="a2", score=88.0, cohort_group="Group_A"),
        ApplicantDemographicRecord(applicant_id="a3", score=85.0, cohort_group="Group_A"),
        ApplicantDemographicRecord(applicant_id="a4", score=81.0, cohort_group="Group_A"),
        ApplicantDemographicRecord(applicant_id="a5", score=60.0, cohort_group="Group_A"),
        # Group B: 1 of 5 scores above overall median -> Scoring Rate = 0.20 (Impact Ratio = 0.20 / 0.80 = 0.25 < 0.80)
        ApplicantDemographicRecord(applicant_id="b1", score=84.0, cohort_group="Group_B"),
        ApplicantDemographicRecord(applicant_id="b2", score=70.0, cohort_group="Group_B"),
        ApplicantDemographicRecord(applicant_id="b3", score=68.0, cohort_group="Group_B"),
        ApplicantDemographicRecord(applicant_id="b4", score=65.0, cohort_group="Group_B"),
        ApplicantDemographicRecord(applicant_id="b5", score=55.0, cohort_group="Group_B"),
    ]

    report = compute_ll144_bias_audit(applicants)
    assert report.adverse_impact_detected is True

    cohort_map = {c.cohort_group: c for c in report.cohorts}
    assert cohort_map["Group_A"].scoring_rate == pytest.approx(0.80)
    assert cohort_map["Group_A"].impact_ratio == pytest.approx(1.00)
    assert cohort_map["Group_A"].adverse_impact_detected is False

    assert cohort_map["Group_B"].scoring_rate == pytest.approx(0.20)
    assert cohort_map["Group_B"].impact_ratio == pytest.approx(0.25)
    assert cohort_map["Group_B"].adverse_impact_detected is True


def test_module6_zero_hallucination_validator_and_retry_loop():
    """Verify Section 7.1 ValidatedResume @model_validator(mode='after') rejects hallucinated skills, employers, metrics, and invalid dates."""
    master_resume = {
        "companies": ["Zendex Inc."],
        "skills": ["Python", "SQL", "Tableau", "Jira"],
        "bullets": [
            "Led roadmap for enterprise analytics suite, $8M ARR in year one",
            "Shipped 14 major releases with 99.2% on-time delivery",
        ],
    }

    # 1. Reject hallucinated skill ('Rust')
    with pytest.raises(ValueError, match="Hallucinated skill/tool detected"):
        validate_tailored_resume_payload(
            candidate_name="Sarah Chen",
            employments=[
                {
                    "title": "Senior Product Manager",
                    "company": "Zendex Inc.",
                    "start_date": "2022-03",
                    "end_date": "Present",
                    "bullets": ["Led roadmap for enterprise analytics suite, $8M ARR in year one"],
                }
            ],
            skills=["Python", "Rust"],
            master_resume_json=master_resume,
        )

    # 2. Reject hallucinated metric ('$25M')
    with pytest.raises(ValueError, match="Hallucinated metric"):
        validate_tailored_resume_payload(
            candidate_name="Sarah Chen",
            employments=[
                {
                    "title": "Senior Product Manager",
                    "company": "Zendex Inc.",
                    "start_date": "2022-03",
                    "end_date": "Present",
                    "bullets": ["Led roadmap for enterprise analytics suite, $25M ARR in year one"],
                }
            ],
            skills=["Python", "SQL"],
            master_resume_json=master_resume,
        )

    # 3. Test automatic retry loop succeeding on second attempt after error traceback feedback
    attempts = {"count": 0}

    def mock_generator(last_err: str | None) -> dict:
        attempts["count"] += 1
        if attempts["count"] == 1:
            # First attempt hallucinates employer
            return {
                "candidate_name": "Sarah Chen",
                "employments": [
                    {
                        "title": "Senior Product Manager",
                        "company": "FakeCorp LLC",
                        "start_date": "2022-03",
                        "end_date": "Present",
                        "bullets": ["Led roadmap for enterprise analytics suite, $8M ARR in year one"],
                    }
                ],
                "skills": ["Python", "SQL"],
            }
        assert last_err is not None and "Hallucinated employer" in last_err
        return {
            "candidate_name": "Sarah Chen",
            "employments": [
                {
                    "title": "Senior Product Manager",
                    "company": "Zendex Inc.",
                    "start_date": "2022-03",
                    "end_date": "Present",
                    "bullets": ["Led roadmap for enterprise analytics suite, $8M ARR in year one"],
                }
            ],
            "skills": ["Python", "SQL"],
        }

    validated = run_constrained_tailor_with_retries(master_resume, mock_generator, max_retries=3)
    assert attempts["count"] == 2
    assert validated.employments[0].company == "Zendex Inc."
