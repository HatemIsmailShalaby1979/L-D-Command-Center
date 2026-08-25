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
        "- There are EXACTLY TWO hosts: {host_name} and {co_host_name}. "
        "Every segment is spoken by one of them — no other speakers.\n"
        "- It is a REAL conversation: they ask each other questions, "
        "disagree, react to what the other just said. {co_host_name} is "
        "never a silent sidekick.\n"
        "- Hosts MUST alternate: two consecutive segments may never have "
        "the same speaker.\n"
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
        "Generate a corrected podcast script with {num_segments} segments.\n"
        "Return valid JSON only."
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
        "Create a lesson pack on the topic \"{topic}\".\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {level}\n\n"
        "Return a JSON object with this exact structure:\n"
        "{{\n"
        '  "topic": "<the topic string>",\n'
        '  "target_language": "{target_language}",\n'
        '  "known_language": "{known_language}",\n'
        '  "level": "{level}",\n'
        '  "dialogue": [\n'
        '    {{\n'
        '      "speaker": "<speaker name>",\n'
        '      "content": "<sentence ENTIRELY in {target_language}>"\n'
        '    }}\n'
        "  ],\n"
        '  "vocab_cards": [\n'
        '    {{\n'
        '      "term": "<word or phrase in {target_language}>",\n'
        '      "reading": "<pronunciation hint or transliteration>",\n'
        '      "translation": "<meaning in {known_language}>",\n'
        '      "example": "<example sentence in {target_language}>"\n'
        '    }}\n'
        "  ],\n"
        '  "grammar_cards": [\n'
        '    {{\n'
        '      "point": "<grammar point>",\n'
        '      "explanation": "<short explanation in {known_language}>",\n'
        '      "drills": [\n'
        '        {{"prompt": "<item in {target_language}>", '
        '"answer": "<correct answer>"}},\n'
        '        {{"prompt": "...", "answer": "..."}}\n'
        "      ]\n"
        '    }}\n'
        "  ],\n"
        '  "evaluation": [\n'
        '    {{\n'
        '      "type": "multiple_choice",\n'
        '      "question": "<question in {known_language}>",\n'
        '      "options": ["<option A>", "<option B>", "<option C>"],\n'
        '      "correct_index": <0-based index into options>\n'
        '    }},\n'
        '    {{\n'
        '      "type": "fill_in_blank",\n'
        '      "sentence_with_blank": "<sentence in {target_language} '
        'with ___ marking the blank>",\n'
        '      "answer": "<the missing word or phrase>"\n'
        '    }},\n'
        '    {{\n'
        '      "type": "translation",\n'
        '      "prompt": "<sentence in {known_language}>",\n'
        '      "answer": "<faithful translation in {target_language}>"\n'
        '    }},\n'
        '    {{\n'
        '      "type": "transformation",\n'
        '      "prompt": "<sentence in {target_language} to rewrite",\n'
        '      "answer": "<correctly rewritten sentence>"\n'
        '    }}\n'
        "  ]\n"
        "}}\n\n"
        "Requirements:\n"
        "- Produce exactly {num_dialogue} dialogue turns between EXACTLY "
        "two distinct named speakers.\n"
        "- All dialogue content and vocab terms/examples MUST be entirely "
        "in {target_language}; explanations, questions, translations in "
        "{known_language}.\n"
        "- Produce exactly {num_vocab} vocab cards, {num_grammar} grammar "
        "cards (each with at least 2 drills), and {num_eval} evaluation "
        "items mixing the four types (multiple_choice, fill_in_blank, "
        "translation, transformation).\n"
        "- fill_in_blank sentences must contain a ___ blank marker.\n"
        "- correct_index must be an integer within range of options.\n"
        "- Content must suit {level} learners.\n"
        "- Return valid JSON only."
    )

    _LESSON_PACK_RETRY_SYSTEM = (
        "You previously generated a lesson pack that failed schema "
        "validation. Fix the errors below and return a corrected JSON "
        "object with the same structure. Return valid JSON only — no "
        "prose, no markdown fences."
    )

    _LESSON_PACK_RETRY_USER_TEMPLATE = (
        "Your previous output had these validation errors:\n"
        "{errors}\n\n"
        "Topic: \"{topic}\"\n"
        "Target language: {target_language}\n"
        "Known language: {known_language}\n"
        "Learner level: {level}\n"
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
        "Learner level: {level}\n\n"
        "Exercise item:\n{item}\n\n"
        "Learner answer:\n{answer}\n\n"
        'Return a JSON object: {{"passed": true|false, '
        '"correct_answer": "<the canonical correct answer>", '
        '"issues": ["<short reason>", ...]}}\n'
        "- passed=true ONLY when the learner answer is a correct, "
        "natural response to the exercise.\n"
        "- List every defect in issues; use an empty list when passed.\n"
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
        "Learner level: {level}\n\n"
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
          - lesson_pack_generate / lesson_pack_retry: whole-lesson pack
            (dialogue + vocab + grammar + evaluation) for the Language
            Lab flagship (P7.2)
          - lesson_judge: one-shot learner-answer grading verdict (P7.3)
          - lesson_verify: pack explanation/translation fidelity audit (P7.3)
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
        self._templates["lesson_judge"] = PromptTemplate(
            name="lesson_judge",
            system=self._LESSON_JUDGE_SYSTEM,
            user=self._LESSON_JUDGE_USER_BASE,
            metadata={"default_max_tokens": 512, "default_temperature": 0.0},
        )
        self._templates["lesson_verify"] = PromptTemplate(
            name="lesson_verify",
            system=self._LESSON_VERIFY_SYSTEM,
            user=self._LESSON_VERIFY_USER_BASE,
            metadata={"default_max_tokens": 1024, "default_temperature": 0.0},
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
