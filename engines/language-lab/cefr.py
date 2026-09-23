# engines/language-lab/cefr.py
#
# WHAT: The CEFR curriculum skeleton — levels A1..C1 (+ the honest
#       locked C2 badge), ten everyday-life topic domains, and the
#       deterministic lesson-slot matrix that gives every language a
#       ready-made "ground to start from": a library and catalogue of
#       each level from beginner to fluent, exactly as the owner's
#       Deutsch-im-Fokus webapp demonstrated.
# WHY:  Owner directive 2026-09-06 — users must find a LIBRARY: a
#       ready catalogue per language covering levels A1 to C1 with
#       vocabulary, grammar, sentence structure, quizzes, audio,
#       listening. This module is ZERO-LLM: the catalog renders
#       instantly for all 15 languages (browsing is never gated on a
#       model), and generation fills slots on demand. Lesson slots are
#       deterministic (stable keys — marketing links never drift),
#       and the 30 curated flagship topics plug in as the verified
#       es/ja/de "world of work" track.
# BREAKS IF DELETED: The library has no structure — the Language Lab
#       reverts to random one-off packs with no learning journey.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "LEVELS", "LEVEL_INFO", "TOPIC_DOMAINS", "LessonSlot", "C2",
    "catalog_index", "lesson_slots", "slot_for", "level_focus",
    "VERIFIED_LANGUAGES", "LANGUAGES",
]

# The ladder: A1 beginner -> C1 fluent. C2 ships as an honest locked
# badge ("C2 — coming soon") rather than shipping weak content.
LEVELS = ("a1", "a2", "b1", "b2", "c1")

C2 = {"key": "c2", "name": "C2", "locked": True,
      "title": "Mastery — coming soon",
      "blurb": "C2 demands literary nuance and academic register. "
               "It unlocks when our verified content earns it — no "
               "generic filler, ever."}

LEVEL_INFO: dict[str, dict[str, str]] = {
    "a1": {"name": "A1", "title": "First contact",
           "blurb": "Greetings, numbers, survival basics. You leave "
                    "able to introduce yourself and handle the "
                    "everyday minimum.",
           "line": "Tiny words, giant first steps. 🌱"},
    "a2": {"name": "A2", "title": "Everyday routines",
           "blurb": "Past tense, comparisons, making plans. You "
                    "handle daily life: shopping, appointments, "
                    "small talk.",
           "line": "The language starts doing chores for you. 🧺"},
    "b1": {"name": "B1", "title": "Opinions & connections",
           "blurb": "Because/although/therefore — you argue, narrate, "
                    "and hold your own in discussions.",
           "line": "Opinions are load-bearing now. 🏗️"},
    "b2": {"name": "B2", "title": "Fluency & nuance",
           "blurb": "Passive voice, formal register, presentations. "
                    "You work and negotiate through the language.",
           "line": "You sound like someone with a life here. 🏙️"},
    "c1": {"name": "C1", "title": "Persuasion & mastery",
           "blurb": "Hypotheticals, elegant connectors, negotiation "
                    "rhetoric. You persuade — and understand "
                    "subtext.",
           "line": "At this point you're teaching E.T. phrases. 👽"},
}

# The ten everyday-life domains — the breadth the owner demanded
# ("all sorts of daily life topics not only technology"). A technical
# "world of work" track exists too via the flagship catalog.
TOPIC_DOMAINS: dict[str, str] = {
    "home_admin": "Home & daily life (apartment, chores, paperwork)",
    "food_dining": "Food & dining (restaurants, markets, recipes)",
    "shopping_money": "Shopping & money (sizes, prices, banking)",
    "health_body": "Health & body (doctor, pharmacy, fitness)",
    "transport_travel": "Transport & travel (tickets, directions, "
                         "airports)",
    "people_friends": "People & friends (meeting, planning, "
                       "empathy)",
    "work_school": "Work & school (first day, meetings, interviews)",
    "services_authorities": "Services & authorities (registers, "
                             "hotlines, complaints)",
    "leisure_media": "Leisure & media (hobbies, movies, classes)",
    "feelings_opinions": "Feelings & opinions (debates, dreams, "
                          "plans)",
}

# Languages with curated/verified content depth (marketing + demo).
# Every other language still gets the full catalog structure — no
# language is ever "not supported".
VERIFIED_LANGUAGES = ("es", "ja", "de")

LANGUAGES = ("en", "es", "fr", "de", "it", "pt", "ru", "zh", "ar",
             "ja", "ko", "hi", "nl", "tr", "vi")


# ---------------------------------------------------------------------------
# Lesson slots — the deterministic catalog matrix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LessonSlot:
    """One catalog cell: a level + domain + title, with a stable key
    (`<level>-<domain>`) that artifacts and marketing links derive
    from forever."""
    key: str
    level: str
    domain: str
    title: str
    focus: str            # what the generated pack emphasizes
    cefr_grammar: str    # grammar spine for this slot

    def topic_prompt(self) -> str:
        """The topic string handed to generate_lesson_pack: everyday
        AND concrete — the anti-generic guarantee."""
        return (f"{self.title}: practical everyday situations, "
                f"dialogues and vocabulary. Grammar focus: "
                f"{self.cefr_grammar}.")


