"""Canary Probe PDF Generator for Live ATS Reverse-Engineering.

Generates 3 synthetic PDFs with deliberate coordinate and character traps to probe
live ATS parsers (Workday, Greenhouse, Lever, Taleo, iCIMS).
"""

from __future__ import annotations

import pathlib
import fitz  # PyMuPDF


def create_margin_clipping_canary(output_path: str) -> None:
    """Probe 1: Tests vertical header margin clipping boundaries."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter: 8.5 x 11 inches

    # Canary A: Placed at y = 20pt (0.28 in) -> Inside extreme margin
    page.insert_text(
        (72, 20),
        "CANARY_MARGIN_20PT_EMAIL: probe.alpha.20pt@canarytest.org",
        fontsize=10,
        fontname="helv",
    )

    # Canary B: Placed at y = 42pt (0.58 in) -> Just below 0.5 in
    page.insert_text(
        (72, 42),
        "CANARY_MARGIN_42PT_PHONE: (555) 019-4242",
        fontsize=10,
        fontname="helv",
    )

    # Canary C: Placed at y = 75pt (1.04 in) -> Inside normal body
    page.insert_text(
        (72, 75),
        "CANARY_MARGIN_75PT_NAME: Alex Rivera Canary",
        fontsize=16,
        fontname="hebo",
    )

    # Body
    page.insert_text((72, 110), "Experience", fontsize=14, fontname="hebo")
    page.insert_text(
        (72, 135),
        "Principal Systems Engineer | CloudCore Systems | 2021 - Present",
        fontsize=11,
        fontname="helv",
    )
    page.insert_text(
        (72, 155),
        "- Designed high-throughput distributed message processing clusters on AWS",
        fontsize=10,
        fontname="helv",
    )

    # Footer Canary: Placed at y = 770pt (0.3 in from bottom edge)
    page.insert_text(
        (72, 770),
        "CANARY_FOOTER_770PT: Confidential Candidate Profile",
        fontsize=9,
        fontname="helv",
    )

    doc.save(output_path)
    doc.close()
    print(f"Created: {output_path}")


def create_multicolumn_interleaving_canary(output_path: str) -> None:
    """Probe 2: Tests whether ATS interleaves two-column text across horizontal baselines."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Header
    page.insert_text((72, 54), "Marcus Vance Canary", fontsize=16, fontname="hebo")
    page.insert_text(
        (72, 72),
        "marcus.canary@example.com | (555) 234-5678",
        fontsize=10,
        fontname="helv",
    )

    # Left Column: x = 72 (width ~ 230pt)
    # Right Column: x = 340 (width ~ 200pt)
    # Both sit on the exact same vertical baselines (y = 120, 145, 170, 195)
    baselines = [
        (120, "Work Experience", "Technical Skills"),
        (145, "Senior Cloud Architect", "AWS, Kubernetes, Docker"),
        (170, "DataFlow Inc. | 2022 - Present", "Terraform, Apache Kafka"),
        (195, "- Spearheaded microservices migration", "Python, Go, PostgreSQL"),
    ]

    for y, left_txt, right_txt in baselines:
        page.insert_text((72, y), left_txt, fontsize=11, fontname="helv")
        page.insert_text((340, y), right_txt, fontsize=11, fontname="helv")

    doc.save(output_path)
    doc.close()
    print(f"Created: {output_path}")


def create_icons_and_soft_skills_canary(output_path: str) -> None:
    """Probe 3: Tests private-use Unicode icons and multi-word soft skills."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 54), "Elena Rostova Canary", fontsize=16, fontname="hebo")

    # Private use Unicode glyph \uf0e0 (FontAwesome envelope) followed by email
    # Some ATS drop the entire token or corrupt text
    page.insert_text(
        (72, 75),
        "\uf0e0 elena.canary@domain.org | \uf095 (555) 789-0123",
        fontsize=10,
        fontname="helv",
    )

    page.insert_text((72, 110), "Professional Summary", fontsize=14, fontname="hebo")
    page.insert_text(
        (72, 130),
        "Experienced software leader specializing in cross-functional stakeholder management and synergistic alignment.",
        fontsize=10,
        fontname="helv",
    )

    page.insert_text((72, 160), "Skills", fontsize=14, fontname="hebo")
    page.insert_text(
        (72, 180),
        "Python, Docker, strategic thought leadership, Kubernetes, agile velocity coaching",
        fontsize=10,
        fontname="helv",
    )

    doc.save(output_path)
    doc.close()
    print(f"Created: {output_path}")


if __name__ == "__main__":
    out_dir = pathlib.Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    create_margin_clipping_canary(str(out_dir / "canary_probe_1_margins.pdf"))
    create_multicolumn_interleaving_canary(str(out_dir / "canary_probe_2_multicolumn_interleaving.pdf"))
    create_icons_and_soft_skills_canary(str(out_dir / "canary_probe_3_icons_and_soft_skills.pdf"))
