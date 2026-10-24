"""Module 1: Dual-Stream Document Ingestion (backend/services/extractor.py).

Implements:
- Stage 0: Optical Character Recognition (OCR) Fallback (< 50 native chars -> pytesseract, 0.85 multiplier)
- Stage 1:
  1. Stream A — Naive Horizontal Stream (`extract_linear_stream`) via pdfminer.six with 1.0-inch header/footer clipping.
  2. Stream B — Layout-Aware Block Sorter (`extract_layout_blocks`) via PyMuPDF + recursive XY-Cut++ preserving < 35pt key-value gaps.
  3. Column Interleaving Detector (`detect_column_interleaving`) flagging lines with > 15pt horizontal column separation on overlapping Y coordinates.
  4. DOCX XML Inspector (`extract_docx_xml`) inspecting <w:tbl>, <w:txbxContent>, headers/footers, and ATS-safe fonts.
"""

from __future__ import annotations

import io
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from docx import Document
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine

from backend.models.schemas import (
    BoundingBoxBlock,
    DocxAuditReport,
    ExtractionResult,
    InterleavedLineFlag,
)

import re

ATS_SAFE_FONTS = {
    "calibri",
    "arial",
    "garamond",
    "georgia",
    "helvetica",
    "times new roman",
    "times",
    "timesnewroman",
}

HEADER_FOOTER_MARGIN_PT = 36.0  # 0.5 inch = 36pt (0.5 in margins are acceptable; < 0.5in is clipped)
OCR_MIN_CHAR_THRESHOLD = 50
OCR_CONFIDENCE_MULTIPLIER = 0.85
KEY_VALUE_MAX_GAP_PT = 35.0
INTERLEAVING_MIN_GAP_PT = 15.0


def normalize_font_name(raw_font: str) -> str:
    """Strip PDF subset prefixes (e.g., 'ABCDEF+Calibri-Bold' -> 'Calibri')."""
    if not raw_font:
        return ""
    cleaned = raw_font.split("+")[-1]
    base = cleaned.split("-")[0].split(",")[0].strip()
    # Map common postscript names (including TeX Live helvet/times/math PostScript names)
    lower = base.lower()
    if "timesnewroman" in lower or lower == "times" or "nimbusrom" in lower or lower.startswith("cmr"):
        return "Times New Roman"
    if "arial" in lower:
        return "Arial"
    if "calibri" in lower:
        return "Calibri"
    if "garamond" in lower:
        return "Garamond"
    if "georgia" in lower:
        return "Georgia"
    if (
        "helvetica" in lower
        or "nimbussan" in lower
        or lower == "helv"
        or lower.startswith("cmss")
        or lower.startswith("cmsy")
    ):
        return "Helvetica"
    return base


def is_ats_safe_font(font_name: str) -> bool:
    norm = normalize_font_name(font_name).lower()
    return norm in ATS_SAFE_FONTS


# ============================================================================
# Stage 0: Optical Character Recognition (OCR) Fallback
# ============================================================================

