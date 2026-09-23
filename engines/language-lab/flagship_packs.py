# engines/language-lab/flagship_packs.py
#
# WHAT: The curated flagship-pack catalog — ten ready-to-run lesson
#       topics per focus language, chosen to demo the app's "personal
#       curriculum" promise and double as shareable marketing artifacts
#       (PROFIT_PLAN §3.1 content engine + §6 Days 31-60).
# WHY:  The single most convincing demo of the Language Lab is a pack
#       about a situation the learner actually faces this week — not
#       "animals" or "colors". These topics are the ones that convert:
#       expat life, job hunting, workplace survival. Each generated pack
#       carries the share footer (app credit) and becomes a landing
#       page when the owner posts it to communities (§3.4).
#       Curated list, not generated: the topics must be stable so links
#       and posts keep working across releases.
# BREAKS IF DELETED: The marketing funnel loses its artifacts; the
#       Language Lab demo reverts to random topics.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["FlagshipTopic", "FLAGSHIP_PACKS", "packs_for_language",
           "flagship_topics_index", "FOCUS_LANGUAGES"]

# The three focus languages from PROFIT_PLAN §6 (top-3 by market reach
# for this portfolio's niche communities).
FOCUS_LANGUAGES = ("es", "ja", "de")


@dataclass(frozen=True)
class FlagshipTopic:
    """One curated lesson topic: the title the user sees, the prompt
    that seeds generation, and why it converts (marketing note)."""
    key: str          # stable slug — artifact names derive from it
    title: str        # user-facing title (English; the pack itself is bilingual)
    prompt: str       # the topic string handed to generate_lesson_pack
    pitch: str        # one line for the storefront / community post


# Ten topics per focus language, identical concepts localized to what
# each audience actually searches for. 30 packs total at 10 per language.
_TOPICS: tuple[FlagshipTopic, ...] = (
    FlagshipTopic(
        "renting-apartment", "Renting an apartment",
        "renting an apartment: viewing, deposit, lease terms, utilities",
        "The expat demo — the pack every 'moving to Berlin/Tokyo/Madrid' "
        "thread wants."),
    FlagshipTopic(
        "job-interview", "Surviving a job interview",
        "a job interview: strengths, weaknesses, 'tell me about yourself', "
        "questions for the interviewer",
        "The career-wedge demo — interview phrases + drills in the target "
        "language."),
    FlagshipTopic(
        "first-week-work", "First week at a new job",
        "the first week at a new job: introductions, asking for help, "
        "tools, meetings, feedback",
        "Workplace survival language — the highest-anxiety week of any "
        "relocation."),
    FlagshipTopic(
        "customer-support-call", "Handling a customer-support call",
        "handling a customer support call: greeting, listening, "
        "apologizing, escalating, closing",
        "The contact-center niche's home-turf pack — the app's job-board "
        "rosters already target this vertical."),
    FlagshipTopic(
        "doctor-visit", "A visit to the doctor",
        "visiting the doctor: describing symptoms, understanding "
        "instructions, booking follow-ups, pharmacy",
        "The pack nobody dares learn from an app — and the reason "
        "offline privacy sells."),
    FlagshipTopic(
        "grocery-small-talk", "Grocery shopping and small talk",
        "grocery shopping: quantities, prices, checkout small talk, "
        "farmer's market",
        "Daily-life confidence — the fastest visible progress for a "
        "beginner."),
    FlagshipTopic(
        "public-transport", "Getting around: public transport",
        "using public transport: buying tickets, asking for directions, "
        "delays, taxis",
        "The 'day one in a new city' pack."),
    FlagshipTopic(
        "banking-paperwork", "Banking and bureaucracy",
        "opening a bank account and basic paperwork: appointments, "
        "identification, forms, official letters",
        "Bureaucracy language — the moment a phrasebook dies and a "
        "curriculum earns its keep."),
    FlagshipTopic(
        "making-friends", "Making friends after moving",
        "making friends after moving: hobbies, invitations, small talk, "
        "excusing yourself",
        "The retention pack — social life is why learners keep "
        "studying."),
    FlagshipTopic(
        "salary-negotiation", "Talking money: salary and contracts",
        "discussing salary and contracts: numbers, benefits, negotiating "
        "politely, written offers",
        "The highest-stakes conversation — the pack that proves a free "
        "app can teach what tutors charge $50/hour for."),
)

# Language-specific title overrides where the localized situation
# differs (e.g., Germany's Anmeldung, Japan's honorific-heavy
# introductions). Keys: (language, topic-key).
_LOCALIZED_NOTES: dict[tuple[str, str], str] = {
    ("de", "banking-paperwork"):
        "German flavor: Anmeldung, Termin culture, Sie vs du in offices.",
    ("ja", "first-week-work"):
        "Japanese flavor: keigo basics for self-introduction at work.",
    ("ja", "making-friends"):
        "Japanese flavor: casual speech vs polite forms when meeting "
        "peers.",
    ("es", "customer-support-call"):
        "Spanish flavor: LATAM vs Castilian greeting registers.",
}

FLAGSHIP_PACKS: dict[str, tuple[FlagshipTopic, ...]] = {
    lang: tuple(
        FlagshipTopic(
            t.key, t.title, t.prompt,
            _LOCALIZED_NOTES.get((lang, t.key), t.pitch),
        )
        for t in _TOPICS
    )
    for lang in FOCUS_LANGUAGES
}


def packs_for_language(language: str) -> tuple[FlagshipTopic, ...]:
    """The curated catalog for one focus language (empty tuple if the
    language has no curated list — generation still works for any
    language, curated or not)."""
    return FLAGSHIP_PACKS.get((language or "").strip().lower(), ())


def flagship_topics_index() -> list[dict[str, Any]]:
    """Flat catalog for the UI/storefront: every topic with its language
    and pitch, in a stable order (language, then topic)."""
    rows: list[dict[str, Any]] = []
    for lang in FOCUS_LANGUAGES:
        for topic in FLAGSHIP_PACKS[lang]:
            rows.append({"language": lang, "key": topic.key,
                         "title": topic.title, "prompt": topic.prompt,
                         "pitch": topic.pitch})
    return rows
