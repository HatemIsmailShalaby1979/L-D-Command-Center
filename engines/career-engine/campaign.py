# engines/career-engine/campaign.py
#
# WHAT: Career Campaign mode v0 — the Campaign tier's core: an
#       apply-tracking pipeline (status ladder per application) plus
#       per-listing interview-prep generation grounded in the resume
#       and the listing text.
# WHY:  PROFIT_PLAN §2 Campaign tier ($29/month) is sold on exactly
#       two things: (1) the watchlist becomes a campaign manager —
#       every application tracked from 'prepared' to 'closed'; (2)
#       interview prep packs generated per listing. v0 delivers both
#       on top of the existing career-engine pieces: tracking is pure
#       offline state (Storage), prep generation is one new Pipeline
#       template validated deterministically. No new infrastructure,
#       no network beyond what career-engine already does.
# BREAKS IF DELETED: The Campaign tier has no product surface; the $29
#       rung of the ladder (PROFIT_PLAN §9's metric: Pro -> Campaign
#       conversion) has nothing to convert to.

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry
from model_layer.schema import _validate_object

logger = logging.getLogger(__name__)

__all__ = [
    "STATUS_LADDER", "DEFAULT_STATUS", "ApplicationRecord",
    "CampaignStore", "generate_interview_prep",
    "validate_interview_prep",
]

# The status ladder: every application moves through these. Ordered by
# the real hiring sequence; the store rejects unknown states so the
# data stays pivotable (a spreadsheet of lies is worse than none).
STATUS_LADDER = (
    "prepared",      # package built by prepare_application
    "submitted",     # human clicked Apply on the board
    "screening",     # recruiter contact / questionnaire
    "interviewing",  # any live conversation scheduled or done
    "offer",         # written offer received
    "rejected",      # closed without offer
    "withdrawn",     # candidate closed it
)
DEFAULT_STATUS = "prepared"

_VALID_STATUSES = set(STATUS_LADDER)


class ApplicationRecord:
    """One tracked application. A plain serializable dict carrier —
    the store owns persistence, this type owns shape discipline."""

    def __init__(self, listing: dict[str, Any], *,
                 status: str = DEFAULT_STATUS,
                 prepared_at: Optional[str] = None,
                 updated_at: Optional[str] = None,
                 notes: str = "",
                 package_dir: str = "",
                 listing_json: Optional[dict[str, Any]] = None):
        self.listing = listing_json or dict(listing)
        self.status = status if status in _VALID_STATUSES else DEFAULT_STATUS
        self.prepared_at = prepared_at or _now_iso()
        self.updated_at = updated_at or self.prepared_at
        self.notes = notes
        self.package_dir = package_dir

    # -- identity -----------------------------------------------------------

    @property
    def url(self) -> str:
        return str(self.listing.get("url") or "")

    @property
    def company(self) -> str:
        return str(self.listing.get("company") or "?")

    @property
    def title(self) -> str:
        return str(self.listing.get("title") or "?")

    @property
    def key(self) -> str:
        return record_key(self.listing)

    # -- lifecycle ----------------------------------------------------------

    def advance(self, status: str, *, notes: str = "") -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"Unknown application status {status!r}; expected one of "
                f"{list(STATUS_LADDER)}")
        self.status = status
        self.updated_at = _now_iso()
        if notes:
            self.notes = (f"{self.notes}\n{self.updated_at}: {notes}"
                          if self.notes else
                          f"{self.updated_at}: {notes}").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing,
            "status": self.status,
            "prepared_at": self.prepared_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
            "package_dir": self.package_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationRecord":
        return cls(data.get("listing") or {},
                   status=str(data.get("status") or DEFAULT_STATUS),
                   prepared_at=data.get("prepared_at"),
                   updated_at=data.get("updated_at"),
                   notes=str(data.get("notes") or ""),
                   package_dir=str(data.get("package_dir") or ""),
                   )


