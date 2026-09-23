# engines/export-engine/pdf_format.py
#
# WHAT: Deterministic PDF renderers and writers (Journey + Resume).
# WHY:  P4.1 split of the former 1004-line export god-module (CONSTITUTION
#       §4): one file per concern so layout bugs localize to one adapter.
# BREAKS IF DELETED: PDF exports disappear.

from __future__ import annotations

import logging
from pathlib import Path as _Path

_FONT_CANDIDATES = [
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),          # Linux
    ("arial.ttf", "arialbd.ttf"),                        # Windows
]

def _find_unicode_fonts():
    roots = [
        _Path("/usr/share/fonts/truetype/dejavu"),
        _Path("/usr/share/fonts/truetype/msttcorefonts"),
        _Path("C:/Windows/Fonts"),
    ]
    for root in roots:
        for regular, bold in _FONT_CANDIDATES:
            r, b = root / regular, root / bold
            if r.exists() and b.exists():
                return str(r), str(b)
        if (root / "DejaVuSans.ttf").exists():
            return str(root / "DejaVuSans.ttf"), str(root / "DejaVuSans-Bold.ttf")
    return None

_UNICODE_FONT = _find_unicode_fonts()

class _UnicodeFPDF:
    """Mixin: transparently swaps Helvetica for a Unicode-capable TTF
    (em-dashes, curly quotes, accents) when such a font exists on this
    machine. Falls back to core Helvetica otherwise — callers drawing
    exotic glyphs should sanitize first."""
    def set_font(self, family=None, style="", size=0):
        if family and family.lower() == "helvetica" and _UNICODE_FONT:
            key = "_dejavu_registered"
            if not getattr(self, key, False):
                self.add_font("DejaVuUnicode", "", _UNICODE_FONT[0])
                self.add_font("DejaVuUnicode", "B", _UNICODE_FONT[1])
                setattr(self, key, True)
            family = "DejaVuUnicode"
        return super().set_font(family, style, size)
from datetime import datetime
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

_EPOCH = datetime(2000, 1, 1)  # pinned so exports are byte-stable (E4)

