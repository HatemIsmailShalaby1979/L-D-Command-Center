# model-layer/prompts.py
#
# WHAT: Prompt-template module — defines structured prompt templates
#       for every generation use case across all engines, rather than
#       constructing free-form prompts at call sites.
# WHY:  CONSTITUTION.md §3 requires deterministic templates for
#       anything structural. Free-form prompts produce inconsistent
#       outputs that are harder to validate, harder to debug, and
#       more likely to drift from the expected schema. This module
#       centralizes all prompt shapes so they can be reviewed, tested,
#       and swapped without touching engine code.
# BREAKS IF DELETED: Every engine falls back to ad-hoc prompt
#       construction, losing structural consistency and making schema
#       validation fragile. The entire generation pipeline becomes
#       harder to audit and reason about.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template data structures
# ---------------------------------------------------------------------------

@dataclass
class PromptTemplate:
    """
    Contract: the canonical shape of a prompt template.

    Fields:
      - name: unique identifier for this template (e.g. "journey_generate").
      - system: the system prompt string (may contain {placeholders}).
      - user: the user-message prompt string (may contain {placeholders}).
      - schema_key: optional key referencing a schema definition in
                    schema.py for downstream validation.
      - metadata: arbitrary extra data (e.g. default max_tokens,
                  temperature hints) consumed by the caller or client.
    """
    name: str
    system: str
    user: str
    schema_key: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

