# engines/export-engine/text_format.py
#
# WHAT: Deterministic plain-text renderers and writers (Journey + Resume).
# WHY:  P4.1 split of the former 1004-line export god-module (CONSTITUTION
#       §4): one file per concern so layout bugs localize to one adapter.
# BREAKS IF DELETED: plain-text exports disappear.

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

def export_to_plain_text(journey: dict[str, Any]) -> str:
    """
    Contract: render a Journey dict to a plain-text string.

    Format:
      TITLE (LEVEL)
      ==============

      Card 1: <title>
      <content>

      Quiz: <question>
      A) <option 0>
      B) <option 1>
      C) <option 2>
      D) <option 3>
      Correct: <correct_option>
      Explanation: <explanation>

      ---

      [repeated for each card]

    Args:
        journey: a validated Journey dict with keys 'topic',
                 'level', and 'cards'.

    Returns:
        A plain-text string.

    Raises:
        ValueError: if the journey is missing required fields.
    """
    topic = journey.get("topic")
    level = journey.get("level", "beginner")
    cards = journey.get("cards", [])

    if not topic:
        raise ValueError("Journey must have a 'topic' field")
    if not cards:
        raise ValueError("Journey must contain at least one card")

    lines = [
        f"{topic.upper()} ({level.upper()})",
        "=" * len(topic),
        "",
    ]

    for i, card in enumerate(cards, start=1):
        card_id = card.get("id", str(i))
        title = card.get("title", "Untitled Card")
        content = card.get("content", "")
        question = card.get("question", "")
        options = card.get("options", [])
        correct_option = card.get("correct_option", "")
        explanation = card.get("explanation", "")

        lines.append(f"Card {i}: {title}")
        lines.append(content)
        lines.append("")
        lines.append(f"Quiz: {question}")

        for j, opt in enumerate(options):
            label = chr(65 + j)  # A, B, C, D...
            lines.append(f"  {label}) {opt}")

        lines.append(f"  Correct: {correct_option}")
        lines.append(f"  Explanation: {explanation}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_to_text_file(journey: dict[str, Any], filepath: str) -> str:
    """
    Contract: write plain-text export to a file.

    Args:
        journey: a validated Journey dict.
        filepath: path to write the .txt file.

    Returns:
        The filepath that was written.
    """
    text = export_to_plain_text(journey)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info("Wrote plain-text export to %s", filepath)
    return filepath


def export_resume_to_plain_text(resume: dict[str, Any]) -> str:
    """
    Contract: render a Resume dict to a plain-text string.

    Format:
      NAME
      Email: email | Phone: phone | Location: location
      LinkedIn: linkedin | GitHub: github

      SUMMARY
      -------
      <summary text>

      EXPERIENCE
      ----------
      Title | Company | Dates
      - Description point 1
      - Description point 2

      EDUCATION
      ---------
      Degree | School | Dates

      SKILLS
      ------
      skill1, skill2, skill3

      PROJECTS
      --------
      Project Name
      - Description
      - Tech: tech1, tech2

    Args:
        resume: a validated Resume dict with keys 'contact', 'summary',
                'experience', 'education', 'skills', 'projects'.

    Returns:
        A plain-text string.

    Raises:
        ValueError: if the resume is missing required fields.
    """
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

    lines = []
    name = contact.get("name", "Unknown")
    lines.append(name.upper())
    lines.append("=" * len(name))
    lines.append("")

    # Contact info
    email = contact.get("email", "")
    phone = contact.get("phone", "")
    location = contact.get("location", "")
    linkedin = contact.get("linkedin", "")
    github = contact.get("github", "")

    contact_parts = [p for p in [email, phone, location, linkedin, github] if p]
    if contact_parts:
        lines.append(" | ".join(contact_parts))
        lines.append("")

    # Summary
    if summary:
        lines.append("SUMMARY")
        lines.append("-" * 7)
        lines.append(summary)
        lines.append("")

    # Experience
    if experience:
        lines.append("EXPERIENCE")
        lines.append("-" * 10)
        for exp in experience:
            title = exp.get("title", "Title")
            company = exp.get("company", "Company")
            dates = exp.get("dates", "Dates")
            description = exp.get("description", "")
            lines.append(f"{title} | {company} | {dates}")
            # Bullet points from description
            for line in description.split("\n"):
                line = line.strip()
                if line:
                    lines.append(f"  - {line}")
            lines.append("")

    # Education
    if education:
        lines.append("EDUCATION")
        lines.append("-" * 9)
        for edu in education:
            degree = edu.get("degree", "Degree")
            school = edu.get("school", "School")
            dates = edu.get("dates", "Dates")
            lines.append(f"{degree} | {school} | {dates}")
        lines.append("")

    # Skills
    if skills:
        lines.append("SKILLS")
        lines.append("-" * 6)
        lines.append(", ".join(skills))
        lines.append("")

    # Projects
    if projects:
        lines.append("PROJECTS")
        lines.append("-" * 8)
        for proj in projects:
            proj_name = proj.get("name", "Project")
            desc = proj.get("description", "")
            tech = proj.get("tech", [])
            lines.append(proj_name)
            if desc:
                lines.append(f"  {desc}")
            if tech:
                lines.append(f"  Tech: {', '.join(tech)}")
            lines.append("")

    return "\n".join(lines).rstrip()


def export_resume_to_text_file(resume: dict[str, Any], filepath: str) -> str:
    """
    Contract: write resume plain-text export to a file.

    Args:
        resume: a validated Resume dict.
        filepath: path to write the .txt file.

    Returns:
        The filepath that was written.
    """
    text = export_resume_to_plain_text(resume)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info("Wrote resume plain-text export to %s", filepath)
    return filepath
