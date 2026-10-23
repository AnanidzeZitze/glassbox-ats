"""Unit tests for Module 2: NLP Pipeline & Taxonomy Normalizer (backend/tests/test_nlp_pipeline.py)."""

from __future__ import annotations

from backend.models.schemas import SkillCategory
from backend.services.nlp_pipeline import (
    normalize_skill_token,
    parse_resume_text,
    sanitize_and_tokenize,
    segment_sections,
)


def test_stage2_unicode_glyph_sanitization():
    raw_text = (
        "Work Experience\n"
        "• Built core APIs with Python\n"
        "➢ Spearheaded migration to Kubernetes\n"
        "✔ Improved latency by 45%\n"
        "★ Awarded top engineer\n"
    )
    sanitized, hazards, tokens = sanitize_and_tokenize(raw_text)

    # '•' is whitelisted; '➢', '✔', '★' must be flagged as phantom_token_hazards
    hazard_glyphs = [h.raw_glyph for h in hazards]
    assert "•" not in hazard_glyphs
    assert "➢" in hazard_glyphs
    assert "✔" in hazard_glyphs
    assert "★" in hazard_glyphs
    assert "- Spearheaded migration to Kubernetes" in sanitized
    assert "Python" in tokens


def test_stage3_mandatory_sections_and_non_standard_header_failures():
    creative_resume = (
        "Alex Rivera\n"
        "alex.rivera@example.com | (415) 555-0199\n"
        "My Journey\n"
        "Senior Engineer | Acme Corp | Jan 2021 - Mar 2024\n"
        "- Built distributed microservices\n"
        "Superpowers\n"
        "Python, Docker, AWS\n"
        "Education\n"
        "B.S. in Computer Science | UCLA | 2020\n"
    )
    sections, headers, failures = segment_sections(creative_resume)

    failure_headers = [f.header_text for f in failures]
    assert "My Journey" in failure_headers
    assert "Superpowers" in failure_headers
    assert "Education" in headers


def test_stage4_lightcast_esco_skill_normalization_and_weights():
    python_skill = normalize_skill_token("Python")
    assert python_skill.canonical_id == "SKILL_ID_402"
    assert python_skill.canonical_name == "Python"
    assert python_skill.category == SkillCategory.HARD_SKILL
    assert python_skill.weight == 2.0

    cert_skill = normalize_skill_token("AWS Certified Solutions Architect")
    assert cert_skill.category == SkillCategory.CERTIFICATION
    assert cert_skill.weight == 2.0

    tool_skill = normalize_skill_token("Docker")
    assert tool_skill.category == SkillCategory.TOOL
    assert tool_skill.weight == 1.5

    soft_skill = normalize_skill_token("stakeholder management")
    assert soft_skill.category == SkillCategory.SOFT_SKILL
    assert soft_skill.weight == 0.5


def test_full_resume_parsing_and_mixed_date_detection():
    resume_text = (
        "Sarah Chen\n"
        "San Francisco, CA | sarah.chen@example.com | (415) 555-0142 | https://linkedin.com/in/sarahchen\n"
        "Professional Summary\n"
        "Senior Product Manager with 7 years of experience in Python and SQL.\n"
        "Work Experience\n"
        "Senior Product Manager | Zendex Inc. | Mar 2022 - Present\n"
        "• Led roadmap for enterprise analytics suite, $8M ARR in year one\n"
        "Product Manager | BetaCorp | 01/2019 - 02/2022\n"
        "• Shipped 10 releases\n"
        "Education\n"
        "M.B.A. | Stanford Graduate School of Business | 2019\n"
        "Skills\n"
        "Python, SQL, Tableau, Jira\n"
    )
    parsed = parse_resume_text(resume_text)
    assert parsed.full_name == "Sarah Chen"
    assert parsed.first_name == "Sarah"
    assert parsed.last_name == "Chen"
    assert parsed.email == "sarah.chen@example.com"
    assert parsed.phone_e164 == "+14155550142"
    assert parsed.linkedin_url == "https://linkedin.com/in/sarahchen"
    assert parsed.address is not None
    assert parsed.address.city == "San Francisco"
    assert parsed.address.region == "CA"
    assert parsed.mixed_date_formats_detected is True
    assert len(parsed.employments) == 2
    assert any(s.canonical_id == "SKILL_ID_402" for s in parsed.normalized_skills)
