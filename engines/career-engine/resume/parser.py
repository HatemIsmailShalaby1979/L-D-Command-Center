# engines/career-engine/resume/parser.py
#
# WHAT: Parse uploaded PDF/DOCX resume files into a Resume dict.
# WHY:  Users need to upload existing resumes and have them converted
#       into the structured schema format. This is a parsing task —
#       it extracts what's present and leaves gaps null with confidence
#       flags, rather than inventing plausible-sounding content.
# BREAKS IF DELETED: Users can't upload resumes for enhancement.
#       Manual entry would be required.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE = "high"
MEDIUM_CONFIDENCE = "medium"
LOW_CONFIDENCE = "low"
UNKNOWN = "unknown"


@dataclass
class ConfidenceFlag:
    """
    Contract: track which fields were extracted with what confidence.

    Fields:
      - field: the field path (e.g., "contact.name", "experience[0].title")
      - confidence: one of HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, LOW_CONFIDENCE, UNKNOWN
      - source: how the value was extracted (e.g., "header_pattern", "table")
    """
    field: str
    confidence: str
    source: str


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(file_path: Path) -> str:
    """
    Contract: extract raw text from a PDF file.

    Returns:
        The extracted text string.
    """
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except ImportError:
        logger.error("pdfplumber not installed — cannot parse PDF")
        raise ImportError("pdfplumber is required for PDF parsing: pip install pdfplumber")
    except Exception as e:
        logger.error("Failed to parse PDF: %s", e)
        raise


def _extract_text_from_docx(file_path: Path) -> str:
    """
    Contract: extract raw text from a DOCX file.

    Returns:
        The extracted text string.
    """
    try:
        from docx import Document
        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        logger.error("python-docx not installed — cannot parse DOCX")
        raise ImportError("python-docx is required for DOCX parsing: pip install python-docx")
    except Exception as e:
        logger.error("Failed to parse DOCX: %s", e)
        raise


def parse_text(text: str) -> tuple[dict[str, Any], list[ConfidenceFlag]]:
    """
    Contract: parse raw resume text into a Resume dict with confidence flags.

    Uses pattern matching and heuristics — NOT the model layer.
    Fields that can't be extracted with reasonable confidence are left
    null/empty, and flagged in the confidence list.

    Args:
        text: raw text extracted from a PDF or DOCX resume file.

    Returns:
        A tuple of (resume_dict, confidence_flags).
        resume_dict may have None/empty values for missing fields.
        confidence_flags lists all fields with their confidence levels.
    """
    flags: list[ConfidenceFlag] = []
    resume: dict[str, Any] = {
        "contact": {
            "name": None,
            "email": None,
            "phone": None,
            "location": None,
            "linkedin": None,
            "github": None,
        },
        "summary": None,
        "experience": [],
        "education": [],
        "skills": [],
        "projects": [],
    }

    lines = text.split("\n")
    lines = [line.strip() for line in lines if line.strip()]

    # --- Contact parsing ---
    resume["contact"] = _parse_contact(lines, flags)

    # --- Section parsing ---
    experience, education, skills, projects, summary = _parse_sections(lines)

    resume["experience"] = experience
    resume["education"] = education
    resume["skills"] = skills
    resume["projects"] = projects
    resume["summary"] = summary

    # Fill in any None fields with empty values for schema compliance
    _fill_empty_fields(resume, flags)

    return resume, flags