def export_to_pdf(journey: dict[str, Any]) -> bytes:
    """
    Contract: render a Journey dict to a PDF document (bytes).
    Uses fpdf2 to generate a clean, multi-page PDF.

    Args:
        journey: a validated Journey dict.

    Returns:
        PDF bytes ready to write to disk or serve.

    Raises:
        ValueError: if the journey is missing required fields.
        ImportError: if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
        pdf_cls = type('_FPDF', (_UnicodeFPDF, FPDF), {})
    except ImportError as exc:
        raise ImportError(
            "pdfexport requires fpdf2: pip install fpdf2"
        ) from exc

    topic = journey.get("topic")
    level = journey.get("level", "beginner")
    cards = journey.get("cards", [])

    if not topic:
        raise ValueError("Journey must have a 'topic' field")
    if not cards:
        raise ValueError("Journey must contain at least one card")

    pdf = pdf_cls()
    pdf.set_creation_date(_EPOCH)  # byte-stability
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, topic, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Level badge
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(67, 97, 238)  # accent color
    pdf.cell(0, 8, f"Level: {level.title()}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    for i, card in enumerate(cards, start=1):
        # If not first card, add a page break if needed (fpdf handles automatically)
        if i > 1:
            pdf.add_page()

        # Card title
        pdf.set_font("Helvetica", "B", 14)
        card_id = card.get("id", str(i))
        title = card.get("title", f"Card {i}")
        pdf.cell(0, 10, f"Card {i}: {title}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Content
        pdf.set_font("Helvetica", "", 11)
        content = card.get("content", "")
        pdf.multi_cell(0, 6, content)
        pdf.ln(4)

        # Quiz question
        pdf.set_font("Helvetica", "B", 11)
        question = card.get("question", "")
        pdf.cell(0, 6, f"Quiz: {question}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Options
        pdf.set_font("Helvetica", "", 11)
        options = card.get("options", [])
        correct_option = card.get("correct_option", "")
        for j, opt in enumerate(options):
            label = f"{chr(65 + j)})"
            pdf.cell(8, 6, label)
            pdf.cell(0, 6, opt, new_x="END", new_y="NEXT")
        pdf.ln(3)

        # Correct answer and explanation
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(46, 196, 182)  # success color
        pdf.cell(0, 6, f"Correct: {correct_option}")
        pdf.ln(4)
        pdf.set_text_color(108, 117, 125)  # muted color
        explanation = card.get("explanation", "")
        pdf.multi_cell(0, 5, f"Explanation: {explanation}")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

    # Serialize to bytes
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def export_resume_to_pdf(resume: dict[str, Any]) -> bytes:
    """
    Contract: render a Resume dict to a PDF document (bytes).
    Uses fpdf2 to generate a professional resume PDF.

    Args:
        resume: a validated Resume dict.

    Returns:
        PDF bytes ready to write to disk or serve.

    Raises:
        ValueError: if the resume is missing required fields.
        ImportError: if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
        pdf_cls = type('_FPDF', (_UnicodeFPDF, FPDF), {})
    except ImportError as exc:
        raise ImportError(
            "pdfexport requires fpdf2: pip install fpdf2"
        ) from exc

    contact = resume.get("contact", {})
    summary = resume.get("summary", "")
    experience = resume.get("experience", [])
    education = resume.get("education", [])
    skills = resume.get("skills", [])
    projects = resume.get("projects", [])

    if not contact.get("name"):
        raise ValueError("Resume must have a contact.name field")
    if not experience:
        raise ValueError("Resume must contain at least one experience entry")

    pdf = pdf_cls()
    pdf.set_creation_date(_EPOCH)  # byte-stability
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    w = pdf.w - pdf.l_margin - pdf.r_margin  # usable width

    # Name
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(w, 12, contact.get("name", "Name"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Contact info
    pdf.set_font("Helvetica", "", 10)
    contact_parts = []
    for key in ["email", "phone", "location", "linkedin", "github"]:
        val = contact.get(key, "")
        if val:
            contact_parts.append(val)
    if contact_parts:
        pdf.cell(w, 6, "  |  ".join(contact_parts), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    # Summary
    if summary:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, "SUMMARY", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(w, 6, summary, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Experience
    if experience:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, "EXPERIENCE", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        for exp in experience:
            title = exp.get("title", "Title")
            company = exp.get("company", "Company")
            dates = exp.get("dates", "Dates")
            description = exp.get("description", "")

            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(w, 6, f"{title} | {company} | {dates}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            for line in description.split("\n"):
                line = line.strip()
                if line:
                    pdf.multi_cell(w, 5, f"- {line}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

    # Education
    if education:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, "EDUCATION", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        for edu in education:
            degree = edu.get("degree", "Degree")
            school = edu.get("school", "School")
            dates = edu.get("dates", "Dates")
            pdf.cell(w, 6, f"{degree} | {school} | {dates}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Skills
    if skills:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, "SKILLS", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(w, 6, ", ".join(skills), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Projects
    if projects:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, "PROJECTS", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        for proj in projects:
            proj_name = proj.get("name", "Project")
            desc = proj.get("description", "")
            tech = proj.get("tech", [])
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(w, 6, proj_name, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            if desc:
                pdf.multi_cell(w, 5, desc, new_x="LMARGIN", new_y="NEXT")
            if tech:
                pdf.cell(w, 5, f"Tech: {', '.join(tech)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

    # Serialize to bytes
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def export_to_pdf_file(journey: dict[str, Any], filepath: str) -> str:
    """
    Contract: write PDF export to a file.

    Args:
        journey: a validated Journey dict.
        filepath: path to write the .pdf file.

    Returns:
        The filepath that was written.
    """
    pdf_bytes = export_to_pdf(journey)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    logger.info("Wrote PDF export to %s (%d bytes)", filepath, len(pdf_bytes))
    return filepath


# ---------------------------------------------------------------------------
# Resume exports
# ---------------------------------------------------------------------------


def export_resume_to_pdf_file(resume: dict[str, Any], filepath: str) -> str:
    """
    Contract: write resume PDF export to a file.

    Args:
        resume: a validated Resume dict.
        filepath: path to write the .pdf file.

    Returns:
        The filepath that was written.
    """
    pdf_bytes = export_resume_to_pdf(resume)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    logger.info("Wrote resume PDF export to %s (%d bytes)", filepath, len(pdf_bytes))
    return filepath
