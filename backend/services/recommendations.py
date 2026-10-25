"""Module: Structured Recommendations Engine & LaTeX LLM Prompt Generator.

Generates actionable, prioritized recommendations based on the Diagnostic & 30-Point Audit
to optimize ATS scores, and constructs structured LLM prompts for LaTeX code remediation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.models.schemas import (
    ATSPlatform,
    ATSScoreBreakdown,
    AuditParameterResult,
    CanonicalResume,
    JDRequirementInput,
    RecommendationItem,
    ResumeAuditReport,
    RetestLatexRequest,
    RetestLatexResponse,
    StructuredRecommendationsResponse,
)
from backend.services.ats_score import (
    audit_resume_content,
    compute_ats_score,
)
from backend.services.tex_parser import (
    detect_latex_hazards,
    parse_tex_to_canonical,
)


def generate_structured_recommendations(
    current_score: float,
    audit_report: ResumeAuditReport,
    jd: JDRequirementInput,
    resume: CanonicalResume,
    latex_source: Optional[str] = None,
) -> StructuredRecommendationsResponse:
    """Analyze the 30-Point Audit results and JD matching to generate categorized recommendations."""
    recommendations: List[RecommendationItem] = []
    rec_counter = 1

    # 1. Evaluate missing Must-Have and Preferred skills
    detected_skills_lower = {s.lower().strip() for s in resume.skills}
    for norm in resume.normalized_skills:
        detected_skills_lower.add(norm.canonical_name.lower().strip())

    missing_must_have: List[str] = []
    for skill in jd.must_have_skills:
        if skill.lower().strip() not in detected_skills_lower:
            missing_must_have.append(skill)

    missing_preferred: List[str] = []
    for skill in jd.preferred_skills:
        if skill.lower().strip() not in detected_skills_lower:
            missing_preferred.append(skill)

    # Priority 1: Critical Missing Must-Have Skills (70% Pool Impact)
    if missing_must_have:
        rec_id = f"REC-{rec_counter:03d}"
        rec_counter += 1
        skills_str = ", ".join(f"'{s}'" for s in missing_must_have[:6])
        recommendations.append(
            RecommendationItem(
                id=rec_id,
                category="KEYWORD_MUST_HAVE",
                title=f"Add {len(missing_must_have)} Missing Must-Have Technical Skills",
                problem_statement=f"Your resume is missing essential core competencies demanded by the JD: {skills_str}.",
                actionable_instruction=(
                    f"Incorporate these skills into both your \\section{{Skills}} and within active work experience bullets: "
                    f"{', '.join(missing_must_have)}. Mention them alongside genuine past achievements or projects."
                ),
                score_impact_estimate="+15 to +25 pts",
                priority="CRITICAL",
            )
        )

    # Priority 2: Missing Preferred Skills (30% Pool Impact)
    if missing_preferred:
        rec_id = f"REC-{rec_counter:03d}"
        rec_counter += 1
        recommendations.append(
            RecommendationItem(
                id=rec_id,
                category="KEYWORD_PREFERRED",
                title=f"Incorporate Preferred Qualifications ({len(missing_preferred)} skills)",
                problem_statement=f"Candidate pool competitors with preferred skills will outrank you: {', '.join(missing_preferred[:5])}.",
                actionable_instruction=(
                    f"Add preferred tools and frameworks ({', '.join(missing_preferred)}) into your Technical Skills list "
                    "or as supporting technologies in project descriptions."
                ),
                score_impact_estimate="+5 to +10 pts",
                priority="HIGH",
            )
        )

    # Priority 3: 30-Point Audit Failures & Warnings
    failed_params: List[Dict[str, Any]] = []
    for p in audit_report.parameters:
        status_str = p.status.value if hasattr(p.status, "value") else str(p.status)
        if status_str in ("FAIL", "WARN"):
            failed_params.append({
                "param_id": p.param_id,
                "name": p.name,
                "status": status_str,
                "message": p.message,
                "category": p.category,
            })

            # Parameter-specific targeted recommendations
            if p.param_id == 4:  # Margins
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="CRITICAL_ATS_HAZARD",
                        title="Calibrate Margins to Safe 0.5-inch (36pt) Standard",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "Ensure \\usepackage[margin=0.5in]{geometry} (or margin=0.75in) is set. "
                            "Do NOT use margins below 0.5 inches (e.g. 0.25in), as Taleo and Workday clip header/footer text outside 36pt."
                        ),
                        score_impact_estimate="+5 to +8 pts",
                        priority="CRITICAL",
                    )
                )
            elif p.param_id in (5, 6):  # Multi-column or Tables
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="CRITICAL_ATS_HAZARD",
                        title="Flatten Multi-Column / Tabular Layout to Single-Column",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "Remove \\usepackage{multicol}, \\begin{multicols}, and \\begin{tabular} layout blocks. "
                            "Use linear, top-to-bottom section formatting with standard \\section and \\item lists to eliminate text interleaving."
                        ),
                        score_impact_estimate="+10 to +15 pts",
                        priority="CRITICAL",
                    )
                )
            elif p.param_id == 8:  # Private-use icons
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="CRITICAL_ATS_HAZARD",
                        title="Replace FontAwesome / Glyph Icons with Standard Text Labels",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "Remove \\usepackage{fontawesome5} and icon macros (\\faEnvelope, \\faPhone, \\faGithub). "
                            "Use plain text labels like 'Email: alex@example.com | Phone: (555) 019-4242 | GitHub: github.com/user'."
                        ),
                        score_impact_estimate="+5 to +10 pts",
                        priority="CRITICAL",
                    )
                )
            elif p.param_id == 16:  # Bullet quantification
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="BULLET_QUANTIFICATION",
                        title="Quantify Bullets with Measurable Metrics (%, $, Numbers)",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "At least 50% of your experience bullet points must contain concrete metrics. "
                            "Example: Instead of 'Improved API speed', write 'Optimized REST API query latency by 42% (reduced p99 from 380ms to 220ms)'."
                        ),
                        score_impact_estimate="+8 to +12 pts",
                        priority="HIGH",
                    )
                )
            elif p.param_id == 19:  # Inconsistent date formats
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="FORMAT_STRUCTURE",
                        title="Standardize All Employment Dates to Unified Format",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "Use a consistent date format across all roles, ideally 'YYYY-MM -- Present' or 'Month YYYY -- Month YYYY' "
                            "(e.g., '2022-04 -- Present' or 'Apr 2022 -- Present')."
                        ),
                        score_impact_estimate="+4 to +6 pts",
                        priority="MEDIUM",
                    )
                )
            elif p.param_id in (14, 15):  # Action verbs
                rec_id = f"REC-{rec_counter:03d}"
                rec_counter += 1
                recommendations.append(
                    RecommendationItem(
                        id=rec_id,
                        category="BULLET_QUANTIFICATION",
                        title="Begin Every Bullet with a Strong Executive Action Verb",
                        problem_statement=p.message,
                        actionable_instruction=(
                            "Replace passive phrases ('Assisted with', 'Worked on', 'Responsible for') with assertive action verbs: "
                            "'Architected', 'Spearheaded', 'Engineered', 'Orchestrated', 'Automated'."
                        ),
                        score_impact_estimate="+5 to +8 pts",
                        priority="MEDIUM",
                    )
                )

    # Fallback general recommendation if all passed
    if not recommendations:
        recommendations.append(
            RecommendationItem(
                id="REC-001",
                category="FORMAT_STRUCTURE",
                title="Maintain High ATS Fidelity",
                problem_statement="Your resume parsed cleanly without structural hazards.",
                actionable_instruction="Review bullet phrasing and verify keyword alignment with upcoming role revisions.",
                score_impact_estimate="+2 pts",
                priority="MEDIUM",
            )
        )

    # Estimate target score
    potential_uplift = sum(
        15 if r.priority == "CRITICAL" else (8 if r.priority == "HIGH" else 4)
        for r in recommendations[:4]
    )
    target_score_est = min(98.5, round(current_score + potential_uplift, 1))

    # Construct the Structured LLM Prompt
    structured_prompt = build_llm_latex_prompt(
        current_score=current_score,
        target_score_est=target_score_est,
        recommendations=recommendations,
        jd=jd,
        resume=resume,
        latex_source=latex_source,
    )

    return StructuredRecommendationsResponse(
        current_score=round(current_score, 1),
        target_score_estimate=target_score_est,
        must_have_missing=missing_must_have,
        preferred_missing=missing_preferred,
        failed_audit_params=failed_params,
        recommendations=recommendations,
        structured_llm_prompt=structured_prompt,
    )


def build_llm_latex_prompt(
    current_score: float,
    target_score_est: float,
    recommendations: List[RecommendationItem],
    jd: JDRequirementInput,
    resume: CanonicalResume,
    latex_source: Optional[str] = None,
) -> str:
    """Generate a prompt formatted for an LLM (Claude/GPT-4o/Gemini) to modify the LaTeX code."""
    recs_formatted = "\n".join(
        f"{idx + 1}. [{r.priority}] {r.title}\n"
        f"   - Issue: {r.problem_statement}\n"
        f"   - Fix: {r.actionable_instruction}\n"
        f"   - Expected Impact: {r.score_impact_estimate}"
        for idx, r in enumerate(recommendations)
    )

    sample_latex_placeholder = latex_source or (
        "% Paste your existing .tex resume code here.\n"
        "\\documentclass[10pt,letterpaper]{article}\n"
        "\\usepackage[margin=0.5in]{geometry}\n"
        "\\begin{document}\n"
        f"\\textbf{{{resume.full_name}}}\\\\\n"
        f"Email: {resume.email or 'candidate@example.com'} | Phone: {resume.phone or '(555) 000-0000'}\\\\\n"
        "\\section{Experience}\n"
        "...\n"
        "\\end{document}"
    )

    return f"""<SYSTEM_INSTRUCTION>