def record_key(listing: dict[str, Any]) -> str:
    """Stable identity for one application: the listing URL (boards
    re-title jobs but never re-URL them); company-role fallback keeps
    keyless watchlist listings trackable too."""
    url = str(listing.get("url") or "").strip()
    if url:
        return url
    return (f"{str(listing.get('company') or '?')}-"
            f"{str(listing.get('title') or '?')}").lower()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class CampaignStore:
    """Contract: the apply-tracking state, persisted as one Storage
    preference (offline, backup-safe, restart-surviving). Shape::

        {"records": {<key>: {listing, status, prepared_at,
                             updated_at, notes, package_dir}}}

    Deduped by listing URL; every mutation rewrites the whole document
    (small data, simple integrity)."""

    def __init__(self, storage):
        self.storage = storage

    _PREF = "campaign_applications"

    def _load(self) -> dict[str, Any]:
        raw = self.storage.get_preference(self._PREF, {}) or {}
        return raw if isinstance(raw, dict) else {}

    def _save(self, doc: dict[str, Any]) -> None:
        self.storage.set_preference(self._PREF, doc)

    # -- CRUD ----------------------------------------------------------------

    def track(self, listing: dict[str, Any], *,
              package_dir: str = "",
              status: str = DEFAULT_STATUS) -> ApplicationRecord:
        """Track (or re-track) one application. Re-preparing an already
        tracked listing does NOT reset its status — the pipeline may be
        re-run, the history is the point."""
        doc = self._load()
        records = doc.get("records") or {}
        record = ApplicationRecord(listing, status=status,
                                   package_dir=package_dir)
        existing = records.get(record.key)
        if isinstance(existing, dict):
            prior = ApplicationRecord.from_dict(existing)
            prior.package_dir = package_dir or prior.package_dir
            prior.updated_at = _now_iso()
            record = prior
        records[record.key] = record.to_dict()
        self._save({"records": records})
        logger.info("Campaign tracking %s @ %s -> %s",
                    record.title, record.company, record.status)
        return record

    def advance(self, listing: dict[str, Any], status: str, *,
                notes: str = "") -> ApplicationRecord:
        doc = self._load()
        records = doc.get("records") or {}
        key = record_key(listing)
        existing = records.get(key)
        if not isinstance(existing, dict):
            raise ValueError(
                "That listing is not tracked yet — track it first "
                "(it becomes tracked when you prepare an application "
                "or press Track).")
        record = ApplicationRecord.from_dict(existing)
        record.advance(status, notes=notes)
        records[key] = record.to_dict()
        self._save({"records": records})
        return record

    def untrack(self, listing: dict[str, Any]) -> None:
        doc = self._load()
        records = doc.get("records") or {}
        records.pop(record_key(listing), None)
        self._save({"records": records})

    def get(self, listing: dict[str, Any]) -> Optional[ApplicationRecord]:
        existing = (self._load().get("records") or {}).get(
            record_key(listing))
        return ApplicationRecord.from_dict(existing) if isinstance(
            existing, dict) else None

    def all_records(self) -> list[ApplicationRecord]:
        records = (self._load().get("records") or {})
        out = [ApplicationRecord.from_dict(r) for r in records.values()
               if isinstance(r, dict)]
        out.sort(key=lambda r: (r.updated_at, r.key), reverse=True)
        return out

    # -- reporting -----------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """The campaign dashboard read: counts per status + open
        pipeline (everything not closed)."""
        rows = self.all_records()
        counts = {status: 0 for status in STATUS_LADDER}
        for record in rows:
            counts[record.status] = counts.get(record.status, 0) + 1
        closed = {"rejected", "withdrawn"}
        open_pipeline = [r for r in rows if r.status not in closed]
        return {"total": len(rows), "counts": counts,
                "open": len(open_pipeline),
                "records": [r.to_dict() for r in rows]}


# ---------------------------------------------------------------------------
# Interview prep generation (Campaign tier feature #2)
# ---------------------------------------------------------------------------

PREP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["role", "company", "likely_questions", "story_bank",
                 "questions_to_ask"],
    "properties": {
        "role": {"type": "string", "minLength": 1},
        "company": {"type": "string", "minLength": 1},
        "likely_questions": {
            "type": "array", "minItems": 3,
            "items": {"type": "object",
                      "required": ["question", "how_to_answer"],
                      "properties": {
                          "question": {"type": "string", "minLength": 1},
                          "how_to_answer": {"type": "string",
                                            "minLength": 1},
                      },
                      "additionalProperties": False},
        },
        "story_bank": {
            "type": "array", "minItems": 2,
            "items": {"type": "object",
                      "required": ["strength", "story"],
                      "properties": {
                          "strength": {"type": "string", "minLength": 1},
                          "story": {"type": "string", "minLength": 1},
                      },
                      "additionalProperties": False},
        },
        "questions_to_ask": {
            "type": "array", "minItems": 2,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": False,
}


def validate_interview_prep(raw: Any, *,
                            expected_company: str = "",
                            expected_role: str = "",
                            ) -> tuple[bool, list[str]]:
    """Schema pass + grounding checks the JSON subset cannot express:
    when expectations are given, the prep must actually reference the
    listing's company and role (prevents a generic, non-tailored prep
    from passing)."""
    if not isinstance(raw, dict):
        return False, [f"expected a JSON object, got {type(raw).__name__}"]
    errors = _validate_object(raw, PREP_SCHEMA, "$")
    if errors:
        return False, errors
    if expected_company:
        company = str(raw.get("company") or "")
        if expected_company.lower()[:6] not in company.lower():
            errors.append(
                f"company must reference {expected_company!r}, "
                f"got {company!r}")
    if expected_role:
        role = str(raw.get("role") or "")
        if expected_role.lower()[:6] not in role.lower():
            errors.append(
                f"role must reference {expected_role!r}, got {role!r}")
    return not errors, errors


def generate_interview_prep(
    resume: dict[str, Any],
    *,
    role: str,
    company: str,
    snippet: str = "",
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Contract: one validated interview-prep document for ONE listing,
    grounded in the resume (the story bank comes from the candidate's
    real experience) and the listing text. Same Guardrail Loop as every
    artifact; the pipeline injects the JSON discipline addendum.

    Raises:
        ValueError: empty role/company, or a resume with nothing to
            ground stories in.
        SchemaValidationError: invalid after all pipeline attempts.
        ConnectionError / ApiError: per the pipeline error taxonomy.
    """
    import json as _json

    role = (role or "").strip()
    company = (company or "").strip()
    if not role:
        raise ValueError("Role must be non-empty")
    if not company:
        raise ValueError("Company must be non-empty")
    if not isinstance(resume, dict) or not resume:
        raise ValueError("A resume is required — interview prep is "
                         "grounded in your real experience")

    def validator(parsed: Any) -> tuple[bool, list[str]]:
        return validate_interview_prep(
            parsed,
            expected_company=company,
            expected_role=role)

    validated = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="interview_prep_generate",
        retry_template="interview_prep_retry",
        variables={
            "role": role,
            "company": company,
            "snippet": snippet or "(full listing not captured)",
            "resume": _json.dumps(resume, ensure_ascii=False)[:4000],
        },
        validator=validator,
        model=model,
        max_tokens=4096,
        temperature=0.4,
    )
    logger.info("Interview prep generated for %s @ %s", role[:40],
                company[:40])
    return validated
