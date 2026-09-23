# engines/career-engine/test_campaign.py
#
# WHAT: Contract tests for Career Campaign mode v0 — the apply-tracking
#       store and the interview-prep generation seam.
# WHY:  The Campaign tier ($29/month, PROFIT_PLAN §2) is sold on this:
#       the ladder must never lose history, dedupe must key on listing
#       URL, prep generation must be grounded (no invented experience,
#       company/role echoed), and the whole thing works offline.
# BREAKS IF DELETED: The $29 rung has no protected surface; a status
#       bug silently corrupts the user's real job-hunt history.

from __future__ import annotations

import json
from types import SimpleNamespace as SN

import pytest

from engines.career_engine.campaign import (
    DEFAULT_STATUS, STATUS_LADDER, ApplicationRecord, CampaignStore,
    generate_interview_prep, record_key, validate_interview_prep,
)
from model_layer.pipeline import DEFAULT_MODEL
from model_layer.schema import SchemaValidationError
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


@pytest.fixture
def store(storage):
    return CampaignStore(storage)


LISTING = {"company": "Widgetco", "title": "Support Engineer",
           "url": "https://boards.example/widgetco/123",
           "snippet": "Customer-first support team."}


class TestRecords:
    def test_ladder_is_ordered_and_complete(self):
        assert STATUS_LADDER[0] == "prepared"
        assert set(STATUS_LADDER) == {
            "prepared", "submitted", "screening", "interviewing",
            "offer", "rejected", "withdrawn"}

    def test_key_is_listing_url(self):
        assert record_key(LISTING) == LISTING["url"]

    def test_keyless_listing_falls_back_to_company_role(self):
        assert record_key({"company": "A", "title": "B"}) == "a-b"

    def test_unknown_status_snaps_to_default(self):
        rec = ApplicationRecord(LISTING, status="nonsense")
        assert rec.status == DEFAULT_STATUS

    def test_advance_appends_timestamped_note(self):
        rec = ApplicationRecord(LISTING)
        rec.advance("submitted", notes="applied via board")
        assert rec.status == "submitted"
        assert "applied via board" in rec.notes
        with pytest.raises(ValueError):
            rec.advance("hired")


class TestCampaignStore:
    def test_track_persists_and_survives_restart(self, store, storage):
        record = store.track(LISTING, package_dir="exports/x")
        assert record.status == "prepared"
        # a NEW store over the same storage = a restart
        again = CampaignStore(storage).get(LISTING)
        assert again is not None and again.status == "prepared"
        assert again.package_dir == "exports/x"

    def test_retrack_keeps_history(self, store):
        store.track(LISTING)
        store.advance(LISTING, "submitted", notes="sent")
        # package re-prepared later: status must NOT reset
        record = store.track(LISTING, package_dir="exports/y")
        assert record.status == "submitted"
        assert "sent" in record.notes

    def test_advance_untracked_listing_rejected(self, store):
        with pytest.raises(ValueError, match="not tracked"):
            store.advance(LISTING, "submitted")

    def test_untrack_removes(self, store):
        store.track(LISTING)
        store.untrack(LISTING)
        assert store.get(LISTING) is None

    def test_summary_counts_statuses(self, store):
        other = {**LISTING, "url": "https://x/2", "company": "Other"}
        third = {**LISTING, "url": "https://x/3"}
        store.track(LISTING)
        store.track(other)
        store.advance(other, "rejected")
        store.track(third)
        store.advance(third, "interviewing")
        summary = store.summary()
        assert summary["total"] == 3
        assert summary["counts"]["prepared"] == 1
        assert summary["counts"]["rejected"] == 1
        assert summary["counts"]["interviewing"] == 1
        assert summary["open"] == 2  # rejected is closed


# ---------------------------------------------------------------------------
# Interview prep generation (through the real Pipeline with a fake client)
# ---------------------------------------------------------------------------

GOOD_PREP = json.dumps({
    "role": "Support Engineer",
    "company": "Widgetco",
    "likely_questions": [
        {"question": "Tell me about yourself.",
         "how_to_answer": "Lead with the 3-year support stretch; close "
                          "with why Widgetco's customer-first line."},
    ] * 5,
    "story_bank": [
        {"strength": "De-escalation",
         "story": "At Initech I turned an angry enterprise account "
                  "into a renewal by owning the outage comms."},
    ] * 3,
    "questions_to_ask": [
        "How does support feed product decisions here?",
        "What does the first 90 days look like?",
        "How is the team measured — CSAT or retention?",
    ],
})


class FakeClient:
    """Matches the LmStudioClient interface; returns queued content."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        from model_layer.client import ModelResponse
        return ModelResponse(content=outcome, model=DEFAULT_MODEL,
                             finish_reason="stop", tool_calls=None,
                             raw={})


RESUME = {"contact": {"name": "Ada"},
          "summary": "Support engineer",
          "skills": ["de-escalation"],
          "experience": [{"title": "Support", "company": "Initech",
                          "description": "Owned outage comms"}]}


class TestInterviewPrepGeneration:
    def test_valid_prep_passes_and_grounded(self):
        client = FakeClient(GOOD_PREP)
        prep = generate_interview_prep(RESUME, role="Support Engineer",
                                       company="Widgetco",
                                       client=client)
        assert prep["company"] == "Widgetco"
        assert len(prep["likely_questions"]) == 5
        assert len(prep["story_bank"]) == 3
        assert len(prep["questions_to_ask"]) == 3

    def test_wrong_company_rejected_and_retried(self):
        wrong = json.dumps({**json.loads(GOOD_PREP),
                           "company": "Somewhere Else"})
        client = FakeClient(wrong, GOOD_PREP)
        prep = generate_interview_prep(RESUME, role="Support Engineer",
                                       company="Widgetco", client=client)
        assert prep["company"] == "Widgetco"
        assert len(client.requests) == 2  # feedback retry fired

    def test_persistent_garbage_raises_schema_error(self):
        client = FakeClient("not json at all", "still not json",
                            "garbage three")
        with pytest.raises(SchemaValidationError):
            generate_interview_prep(RESUME, role="R", company="C",
                                    client=client)

    def test_empty_inputs_raise_valueerror(self):
        with pytest.raises(ValueError):
            generate_interview_prep(RESUME, role="", company="C",
                                    client=FakeClient())
        with pytest.raises(ValueError):
            generate_interview_prep(RESUME, role="R", company="",
                                    client=FakeClient())
        with pytest.raises(ValueError):
            generate_interview_prep({}, role="R", company="C",
                                    client=FakeClient())

    def test_template_registered(self):
        from model_layer.prompts import PromptRegistry
        registry = PromptRegistry()
        system, user, _ = registry.render(
            "interview_prep_generate",
            {"role": "R", "company": "C", "snippet": "s",
             "resume": "r"})
        assert "interview coach" in system.lower()
        assert "Widgetco" not in user
        assert "exactly 5" in user or "5 questions" in user


class TestValidateInterviewPrep:
    def test_grounding_checker(self):
        parsed = json.loads(GOOD_PREP)
        ok, errors = validate_interview_prep(
            parsed, expected_company="Widgetco",
            expected_role="Support Engineer")
        assert ok, errors
        wrong = json.loads(GOOD_PREP)
        wrong["company"] = "Different Co"
        ok, errors = validate_interview_prep(
            wrong, expected_company="Widgetco",
            expected_role="Support Engineer")
        assert not ok
        assert any("company" in e for e in errors)
