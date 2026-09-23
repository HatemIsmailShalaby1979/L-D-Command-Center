# storage/test_licensing.py
#
# WHAT: Offline contract tests for the license seam (F7 / PROFIT_PLAN §2).
# WHY:  A monetization mechanism that fails silently is worse than none:
#       a forged key must never unlock Pro, a subscription must stop on
#       its expiry date, a free user must hit the published quota (3
#       packs/week, 5 packages, 1 profile) at exactly the right moment,
#       and none of it may touch the network.
# BREAKS IF DELETED: Piracy passes undetected, quotas drift off the
#       advertised ladder, and paying users get locked out on renewal.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from storage.licensing import (
    CAMPAIGN, FREE, PRO, TIER_PRICES, LicenseStatus, LicenseStore,
    decode_token, issue_license, verify_token,
)
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


@pytest.fixture
def store(storage):
    return LicenseStore(storage)


NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


class TestIssuing:
    def test_lifetime_pro_key_has_no_expiry(self):
        token = issue_license(PRO, licensee="Ada", issued_at=NOW)
        payload = decode_token(token)
        assert payload["tier"] == PRO
        assert payload["licensee"] == "Ada"
        assert payload["exp"] is None

    def test_monthly_key_expires_in_30_days(self):
        token = issue_license(PRO, licensee="Ada", days=30, issued_at=NOW)
        payload = decode_token(token)
        assert payload["exp"] == "2026-10-06T12:00:00Z"

    def test_unknown_tier_rejected(self):
        with pytest.raises(ValueError, match="Unknown tier"):
            issue_license("platinum")

    def test_non_positive_days_rejected(self):
        with pytest.raises(ValueError, match="days"):
            issue_license(PRO, days=0)

    def test_nonce_keeps_two_identical_orders_distinct(self):
        a = issue_license(PRO, licensee="Ada", issued_at=NOW)
        b = issue_license(PRO, licensee="Ada", issued_at=NOW)
        assert a != b

    def test_note_carries_seller_memo(self):
        token = issue_license(PRO, note="founder key #7", issued_at=NOW)
        assert decode_token(token)["note"] == "founder key #7"


class TestVerification:
    def test_valid_key_is_valid(self):
        token = issue_license(PRO, licensee="Ada", issued_at=NOW)
        status = verify_token(token, now=NOW)
        assert status.valid and status.tier == PRO
        assert status.licensee == "Ada"
        assert status.reason == "ok"

    def test_empty_key_is_free_not_error(self):
        status = verify_token("", now=NOW)
        assert not status.valid and status.reason == "no_license"
        assert status.tier == FREE

    def test_garbage_is_malformed(self):
        assert verify_token("hello", now=NOW).reason == "malformed"

    def test_wrong_prefix_is_malformed(self):
        assert verify_token("XXXX.abc.def", now=NOW).reason == "malformed"

    def test_edited_payload_fails_signature(self):
        token = issue_license(FREE, licensee="Ada", issued_at=NOW)
        body = token.split(".")[1]
        forged = issue_license(PRO, licensee="Ada", issued_at=NOW).split(".")[1]
        # keep the real signature but swap in a Pro payload: the classic
        # "edit the tier" attack must fail.
        tampered = f"LDCC1.{forged}.{token.split('.')[2]}"
        assert body != forged
        status = verify_token(tampered, now=NOW)
        assert not status.valid and status.reason == "bad_signature"

    def test_foreign_secret_cannot_mint_accepted_keys(self):
        token = issue_license(PRO, licensee="Ada", secret="private-deployment",
                              issued_at=NOW)
        assert not verify_token(token, now=NOW).valid
        assert verify_token(token, secret="private-deployment",
                            now=NOW).valid

    def test_expired_subscription_drops_to_free(self):
        token = issue_license(PRO, days=30, issued_at=NOW)
        later = NOW + timedelta(days=31)
        status = verify_token(token, now=later)
        assert not status.valid and status.reason == "expired"
        assert status.tier == FREE and status.days_left == 0

    def test_key_on_last_day_still_valid(self):
        token = issue_license(PRO, days=30, issued_at=NOW)
        status = verify_token(token, now=NOW + timedelta(days=29))
        assert status.valid and status.days_left == 1

    def test_machine_locked_key_rejected_elsewhere(self):
        token = issue_license(PRO, machine_id="lab-01", issued_at=NOW)
        assert verify_token(token, machine_id="lab-01", now=NOW).valid
        status = verify_token(token, machine_id="lab-02", now=NOW)
        assert not status.valid and status.reason == "other_machine"

    def test_unlocked_key_works_anywhere(self):
        token = issue_license(PRO, issued_at=NOW)
        assert verify_token(token, machine_id="any-host", now=NOW).valid