def _parse_contact(lines: list[str], flags: list[ConfidenceFlag]) -> dict[str, Any]:
    """
    Contract: extract contact information from resume text.

    Args:
        lines: list of text lines from the resume.
        flags: list to append confidence flags.

    Returns:
        Contact dict with extracted fields (may contain None).
    """
    contact = {
        "name": None,
        "email": None,
        "phone": None,
        "location": None,
        "linkedin": None,
        "github": None,
    }

    # Email patterns (high confidence)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    for line in lines:
        match = re.search(email_pattern, line)
        if match and not contact["email"]:
            contact["email"] = match.group(0)
            flags.append(ConfidenceFlag("contact.email", HIGH_CONFIDENCE, "email_pattern"))

    # Phone patterns (medium confidence)
    phone_pattern = r'\+?[\d\s\-\(\)]{7,20}'
    for line in lines:
        if contact["email"] and contact["email"] in line:
            match = re.search(phone_pattern, line)
            if match and not contact["phone"]:
                phone = match.group(0).strip()
                # Filter out things that look like dates
                if not re.match(r'^19\d{2}|20\d{2}', phone):
                    contact["phone"] = phone
                    flags.append(ConfidenceFlag("contact.phone", MEDIUM_CONFIDENCE, "phone_pattern"))
                    break

    # LinkedIn patterns (high confidence)
    linkedin_pattern = r'(?:linkedin\.com/in/|LinkedIn)[\w/\-]+'
    for line in lines:
        match = re.search(linkedin_pattern, line, re.IGNORECASE)
        if match and not contact["linkedin"]:
            contact["linkedin"] = match.group(0)
            flags.append(ConfidenceFlag("contact.linkedin", HIGH_CONFIDENCE, "linkedin_pattern"))

    # GitHub patterns (high confidence)
    github_pattern = r'(?:github\.com/|GitHub)[\w/\-]+'
    for line in lines:
        match = re.search(github_pattern, line, re.IGNORECASE)
        if match and not contact["github"]:
            contact["github"] = match.group(0)
            flags.append(ConfidenceFlag("contact.github", HIGH_CONFIDENCE, "github_pattern"))

    # Location patterns (medium confidence)
    location_pattern = r'\b([A-Z][a-z]+\s+[A-Z][a-z]+\s*,\s*[A-Z]{2})\b'
    for line in lines:
        if contact["location"]:
            break
        match = re.search(location_pattern, line)
        if match:
            contact["location"] = match.group(1)
            flags.append(ConfidenceFlag("contact.location", MEDIUM_CONFIDENCE, "location_pattern"))

    # Name detection (first non-empty line is often the name)
    for line in lines[:5]:
        # Skip lines that look like email/phone
        if '@' in line or re.search(phone_pattern, line):
            continue
        # Skip lines that look like URLs
        if line.startswith(('http', 'www', 'linkedin', 'github')):
            continue
        # Skip lines that contain email pattern
        if re.search(email_pattern, line):
            continue
        # Skip very short or very long lines
        if 3 < len(line) < 50:
            # Check if it looks like a name (title case or all caps)
            if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+', line) or re.match(r'^[A-Z\s]+$', line):
                contact["name"] = line
                flags.append(ConfidenceFlag("contact.name", MEDIUM_CONFIDENCE, "first_line_heuristic"))
                break

    return contact


def _parse_sections(lines: list[str]) -> tuple[list[dict], list[dict], list[str], list[dict], Optional[str]]:
    """
    Contract: parse resume into experience, education, skills, projects, and summary sections.

    Args:
        lines: list of text lines from the resume.

    Returns:
        Tuple of (experience, education, skills, projects, summary).
    """
    experience = []
    education = []
    skills = []
    projects = []
    summary = None

    # Section keywords
    section_keywords = {
        'experience': ['experience', 'work history', 'employment', 'professional experience', 'work experience'],
        'education': ['education', 'academic', 'degrees', 'qualification', 'qualifications'],
        'skills': ['skills', 'technical skills', 'competencies', 'core competencies'],
        'projects': ['projects', 'portfolio', 'personal projects', 'relevant projects'],
        'summary': ['summary', 'profile', 'objective', 'professional summary', 'career summary'],
    }

    # First pass: identify sections
    current_section = None
    section_lines: dict[str, list[str]] = {k: [] for k in section_keywords}

    for line in lines:
        line_lower = line.lower().strip()

        # Check for section headers
        found_section = None
        for section, keywords in section_keywords.items():
            if any(line_lower == kw or line_lower.startswith(kw + ':') for kw in keywords):
                # Switch to this section if it's the first or previous has content
                if current_section is None or section_lines[current_section]:
                    current_section = section
                found_section = section
                break

        if found_section:
            # Start collecting lines for this section
            pass
        else:
            # Add line to current section
            if current_section:
                section_lines[current_section].append(line)
            else:
                # Pre-header text is likely summary/profile
                section_lines['summary'].append(line)

    # Second pass: parse each section
    for section, section_lines_list in section_lines.items():
        if not section_lines_list:
            continue

        if section == 'experience':
            experience = _parse_experience(section_lines_list)
        elif section == 'education':
            education = _parse_education(section_lines_list)
        elif section == 'skills':
            skills = _parse_skills(section_lines_list)
        elif section == 'projects':
            projects = _parse_projects(section_lines_list)
        elif section == 'summary':
            summary = _parse_summary(section_lines_list)

    return experience, education, skills, projects, summary