# Grammar spine per level (the pedagogical ladder; prompts demand it
# so packs actually progress instead of repeating A1 topics forever).
_LEVEL_FOCUS: dict[str, tuple[str, str]] = {
    # (sentence focus, grammar spine)
    "a1": ("first contact: greetings, names, numbers, simple needs",
           "present tense, articles, basic question words"),
    "a2": ("daily routines: past events, shopping, appointments",
           "Perfekt/past tense, comparatives, wenn-clauses"),
    "b1": ("opinions and reasons: plans, advice, work life",
           "subordinate clauses (weil/dass/obwohl), modal verbs"),
    "b2": ("formal fluency: work processes, media, presentations",
           "passive voice, nominalization, Konjunktiv II basics"),
    "c1": ("persuasion and nuance: negotiation, abstract debate",
           "advanced connectors (folglich/ungeachtet), irrealis"),
}

# Domain rotation per level: 6 slots per level, chosen so every level
# touches the most life-relevant domains for that band.
_LEVEL_DOMAINS: dict[str, tuple[str, ...]] = {
    "a1": ("people_friends", "food_dining", "transport_travel",
            "shopping_money", "home_admin", "health_body"),
    "a2": ("home_admin", "shopping_money", "health_body",
            "people_friends", "leisure_media", "work_school"),
    "b1": ("work_school", "services_authorities", "feelings_opinions",
           "transport_travel", "people_friends", "leisure_media"),
    "b2": ("work_school", "services_authorities", "feelings_opinions",
           "food_dining", "leisure_media", "transport_travel"),
    "c1": ("feelings_opinions", "work_school", "services_authorities",
           "leisure_media", "people_friends", "food_dining"),
}

# Concrete titles per (level, domain) — the everyday specificity the
# owner's webapp proved converts. Curated, never machine-fancied.
_TITLES: dict[tuple[str, str], str] = {
    ("a1", "people_friends"): "Meeting people & introducing yourself",
    ("a1", "food_dining"): "Ordering food & drinks",
    ("a1", "transport_travel"): "Getting around: tickets & directions",
    ("a1", "shopping_money"): "Shopping: prices & quantities",
    ("a1", "home_admin"): "Your home: rooms, furniture, chores",
    ("a1", "health_body"): "At the doctor: symptoms & basics",
    ("a2", "home_admin"): "Renting & setting up a home",
    ("a2", "shopping_money"): "Banking & everyday money",
    ("a2", "health_body"): "Pharmacy, fitness & appointments",
    ("a2", "people_friends"): "Making plans with friends",
    ("a2", "leisure_media"): "Hobbies & free time",
    ("a2", "work_school"): "First week at work or school",
    ("b1", "work_school"): "Standing your ground at work",
    ("b1", "services_authorities"): "Dealing with authorities",
    ("b1", "feelings_opinions"): "Giving opinions with reasons",
    ("b1", "transport_travel"): "Travel problems & solutions",
    ("b1", "people_friends"): "Empathy: good days and bad days",
    ("b1", "leisure_media"): "Recommending books, films, music",
    ("b2", "work_school"): "Meetings, processes & presentations",
    ("b2", "services_authorities"): "Negotiating with services",
    ("b2", "feelings_opinions"): "Debating topics that matter",
    ("b2", "food_dining"): "Culture at the table: hosting & guests",
    ("b2", "leisure_media"): "Media literacy & reviews",
    ("b2", "transport_travel"): "Relocating: the full move",
    ("c1", "feelings_opinions"): "Persuasion, subtlety & register",
    ("c1", "work_school"): "Negotiation & leadership language",
    ("c1", "services_authorities"): "Complex cases & formal advocacy",
    ("c1", "leisure_media"): "Humor, irony & cultural subtext",
    ("c1", "people_friends"): "Deep conversations & storytelling",
    ("c1", "food_dining"): "Gastronomy, traditions & identity",
}


def level_focus(level: str) -> tuple[str, str]:
    return _LEVEL_FOCUS.get((level or "a1").lower(),
                            _LEVEL_FOCUS["a1"])


def lesson_slots(level: str) -> list[LessonSlot]:
    """The 6 deterministic slots for one level."""
    level = (level or "a1").lower()
    if level not in LEVELS:
        raise ValueError(f"Level must be one of {list(LEVELS)}")
    focus, grammar = level_focus(level)
    slots = []
    for domain in _LEVEL_DOMAINS[level]:
        title = _TITLES.get((level, domain),
                             TOPIC_DOMAINS[domain])
        slots.append(LessonSlot(
            key=f"{level}-{domain}",
            level=level, domain=domain, title=title,
            focus=focus, cefr_grammar=grammar))
    return slots


def slot_for(key: str) -> Optional[LessonSlot]:
    for level in LEVELS:
        for slot in lesson_slots(level):
            if slot.key == (key or "").strip():
                return slot
    return None


def catalog_index(language: str) -> list[dict[str, Any]]:
    """The full library view for one language: every level, every
    slot, with generation/readiness left to the caller (catalog_store
    merges status in). Zero LLM calls — instant for all languages."""
    language = (language or "en").lower()[:2]
    rows: list[dict[str, Any]] = []
    for level in LEVELS:
        info = LEVEL_INFO[level]
        rows.append({"kind": "level", "level": level,
                     "name": info["name"], "title": info["title"],
                     "blurb": info["blurb"], "line": info["line"]})
        for slot in lesson_slots(level):
            rows.append({"kind": "slot", "key": slot.key,
                         "level": level, "domain": slot.domain,
                         "title": slot.title,
                         "domain_label": TOPIC_DOMAINS[slot.domain]})
    rows.append({"kind": "level", "level": "c2", "name": C2["name"],
                 "title": C2["title"], "blurb": C2["blurb"],
                 "line": "The mountain top waits for worthy gear. ⛰️",
                 "locked": True})
    return rows