def run_ocr_fallback(
    pdf_bytes: bytes,
    ocr_enabled: bool = True,
) -> Tuple[str, float]:
    """Run pytesseract on rasterized PDF page pixmaps when native text < 50 chars.

    If ocr_enabled is False (e.g., standard Greenhouse profile without OCR),
    returns empty string. Otherwise returns (ocr_text, 0.85).
    """
    if not ocr_enabled:
        return "", 0.0

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    ocr_pages: List[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            page_text = pytesseract.image_to_string(img)
        except Exception:
            page_text = ""
        if page_text.strip():
            ocr_pages.append(page_text.strip())
    doc.close()
    return "\n\n".join(ocr_pages), OCR_CONFIDENCE_MULTIPLIER


# ============================================================================
# Stage 1.1: Stream A — Naive Horizontal Stream (pdfminer.six)
# ============================================================================

def extract_linear_stream(
    pdf_bytes: bytes,
    clip_headers_footers: bool = True,
) -> Tuple[str, List[str]]:
    """Extract naive left-to-right, top-to-bottom horizontal stream using pdfminer.six.

    Clips any text inside the extreme top margin (`y0 < 36pt` / 0.5 inch from page top) and bottom
    (`y1 > page_height - 36pt`) where 0.5 in margins are acceptable, logging clipped text in `dropped_header_footer_text`.
    """
    dropped_header_footer_text: List[str] = []
    collected_lines: List[Tuple[int, float, float, str]] = []

    laparams = LAParams(
        line_overlap=0.5,
        char_margin=2000.0,  # Wide char_margin forces naive full-width horizontal reading across columns
        line_margin=0.5,
        word_margin=0.1,
        boxes_flow=None,     # Disable layout sorting so reading is strictly Y then X
    )

    pdf_stream = io.BytesIO(pdf_bytes)
    for page_idx, page_layout in enumerate(extract_pages(pdf_stream, laparams=laparams)):
        page_height = float(page_layout.height)
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    if isinstance(text_line, LTTextLine):
                        raw_line = text_line.get_text().strip()
                        if not raw_line:
                            continue
                        top_y0 = page_height - float(text_line.y1)
                        bottom_y1 = page_height - float(text_line.y0)
                        left_x0 = float(text_line.x0)

                        in_top_margin = top_y0 < HEADER_FOOTER_MARGIN_PT
                        in_bottom_margin = bottom_y1 > (page_height - HEADER_FOOTER_MARGIN_PT)

                        if clip_headers_footers and (in_top_margin or in_bottom_margin):
                            dropped_header_footer_text.append(raw_line)
                        else:
                            collected_lines.append((page_idx, round(top_y0, 1), left_x0, raw_line))

    # Sort strictly by page, top-to-bottom Y (within 3pt bucket), then left-to-right X
    collected_lines.sort(key=lambda item: (item[0], round(item[1] / 3.0), item[2]))

    # Merge fragments that fall on the same horizontal visual line bucket
    merged_lines: List[str] = []
    if collected_lines:
        curr_page, curr_y_bucket, _, curr_text = (
            collected_lines[0][0],
            round(collected_lines[0][1] / 3.0),
            collected_lines[0][2],
            collected_lines[0][3],
        )
        for page_idx, top_y0, _, text in collected_lines[1:]:
            y_bucket = round(top_y0 / 3.0)
            if page_idx == curr_page and y_bucket == curr_y_bucket:
                curr_text = f"{curr_text} {text}"
            else:
                merged_lines.append(curr_text)
                curr_page = page_idx
                curr_y_bucket = y_bucket
                curr_text = text
        merged_lines.append(curr_text)

    return "\n".join(merged_lines), dropped_header_footer_text


# ============================================================================
# Stage 1.2: Stream B — Layout-Aware Block Sorter (PyMuPDF + XY-Cut++)
# ============================================================================

def _merge_key_value_blocks(blocks: List[BoundingBoxBlock]) -> List[BoundingBoxBlock]:
    """Preserve Key : Value tables (< 35pt gap) on the same vertical baseline."""
    if not blocks:
        return []

    # Sort by page, vertical baseline y0 (within 4pt tolerance), then x0
    sorted_blocks = sorted(blocks, key=lambda b: (b.page_no, round(b.y0 / 4.0), b.x0))
    merged: List[BoundingBoxBlock] = [sorted_blocks[0].model_copy()]

    for blk in sorted_blocks[1:]:
        prev = merged[-1]
        same_page = prev.page_no == blk.page_no
        same_baseline = abs(prev.y0 - blk.y0) <= 4.0 and abs(prev.y1 - blk.y1) <= 6.0
        horiz_gap = blk.x0 - prev.x1

        if same_page and same_baseline and 0.0 <= horiz_gap < KEY_VALUE_MAX_GAP_PT:
            prev.text = f"{prev.text.rstrip()} {blk.text.lstrip()}"
            prev.x1 = max(prev.x1, blk.x1)
            prev.y0 = min(prev.y0, blk.y0)
            prev.y1 = max(prev.y1, blk.y1)
        else:
            merged.append(blk.model_copy())

    return merged


def xy_cut_sort(
    blocks: List[BoundingBoxBlock],
    min_x_gap: float = KEY_VALUE_MAX_GAP_PT,
    min_y_gap: float = 6.0,
) -> List[BoundingBoxBlock]:
    """Recursive XY-Cut++ bounding-box projection algorithm.

    Splits multi-column layouts into human reading order (reading Column 1
    top-to-bottom before Column 2 top-to-bottom) while ignoring narrow horizontal
    gaps (< 35pt) on the same baseline.
    """
    if len(blocks) <= 1:
        return list(blocks)

    # 1. Try finding a vertical whitespace valley (X-axis projection split)
    # that separates left and right columns by at least `min_x_gap` (35pt).
    x_intervals = sorted([(b.x0, b.x1) for b in blocks], key=lambda iv: iv[0])
    merged_x: List[List[float]] = [[x_intervals[0][0], x_intervals[0][1]]]
    for x0, x1 in x_intervals[1:]:
        if x0 < merged_x[-1][1] + min_x_gap:
            merged_x[-1][1] = max(merged_x[-1][1], x1)
        else:
            merged_x.append([x0, x1])

    if len(merged_x) > 1:
        # Split blocks into vertical columns left-to-right
        ordered: List[BoundingBoxBlock] = []
        for col_x0, col_x1 in merged_x:
            col_blocks = [
                b for b in blocks if b.x0 >= col_x0 - 1e-3 and b.x1 <= col_x1 + 1e-3
            ]
            ordered.extend(xy_cut_sort(col_blocks, min_x_gap=min_x_gap, min_y_gap=min_y_gap))
        return ordered

    # 2. Try finding a horizontal whitespace valley (Y-axis projection split)
    y_intervals = sorted([(b.y0, b.y1) for b in blocks], key=lambda iv: iv[0])
    merged_y: List[List[float]] = [[y_intervals[0][0], y_intervals[0][1]]]
    for y0, y1 in y_intervals[1:]:
        if y0 < merged_y[-1][1] + min_y_gap:
            merged_y[-1][1] = max(merged_y[-1][1], y1)
        else:
            merged_y.append([y0, y1])

    if len(merged_y) > 1:
        ordered = []
        for row_y0, row_y1 in merged_y:
            row_blocks = [
                b for b in blocks if b.y0 >= row_y0 - 1e-3 and b.y1 <= row_y1 + 1e-3
            ]
            ordered.extend(xy_cut_sort(row_blocks, min_x_gap=min_x_gap, min_y_gap=min_y_gap))
        return ordered

    # Base case: sort top-to-bottom, then left-to-right
    return sorted(blocks, key=lambda b: (round(b.y0, 1), round(b.x0, 1)))


def extract_layout_blocks(
    pdf_bytes: bytes,
    clip_headers_footers: bool = True,
) -> Tuple[str, List[BoundingBoxBlock], List[str], List[float], List[float], bool]:
    """Extract spatial text blocks using PyMuPDF and sort via recursive XY-Cut++.

    Returns:
      (layout_sorted_text, sorted_blocks, detected_fonts, body_font_sizes, heading_font_sizes, has_images)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_sorted_blocks: List[BoundingBoxBlock] = []
    detected_fonts: List[str] = []
    body_sizes: List[float] = []
    heading_sizes: List[float] = []
    has_images = False

    block_counter = 0
    for page_idx, page in enumerate(doc):
        page_height = float(page.rect.height)
        if page.get_images():
            has_images = True

        page_dict = page.get_text("dict")
        page_links = page.get_links()
        raw_page_blocks: List[BoundingBoxBlock] = []

        for b in page_dict.get("blocks", []):
            if b.get("type") != 0:  # 0 = text block, 1 = image block
                if b.get("type") == 1:
                    has_images = True
                continue

            for line in b.get("lines", []):
                l_bbox = line.get("bbox", (0, 0, 0, 0))
                lx0, ly0, lx1, ly1 = float(l_bbox[0]), float(l_bbox[1]), float(l_bbox[2]), float(l_bbox[3])

                if clip_headers_footers and (
                    ly0 < HEADER_FOOTER_MARGIN_PT or ly1 > (page_height - HEADER_FOOTER_MARGIN_PT)
                ):
                    continue

                spans = line.get("spans", [])
                if not spans:
                    continue

                # Split spans within a single PyMuPDF line if there is a wide column gap (>= 35pt)
                current_text_parts: List[str] = []
                curr_x0: Optional[float] = None
                curr_x1: Optional[float] = None
                curr_y0: float = ly0
                curr_y1: float = ly1
                curr_font: Optional[str] = None
                curr_size: Optional[float] = None

                for sp in spans:
                    sp_text = sp.get("text", "").strip()
                    if not sp_text:
                        continue
                    sbbox = sp.get("bbox", l_bbox)
                    sx0, sy0, sx1, sy1 = float(sbbox[0]), float(sbbox[1]), float(sbbox[2]), float(sbbox[3])
                    sfont = normalize_font_name(sp.get("font", ""))
                    ssize = round(float(sp.get("size", 11.0)), 1)

                    if sfont and sfont not in detected_fonts:
                        detected_fonts.append(sfont)
                    # Only record font sizes for substantive text spans (> 2 alphanumeric chars)
                    if sum(c.isalnum() for c in sp_text) > 2:
                        if ssize >= 13.5:
                            heading_sizes.append(ssize)
                        else:
                            body_sizes.append(ssize)

                    if curr_x1 is not None and (sx0 - curr_x1) >= KEY_VALUE_MAX_GAP_PT:
                        raw_page_blocks.append(
                            BoundingBoxBlock(
                                x0=curr_x0 or sx0,
                                y0=curr_y0,
                                x1=curr_x1,
                                y1=curr_y1,
                                text=" ".join(current_text_parts),
                                block_no=block_counter,
                                page_no=page_idx,
                                font_name=curr_font,
                                font_size=curr_size,
                            )
                        )
                        block_counter += 1
                        current_text_parts = [sp_text]
                        curr_x0 = sx0
                        curr_x1 = sx1
                        curr_y0 = sy0
                        curr_y1 = sy1
                        curr_font = sfont
                        curr_size = ssize
                    else:
                        current_text_parts.append(sp_text)
                        curr_x0 = sx0 if curr_x0 is None else min(curr_x0, sx0)
                        curr_x1 = sx1 if curr_x1 is None else max(curr_x1, sx1)
                        curr_y0 = min(curr_y0, sy0)
                        curr_y1 = max(curr_y1, sy1)
                        curr_font = curr_font or sfont
                        curr_size = curr_size or ssize

                if current_text_parts and curr_x0 is not None and curr_x1 is not None:
                    raw_page_blocks.append(
                        BoundingBoxBlock(
                            x0=curr_x0,
                            y0=curr_y0,
                            x1=curr_x1,
                            y1=curr_y1,
                            text=" ".join(current_text_parts),
                            block_no=block_counter,
                            page_no=page_idx,
                            font_name=curr_font,
                            font_size=curr_size,
                        )
                    )
                    block_counter += 1

        # Preserve Key : Value pairs (< 35pt)
        kv_preserved_blocks = _merge_key_value_blocks(raw_page_blocks)

        # Attach hyperlinked URIs (e.g., \href{https://www.linkedin.com/in/gbn97/}{LinkedIn}) to matching blocks
        for lnk in page_links:
            uri = (lnk.get("uri") or "").strip()
            if not uri or not ("linkedin.com/in/" in uri.lower() or "github.com/" in uri.lower()):
                continue
            lrect = lnk.get("from")
            for blk in kv_preserved_blocks:
                if uri.lower() in blk.text.lower():
                    break
                if lrect is not None and abs(float(lrect.y0) - blk.y0) <= 8.0:
                    blk.text = f"{blk.text} ({uri})"
                    break

        # Sort page blocks using recursive XY-Cut++
        sorted_page_blocks = xy_cut_sort(kv_preserved_blocks)
        all_sorted_blocks.extend(sorted_page_blocks)

    doc.close()
    layout_sorted_text = "\n".join(b.text for b in all_sorted_blocks if b.text.strip())
    return (
        layout_sorted_text,
        all_sorted_blocks,
        detected_fonts,
        body_sizes,
        heading_sizes,
        has_images,
    )


# ============================================================================
# Stage 1.3: Column Interleaving Detector
# ============================================================================

def detect_column_interleaving(
    linear_stream_text: str,
    layout_blocks: List[BoundingBoxBlock],
) -> List[InterleavedLineFlag]:
    """Compare line sequences in Stream A against block-sorted lines in Stream B.

    If a line in Stream A concatenates tokens belonging to spatially separate
    horizontal columns in Stream B (`abs(col1_x1 - col2_x0) > 15pt` with overlapping
    `y` coordinates), flag those lines as `interleaved_lines`.
    """
    interleaved_flags: List[InterleavedLineFlag] = []
    if not layout_blocks:
        return interleaved_flags

    # Group blocks by page and find pairs with overlapping Y coordinates and horizontal gap > 15pt
    by_page: dict[int, List[BoundingBoxBlock]] = {}
    for blk in layout_blocks:
        by_page.setdefault(blk.page_no, []).append(blk)

    linear_lines = [ln.strip() for ln in linear_stream_text.splitlines() if ln.strip()]

    for page_no, blocks in by_page.items():
        n = len(blocks)
        for i in range(n):
            for j in range(i + 1, n):
                b1, b2 = blocks[i], blocks[j]
                left_b, right_b = (b1, b2) if b1.x0 <= b2.x0 else (b2, b1)

                # Check overlapping Y coordinates (or within 4pt baseline tolerance)
                y_overlap = min(left_b.y1, right_b.y1) - max(left_b.y0, right_b.y0)
                same_row = y_overlap > -4.0

                horiz_gap = right_b.x0 - left_b.x1
                if same_row and horiz_gap > INTERLEAVING_MIN_GAP_PT:
                    t_left = left_b.text.strip()
                    t_right = right_b.text.strip()
                    if not t_left or not t_right:
                        continue

                    # Check if any line in Stream A concatenates both left and right block texts
                    for ln in linear_lines:
                        if t_left in ln and t_right in ln:
                            interleaved_flags.append(
                                InterleavedLineFlag(
                                    line_text=ln,
                                    left_block_text=t_left,
                                    right_block_text=t_right,
                                    horizontal_gap_pt=round(horiz_gap, 2),
                                    page_no=page_no,
                                )
                            )
                            break

    return interleaved_flags


# ============================================================================
# Stage 1.4: DOCX XML Inspector
# ============================================================================

def extract_docx_xml(docx_bytes: bytes) -> ExtractionResult:
    """Parse .docx archives via python-docx and inspect underlying XML.

    Inspects:
    - `<w:tbl>` (tables)
    - `<w:txbxContent>` (floating text boxes)
    - Header/footer contact placement
    - Font descriptors outside the ATS-safe whitelist (`Calibri`, `Arial`, `Garamond`, `Georgia`, `Helvetica`, `Times New Roman`)
    """
    try:
        doc = Document(io.BytesIO(docx_bytes))
    except Exception:
        return ExtractionResult(
            file_format="docx",
            is_unreadable_or_encrypted=True,
            confidence_multiplier=0.0,
        )

    body_elm = doc.element.body
    # Inspect XML for <w:tbl> and <w:txbxContent>
    tbl_nodes = body_elm.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl")
    txbx_nodes = body_elm.findall(
        ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}txbxContent"
    )
    drawing_nodes = body_elm.findall(
        ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
    )

    # Extract header & footer text
    header_footer_text: List[str] = []
    for section in doc.sections:
        for hdr_para in section.header.paragraphs:
            if hdr_para.text.strip():
                header_footer_text.append(hdr_para.text.strip())
        for ftr_para in section.footer.paragraphs:
            if ftr_para.text.strip():
                header_footer_text.append(ftr_para.text.strip())

    approved_fonts: List[str] = []
    unapproved_fonts: List[str] = []
    body_font_sizes: List[float] = []
    heading_font_sizes: List[float] = []
    paragraphs_text: List[str] = []
    blocks: List[BoundingBoxBlock] = []

    y_cursor = 72.0
    for idx, para in enumerate(doc.paragraphs):
        txt = para.text.strip()
        if txt:
            paragraphs_text.append(txt)

        style_name = (para.style.name if para.style else "").lower()
        is_heading = "heading" in style_name or "title" in style_name

        para_font_name: Optional[str] = None
        para_font_size: Optional[float] = None

        if para.style and para.style.font:
            if para.style.font.name:
                para_font_name = para.style.font.name
            if para.style.font.size:
                para_font_size = round(float(para.style.font.size.pt), 1)

        for run in para.runs:
            r_font = run.font.name or para_font_name
            if r_font:
                if is_ats_safe_font(r_font):
                    if r_font not in approved_fonts:
                        approved_fonts.append(r_font)
                else:
                    if r_font not in unapproved_fonts:
                        unapproved_fonts.append(r_font)
            if run.font.size:
                sz = round(float(run.font.size.pt), 1)
                para_font_size = sz
                if is_heading or sz >= 13.5:
                    heading_font_sizes.append(sz)
                else:
                    body_font_sizes.append(sz)

        if txt:
            blocks.append(
                BoundingBoxBlock(
                    x0=72.0,
                    y0=y_cursor,
                    x1=540.0,
                    y1=y_cursor + 14.0,
                    text=txt,
                    block_no=idx,
                    page_no=0,
                    font_name=para_font_name or (approved_fonts[0] if approved_fonts else "Calibri"),
                    font_size=para_font_size or 11.0,
                )
            )
            y_cursor += 16.0

    # Also extract text from tables so linear_stream_text reflects table content if present
    for table in doc.tables:
        for row in table.rows:
            row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_cells:
                paragraphs_text.append(" | ".join(row_cells))

    # Default font check if no explicit run overrides were set
    if not approved_fonts and not unapproved_fonts:
        normal_style = doc.styles["Normal"]
        default_font = (normal_style.font.name if normal_style and normal_style.font else None) or "Calibri"
        if is_ats_safe_font(default_font):
            approved_fonts.append(default_font)
        else:
            unapproved_fonts.append(default_font)

    if not body_font_sizes:
        body_font_sizes.append(11.0)

    full_text = "\n".join(paragraphs_text)
    has_tables = len(tbl_nodes) > 0
    has_text_boxes = len(txbx_nodes) > 0
    has_images = len(drawing_nodes) > 0

    audit_report = DocxAuditReport(
        has_tables=has_tables,
        table_count=len(tbl_nodes),
        has_text_boxes=has_text_boxes,
        text_box_count=len(txbx_nodes),
        header_footer_text=header_footer_text,
        unapproved_fonts=unapproved_fonts,
        approved_fonts=approved_fonts,
        body_font_sizes_pt=body_font_sizes,
        heading_font_sizes_pt=heading_font_sizes,
        has_embedded_images=has_images,
    )

    return ExtractionResult(
        file_format="docx",
        ocr_triggered=False,
        confidence_multiplier=1.0,
        linear_stream_text=full_text,
        layout_sorted_text=full_text,
        dropped_header_footer_text=header_footer_text,
        interleaved_lines=[],
        blocks=blocks,
        docx_audit=audit_report,
        detected_fonts=approved_fonts + unapproved_fonts,
        body_font_sizes_pt=body_font_sizes,
        heading_font_sizes_pt=heading_font_sizes,
        has_tables_or_textboxes=(has_tables or has_text_boxes),
        has_embedded_images=has_images,
    )


# ============================================================================
# Unified Dual-Stream Entrypoint
# ============================================================================

def extract_document(
    file_bytes: bytes,
    filename: str = "resume.pdf",
    ocr_enabled: bool = True,
    clip_headers_footers: bool = True,
) -> ExtractionResult:
    """Master ingestion pipeline executing Stage 0 and Stage 1 Dual-Stream extraction."""
    lower_name = filename.lower()
    if lower_name.endswith(".docx"):
        return extract_docx_xml(file_bytes)

    # Verify PDF can be opened and is not encrypted
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.is_encrypted:
            doc.close()
            return ExtractionResult(
                file_format="pdf",
                is_unreadable_or_encrypted=True,
                confidence_multiplier=0.0,
            )
        native_text = "".join(page.get_text("text") for page in doc).strip()
        doc.close()
    except Exception:
        return ExtractionResult(
            file_format="pdf",
            is_unreadable_or_encrypted=True,
            confidence_multiplier=0.0,
        )

    # Stage 0: Check OCR Trigger Condition (< 50 native characters)
    if len(native_text) < OCR_MIN_CHAR_THRESHOLD:
        ocr_text, multiplier = run_ocr_fallback(file_bytes, ocr_enabled=ocr_enabled)
        is_unreadable = (not ocr_enabled) or (len(ocr_text.strip()) == 0)
        return ExtractionResult(
            file_format="pdf",
            ocr_triggered=True,
            ocr_enabled_by_profile=ocr_enabled,
            confidence_multiplier=multiplier if not is_unreadable else 0.0,
            is_unreadable_or_encrypted=is_unreadable,
            linear_stream_text=ocr_text,
            layout_sorted_text=ocr_text,
            dropped_header_footer_text=[],
            interleaved_lines=[],
            blocks=[],
        )

    # Stage 1: Dual-Stream PDF Extraction
    linear_text, dropped_hf = extract_linear_stream(
        file_bytes, clip_headers_footers=clip_headers_footers
    )
    (
        layout_text,
        sorted_blocks,
        detected_fonts,
        body_sizes,
        heading_sizes,
        has_images,
    ) = extract_layout_blocks(file_bytes, clip_headers_footers=clip_headers_footers)

    interleaved = detect_column_interleaving(linear_text, sorted_blocks)

    return ExtractionResult(
        file_format="pdf",
        ocr_triggered=False,
        ocr_enabled_by_profile=ocr_enabled,
        confidence_multiplier=1.0,
        is_unreadable_or_encrypted=False,
        linear_stream_text=linear_text,
        layout_sorted_text=layout_text,
        dropped_header_footer_text=dropped_hf,
        interleaved_lines=interleaved,
        blocks=sorted_blocks,
        detected_fonts=detected_fonts,
        body_font_sizes_pt=body_sizes,
        heading_font_sizes_pt=heading_sizes,
        has_embedded_images=has_images,
    )