You are an expert Technical Resume Optimization and LaTeX Typesetting Specialist.
Your task is to revise the provided LaTeX resume code to dramatically increase its ATS (Applicant Tracking System) compatibility and match score for the specified Job Description.

STRICT ATS CONSTRAINTS:
1. ATS GEOMETRY: Enforce single-column layout with `\\usepackage[margin=0.5in]{{geometry}}` (or 0.75in). NEVER use margins below 0.5in.
2. ZERO MULTICOLUMN / ZERO TABULAR LAYOUT: Remove `\\usepackage{{multicol}}`, `\\begin{{multicols}}`, or `\\begin{{tabular}}` environments used for formatting. ATS parsers interleave horizontal text baselines across columns.
3. ZERO PRIVATE-USE GLYPH ICONS: Remove `fontawesome5`, `marvosym`, and macros like `\\faEnvelope` or `\\faPhone`. Replace them with plain searchable text labels ("Email:", "Phone:", "LinkedIn:").
4. KEYWORD INTEGRATION: Naturally weave the missing Must-Have and Preferred skills into active employment bullets and the \\section{{Skills}} block. Do not keyword stuff or fabricate past company names.
5. METRIC QUANTIFICATION: Ensure bullet points follow the Google XYZ formula: "Accomplished [X] as measured by [Y] by doing [Z]". Include realistic, verifiable percentages, dollar values, or scale numbers.
6. COMPLIANT FONTS: Use standard web/ATS-safe fonts (Helvetica, Times, Georgia, Computer Modern).
7. OUTPUT ONLY VALID LATEX: Return ONLY the complete, compilable LaTeX source code enclosed in a ```latex code block. Do not include introductory conversational pleasantries or explanations outside the code block.
</SYSTEM_INSTRUCTION>

<TARGET_JOB_DESCRIPTION>
Target Role: {jd.target_title}
Must-Have Competencies: {', '.join(jd.must_have_skills) if jd.must_have_skills else 'Software Engineering'}
Preferred Qualifications: {', '.join(jd.preferred_skills) if jd.preferred_skills else 'Distributed Systems, Cloud'}
Required Experience: {jd.required_years_experience} years
</TARGET_JOB_DESCRIPTION>

<DIAGNOSTIC_AUDIT_RECOMMENDATIONS>
Current ATS Score: {current_score:.1f} / 100
Projected ATS Score Post-Optimization: {target_score_est:.1f} / 100

Actionable Fix Checklist:
{recs_formatted}
</DIAGNOSTIC_AUDIT_RECOMMENDATIONS>

<ORIGINAL_LATEX_RESUME>
```latex
{sample_latex_placeholder}
```
</ORIGINAL_LATEX_RESUME>

<OUTPUT_FORMAT>
Return the updated, compilable LaTeX code inside a single ```latex code block.
</OUTPUT_FORMAT>
"""


def auto_apply_latex_optimizations(
    raw_tex: str,
    recommendations: StructuredRecommendationsResponse,
    jd: JDRequirementInput,
) -> str:
    """Deterministically apply AST and keyword fixes to raw LaTeX code.

    Used when the user clicks 'Auto-Optimize in App' without an external LLM.
    """
    updated = raw_tex

    # 1. Fix margins: Replace sub-0.5in margins with 0.5in
    updated = re.sub(
        r"\\usepackage\[(.*?)\]\{geometry\}",
        r"\\usepackage[margin=0.5in]{geometry}",
        updated,
    )
    if "\\usepackage" not in updated and "\\documentclass" in updated:
        updated = updated.replace(
            "\\begin{document}",
            "\\usepackage[margin=0.5in]{geometry}\n\\begin{document}",
        )

    # 2. Strip multicol / paracol
    updated = re.sub(r"\\usepackage(\[[^\]]*\])?\{(multicol|paracol|flowfram)\}", "% [ATS Safe] Multicolumn removed", updated)
    updated = re.sub(r"\\begin\{(multicols|paracol)\}(\{[^}]*\})?", "% [ATS Safe] Linear single-column flow", updated)
    updated = re.sub(r"\\end\{(multicols|paracol)\}", "% [ATS Safe] End column", updated)

    # 3. Strip icon packages and replace icon macros with clean text labels
    updated = re.sub(r"\\usepackage(\[[^\]]*\])?\{(fontawesome5?|marvosym|pifont|wasysym)\}", "% [ATS Safe] Text labels used instead of glyph icons", updated)
    updated = re.sub(r"\\faEnvelope\s*", "Email: ", updated)
    updated = re.sub(r"\\faPhone\s*", "Phone: ", updated)
    updated = re.sub(r"\\faLinkedin\s*", "LinkedIn: ", updated)
    updated = re.sub(r"\\faGithub\s*", "GitHub: ", updated)
    updated = re.sub(r"\\faMapMarker\s*", "Location: ", updated)

    # 4. Inject missing Must-Have and Preferred skills into Skills section if present
    all_missing = recommendations.must_have_missing + recommendations.preferred_missing
    if all_missing:
        missing_to_inject = [s for s in all_missing[:6] if s.lower() not in updated.lower()]
        if missing_to_inject:
            # Look for \section{Skills} or similar
            skills_match = re.search(r"(\\section\{(Skills|Technical Skills|Core Competencies)\}.*?)(\n\s*\\section|\n\s*\\end\{document\})", updated, re.DOTALL | re.IGNORECASE)
            if skills_match:
                sec_head = skills_match.group(1)
                sec_tail = skills_match.group(3)
                addition = f"\n\\textbf{{Key Technologies & Tools:}} {', '.join(missing_to_inject)}\\\\"
                updated = updated.replace(skills_match.group(0), f"{sec_head}{addition}{sec_tail}")

    return updated
