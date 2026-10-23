"""Module 6: Constrained AI Tailoring (backend/services/tailor.py).

Implements:
- Zero-Hallucination Pydantic Validator (`ValidatedResume`)
- Constrained bullet point rewriter with `max_retries = 3` that rejects any generated skill,
  tool, employer, or metric not already present in the candidate's `master_resume_json`.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from backend.models.schemas import TailoredEmploymentEntry, ValidatedResume

MAX_TAILOR_RETRIES = 3


def validate_tailored_resume_payload(
    candidate_name: str,
    employments: List[Dict[str, Any]],
    skills: List[str],
    master_resume_json: Dict[str, Any],
) -> ValidatedResume:
    """Validate candidate tailored resume against master_resume_json with zero-hallucination rules."""
    entries = [TailoredEmploymentEntry(**emp) for emp in employments]
    return ValidatedResume(
        candidate_name=candidate_name,
        employments=entries,
        skills=skills,
        master_resume_json=master_resume_json,
    )


def run_constrained_tailor_with_retries(
    master_resume_json: Dict[str, Any],
    generator_fn: Callable[[Optional[str]], Dict[str, Any]],
    max_retries: int = MAX_TAILOR_RETRIES,
) -> ValidatedResume:
    """Execute constrained tailoring with automatic traceback retry loop (up to max_retries = 3)."""
    last_error: Optional[str] = None
    for _ in range(max_retries):
        candidate_payload = generator_fn(last_error)
        try:
            return validate_tailored_resume_payload(
                candidate_name=candidate_payload.get("candidate_name", "Candidate"),
                employments=candidate_payload.get("employments", []),
                skills=candidate_payload.get("skills", []),
                master_resume_json=master_resume_json,
            )
        except ValueError as err:
            last_error = str(err)

    raise ValueError(
        f"Constrained tailoring failed after {max_retries} retries. Last validation error: {last_error}"
    )
