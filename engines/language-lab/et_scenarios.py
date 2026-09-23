# engines/language-lab/et_scenarios.py
#
# WHAT: The E.T. conversation scenario bank — curated topics across
#       everyday-life domains, three lengths each, plus the special
#       modes (mock job interview, support-call roleplay, free talk).
# WHY:  Owner directive: "short and medium and long conversation
#       templates where user only chooses and starts practice" and
#       "mock full interviews by simply asking Mr. E.T." The bank is
#       language-neutral (each scenario opens in the TARGET language);
#       opening lines are curated for es/ja/de and pipeline-generated
#       once per language elsewhere, then cached. Ten domains × three
#       contexts give 30 grounded situations — same everyday-life
#       coverage as the curriculum catalog so the Library and E.T.
#       reinforce each other.
# BREAKS IF DELETED: E.T. has nothing to talk about — conversations
#       become generic small talk, exactly what the owner banned.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "Scenario", "SCENARIOS", "SPECIAL_SCENARIOS", "scenario_bank",
    "scenario_for", "LENGTHS", "ScenarioLength",
]

LENGTHS = {"short": (6, 8), "medium": (10, 14), "long": (18, 24)}
ScenarioLength = str  # "short" | "medium" | "long"


@dataclass(frozen=True)
class Scenario:
    key: str                 # stable slug — sessions name from it
    domain: str              # matches cefr.TOPIC_DOMAINS keys
    title_en: str             # UI label (English master)
    situation: str            # the prompt context E.T. receives
    goal: str                # what the learner practices
    special: str = ""         # "interview" | "support" | "freetalk" | ""


def _s(key, domain, title, situation, goal, special=""):
    return Scenario(key=key, domain=domain, title_en=title,
                    situation=situation, goal=goal, special=special)