def _parse_experience(lines: list[str]) -> list[dict[str, str]]:
    """
    Contract: parse experience section into list of experience dicts.

    Args:
        lines: text lines from the experience section.

    Returns:
        List of experience dicts with title, company, dates, description.
    """
    experience = []

    # Try to find date patterns that indicate job boundaries
    date_pattern = r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|(?:19|20)\d{2}[–-](?:19|20)\d{2}|\d{4}[–-]\d{4}|Present)\b'

    # Split by date patterns to separate job entries
    job_entries = []
    current_entry_lines = []

    for line in lines:
        if re.search(date_pattern, line, re.IGNORECASE):
            if current_entry_lines:
                job_entries.append(current_entry_lines)
            current_entry_lines = [line]
        else:
            current_entry_lines.append(line)

    if current_entry_lines:
        job_entries.append(current_entry_lines)

    # Parse each job entry
    for entry_lines in job_entries:
        if len(entry_lines) < 1:
            continue

        title = None
        company = None
        dates = None
        description_lines = []

        # First line should have title/company/dates
        first_line = entry_lines[0]
        parts = re.split(r'\s*\|\s*', first_line)

        if len(parts) >= 3:
            # Format: Title | Company | Dates
            title = parts[0].strip()
            company = parts[1].strip()
            dates = parts[2].strip()
        elif len(parts) == 2:
            # Could be "Title | Company" or "Title | Dates"
            # Check if second part looks like dates
            if re.match(r'^\d{4}', parts[1]):
                title = parts[0].strip()
                dates = parts[1].strip()
            else:
                title = parts[0].strip()
                company = parts[1].strip()
        else:
            # Single part - try to extract what we can
            title = first_line.strip()

        # Remaining lines are description
        for line in entry_lines[1:]:
            if line.startswith(('-', '•', '*')):
                line = line.lstrip('-•* ').strip()
            if line:
                description_lines.append(line)

        if title or company:
            experience.append({
                "title": title or "",
                "company": company or "",
                "dates": dates or "",
                "description": "\n".join(description_lines[:10]).strip(),
            })

    return experience


def _parse_education(lines: list[str]) -> list[dict[str, str]]:
    """
    Contract: parse education section into list of education dicts.

    Args:
        lines: text lines from the education section.

    Returns:
        List of education dicts with degree, school, dates.
    """
    education = []

    date_pattern = r'\b((?:19|20)\d{2}[–-](?:19|20)\d{2}|\d{4})\b'
    degree_keywords = ['bachelor', 'master', 'phd', 'doctorate', 'associate', 'diploma', 'certification']

    # Group lines into education entries
    entries = []
    current_entry = []

    for line in lines:
        if re.search(date_pattern, line):
            if current_entry:
                entries.append(current_entry)
            current_entry = [line]
        else:
            current_entry.append(line)

    if current_entry:
        entries.append(current_entry)

    # Parse each entry
    for entry_lines in entries:
        degree = None
        school = None
        dates = None

        # Join all lines and split by |
        full_line = " ".join(entry_lines)

        # Try to extract dates first
        date_match = re.search(date_pattern, full_line)
        if date_match:
            dates = date_match.group(1)

        # Split by | delimiter
        parts = re.split(r'\s*\|\s*', full_line)

        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            lower_part = part.lower()

            # Check for degree indicators
            if any(kw in lower_part for kw in degree_keywords):
                if degree is None:
                    degree = part
            elif school is None:
                # This is likely the school name
                school = part

        if degree or school:
            education.append({
                "degree": degree or "",
                "school": school or "",
                "dates": dates or "",
            })

    return education


def _parse_skills(lines: list[str]) -> list[str]:
    """
    Contract: extract skills from the skills section.

    Args:
        lines: text lines from the skills section.

    Returns:
        List of skill strings.
    """
    skills = []

    for line in lines:
        # Handle comma-separated skills
        if ',' in line or ';' in line:
            for skill in re.split(r'[,;]', line):
                skill = skill.strip()
                if skill and len(skill) < 50:
                    skills.append(skill)
        # Handle bullet-point skills
        elif line.startswith(('•', '-', '*', '–')):
            skill = line.lstrip('•-*–').strip()
            if skill and len(skill) < 50:
                skills.append(skill)
        # Handle single-line skills
        elif len(line) < 50 and not line.lower().startswith(('years', 'total')):
            skills.append(line.strip())

    # Remove duplicates while preserving order
    seen = set()
    unique_skills = []
    for skill in skills:
        if skill.lower() not in seen:
            seen.add(skill.lower())
            unique_skills.append(skill)

    return unique_skills