class TestActivation:
    def test_activate_stores_only_valid_keys(self, store):
        ok = store.activate(issue_license(PRO, licensee="Ada", issued_at=NOW),
                            now=NOW)
        assert ok.valid
        assert store.status(now=NOW).tier == PRO

    def test_bad_key_never_replaces_a_working_one(self, store):
        store.activate(issue_license(CAMPAIGN, licensee="Ada", issued_at=NOW),
                       now=NOW)
        bad = store.activate("LDCC1.nonsense.nonsense", now=NOW)
        assert not bad.valid
        assert store.status(now=NOW).tier == CAMPAIGN

    def test_deactivate_returns_to_free_but_keeps_counters(self, store):
        store.activate(issue_license(PRO, issued_at=NOW), now=NOW)
        store.consume("lesson_pack", now=NOW)
        store.deactivate()
        assert store.tier(now=NOW) == FREE
        assert store.used("lesson_pack", now=NOW) == 1

    def test_license_survives_a_new_store_instance(self, storage):
        LicenseStore(storage).activate(
            issue_license(PRO, licensee="Ada", issued_at=NOW), now=NOW)
        assert LicenseStore(storage).status(now=NOW).tier == PRO


class TestTierFeatures:
    def test_free_has_no_campaign_mode(self, store):
        assert store.tier(now=NOW) == FREE
        assert not store.has("campaign_mode", now=NOW)

    def test_pro_unlocks_srs_and_posts(self, store):
        store.activate(issue_license(PRO, issued_at=NOW), now=NOW)
        assert store.has("srs_history", now=NOW)
        assert store.has("priority_engines", now=NOW)

    def test_campaign_includes_every_pro_right(self, store):
        store.activate(issue_license(CAMPAIGN, issued_at=NOW), now=NOW)
        assert store.has("campaign_mode", now=NOW)
        assert store.has("srs_history", now=NOW)

    def test_shareable_pack_stays_free_growth_loop(self, store):
        assert store.has("shareable_pack", now=NOW)


class TestFreeQuotas:
    def test_three_packs_then_gate(self, store):
        for _ in range(3):
            assert store.quota("lesson_pack", now=NOW).allowed
            store.consume("lesson_pack", now=NOW)
        blocked = store.quota("lesson_pack", now=NOW)
        assert not blocked.allowed and blocked.remaining == 0
        assert "Upgrade" in blocked.message

    def test_pack_counter_resets_on_the_next_iso_week(self, store):
        for _ in range(3):
            store.consume("lesson_pack", now=NOW)
        assert not store.quota("lesson_pack", now=NOW).allowed
        next_week = NOW + timedelta(days=7)
        assert store.quota("lesson_pack", now=next_week).allowed
        assert store.used("lesson_pack", now=next_week) == 0

    def test_application_packages_are_lifetime_metered(self, store):
        for _ in range(5):
            store.consume("application_package", now=NOW)
        assert not store.quota("application_package", now=NOW).allowed
        # still blocked a month later — lifetime means lifetime
        assert not store.quota(
            "application_package", now=NOW + timedelta(days=30)).allowed

    def test_one_resume_profile_on_free(self, store):
        assert store.quota("resume_profile", now=NOW).allowed
        store.consume("resume_profile", now=NOW)
        assert not store.quota("resume_profile", now=NOW).allowed

    def test_pro_makes_every_quota_unlimited(self, store):
        store.activate(issue_license(PRO, issued_at=NOW), now=NOW)
        for feature in ("lesson_pack", "application_package",
                        "resume_profile", "linkedin_post"):
            for _ in range(10):
                store.consume(feature, now=NOW)
            quota = store.quota(feature, now=NOW)
            assert quota.allowed and quota.remaining is None

    def test_expired_pro_falls_back_to_metered_free(self, store):
        store.activate(issue_license(PRO, days=30, issued_at=NOW), now=NOW)
        later = NOW + timedelta(days=40)
        for _ in range(3):
            store.consume("lesson_pack", now=later)
        assert not store.quota("lesson_pack", now=later).allowed

    def test_reset_usage_clears_one_or_all_features(self, store):
        store.consume("lesson_pack", now=NOW)
        store.consume("application_package", now=NOW)
        store.reset_usage("lesson_pack")
        assert store.used("lesson_pack", now=NOW) == 0
        assert store.used("application_package", now=NOW) == 1
        store.reset_usage()
        assert store.used("application_package", now=NOW) == 0


class TestSummary:
    def test_summary_carries_prices_and_upgrade_link(self, store):
        summary = store.summary(now=NOW)
        assert summary["tier"] == FREE and not summary["valid"]
        assert summary["upgrade_url"]
        # Project E.T. (2026-09-06): the free tier now meters E.T.
        # conversation turns, writing evaluations and level exams too.
        assert set(summary["quotas"]) == {"lesson_pack",
                                          "application_package",
                                          "resume_profile",
                                          "linkedin_post",
                                          "et_turn",
                                          "writing_eval",
                                          "level_exam"}
        assert TIER_PRICES[PRO]["price"] in summary["prices"][PRO]["price"]

    def test_summary_reports_activated_tier(self, store):
        store.activate(issue_license(CAMPAIGN, licensee="Bo", issued_at=NOW),
                       now=NOW)
        summary = store.summary(now=NOW)
        assert summary["tier"] == CAMPAIGN and summary["valid"]
        assert summary["licensee"] == "Bo"
        assert summary["features"]["campaign_mode"] is True


class TestStatusShape:
    def test_status_is_falsy_when_invalid(self):
        assert not LicenseStatus(False)

    def test_label_matches_the_price_ladder(self):
        assert LicenseStatus(True, tier=PRO).label == "Pro"
