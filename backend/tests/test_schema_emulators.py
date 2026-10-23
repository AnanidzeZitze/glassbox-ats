"""Unit tests for Module 3: Stage 5 Platform JSON Schema Emulators (backend/tests/test_schema_emulators.py).

Verifies exact ground-truth output structures for Benchmark Candidate Sarah Chen across:
- 4.1 Greenhouse JSON Schema (Sovren Engine Profile)
- 4.2 Workday JSON Schema (Enterprise ASCII Profile)
- 4.3 Lever JSON Schema (NLP Pattern & Tag-Truncated Profile)
"""

from __future__ import annotations

from backend.services.schema_emulators import (
    build_sarah_chen_canonical_fixture,
    emulate_greenhouse,
    emulate_lever,
    emulate_workday,
)


def test_greenhouse_emulator_sarah_chen_benchmark():
    sarah = build_sarah_chen_canonical_fixture()
    gh = emulate_greenhouse(sarah)
    gh_dict = gh.to_spec_dict()

    expected_greenhouse = {
        "first_name": "Sarah",
        "last_name": "Chen",
        "email_addresses": ["sarah.chen@example.com"],
        "phone_numbers": [{"value": "+14155550142", "type": "mobile"}],
        "addresses": [{"city": "San Francisco", "region": "CA", "country": "US"}],
        "employments": [
            {
                "title": "Senior Product Manager",
                "company_name": "Zendex Inc.",
                "start_month": 3,
                "start_year": 2022,
                "end_month": None,
                "end_year": None,
                "is_current": True,
                "description_bullets": [
                    "Led roadmap for enterprise analytics suite, $8M ARR in year one",
                    "Managed team of 4 PMs and 18 engineers across 3 time zones",
                    "Shipped 14 major releases with 99.2% on-time delivery",
                ],
            }
        ],
        "educations": [
            {
                "degree": "M.B.A.",
                "school": "Stanford Graduate School of Business",
                "end_year": 2019,
            },
            {
                "degree": "B.S.",
                "major": "Computer Science",
                "school": "UC Berkeley",
                "end_year": 2015,
            },
        ],
        "skills": [
            "SQL",
            "Python",
            "Tableau",
            "Jira",
            "Confluence",
            "Figma",
            "A/B testing",
            "product analytics",
            "stakeholder management",
            "OKRs",
        ],
    }

    assert gh_dict == expected_greenhouse


def test_workday_emulator_sarah_chen_benchmark():
    sarah = build_sarah_chen_canonical_fixture()
    wd = emulate_workday(sarah)
    wd_dict = wd.model_dump()

    expected_workday = {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "phone": "(415) 555-0142",
        "country": "United States",
        "experience": [
            {
                "jobTitle": "Senior Product Manager",
                "company": "Zendex Inc.",
                "startDate": "2022-03-01",
                "endDate": None,
                "currentlyWorkHere": True,
                "description": (
                    "Led roadmap for enterprise analytics suite, $8M ARR in year one. "
                    "Managed team of 4 PMs and 18 engineers across 3 time zones. "
                    "Shipped 14 major releases with 99.2% on-time delivery."
                ),
            }
        ],
        "education": [
            {
                "degreeLevel": "Master's",
                "schoolName": "Stanford Graduate School of Business",
                "graduationYear": 2019,
            },
            {
                "degreeLevel": "Bachelor's",
                "schoolName": "UC Berkeley",
                "graduationYear": 2015,
            },
        ],
        "skills": ["SQL", "Python", "Tableau", "Jira", "Confluence", "Figma"],
    }

    assert wd_dict == expected_workday


def test_lever_emulator_sarah_chen_benchmark():
    sarah = build_sarah_chen_canonical_fixture()
    lv = emulate_lever(sarah)
    lv_dict = lv.model_dump()

    assert lv_dict["name"] == "Sarah Chen"
    assert lv_dict["contact"]["email"] == "sarah.chen@example.com"
    assert lv_dict["contact"]["phone"] == "(415) 555-0142"
    assert lv_dict["headline"] == "Senior Product Manager"
    assert lv_dict["positions"] == [
        {
            "title": "Senior Product Manager",
            "org": "Zendex Inc.",
            "start": "2022-03",
            "end": "Present",
            "summary": (
                "Led roadmap for enterprise analytics suite, $8M ARR in year one\n"
                "Managed team of 4 PMs and 18 engineers across 3 time zones\n"
                "Shipped 14 major releases with 99.2% on-time delivery"
            ),
        }
    ]
    assert lv_dict["schools"] == [
        {"name": "Stanford Graduate School of Business", "degree": "M.B.A.", "end": "2019"},
        {"name": "UC Berkeley", "degree": "B.S. Computer Science", "end": "2015"},
    ]
    # Verify Lever truncates tags to the first 4 skills only
    assert lv_dict["tags"] == ["SQL", "Python", "Tableau", "Jira"]