class PromptRegistry:
    """
    Contract: a centralized registry of all prompt templates used by
    every engine. Each template is defined once here and referenced by
    name from engine code — never constructed inline.

    Responsibilities:
      - Store all templates as PromptTemplate instances
      - Render a template by name with a variable dict, substituting
        all {placeholders} in system and user strings
      - Return the schema_key (if any) so the caller can wire up
        validation

    Non-responsibilities:
      - HTTP communication (handled by client.py)
      - Schema validation (handled by schema.py)
      - Engine-specific prompt composition beyond template definitions
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Journey templates
    # ------------------------------------------------------------------

    _JOURNEY_SYSTEM = (
        "You are a Learning & Development content generator. "
        "Your task is to produce structured learning journeys that "
        "conform exactly to the requested JSON schema. "
        "Always return valid JSON only — no prose, no markdown fences, "
        "no explanation outside the JSON object."
    )

    _JOURNEY_USER_BASE = (
        "Generate a learning journey for the topic \"{topic}\" "
        "at the {level} level.\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "topic": "<the topic string>",\n'
        '  "level": "<beginner|intermediate|advanced>",\n'
        '  "cards": [\n'
        '    {{\n'
        '      "id": "<unique string id>",\n'
        '      "title": "<card title>",\n'
        '      "content": "<learning content for this card>",\n'
        '      "question": "<quiz question>",\n'
        '      "options": ["<option A>", "<option B>", '
        '"<option C>", "<option D>"],\n'
        '      "correct_option": "<the correct option text>",\n'
        '      "explanation": "<why the answer is correct>"\n'
        '    }},\n'
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Produce exactly {num_cards} cards.\n"
        "- Each card must have a unique id.\n"
        "- Options must be between 2 and 4.\n"
        "- correct_option must match one of the options exactly.\n"
        "- Content must be accurate, pedagogically sound, and "
        "appropriate for the {level} level."
    )

    _JOURNEY_RETRY_SYSTEM = (
        "You previously generated a learning journey that failed "
        "schema validation. Fix the errors below and return a "
        "corrected JSON object with the same structure. "
        "Return valid JSON only — no prose, no markdown fences."
    )

    _JOURNEY_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "The topic is \"{topic}\" at {level} level.\n"
        "Generate a corrected journey with {num_cards} cards "
        "following the same schema as before.\n"
        "Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Resume templates
    # ------------------------------------------------------------------

    _RESUME_SYSTEM = (
        "You are a professional resume writer. Your task is to generate "
        "a well-structured resume JSON from the provided profile description. "
        "Return ONLY valid JSON — no prose, no markdown fences, no explanation."
    )

    _RESUME_USER_BASE = (
        "Generate a resume for the following profile:\n\n"
        "{profile}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "contact": {{\n'
        '    "name": "<full name>",\n'
        '    "email": "<email>",\n'
        '    "phone": "<phone>",\n'
        '    "location": "<location>",\n'
        '    "linkedin": "<linkedin URL>",\n'
        '    "github": "<github URL>"\n'
        "  }},\n"
        '  "summary": "<professional summary>",\n'
        '  "experience": [\n'
        '    {{\n'
        '      "title": "<job title>",\n'
        '      "company": "<company>",\n'
        '      "dates": "<start - end>",\n'
        '      "description": "<description>"\n'
        "    }},\n"
        "  ],\n"
        '  "education": [\n'
        '    {{\n'
        '      "degree": "<degree>",\n'
        '      "school": "<school>",\n'
        '      "dates": "<start - end>"\n'
        "    }},\n"
        "  ],\n"
        '  "skills": ["<skill1>", "<skill2>", ...],\n'
        '  "projects": [\n'
        '    {{\n'
        '      "name": "<project name>",\n'
        '      "description": "<description>",\n'
        '      "tech": ["<tech1>", "<tech2>"]\n'
        "    }},\n"
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Make the resume professional and tailored to the profile.\n"
        "- Include at least 2 experience entries.\n"
        "- Include at least 1 education entry.\n"
        "- Include at least 5 skills.\n"
        "- Include at least 1 project.\n"
        "- Return valid JSON only."
    )

    _RESUME_RETRY_SYSTEM = (
        "You previously generated a resume that failed schema validation. "
        "Fix the errors below and return a corrected JSON object. "
        "Return valid JSON only — no prose, no markdown fences."
    )

    _RESUME_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "The profile was: {profile}\n"
        "Generate a corrected resume following the same schema.\n"
        "Return valid JSON only."
    )

    _RESUME_ENHANCE_SYSTEM = (
        "You are a professional resume writer and career coach. "
        "Your task is to enhance an existing resume for a specific target role. "
        "Return TWO things as a JSON object:\n"
        "1. \"enhanced_resume\" - the improved resume JSON following the same schema\n"
        "2. \"changes\" - a list of objects describing what changed and why\n\n"
        "Return ONLY valid JSON — no prose, no markdown fences, no explanation."
    )

    _RESUME_ENHANCE_USER_BASE = (
        "Enhance the following resume for the target role:\n\n"
        "{target_role}\n\n"
        "Current resume:\n"
        "{resume}\n\n"
        "Return a JSON object with this structure:\n"
        "{{\n"
        '  "enhanced_resume": {{\n'
        '    "contact": {{...}},\n'
        '    "summary": "...",\n'
        '    "experience": [...],\n'
        '    "education": [...],\n'
        '    "skills": [...],\n'
        '    "projects": [...]  \n'
        '  }},\n'
        '  "changes": [\n'
        '    {{\n'
        '      "field": "<field name>",\n'
        '      "change": "<what changed>",\n'
        '      "reason": "<why this helps for the target role>"\n'
        '    }}\n'
        '  ]\n'
        "}}\n\n"
        "Requirements:\n"
        "- Tailor the resume to match the target role\n"
        "- Highlight relevant experience and skills\n"
        "- Improve the summary to reflect the career goal\n"
        "- Keep the same structure and format\n"
        "- Return valid JSON only."
    )

    _RESUME_ENHANCE_RETRY_SYSTEM = (
        "You previously attempted to enhance a resume for a target role but the output failed validation. "
        "Fix the errors below and return a corrected enhanced resume. "
        "Return valid JSON only — no prose, no markdown fences."
    )

    _RESUME_ENHANCE_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Target role: {target_role}\n"
        "Current resume:\n"
        "{resume}\n"
        "Generate a corrected enhanced resume following the same schema.\n"
        "Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Podcast script templates
    # ------------------------------------------------------------------

    _PODCAST_SYSTEM = (
        "You are a podcast scriptwriter. Your task is to generate "
        "a structured podcast episode script that conforms exactly to "
        "the requested JSON schema. "
        "Always return valid JSON only — no prose, no markdown fences, "
        "no explanation outside the JSON object."
    )

    _PODCAST_USER_BASE = (
        "Generate a podcast episode script for the topic \"{topic}\".\n\n"
        "Spoken language: EVERY segment's content must be written entirely "
        "in {language}.\n"
        "Audience level: {level} learners.\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "topic": "<the topic string>",\n'
        '  "title": "<episode title>",\n'
        '  "host_name": "{host_name}",\n'
        '  "co_host_name": "{co_host_name}",\n'
        '  "duration_minutes": <number>,\n'
        '  "segments": [\n'
        '    {{\n'
        '      "type": "<intro|monologue|dialogue|conclusion>",\n'
        '      "speaker": "<speaker name>",\n'
        '      "content": "<what is said>",\n'
        '      "duration_seconds": <number>\n'
        '    }}\n'
        "  ],\n"
        '  "speakers": ["{host_name}", "{co_host_name}"]\n'
        "}}\n\n"
        "Requirements:\n"
        "- Produce exactly {num_segments} segments.\n"
        "- Each segment's 'duration_seconds' MUST be approximately "
        "{segment_duration_seconds} seconds (i.e. the total adds up "
        "to ~{duration_minutes} minutes). Intro and conclusion are "
        "shorter (~45-60s); the bulk of the time goes to monologue "
        "and dialogue segments.\n"
        "- There are EXACTLY TWO hosts: {host_name} and {co_host_name}. "
        "Every segment is spoken by one of them — no other speakers.\n"
        "- It is a REAL conversation: they ask each other questions, "
        "disagree, react to what the other just said. {co_host_name} is "
        "never a silent sidekick.\n"
        "- Hosts should alternate frequently. At most two consecutive "
        "segments may share the same speaker.\n"
        "- First segment must be type 'intro'.\n"
        "- Last segment must be type 'conclusion'.\n"
        "- Intro and conclusion are spoken by {host_name}, who welcomes "
        "and thanks {co_host_name} by name.\n"
        "- Total duration should be approximately {duration_minutes} minutes.\n"
        "- Vocabulary and sentence complexity must suit {level} learners of {language}.\n"
        "- Content must be engaging, informative, and appropriate for a podcast audience.\n"
        "- Return valid JSON only."
    )

    _PODCAST_RETRY_SYSTEM = (
        "You previously generated a podcast script that failed "
        "schema validation. Fix the errors below and return a "
        "corrected JSON object with the same structure. "
        "Return valid JSON only — no prose, no markdown fences."
    )

    _PODCAST_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "The topic is \"{topic}\".\n"
        "Produce exactly {num_segments} segments.\n"
        "Each segment must be approximately {segment_duration_seconds} "
        "seconds long so the total adds up to ~{duration_minutes} minutes.\n\n"
        "Return a SINGLE valid JSON object that follows the EXACT "
        "structure:\n"
        "{{\n"
        '  "topic": "<the topic string>",\n'
        '  "title": "<episode title>",\n'
        '  "host_name": "{host_name}",\n'
        '  "co_host_name": "{co_host_name}",\n'
        '  "duration_minutes": <number>,\n'
        "  \"segments\": [\n"
        "    {{\n"
        '      "type": "<intro|monologue|dialogue|conclusion>",\n'
        '      "speaker": "<one of the two hosts>",\n'
        '      "content": "<spoken words, ENTIRELY in {language}, '
        'suitable for {level} learners>",\n'
        '      "duration_seconds": <number>\n'
        "    }}\n"
        "  ],\n"
        '  "speakers": ["{host_name}", "{co_host_name}"]\n'
        "}}\n\n"
        "Rules that fix the most common failures:\n"
        "- EXACTLY two hosts — {host_name} and {co_host_name} — and "
        "they really converse: they ask each other questions, react, "
        "disagree. BOTH must speak at least twice across the whole "
        "script.\n"
        "- Alternate frequently; never more than two consecutive "
        "segments from the same speaker.\n"
        "- First segment is type 'intro' (spoken by {host_name}); last "
        "segment is type 'conclusion'.\n"
        "- Every 'content' field must be FULLY written in {language}, "
        "at a {level} level — never empty, never the same text twice.\n"
        "- Return valid JSON only — no prose, no markdown fences."
    )

    # ------------------------------------------------------------------
    # Bilingual pair templates
    # ------------------------------------------------------------------

    _BILINGUAL_SYSTEM = (
        "You are a professional translator and language teacher. "
        "Your task is to produce accurate, sentence-by-sentence bilingual "
        "content for language learning. Translation accuracy is critical — "
        "each target-language sentence must have a faithful, natural "
        "translation in the user's known language. Return valid JSON only "
        "— no prose, no markdown fences, no explanation outside the JSON."
    )

    _BILINGUAL_USER_BASE = (
        "Create a bilingual learning pair on the topic \"{topic}\".\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "topic": "<the topic string>",\n'
        '  "target_language": "<language code, e.g. es>",\n'
        '  "known_language": "<language code, e.g. en>",\n'
        '  "segments": [\n'
        '    {{\n'
        '      "target_text": "<sentence in target language>",\n'
        '      "translation_text": "<accurate translation in known language>"\n'
        '    }}\n'
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Produce exactly {num_segments} segments.\n"
        "- Each segment must have BOTH target_text and translation_text.\n"
        "- target_text must be natural, grammatically correct {target_language}.\n"
        "- translation_text must be an ACCURATE, faithful translation — not creative.\n"
        "- Content should be appropriate for language learners (clear, practical phrases).\n"
        "- Return valid JSON only."
    )

    _BILINGUAL_RETRY_SYSTEM = (
        "You previously generated a bilingual pair that failed schema "
        "validation. Fix the errors below and return a corrected JSON "
        "object with the same structure. Return valid JSON only — no prose, "
        "no markdown fences."
    )

    _BILINGUAL_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Topic: \"{topic}\"\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Generate a corrected bilingual pair with {num_segments} segments.\n"
        "Return valid JSON only."
    )

    _BILINGUAL_VERIFY_SYSTEM = (
        "You are a meticulous translation reviewer for language-learning "
        "material. Judge whether each known-language sentence is a faithful "
        "translation of its target-language sentence. Translation accuracy "
        "is a correctness problem, not a stylistic one. Return valid JSON only."
    )

    _BILINGUAL_VERIFY_USER_BASE = (
        "Topic: \"{topic}\"\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n\n"
        "Sentence pairs:\n{segments}\n\n"
        'Return a JSON object: {{\"passed\": true|false, \"issues\": '
        '[{{\"segment_index\": <0-based index>, \"problem\": '
        '\"<what makes the translation unfaithful or unnatural>\"}}]}}\n\n'
        "Rules:\n"
        "- passed=false ONLY when at least one translation is unfaithful, "
        "omits meaning, or would confuse a learner.\n"
        "- List every problematic segment in issues with its 0-based index.\n"
        "- Do not invent issues for purely stylistic preferences.\n"
        "- Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # YouTube summary templates
    # ------------------------------------------------------------------

    _YOUTUBE_SUMMARY_SYSTEM = (
        "You are a research assistant that summarizes YouTube educational content. "
        "Extract the key points from the video description and any provided transcript. "
        "Be concise, factual, and highlight practical takeaways. "
        "Return ONLY valid JSON — no prose, no markdown fences."
    )

    _YOUTUBE_SUMMARY_USER_BASE = (
        "Summarize this YouTube video about {topic}:\n\n"
        "Title: {title}\n"
        "Channel: {channel}\n"
        "URL: {url}\n"
        "Description:\n{description}\n\n"
        "Return a JSON object with this structure:\n"
        "{{\n"
        '  "summary": "<1-3 paragraph summary of the video content>",\n'
        '  "key_takeaways": [\n'
        '    "<key point 1>",\n'
        '    "<key point 2>",\n'
        '    "<key point 3>"\n'
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Summary must be informative but concise (100-300 words)\n"
        "- Key takeaways should be actionable insights\n"
        "- Include at least 2-5 key points\n"
        "- Return valid JSON only."
    )

    _YOUTUBE_SUMMARY_RETRY_SYSTEM = (
        "You previously generated a video summary that failed schema "
        "validation. Fix the errors below and return a corrected JSON "
        "object with the same structure. Return valid JSON only — no "
        "prose, no markdown fences."
    )

    _YOUTUBE_SUMMARY_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Summarize this YouTube video about {topic}:\n\n"
        "Title: {title}\n"
        "Channel: {channel}\n"
        "URL: {url}\n"
        "Description:\n{description}\n\n"
        "Generate a corrected summary following the same schema as before.\n"
        "Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Lesson pack templates (P7.2)
    # ------------------------------------------------------------------

    _LESSON_PACK_SYSTEM = (
        "You are a language teacher producing one complete interactive "
        "lesson pack. Every generation must follow the exact JSON "
        "structure requested — dialogue, vocabulary cards, grammar "
        "cards, and evaluation items together. Return valid JSON only "
        "— no prose, no markdown fences, no explanation outside the "
        "JSON object."
    )

    _LESSON_PACK_USER_BASE = (
        "Create the DIALOGUE and VOCABULARY half of a lesson pack on "
        "the topic \"{topic}\".\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {difficulty}.\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "dialogue": [  // exactly {num_dialogue} turns, EXACTLY '
        "2 distinct speakers alternating naturally\n"
        '    {{"speaker": "<name>",\n'
        '      "content": "<sentence ENTIRELY in {target_language}>"}}\n'
        "  ],\n"
        '  "vocab_cards": [  // exactly {num_vocab} cards\n'
        '    {{"term": "<word or phrase in {target_language}>",\n'
        '      "reading": "<pronunciation hint or transliteration>",\n'
        '      "translation": "<meaning in {known_language}>",\n'
        '      "example": "<example sentence in {target_language}>"}}\n'
        "  ]\n"
        "}}\n"
        "Match this worked example's shape:\n"
        '{{"dialogue": [{{"speaker": "Ana", "content": "Hola, '
        '¿qué tal?"}}, {{"speaker": "Luis", "content": "Muy bien, '
        'gracias."}}], "vocab_cards": [{{"term": "hola", '
        '"reading": "OH-lah", "translation": "hello", '
        '"example": "Hola, me llamo Ana."}}]}}\n"'
        "Return valid JSON only."
    )
    _LESSON_PACK_PART2_USER_BASE = (
        "Create the GRAMMAR and EVALUATION half of a lesson pack on "
        "the topic \"{topic}\".\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {difficulty}.\n"
        "The lesson already teaches these words: {context_terms}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "grammar_cards": [  // exactly {num_grammar} cards\n'
        '    {{\n'
        '      "point": "<grammar point arising from the topic>",\n'
        '      "explanation": "<short explanation in {known_language}>",\n'
        '      "drills": [  // at least 2 per card\n'
        '        {{"prompt": "<item in {target_language}>", '
        '"answer": "<correct answer>"}}]\n'
        '    }}\n'
        "  ],\n"
        '  "evaluation": [  // exactly {num_eval} items mixing types\n'
        '    {{"type": "multiple_choice",\n'
        '      "question": "<question in {known_language}>",\n'
        '      "options": ["<A>", "<B>", "<C>"],\n'
        '      "correct_index": <0-based index>}},\n'
        '    {{"type": "fill_in_blank",\n'
        '      "sentence_with_blank": "<sentence in {target_language} '
        'with ___>", "answer": "<missing word>"}},\n'
        '    {{"type": "translation",\n'
        '      "prompt": "<sentence in {known_language}>",\n'
        '      "answer": "<translation in {target_language}>"}},\n'
        '    {{"type": "transformation",\n'
        '      "prompt": "<sentence in {target_language} to rewrite>",\n'
        '      "answer": "<rewritten sentence>"}}\n'
        "  ]\n"
        "}}\n"
        "Match this worked example's shape:\n"
        '{{"grammar_cards": [{{"point": "ser vs estar", '
        '"explanation": "Use ser for identity.", "drills": '
        '[{{"prompt": "Yo ___ Ana.", "answer": "soy"}}, '
        '{{"prompt": "Ellos ___ contentos.", '
        '"answer": "están"}}]}}], "evaluation": [{{"type": '
        '"multiple_choice", "question": "Pick the greeting.", '
        '"options": ["Hola", "Adiós", "Gracias"], '
        '"correct_index": 0}}]}}\n'
        "Requirements:\n"
        "- Exactly {num_grammar} grammar cards (each 2+ drills) and "
        "exactly {num_eval} evaluation items.\n"
        "- fill_in_blank sentences must contain a ___ blank marker; "
        "correct_index must be a valid 0-based index.\n"
        "- Ground drills and items in the listed words where natural.\n"
        "- Every evaluation item MUST have a \"type\" field with one "
        "of exactly these four values: multiple_choice, "
        "fill_in_blank, translation, transformation — nothing else.\n"
        "- multiple_choice correct_index is a NUMBER (0, 1 or 2) — "
        "never null, never a string, never missing.\n"
        "- Return valid JSON only."
    )


    _LESSON_PACK_RETRY_SYSTEM = (
        "You previously generated a lesson pack that failed schema "
        "validation. Fix the errors below and return a corrected JSON "
        "object with the same structure. Return valid JSON only — no "
        "prose, no markdown fences."
    )

    _LESSON_PACK_PART1_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Topic: \"{topic}\" ({target_language}, {difficulty} level).\n"
        "Regenerate ONLY the dialogue + vocabulary half: exactly "
        "{num_dialogue} turns between EXACTLY two distinct speakers, "
        "exactly {num_vocab} vocab cards "
        "(term/reading/translation/example).\n"
        "Return valid JSON only."
    )

    _LESSON_PACK_PART2_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Topic: \"{topic}\" ({target_language}, {difficulty} level; "
        "words taught: {context_terms}).\n"
        "Regenerate ONLY the grammar + evaluation half: exactly "
        "{num_grammar} grammar cards (each 2+ drills) and exactly "
        "{num_eval} evaluation items.\n"
        "Shape discipline: every evaluation item needs its \"type\" "
        "field (multiple_choice, fill_in_blank, translation, or "
        "transformation — nothing else); multiple_choice needs "
        "correct_index as a NUMBER. Match the worked example shapes "
        "exactly.\n"
        "Return valid JSON only."
    )

    _LESSON_PACK_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Topic: \"{topic}\"\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {difficulty}\n"
        "Generate a corrected lesson pack following the same schema as "
        "before ({num_dialogue} dialogue turns, {num_vocab} vocab cards, "
        "{num_grammar} grammar cards, {num_eval} evaluation items).\n"
        "Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Lesson-pack judge + verification templates (P7.3)
    # ------------------------------------------------------------------

    _LESSON_JUDGE_SYSTEM = (
        "You are a meticulous language teacher grading ONE learner "
        "answer. Accept an answer only when its meaning is correct and "
        "it is appropriate for the learner level — minor typos or "
        "missing accents do not fail an otherwise correct answer. "
        "Return valid JSON only."
    )

    _LESSON_JUDGE_USER_BASE = (
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {difficulty}\n\n"
        "Exercise item:\n{item}\n\n"
        "Learner answer:\n{answer}\n\n"
        'Return a JSON object: {{"passed": true|false, '
        '"correct_answer": "<the canonical correct answer>", '
        '"issues": ["<short reason>", ...]}}\n'
        "- passed=true ONLY when the learner answer is a correct, "
        "natural response to the exercise.\n"
        "- List every defect in issues; use an empty list when passed.\n"
        "- Worked example — item asks for the Spanish word for "
        "bread, learner answered \"pan\": "
        '{{"passed": true, "correct_answer": "pan", "issues": []}}.\n'
        "- Return valid JSON only."
    )

    _LESSON_VERIFY_SYSTEM = (
        "You are a meticulous reviewer of language-learning material. "
        "Judge whether each claim below is faithful and correct: vocab "
        "translations must be accurate, grammar explanations must be "
        "true for the target language. Accuracy is a correctness "
        "problem, not a stylistic one. Return valid JSON only."
    )

    _LESSON_VERIFY_USER_BASE = (
        "Topic: \"{topic}\"\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {difficulty}\n\n"
        "Claims to review:\n{claims}\n\n"
        "Return a JSON object: {{\"passed\": true|false, \"issues\": "
        "[{{\"claim\": \"<claim id, e.g. V0 or G1>\", \"problem\": "
        "\"<what makes the claim wrong or misleading>\"}}]}}\n"
        "- passed=false ONLY when at least one claim is factually "
        "wrong, unfaithful, or would mislead a learner.\n"
        "- List every problematic claim with its id.\n"
        "- Do not invent issues for purely stylistic preferences.\n"
        "- Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Cover letter template (career agent)
    # ------------------------------------------------------------------

    _COVER_LETTER_SYSTEM = (
        "You are a concise, honest career coach writing a cover letter "
        "for a candidate. Use only facts from the provided resume and "
        "job details — never invent experience. Specific and warm, no "
        "cliches. Return valid JSON only."
    )

    _COVER_LETTER_USER_BASE = (
        "Target role: {role}\n"
        "Company: {company}\n"
        "Job listing snippet:\n{snippet}\n\n"
        "Candidate resume:\n{resume}\n\n"
        'Return a JSON object: {{"cover_letter": "<full letter text>"}}\n'
        "Rules:\n"
        "- 150-250 words.\n"
        "- Reference the company and role by name.\n"
        "- Ground every claim in the resume.\n"
        "- Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Capability probe template (P7.1)
    # ------------------------------------------------------------------

    _CAPABILITY_PROBE_SYSTEM = (
        "You are being calibrated. Answer the tiny task below to prove "
        "you can follow strict JSON output discipline for this task "
        "family. Return valid JSON only — no prose, no markdown fences, "
        "no explanation outside the JSON object."
    )

    _CAPABILITY_PROBE_USER_BASE = (
        "{task_instruction}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{expected_shape}\n\n"
        "Requirements:\n"
        "- Keep every string short (one sentence at most).\n"
        "- Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # LinkedIn post templates (career agent, 2026-09-05)
    # ------------------------------------------------------------------

    _LINKEDIN_POST_SYSTEM = (
        "You are a seasoned professional writing a LinkedIn post AS the "
        "candidate themselves — never as an assistant, never as a brand. "
        "The post must read like a human typed it between meetings: "
        "concrete, specific, first-person, imperfect on purpose. "
        "ABSOLUTELY FORBIDDEN: hashtags like #grateful #blessed "
        "#humbled, 'I am thrilled to announce', 'excited to share', "
        "'delve', 'in today's fast-paced world', em-dash chains, "
        "emoji bullets, listicles that all start with verbs, and any "
        "sentence a marketing department would approve. Return ONLY a "
        "JSON object — no prose around it."
    )

    _LINKEDIN_POST_USER_BASE = (
        "Write one LinkedIn post for this person.\n\n"
        "Person: {name} — {headline}\n"
        "Background (resume facts, use them for specifics):\n"
        "{background}\n\n"
        "Post goal: {goal}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "post_text": "<the post, 60-200 words, plain text>",\n'
        '  "style_notes": "<one line: what makes this read human>"\n'
        "}}\n\n"
        "Requirements:\n"
        "- Open mid-thought or with a concrete moment, never with an "
        "announcement.\n"
        "- At most 2 hashtags, only if they are genuinely what people in "
        "the field type; zero hashtags is fine.\n"
        "- Short paragraphs. One idea. Say one specific, verifiable "
        "thing from the background.\n"
        "- No call-to-action begging ('thoughts?', 'agree?') unless "
        "the goal genuinely asks a question.\n"
        "- The words must sound like {name} talking, not a ghostwriter."
    )

    _LINKEDIN_POST_RETRY_SYSTEM = (
        "Your previous post draft failed validation. Fix the errors "
        "and return a corrected JSON object with the same structure. "
        "Remember: no AI-tell phrases, no announcement openers, no "
        "hashtag soup. Return valid JSON only."
    )

    _LINKEDIN_POST_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same person, same goal as before. Rewrite the post as a "
        "human-sounding first-person LinkedIn post (60-200 words) "
        "grounded in the background facts.\n"
        "Return valid JSON only: {{\"post_text\": \"...\", "
        "\"style_notes\": \"...\"}}"
    )

    # ------------------------------------------------------------------
    # Interview prep templates (Campaign tier, 2026-09-06)
    # ------------------------------------------------------------------

    _INTERVIEW_PREP_SYSTEM = (
        "You are an interview coach preparing ONE candidate for ONE "
        "specific interview. Everything you write is grounded in the "
        "candidate's actual resume — you never invent experience they "
        "do not have. Answers must sound like the candidate talking, "
        "not a script. Return ONLY a JSON object — no prose, no "
        "fences, no commentary."
    )

    _INTERVIEW_PREP_USER_BASE = (
        "Prepare interview coaching for this interview.\n\n"
        "Role: {role}\n"
        "Company: {company}\n"
        "Listing notes: {snippet}\n\n"
        "Candidate (real resume facts — the ONLY experience you may "
        "reference):\n"
        "{resume}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "role": "<the role, echoing the listing>",\n'
        '  "company": "<the company, echoing the listing>",\n'
        '  "likely_questions": [\n'
        '    {{"question": "<a likely interview question>",\n'
        '      "how_to_answer": "<2-3 sentences: the angle, which '
        'resume facts to use, one pitfall to avoid>"}},\n'
        "    ... exactly 5 items ...\n"
        "  ],\n"
        '  "story_bank": [\n'
        '    {{"strength": "<one strength the resume supports>",\n'
        '      "story": "<a 3-4 sentence story-arc from the resume: '
        'situation, action, result>"}},\n'
        "    ... exactly 3 items ...\n"
        "  ],\n"
        '  "questions_to_ask": [\n'
        '    "<a smart question for the candidate to ask them>",\n'
        "    ... exactly 3 items ...\n"
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Every story must reference concrete facts from the resume "
        "(companies, skills, project names). No invented experience.\n"
        "- Questions must fit the role and company in the listing.\n"
        "- The role and company strings must echo the listing's exact "
        "role and company.\n"
        "- 5 questions, 3 stories, 3 questions-to-ask — exact counts."
    )

    _INTERVIEW_PREP_RETRY_SYSTEM = (
        "Your previous prep failed validation. Fix the errors and "
        "return a corrected JSON object with the same structure. "
        "Remember: ground every story in the real resume, exact item "
        "counts, no invented experience. Return valid JSON only."
    )

    _INTERVIEW_PREP_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same interview as before — role {role} at {company}. Correct "
        "the JSON: 5 likely_questions (question + how_to_answer), "
        "3 story_bank items (strength + story from the real resume), "
        "3 questions_to_ask, role and company echoing the listing.\n"
        "Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # E.T. conversation templates (Project E.T., 2026-09-06)
    # ------------------------------------------------------------------

    _ET_REPLY_SYSTEM = (
        "{persona}\n\n"
        "You are in a LIVE spoken conversation with a human learner of "
        "{language_name}. Reply ONLY with a JSON object.\n\n"
        "TONE RULES — NON-NEGOTIABLE:\n"
        "- Your reply text ({language_name}) must fit the learner's "
        "level: short simple sentences for absolute beginners, "
        "connected ideas once they hold conversations, natural rich "
        "language for advanced learners — but ALWAYS within reach "
        "of that learner.\n"
        "- Be warm and a little funny. Light cosmic humor is welcome. "
        "Never mock the learner. Never lecture.\n"
        "- At most one emoji per reply.\n"
        "- BANNED phrases (they smell like a robot): {banned}.\n"
        "- Corrections are gifts: state them kindly, briefly, like a "
        "friend who happens to know the word.\n"
        "- Keep the conversation ALIVE: end with a natural question or "
        "hook that invites the learner to speak again.\n"
        "- Stay in character the whole time. You are not an assistant; "
        "you are {persona_name}.\n"
        "- If the learner wrote in the wrong language, gently answer in "
        "{language_name} and note it in notes.\n"
        "- Return ONLY the JSON object. No fences, no prose."
    )

    _ET_REPLY_USER_BASE = (
        "SITUATION: {situation}\n"
        "LEARNER'S GOAL for this conversation: {goal}\n"
        "TARGET LENGTH: {turn_min} to {turn_max} total turns; "
        "{turn_number} done so far{end_hint}\n\n"
        "CONVERSATION SO FAR:\n{history}\n\n"
        "LEARNER JUST SAID (transcribed from their voice, may contain "
        "speech-to-text noise):\n\"{user_text}\"\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "reply": "<your reply in {language_name}>, 1-4 sentences '
        'at {difficulty} level",\n'
        '  "corrections": [{{"wrong": "<what they said or structured '
        'wrongly>", "right": "<the natural {language_name} way>", '
        '"why": "<6-15 word reason>"}}],  // 0-3 items, [] if perfect\n'
        '  "praise": "<one short warm sentence about what they did '
        'well>",\n'
        '  "end_conversation": <true only when {turn_number} reached '
        '{turn_min} AND the exchange naturally finished>\n'
        "}}\n"
        "The reply string is spoken aloud by your voice — make it "
        "sound alive, not written."
    )

    _ET_REPLY_RETRY_SYSTEM = (
        "Your previous reply failed validation. Fix the errors and "
        "return the same JSON shape. Stay in character as "
        "{persona_name}. Return ONLY valid JSON."
    )

    _ET_REPLY_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same conversation, same learner. Return the corrected JSON "
        'object: {{"reply", "corrections": [{{"wrong","right","why"}}], '
        '"praise", "end_conversation"}} — reply in {language_name} at '
        "{difficulty} level."
    )

    _ET_EVALUATE_SYSTEM = (
        "You are a strict but kind language coach evaluating ONE turn "
        "of a spoken conversation. Judge ONLY what the learner said "
        "against {difficulty} expectations for "
        "{language_name}. Return ONLY a JSON object."
    )

    _ET_EVALUATE_USER_BASE = (
        "Learner's transcribed speech (voice-to-text; judge the "
        "learner's language, not any transcription quirks):\n"
        "\"{user_text}\"\n\n"
        "Conversation context (what was being discussed):\n"
        "{history}\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "grammar": <1-5>,\n'
        '  "vocabulary": <1-5>,\n'
        '  "structure": <1-5>,\n'
        '  "relevance": <1-5>,\n'
        '  "corrected_sentence": "<their sentence rewritten naturally '
        'in {language_name} (empty string if already perfect)",\n'
        '  "notes": "<one honest sentence: the single most useful '
        'thing to improve>"\n'
        "}}\n"
        "1 = beginner attempt at this difficulty; 3 = solid for a "
        "{difficulty} learner; 5 = above the level. Judge against "
        "{difficulty}, never against native perfection.\n"
        "Worked example — learner said \"Ich geht nach Hause\": "
        '{{"grammar": 2, "vocabulary": 4, "structure": 3, '
        '"relevance": 5, "corrected_sentence": "Ich gehe nach Hause.", '
        '"notes": "verb conjugation: ich gehe, not ich geht"}}'
    )

    _ET_EVALUATE_RETRY_SYSTEM = (
        "Your previous evaluation failed validation. Fix the errors "
        "and return the same JSON shape: grammar/vocabulary/structure/"
        "relevance as integers 1-5, corrected_sentence string, notes "
        "string. Return ONLY valid JSON."
    )

    _ET_EVALUATE_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same learner turn, same conversation. Return the corrected "
        "JSON evaluation now — compact, no deliberation. Return valid "
        "JSON only."
    )

    # ------------------------------------------------------------------
    # Level exam templates (L5, Project E.T. 2026-09-06) — the inclusive
    # final test per CEFR level: vocabulary, grammar, reading, writing,
    # listening, speaking, with full evaluation + recommendations.
    # ------------------------------------------------------------------

    _LEVEL_EXAM_SYSTEM = (
        "You are an official examiner writing ONE complete final exam "
        "({difficulty} level) for {language_name}. The exam is "
        "inclusive: realistic everyday content, natural formal "
        "register, no trick questions, no obscure literature. Content "
        "must be authentic for the difficulty — beginner exams sound "
        "like a bakery, advanced exams sound like a newspaper opinion "
        "piece. Return ONLY a JSON object."
    )

    _LEVEL_EXAM_USER_BASE = (
        "Create the complete {difficulty} final exam for "
        "{language_name}.\n"
        "Everyday-life coverage: home, food, shopping, health, "
        "travel, people, work, services, leisure, feelings — spread "
        "across sections.\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "level": "{level}",\n'
        '  "language": "{language_name}",\n'
        '  "vocabulary": [  // 8 items\n'
        '    {{"question": "<which word fits this everyday gap?>",\n'
        '      "options": ["...", "...", "...", "..."],\n'
        '      "correct_index": <0-3>,\n'
        '      "topic": "<domain e.g. food_dining>"}}\n'
        "  ],\n"
        '  "grammar": [  // 10 items: 6 MC + 4 fill-in\n'
        '    {{"type": "mc", "question": "<{difficulty} structure test>",\n'
        '      "options": ["...", "...", "...", "..."],\n'
        '      "correct_index": <0-3>,\n'
        '      "grammar_point": "<e.g. Perfekt>"}},\n'
        '    {{"type": "fill", "sentence_with_blank": "<sentence with '
        '___ where the {difficulty} structure goes>",\n'
        '      "answer": "<one word or short phrase>",\n'
        '      "grammar_point": "<e.g. passive voice>"}}\n'
        "  ],\n"
        '  "reading": {{"passage": "<150-250 words of authentic '
        '{difficulty} text about an everyday situation>",\n'
        '    "questions": [  // 5 items\n'
        '      {{"question": "<comprehension>",\n'
        '        "options": ["...", "...", "...", "..."],\n'
        '        "correct_index": <0-3>}}\n'
        "    ]}},\n"
        '  "writing": {{"prompt": "<one everyday writing task at '
        '{difficulty}: email, note, review, or opinion>",\n'
        '    "min_words": <50-120 depending on difficulty>}},\n'
        '  "listening": {{"script": [  // 6-8 dialogue turns, two '
        'distinct speakers, everyday situation\n'
        '    {{"speaker": "<name>", "content": "<{language_name} '
        'line>"}}\n'
        "  ],\n"
        '    "questions": [  // 5 items about the dialogue\n'
        '      {{"question": "<comprehension>",\n'
        '        "options": ["...", "...", "...", "..."],\n'
        '        "correct_index": <0-3>}}\n'
        "    ]}},\n"
        '  "speaking": [  // 3 tasks\n'
        '    {{"type": "repeat", "text": "<one {difficulty} sentence to '
        'repeat aloud, 6-12 words>"}},\n'
        '    {{"type": "describe", "situation": "<everyday situation: '
        'describe what you would do/say>",\n'
        '      "target_phrases": ["<phrase>", "<phrase>"]}},\n'
        '    {{"type": "respond", "prompt": "<question to answer '
        'aloud in 2-3 sentences>"}}\n'
        "  ]\n"
        "}}\n"
        "Requirements:\n"
        "- Exactly 8 vocabulary, 10 grammar, 5 reading questions, 5 "
        "listening questions, 3 speaking tasks.\n"
        "- All option sets have exactly 4 options; correct_index "
        "0-3.\n"
        "- The listening script must be a REAL conversation (two "
        "named speakers, everyday topic, natural {language_name}).\n"
        "- No meta-text, no explanations, no humor inside exam "
        "items — exams stay serious, the UI carries the charm."
    )

    _LEVEL_EXAM_RETRY_SYSTEM = (
        "Your previous exam failed validation. Fix the errors and "
        "return the same JSON shape with exact item counts. Return "
        "ONLY valid JSON."
    )

    _LEVEL_EXAM_RETRY_USER_BASE = (
        "Your previous exam had these validation errors:\n"
        "{errors}\n\n"
        "Rebuild the complete {difficulty} exam for {language_name} "
        "with the exact same structure: 8 vocabulary MC, 10 grammar "
        "(6 MC + 4 fill), reading passage + 5 questions, 1 writing "
        "task, listening script (6-8 turns, 2 speakers) + 5 "
        "questions, 3 speaking tasks. Return valid JSON only."
    )

    _EXAM_JUDGE_SYSTEM = (
        "You are a fair examiner grading ONE written or spoken "
        "answer at {difficulty} level in {language_name}. Judge "
        "against {difficulty} expectations — not native perfection. "
        "Encouraging but honest. Return ONLY a JSON object."
    )

    _EXAM_JUDGE_USER_BASE = (
        "TASK GIVEN TO THE CANDIDATE:\n{task}\n\n"
        "CANDIDATE'S ANSWER:\n{answer}\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "grammar": <1-5>,\n'
        '  "vocabulary": <1-5>,\n'
        '  "structure": <1-5>,\n'
        '  "register": <1-5>,\n'
        '  "feedback": "<2-3 sentences: what was strong, what to '
        'improve, one concrete next step>",\n'
        '  "band_estimate": "<a1|a2|b1|b2|c1 — the CEFR band this '
        'answer actually demonstrates>"\n'
        "}}\n"
        "Scores of 3 mean solid for a {difficulty} learner. Judge the "
        "language, not handwriting or transcription noise.\n"
        "Worked example — task \"describe your morning\", answer "
        "\"Ich trinke Kaffee und ich esse Brot\": "
        '{{"grammar": 4, "vocabulary": 3, "structure": 4, '
        '"register": 4, "feedback": "Clear routine, natural word '
        'order. Next: add one time phrase.", "band_estimate": "a2"}}'
    )

    _EXAM_JUDGE_RETRY_SYSTEM = (
        "Your previous grading failed validation. Fix the errors and "
        "return the same JSON shape: four integer scores 1-5, a "
        "feedback string, and a band_estimate of a1|a2|b1|b2|c1. "
        "Return ONLY valid JSON."
    )

    _EXAM_JUDGE_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same candidate answer. Return the corrected grading JSON "
        "now — compact, no deliberation. Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Placement quiz (L5): the 10-minute "where do I start?" test.
    # Built as three 4-item band blocks (a1/a2/b1) assembled in
    # order — a single 12-item call spirals reasoning models
    # (measured live: 4000+ deliberation tokens, zero content), while
    # 4-item blocks complete reliably.
    # ------------------------------------------------------------------

    _PLACEMENT_BAND_SYSTEM = (
        "You are a placement-test designer. Create a SHORT diagnostic "
        "block: exactly 4 multiple-choice items at {difficulty} "
        "difficulty for {language_name}. Everyday vocabulary and "
        "structures only. Return ONLY a JSON object."
    )

    _PLACEMENT_BAND_USER_BASE = (
        "Create 4 {difficulty} multiple-choice items for "
        "{language_name} about food, shopping, work, directions or "
        "health.\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "items": [\n'
        '    {{"question": "<question>",\n'
        '      "options": ["...", "...", "...", "..."],\n'
        '      "correct_index": <0-3>}}\n'
        "  ]\n"
        "}}\n"
        "Exactly 4 items. Every item must test {language_name} "
        "itself — word meanings, articles, simple sentences in "
        "{language_name}. NEVER general knowledge, math, science "
        "trivia, or questions answerable without knowing "
        "{language_name}.\n"
        "Every option must look plausible with exactly one clearly "
        "best answer.\n"
        "Example:\n"
        '{{"items": [{{"question": "Which word means '
        "'bread'\", "
        '"options": ["Brot", "Milch", "Wasser", "Apfel"], '
        '"correct_index": 0}}]}}\n'
    )

    _PLACEMENT_BAND_RETRY_SYSTEM = (
        "Your previous block failed validation. Fix the errors and "
        "return the same shape: exactly 4 items, each with question, "
        "4 options, correct_index 0-3. Return ONLY valid JSON."
    )

    _PLACEMENT_BAND_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Rebuild the 4 {difficulty} items now — compact, no "
        "deliberation. Return valid JSON only."
    )

    # ------------------------------------------------------------------
    # Skills Arena templates (L6, Project E.T. 2026-09-06)
    # ------------------------------------------------------------------

    _READING_PACK_SYSTEM = (
        "You are a reading-comprehension coach. Turn the given text "
        "into a {difficulty}-appropriate reading pack for "
        "{language_name} learners: a cleaned-up version of the text "
        "(kept in its original language), a short glossary of the "
        "hardest words with translations, and exactly 4 comprehension "
        "questions with 4 options each. Return ONLY a JSON object."
    )

    _READING_PACK_USER_BASE = (
        "SOURCE TEXT (a document the learner imported):\n"
        "\"\"\"{text}\"\"\"\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "title": "<short title>",\n'
        '  "cleaned_text": "<the text, lightly edited for clarity, '
        'original language preserved>",\n'
        '  "glossary": [  // 5-8 entries\n'
        '    {{"term": "<word or phrase>", "translation": "<meaning '
        'in {language_name}>"}}\n'
        "  ],\n"
        '  "questions": [  // exactly 4\n'
        '    {{"question": "<comprehension>",\n'
        '      "options": ["...", "...", "...", "..."],\n'
        '      "correct_index": <0-3>}}\n'
        "  ]\n"
        "}}\n"
        "Questions test understanding, not trivia. The glossary picks "
        "the words a {difficulty} learner would stumble on."
    )

    _WRITING_EVAL_SYSTEM = (
        "You are a warm writing coach for {language_name} learners at "
        "{difficulty} level. Evaluate the learner's text honestly, "
        "then produce a corrected version. Praise what works FIRST. "
        "Return ONLY a JSON object."
    )

    _WRITING_EVAL_USER_BASE = (
        "WRITING TASK GIVEN:\n{task}\n\n"
        "LEARNER'S TEXT:\n\"\"\"{text}\"\"\"\n\n"
        "Return this exact JSON:\n"
        "{{\n"
        '  "grammar": <1-5>, "vocabulary": <1-5>, '
        '"structure": <1-5>, "register": <1-5>,\n'
        '  "strength": "<one sentence: the best thing about this '
        'text>",\n'
        '  "corrected_text": "<the learner\'s text rewritten to '
        'natural, level-appropriate {language_name} — same ideas, '
        'their voice, just said well>",\n'
        '  "highlights": [  // 2-5 specific fixes\n'
        '    {{"wrong": "<from their text>", "right": "<the fix>", '
        '"why": "<short reason>"}}\n'
        "  ],\n"
        '  "next_step": "<one concrete practice suggestion>"\n'
        "}}\n"
        "The corrected text must preserve the learner's meaning and "
        "personality — improve, never replace."
    )

    _WRITING_EVAL_RETRY_SYSTEM = (
        "Your previous evaluation failed validation. Fix the errors "
        "and return the same JSON shape. Return ONLY valid JSON."
    )

    _WRITING_EVAL_RETRY_USER_BASE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Same learner text, same task. Return the corrected JSON: "
        "grammar/vocabulary/structure/register 1-5, strength, "
        "corrected_text, 2-5 highlights (wrong/right/why), "
        "next_step. Return valid JSON only."
    )

    def _register_builtins(self) -> None:
        """
        Contract: populate the registry with the templates required
        by the current v1 scope. New templates are added here as
        engines grow.

        Templates defined:
          - journey_generate: primary template for topic+level →
            journey JSON (cards with quizzes)
          - journey_retry: feedback template used on validation
            failure to ask the model to self-correct
          - resume_generate: primary template for profile → resume JSON
          - resume_retry: feedback template for resume validation failure
          - resume_enhance: primary template for enhancing a resume
          - resume_enhance_retry: feedback template for resume enhance failure
          - podcast_script_generate: primary template for podcast script
          - podcast_script_retry: feedback template for podcast script failure
          - bilingual_generate / bilingual_retry: Bilingual Pair lesson
          - youtube_summary_generate / youtube_summary_retry: traceable
            video summaries (P1.6)
          - bilingual_verify: translation-fidelity verdict (P3.2)
          - capability_probe: one-shot model calibration prompt (P7.1)
          - lesson_pack_generate / lesson_pack_retry: dialogue +
            vocabulary half of a whole-lesson pack (P7.2, split
            2026-09-07 — halves complete reliably where full packs
            spiral reasoning models)
          - lesson_pack_part2_generate / lesson_pack_part2_retry:
            grammar + evaluation half (receives part 1's vocab terms
            as grounding context)
          - lesson_judge: one-shot learner-answer grading verdict (P7.3)
          - lesson_verify: pack explanation/translation fidelity audit (P7.3)
          - cover_letter_generate: tailored cover letter for a listing (career agent)
        """
        self._templates["journey_generate"] = PromptTemplate(
            name="journey_generate",
            system=self._JOURNEY_SYSTEM,
            user=self._JOURNEY_USER_BASE,
            schema_key="journey",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.7},
        )
        self._templates["journey_retry"] = PromptTemplate(
            name="journey_retry",
            system=self._JOURNEY_RETRY_SYSTEM,
            user=self._JOURNEY_RETRY_USER_TEMPLATE,
            schema_key="journey",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["resume_generate"] = PromptTemplate(
            name="resume_generate",
            system=self._RESUME_SYSTEM,
            user=self._RESUME_USER_BASE,
            schema_key="resume",
            metadata={"default_max_tokens": 2048, "default_temperature": 0.3},
        )
        self._templates["resume_retry"] = PromptTemplate(
            name="resume_retry",
            system=self._RESUME_RETRY_SYSTEM,
            user=self._RESUME_RETRY_USER_TEMPLATE,
            schema_key="resume",
            metadata={"default_max_tokens": 2048, "default_temperature": 0.3},
        )
        self._templates["resume_enhance"] = PromptTemplate(
            name="resume_enhance",
            system=self._RESUME_ENHANCE_SYSTEM,
            user=self._RESUME_ENHANCE_USER_BASE,
            schema_key="resume",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["resume_enhance_retry"] = PromptTemplate(
            name="resume_enhance_retry",
            system=self._RESUME_ENHANCE_RETRY_SYSTEM,
            user=self._RESUME_ENHANCE_RETRY_USER_TEMPLATE,
            schema_key="resume",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["podcast_script_generate"] = PromptTemplate(
            name="podcast_script_generate",
            system=self._PODCAST_SYSTEM,
            user=self._PODCAST_USER_BASE,
            schema_key="podcast_script",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.7},
        )
        self._templates["podcast_script_retry"] = PromptTemplate(
            name="podcast_script_retry",
            system=self._PODCAST_RETRY_SYSTEM,
            user=self._PODCAST_RETRY_USER_TEMPLATE,
            schema_key="podcast_script",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["bilingual_generate"] = PromptTemplate(
            name="bilingual_generate",
            system=self._BILINGUAL_SYSTEM,
            user=self._BILINGUAL_USER_BASE,
            schema_key="bilingual",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["bilingual_retry"] = PromptTemplate(
            name="bilingual_retry",
            system=self._BILINGUAL_RETRY_SYSTEM,
            user=self._BILINGUAL_RETRY_USER_TEMPLATE,
            schema_key="bilingual",
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["youtube_summary_generate"] = PromptTemplate(
            name="youtube_summary_generate",
            system=self._YOUTUBE_SUMMARY_SYSTEM,
            user=self._YOUTUBE_SUMMARY_USER_BASE,
            schema_key="youtube_summary",
            metadata={"default_max_tokens": 1024, "default_temperature": 0.3},
        )
        self._templates["bilingual_verify"] = PromptTemplate(
            name="bilingual_verify",
            system=self._BILINGUAL_VERIFY_SYSTEM,
            user=self._BILINGUAL_VERIFY_USER_BASE,
            schema_key="bilingual",
            metadata={"default_max_tokens": 1024, "default_temperature": 0.0},
        )
        self._templates["youtube_summary_retry"] = PromptTemplate(
            name="youtube_summary_retry",
            system=self._YOUTUBE_SUMMARY_RETRY_SYSTEM,
            user=self._YOUTUBE_SUMMARY_RETRY_USER_TEMPLATE,
            schema_key="youtube_summary",
            metadata={"default_max_tokens": 1024, "default_temperature": 0.3},
        )
        self._templates["capability_probe"] = PromptTemplate(
            name="capability_probe",
            system=self._CAPABILITY_PROBE_SYSTEM,
            user=self._CAPABILITY_PROBE_USER_BASE,
            metadata={"default_max_tokens": 512, "default_temperature": 0.0},
        )
        self._templates["lesson_pack_generate"] = PromptTemplate(
            name="lesson_pack_generate",
            system=self._LESSON_PACK_SYSTEM,
            user=self._LESSON_PACK_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["lesson_pack_retry"] = PromptTemplate(
            name="lesson_pack_retry",
            system=self._LESSON_PACK_RETRY_SYSTEM,
            user=self._LESSON_PACK_RETRY_USER_TEMPLATE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["lesson_pack_part2_generate"] = PromptTemplate(
            name="lesson_pack_part2_generate",
            system=self._LESSON_PACK_SYSTEM,
            user=self._LESSON_PACK_PART2_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["lesson_pack_part1_retry"] = PromptTemplate(
            name="lesson_pack_part1_retry",
            system=self._LESSON_PACK_RETRY_SYSTEM,
            user=self._LESSON_PACK_PART1_RETRY_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["lesson_pack_part2_retry"] = PromptTemplate(
            name="lesson_pack_part2_retry",
            system=self._LESSON_PACK_RETRY_SYSTEM,
            user=self._LESSON_PACK_PART2_RETRY_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["lesson_judge"] = PromptTemplate(
            name="lesson_judge",
            system=self._LESSON_JUDGE_SYSTEM,
            user=self._LESSON_JUDGE_USER_BASE,
            metadata={"default_max_tokens": 512, "default_temperature": 0.0},
        )
        self._templates["cover_letter_generate"] = PromptTemplate(
            name="cover_letter_generate",
            system=self._COVER_LETTER_SYSTEM,
            user=self._COVER_LETTER_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.4},
        )
        self._templates["lesson_verify"] = PromptTemplate(
            name="lesson_verify",
            system=self._LESSON_VERIFY_SYSTEM,
            user=self._LESSON_VERIFY_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.0},
        )
        self._templates["linkedin_post_generate"] = PromptTemplate(
            name="linkedin_post_generate",
            system=self._LINKEDIN_POST_SYSTEM,
            user=self._LINKEDIN_POST_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.7},
        )
        self._templates["linkedin_post_retry"] = PromptTemplate(
            name="linkedin_post_retry",
            system=self._LINKEDIN_POST_RETRY_SYSTEM,
            user=self._LINKEDIN_POST_RETRY_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.7},
        )
        self._templates["interview_prep_generate"] = PromptTemplate(
            name="interview_prep_generate",
            system=self._INTERVIEW_PREP_SYSTEM,
            user=self._INTERVIEW_PREP_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.4},
        )
        self._templates["interview_prep_retry"] = PromptTemplate(
            name="interview_prep_retry",
            system=self._INTERVIEW_PREP_RETRY_SYSTEM,
            user=self._INTERVIEW_PREP_RETRY_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.4},
        )
        self._templates["et_reply"] = PromptTemplate(
            name="et_reply",
            system=self._ET_REPLY_SYSTEM,
            user=self._ET_REPLY_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.8},
        )
        self._templates["et_reply_retry"] = PromptTemplate(
            name="et_reply_retry",
            system=self._ET_REPLY_RETRY_SYSTEM,
            user=self._ET_REPLY_RETRY_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.8},
        )
        self._templates["et_evaluate"] = PromptTemplate(
            name="et_evaluate",
            system=self._ET_EVALUATE_SYSTEM,
            user=self._ET_EVALUATE_USER_BASE,
            metadata={"default_max_tokens": 2048, "default_temperature": 0.2},
        )
        self._templates["et_evaluate_retry"] = PromptTemplate(
            name="et_evaluate_retry",
            system=self._ET_EVALUATE_RETRY_SYSTEM,
            user=self._ET_EVALUATE_RETRY_USER_BASE,
            metadata={"default_max_tokens": 2048, "default_temperature": 0.2},
        )
        self._templates["level_exam_generate"] = PromptTemplate(
            name="level_exam_generate",
            system=self._LEVEL_EXAM_SYSTEM,
            user=self._LEVEL_EXAM_USER_BASE,
            metadata={"default_max_tokens": 8192, "default_temperature": 0.5},
        )
        self._templates["level_exam_retry"] = PromptTemplate(
            name="level_exam_retry",
            system=self._LEVEL_EXAM_RETRY_SYSTEM,
            user=self._LEVEL_EXAM_RETRY_USER_BASE,
            metadata={"default_max_tokens": 8192, "default_temperature": 0.5},
        )
        self._templates["exam_judge"] = PromptTemplate(
            name="exam_judge",
            system=self._EXAM_JUDGE_SYSTEM,
            user=self._EXAM_JUDGE_USER_BASE,
            metadata={"default_max_tokens": 2048, "default_temperature": 0.2},
        )
        self._templates["exam_judge_retry"] = PromptTemplate(
            name="exam_judge_retry",
            system=self._EXAM_JUDGE_RETRY_SYSTEM,
            user=self._EXAM_JUDGE_RETRY_USER_BASE,
            metadata={"default_max_tokens": 2048, "default_temperature": 0.2},
        )
        self._templates["placement_band_generate"] = PromptTemplate(
            name="placement_band_generate",
            system=self._PLACEMENT_BAND_SYSTEM,
            user=self._PLACEMENT_BAND_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.4},
        )
        self._templates["placement_band_retry"] = PromptTemplate(
            name="placement_band_retry",
            system=self._PLACEMENT_BAND_RETRY_SYSTEM,
            user=self._PLACEMENT_BAND_RETRY_USER_BASE,
            metadata={"default_max_tokens": 2048, "default_temperature": 0.4},
        )
        self._templates["reading_pack_generate"] = PromptTemplate(
            name="reading_pack_generate",
            system=self._READING_PACK_SYSTEM,
            user=self._READING_PACK_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["writing_eval_generate"] = PromptTemplate(
            name="writing_eval_generate",
            system=self._WRITING_EVAL_SYSTEM,
            user=self._WRITING_EVAL_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )
        self._templates["writing_eval_retry"] = PromptTemplate(
            name="writing_eval_retry",
            system=self._WRITING_EVAL_RETRY_SYSTEM,
            user=self._WRITING_EVAL_RETRY_USER_BASE,
            metadata={"default_max_tokens": 4096, "default_temperature": 0.3},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> PromptTemplate:
        """
        Contract: return the PromptTemplate for the given name.

        Raises:
            KeyError: if no template with the given name exists.
        """
        if name not in self._templates:
            raise KeyError(
                f"Unknown prompt template '{name}'. "
                f"Available: {list(self._templates.keys())}"
            )
        return self._templates[name]

    def render(self, name: str, variables: dict[str, Any]) -> tuple[str, str, Optional[str]]:
        """
        Contract: render a named template with the given variables and
        return (system_prompt, user_prompt, schema_key).

        Placeholder format: {variable_name} — substituted directly
        from the variables dict. Missing variables raise KeyError.

        Args:
            name: the template name registered in this registry.
            variables: a flat dict of substitution values. Keys must
                       match all {placeholders} in the template.

        Returns:
            A 3-tuple of (system_prompt, user_prompt, schema_key)
            ready to be passed to LmStudioClient.generate().
        """
        template = self.get(name)
        system = template.system.format(**variables)
        user = template.user.format(**variables)
        return system, user, template.schema_key