def _parse_projects(lines: list[str]) -> list[dict[str, Any]]:
    """
    Contract: extract projects from the projects section.

    Args:
        lines: text lines from the projects section.

    Returns:
        List of project dicts with name, description, tech.
    """
    projects = []

    # Skip the section header itself
    section_headers = ['projects', 'portfolio', 'personal projects', 'relevant projects']

    for line in lines:
        lower_line = line.lower().strip()

        # Skip section headers
        if lower_line in section_headers or any(lower_line.startswith(h + ':') for h in section_headers):
            continue

        # Skip lines that are just bullets
        if line.startswith(('•', '-', '*', '–')):
            line = line.lstrip('•-*–').strip()

        # Look for project names (often followed by colon and description)
        if line and not line.lower().startswith(('using', 'with', 'built', 'developed')):
            # Try to extract project name
            parts = re.split(r'\s*:\s*', line, maxsplit=1)
            if parts:
                name = parts[0].strip()
                if name and len(name) < 80 and not name.lower().startswith(('using', 'with')):
                    description = parts[1].strip() if len(parts) > 1 else ""
                    projects.append({
                        "name": name,
                        "description": description,
                        "tech": [],
                    })

    return projects


def _parse_summary(lines: list[str]) -> Optional[str]:
    """
    Contract: extract professional summary from pre-header text.

    Args:
        lines: text lines before any section headers.

    Returns:
        Summary string or None if not found.
    """
    if not lines:
        return None

    # Join and clean up
    summary = " ".join(line.strip() for line in lines[:5])
    summary = re.sub(r'\s+', ' ', summary).strip()

    if len(summary) < 10:
        return None

    return summary


def _fill_empty_fields(resume: dict[str, Any], flags: list[ConfidenceFlag]) -> None:
    """
    Contract: ensure all schema-required fields exist, filling None with empty values.

    Args:
        resume: the resume dict to fill.
        flags: list to append confidence flags for empty fields.
    """
    # Contact
    for field in ["name", "email", "phone", "location", "linkedin", "github"]:
        if resume["contact"].get(field) is None:
            resume["contact"][field] = ""
            flags.append(ConfidenceFlag(f"contact.{field}", UNKNOWN, "missing"))

    # Summary
    if resume["summary"] is None:
        resume["summary"] = ""
        flags.append(ConfidenceFlag("summary", UNKNOWN, "missing"))

    # Experience
    if not resume["experience"]:
        resume["experience"] = []
        flags.append(ConfidenceFlag("experience", UNKNOWN, "missing"))

    # Education
    if not resume["education"]:
        resume["education"] = []
        flags.append(ConfidenceFlag("education", UNKNOWN, "missing"))

    # Skills
    if not resume["skills"]:
        resume["skills"] = []
        flags.append(ConfidenceFlag("skills", UNKNOWN, "missing"))

    # Projects
    if not resume["projects"]:
        resume["projects"] = []
        flags.append(ConfidenceFlag("projects", UNKNOWN, "missing"))


def parse_resume_file(file_path: Path) -> tuple[dict[str, Any], list[ConfidenceFlag]]:
    """
    Contract: parse a PDF or DOCX resume file into a Resume dict.

    Args:
        file_path: path to the PDF or DOCX file.

    Returns:
        A tuple of (resume_dict, confidence_flags).
        resume_dict matches RESUME_SCHEMA with None/empty values for missing fields.
        confidence_flags lists all fields with their extraction confidence.

    Raises:
        ValueError: if file type is not supported.
        ImportError: if required parsing library is not installed.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise ValueError(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()

    if suffix == '.pdf':
        text = _extract_text_from_pdf(file_path)
    elif suffix in ('.docx', '.doc'):
        text = _extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .docx, .doc")

    return parse_text(text)


# Re-export for convenience
__all__ = [
    "parse_resume_file",
    "parse_text",
    "ConfidenceFlag",
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "LOW_CONFIDENCE",
    "UNKNOWN",
]