# 10 domains × 3 contexts = 30 grounded everyday scenarios
SCENARIOS: tuple[Scenario, ...] = (
    # Home & admin
    _s("apartment-viewing", "home_admin", "Apartment viewing",
       "The learner is viewing an apartment to rent; E.T. plays the "
       "landlord explaining rooms, rent, deposit, and house rules.",
       "Ask about rent, deposit, utilities; negotiate politely."),
    _s("neighbor-chat", "home_admin", "Chat with a neighbor",
       "E.T. is the friendly neighbor met in the stairwell; small talk "
       "about the building, noise rules, the neighborhood.",
       "Casual small talk, asking favors (borrowing, packages)."),
    _s("call-utilities", "home_admin", "Setting up electricity",
       "E.T. plays a customer-service agent; the learner sets up an "
       "electricity/internet account for their new home.",
       "Give personal details by voice, confirm numbers, ask costs."),
    # Food & dining
    _s("restaurant-order", "food_dining", "Ordering at a restaurant",
       "E.T. is the waiter; the learner orders a full meal, asks about "
       "ingredients (allergies), and pays.",
       "Order dishes, ask ingredients, request the bill politely."),
    _s("market-shopping", "food_dining", "At the farmers' market",
       "E.T. is a market vendor selling fruit/cheese; haggling lightly, "
       "quantities, picking ripe items.",
       "Quantities, prices, preferences, light haggling."),
    _s("caux-coffee", "food_dining", "Coffee with a new friend",
       "E.T. is a potential friend at a café; finding common interests, "
       "making plans.",
       "Present-tense self-intro, likes/dislikes, proposing plans."),
    # Shopping & money
    _s("clothes-shop", "shopping_money", "Buying clothes",
       "E.T. plays a shop assistant; sizes, trying on, returns policy.",
       "Sizes, colors, paying, returns — transactional fluency."),
    _s("phone-plan", "shopping_money", "Choosing a phone plan",
       "E.T. is a telecom salesperson comparing plans, data, contracts.",
       "Comparatives (more/less/cheaper), asking clear questions."),
    _s("bank-account", "shopping_money", "Opening a bank account",
       "E.T. plays a bank clerk; the learner opens an account: ID, "
       "cards, fees, transfer limits.",
       "Formal register, numbers, understanding conditions."),
    # Health & body
    _s("doctor-visit", "health_body", "A visit to the doctor",
       "E.T. plays a doctor; the learner describes symptoms (cold, "
       "back pain), understands instructions, asks about medication.",
       "Describing symptoms, understanding advice, dosage questions."),
    _s("pharmacy-run", "health_body", "At the pharmacy",
       "E.T. is the pharmacist; over-the-counter advice, prescriptions.",
       "Describing minor ailments, understanding dosage instructions."),
    _s("gym-intro", "health_body", "Joining a gym",
       "E.T. plays a gym trainer; membership options, schedule, "
       "beginner advice.",
       "Days/times, routines, polite persistence."),
    # Transport & travel
    _s("buy-ticket", "transport_travel", "Buying a train ticket",
       "E.T. plays a station clerk; destinations, times, returns, "
       "platforms, discounts.",
       "Times, destinations, seat preferences, price questions."),
    _s("lost-in-city", "transport_travel", "Asking for directions",
       "E.T. plays a passerby; the learner asks directions, "
       "clarifies, says where they're going.",
       "Directions vocabulary, repetition requests, confirmation."),
    _s("airport-checkin", "transport_travel", "Airport check-in",
       "E.T. plays an airline agent; passport, luggage, seats, gates.",
       "Formal transactional language, following instructions."),
    # People & friends
    _s("meet-new", "people_friends", "Meeting someone new",
       "E.T. is a stranger at a language meetup; introductions, "
       "origins, jobs, hobbies.",
       "Self-introduction at the target level, question tags."),
    _s("invite-friends", "people_friends", "Planning a weekend",
       "E.T. and the learner plan a weekend trip together; "
       "suggestions, preferences, compromise.",
       "Proposing, accepting, declining gracefully."),
    _s("console-friend", "people_friends", "A friend had a bad day",
       "E.T. had a rough day (his spaceship broke); the learner "
       "comforts, empathizes, offers perspective.",
       "Past tense, empathy phrases, emotional vocabulary."),
    # Work & school
    _s("first-day", "work_school", "First day at a new job",
       "E.T. plays a team lead welcoming the learner; introductions, "
       "tools, the first task.",
       "Workplace politeness, asking for help, clarifying tasks."),
    _s("standup", "work_school", "The daily stand-up",
       "E.T. plays a colleague in a stand-up meeting; the learner "
       "reports yesterday/today/blockers.",
       "Past + future tense work talk, concise reporting."),
    _s("parent-teacher", "work_school", "Parent-teacher talk",
       "E.T. plays a teacher discussing the learner's child's progress.",
       "Formal register, understanding feedback, asking next steps."),
    # Services & authorities
    _s("register-address", "services_authorities", "Registering an address",
       "E.T. plays a city-office clerk; the learner registers their "
       "address (the famous Anmeldung moment).",
       "Formal bureaucracy talk, documents, appointment systems."),
    _s("report-problem", "services_authorities", "Reporting a problem",
       "E.T. plays a hotline agent; the learner reports a broken "
       "heating/lost package and follows the process.",
       "Problem description, ticket/confirmation numbers, polite pressure."),
    _s("customer-complaint", "services_authorities", "Making a complaint",
       "E.T. plays a shop's support desk; a wrong delivery, refund ask.",
       "Complaint register, firm-but-polite, negotiating a solution."),
    # Leisure & media
    _s("movie-night", "leisure_media", "Choosing a movie",
       "E.T. and the learner pick a movie for tonight; genres, "
       "recommendations, past experiences.",
       "Opinions, recommendations, storytelling fragments."),
    _s("hobby-talk", "leisure_media", "Talking about hobbies",
       "E.T. is curious about the learner's hobby; questions, "
       "describing why they love it.",
       "Describing passion, vocabulary depth in one topic."),
    _s("sports-class", "leisure_media", "Signing up for a class",
       "E.T. plays a community-center desk; course options, levels, "
       "what to bring.",
       "Schedules, requirements, enrollment phrases."),
    # Feelings & opinions
    _s("opinions-food", "feelings_opinions", "Strong opinions: food",
       "E.T. claims Earth food is overrated; the learner defends "
       "their favorite dish with arguments.",
       "B1+ argumentation, agreeing/disagreeing with reasons."),
    _s("opinions-tech", "feelings_opinions", "Debate: phones in schools",
       "E.T. plays a debate partner: are phones good for students?",
       "B2 discourse: concessions, counterpoints, examples."),
    _s("future-plans", "feelings_opinions", "Where life is going",
       "E.T. asks about the learner's dreams and 5-year plans.",
       "Future tense, conditionals, aspirational vocabulary."),
)

SPECIAL_SCENARIOS: tuple[Scenario, ...] = (
    _s("mock-interview", "work_school", "Mock job interview",
       "E.T. plays a hiring manager running a full job interview for "
       "a role the learner cares about: tell-me-about-yourself, "
       "strengths/weaknesses, behavioral questions, reverse "
       "questions. E.T. stays in character the whole time and ends "
       "with a warm verdict.",
       "Interview register: STAR answers, polite confidence, asking "
       "smart questions back.", special="interview"),
    _s("support-call", "work_school", "Customer-support call roleplay",
       "E.T. plays an upset-but-reasonable customer calling the "
       "learner (who works support): describe the issue, de-escalate, "
       "offer a fix, close warmly. Mirrors the contact-center niche "
       "the app already serves.",
       "De-escalation, empathy phrases, resolution language, "
       "confirmation loops.", special="support"),
    _s("free-talk", "people_friends", "Free talk with E.T.",
       "No script. E.T. starts with one curiosity question and lets "
       "the conversation go wherever the learner takes it.",
       "Unscripted fluency — the real thing.", special="freetalk"),
)


def scenario_bank(include_special: bool = True) -> list[Scenario]:
    """All scenarios, standard first (domain order), specials last."""
    bank = list(SCENARIOS)
    if include_special:
        bank.extend(SPECIAL_SCENARIOS)
    return bank


def scenario_for(key: str) -> Optional[Scenario]:
    for scenario in scenario_bank():
        if scenario.key == (key or "").strip():
            return scenario
    return None


def turn_range(length: ScenarioLength) -> tuple[int, int]:
    """(min, max) turns for a session length; unknown -> medium."""
    return LENGTHS.get((length or "medium").strip().lower(),
                       LENGTHS["medium"])
