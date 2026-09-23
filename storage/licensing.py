# storage/licensing.py
#
# WHAT: The offline license seam — issue, verify and meter Pro/Campaign
#       entitlements with no server, no account, and no phone-home.
# WHY:  docs/PROFIT_PLAN.md §2 + task F7. The product's moat is local,
#       private inference (PROFIT_PLAN §0); a license check that called
#       home would break both the privacy promise and the offline story.
#       Keys are HMAC-Signed tokens (base64url payload + signature) the
#       app verifies LOCALLY against a public signing key. This is an
#       honour-system license by design — PROFIT_PLAN §8 explicitly
#       accepts piracy risk because the audience converts on trust, and
#       institutional buyers pay regardless. Institutions that want
#       private issuance set LDCC_LICENSE_SECRET and ship a build with
#       the same value.
# BREAKS IF DELETED: No tier exists; the Free/Pro/Campaign ladder has no
#       mechanism, the shareable-pack funnel has nothing to upsell, and
#       the success metric (MRR per installer) is unmeasurable.

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "TIERS", "TIER_PRICES", "FREE_QUOTAS", "PRO_ONLY_FEATURES",
    "LicenseStatus", "LicenseStore", "issue_license", "verify_token",
    "decode_token", "signing_key",
]

# --------------------------------------------------------------------------
# Product ladder (docs/PROFIT_PLAN.md §2) — single source of truth for
# both the gate logic and the upgrade copy the UI shows.
# --------------------------------------------------------------------------

FREE = "free"
PRO = "pro"
CAMPAIGN = "campaign"

TIERS = (FREE, PRO, CAMPAIGN)
_TIER_RANK = {FREE: 0, PRO: 1, CAMPAIGN: 2}

TIER_PRICES = {
    FREE: {"label": "Free", "price": "$0 forever",
           "blurb": "Full Language Lab (3 packs/week), 1 resume profile, "
                    "5 application packages, job search, Playground."},
    PRO: {"label": "Pro", "price": "$9/month · $79/year · $149 lifetime",
          "blurb": "Unlimited packs + SRS history, unlimited application "
                   "packages, multi-resume profiles, LinkedIn post studio."},
    CAMPAIGN: {"label": "Campaign", "price": "$29/month",
               "blurb": "Everything in Pro + Career Campaign mode: "
                        "apply-tracking and per-listing interview prep."},
}

# Free-tier metering. period "week" resets on the ISO week; "lifetime"
# never resets. A limit of 0 means the feature is paid-only.
FREE_QUOTAS: dict[str, dict[str, Any]] = {
    "lesson_pack": {"limit": 3, "period": "week",
                    "label": "lesson packs"},
    "application_package": {"limit": 5, "period": "lifetime",
                            "label": "application packages"},
    "resume_profile": {"limit": 1, "period": "lifetime",
                       "label": "resume profiles"},
    # PROFIT_PLAN §2 lists the LinkedIn post studio as Pro. Free users
    # still get ONE draft: a free tier you cannot try is a free tier that
    # does not convert (PROFIT_PLAN §7 bans crippled free tiers).
    "linkedin_post": {"limit": 1, "period": "lifetime",
                      "label": "LinkedIn post drafts"},
    # Project E.T. (2026-09-06): one full short conversation per week
    # on the free tier + change. Unlimited E.T. is the Pro headline.
    "et_turn": {"limit": 10, "period": "week",
                "label": "E.T. conversation turns"},
    # Skills Arena (L6): a real taste of rubric-graded writing.
    "writing_eval": {"limit": 3, "period": "week",
                     "label": "writing evaluations"},
    # One inclusive final exam per CEFR level; retakes are Pro depth.
    "level_exam": {"limit": 5, "period": "lifetime",
                   "label": "level exams (one per level)"},
}

# Features gated purely by tier (no counter): the ladder must be able to
# answer "is this feature available?" before any usage is recorded.
PRO_ONLY_FEATURES = {
    "srs_history": PRO,
    "priority_engines": PRO,
    "shareable_pack": FREE,       # the growth loop stays free on purpose
    "campaign_mode": CAMPAIGN,
}

UPGRADE_URL = "https://github.com/HatemIsmailShalaby1979/L-D-Command-Center#pricing"


# --------------------------------------------------------------------------
# Token format:  LDCC1.<base64url(payload)>.<base64url(hmac)>
# --------------------------------------------------------------------------

TOKEN_PREFIX = "LDCC1"
TOKEN_VERSION = 1

# The default verification key is PUBLIC BY DESIGN (this file is MIT and
# open). It makes casual key editing fail, not piracy. Private deployments
# override both sides with LDCC_LICENSE_SECRET.
PUBLIC_SIGNING_KEY = "ldcc-v1-public-honour-system-key"


def signing_key(secret: Optional[str] = None) -> bytes:
    """The HMAC key: explicit arg > LDCC_LICENSE_SECRET > public default."""
    raw = secret or os.environ.get("LDCC_LICENSE_SECRET") or PUBLIC_SIGNING_KEY
    return raw.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: Any) -> Optional[datetime]:
    if not text or not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _week_key(moment: datetime) -> str:
    iso = moment.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def issue_license(
    tier: str,
    *,
    licensee: str = "",
    days: Optional[int] = None,
    machine_id: Optional[str] = None,
    note: str = "",
    secret: Optional[str] = None,
    issued_at: Optional[datetime] = None,
) -> str:
    """Mint one license token.

    tier      free | pro | campaign (campaign implies every Pro right).
    days      subscription length in days; None = lifetime (never expires).
    machine_id  optional host lock for institutional site licenses; the
                app refuses the key on a different machine.
    note      free-form seller memo ("founder key #42") — carried in the
              token so a buyer's key can be recognised later.
    """
    tier = (tier or "").strip().lower()
    if tier not in TIERS:
        raise ValueError(f"Unknown tier {tier!r}; expected one of {list(TIERS)}")
    if days is not None and int(days) <= 0:
        raise ValueError("days must be positive (or None for lifetime)")
    iat = issued_at or _now()
    payload = {
        "v": TOKEN_VERSION,
        "tier": tier,
        "licensee": licensee.strip(),
        "iat": _iso(iat),
        "exp": _iso(iat + timedelta(days=int(days))) if days else None,
        "mid": machine_id or None,
        "note": note.strip(),
        "nonce": secrets.token_hex(6),  # keeps identical orders distinct
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(signing_key(secret), body.encode("ascii"),
                         hashlib.sha256).digest())
    token = f"{TOKEN_PREFIX}.{body}.{sig}"
    logger.info("Issued %s license for %r (days=%s)", tier,
                payload["licensee"] or "unlicensed", days)
    return token


def decode_token(token: str) -> dict[str, Any]:
    """Read a token's payload WITHOUT trusting it (display/debug only)."""
    text = (token or "").strip()
    parts = text.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        raise ValueError("Not an L&D Command Center license key "
                         "(expected LDCC1.<payload>.<signature>)")
    try:
        payload = json.loads(_b64d(parts[1]).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — any malformed body is one error
        raise ValueError(f"License key payload is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("License key payload is not an object")
    return payload


@dataclass
class LicenseStatus:
    """The answer to 'what is this install allowed to do?'."""
    valid: bool
    tier: str = FREE
    reason: str = "ok"               # ok|no_license|malformed|bad_signature|
                                     # expired|other_machine|unknown_tier
    licensee: str = ""
    note: str = ""
    expires_at: Optional[str] = None
    days_left: Optional[int] = None

    def __bool__(self) -> bool:
        return self.valid

    @property
    def label(self) -> str:
        return TIER_PRICES.get(self.tier, TIER_PRICES[FREE])["label"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid, "tier": self.tier, "reason": self.reason,
            "licensee": self.licensee, "note": self.note,
            "expires_at": self.expires_at, "days_left": self.days_left,
            "label": self.label,
        }


def verify_token(
    token: str,
    *,
    secret: Optional[str] = None,
    machine_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> LicenseStatus:
    """Verify a key offline: signature, tier, expiry, optional host lock."""
    text = (token or "").strip()
    if not text:
        return LicenseStatus(False, reason="no_license")
    parts = text.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return LicenseStatus(False, reason="malformed")
    body, sig = parts[1], parts[2]
    expected = _b64e(hmac.new(signing_key(secret), body.encode("ascii"),
                              hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        logger.warning("License key rejected: signature mismatch")
        return LicenseStatus(False, reason="bad_signature")
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — signed but unreadable = tampered
        logger.warning("License key rejected: unreadable payload (%s)", exc)
        return LicenseStatus(False, reason="malformed")
    tier = str(payload.get("tier", "")).strip().lower()
    if tier not in TIERS:
        return LicenseStatus(False, reason="unknown_tier")
    moment = now or _now()
    status = LicenseStatus(True, tier=tier,
                           licensee=str(payload.get("licensee") or ""),
                           note=str(payload.get("note") or ""),
                           expires_at=payload.get("exp"))
    if status.expires_at:
        exp = _parse_iso(status.expires_at)
        if exp is None:
            return LicenseStatus(False, reason="malformed",
                                 licensee=status.licensee)
        status.days_left = (exp - moment).days
        if exp < moment:
            logger.info("License expired on %s", status.expires_at)
            return LicenseStatus(False, tier=FREE, reason="expired",
                                 licensee=status.licensee,
                                 note=status.note,
                                 expires_at=status.expires_at, days_left=0)
    locked_to = payload.get("mid")
    if locked_to and machine_id and str(locked_to) != str(machine_id):
        logger.warning("License key rejected: issued for another machine")
        return LicenseStatus(False, tier=FREE, reason="other_machine",
                             licensee=status.licensee, note=status.note)
    return status


# --------------------------------------------------------------------------
# Store: activation + usage counters, persisted through Storage preferences
# --------------------------------------------------------------------------

_LICENSE_KEY = "license"
_USAGE_KEY = "license_usage"


@dataclass
class Quota:
    """How much of a metered feature is left on the current install."""
    feature: str
    allowed: bool
    used: int = 0
    limit: Optional[int] = None      # None = unlimited
    period: str = "lifetime"        # lifetime | week
    remaining: Optional[int] = None  # None = unlimited
    label: str = ""
    tier: str = FREE

    def as_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "allowed": self.allowed,
                "used": self.used, "limit": self.limit,
                "period": self.period, "remaining": self.remaining,
                "label": self.label, "tier": self.tier}

    @property
    def message(self) -> str:
        """One honest sentence the UI can show verbatim."""
        if self.allowed:
            return ""
        if self.limit == 0:
            return (f"{self.label} is a {TIER_PRICES[PRO]['label']} "
                    f"feature. {TIER_PRICES[PRO]['price']}.")
        window = "this week" if self.period == "week" else "on the free tier"
        return (f"You have used all {self.limit} {self.label} {window}. "
                f"Upgrade for unlimited — {TIER_PRICES[PRO]['price']}.")


class LicenseStore:
    """Contract: the install's entitlement state. Purely offline; every
    read and write goes through Storage preferences so nothing is hidden
    in memory and a backup of the data dir carries the license with it.

    Usage counters are stored per feature with the period they belong to::

        {"lesson_pack": {"period": "2026-W36", "count": 2}, ...}

    A period change (new ISO week) resets the counter on the next read —
    no cron, no timer, no background thread.
    """

    def __init__(self, storage, *, machine_id: Optional[str] = None,
                 secret: Optional[str] = None) -> None:
        self.storage = storage
        self.machine_id = machine_id
        self.secret = secret

    # -- activation ------------------------------------------------------

    def activate(self, token: str, *, now: Optional[datetime] = None) -> LicenseStatus:
        """Verify a key and persist it only when it is genuinely valid.
        An invalid key never replaces a working one."""
        status = verify_token(token, secret=self.secret,
                              machine_id=self.machine_id, now=now)
        if not status.valid:
            return status
        self.storage.set_preference(_LICENSE_KEY, {"token": token.strip()})
        logger.info("License activated: %s (%s)", status.tier,
                    status.licensee or "unlicensed")
        return status

    def deactivate(self) -> None:
        """Forget the key (support hand-off / reinstalls). Usage counters
        survive — they belong to the install, not the license."""
        self.storage.set_preference(_LICENSE_KEY, {})
        logger.info("License deactivated")

    def status(self, *, now: Optional[datetime] = None) -> LicenseStatus:
        stored = self.storage.get_preference(_LICENSE_KEY, {}) or {}
        token = stored.get("token") if isinstance(stored, dict) else None
        if not token:
            return LicenseStatus(False, reason="no_license")
        return verify_token(token, secret=self.secret,
                            machine_id=self.machine_id, now=now)

    # -- tier ------------------------------------------------------------

    def tier(self, *, now: Optional[datetime] = None) -> str:
        return self.status(now=now).tier

    def has(self, feature: str, *, now: Optional[datetime] = None) -> bool:
        """Tier-only features (no counter): is this right included?"""
        required = PRO_ONLY_FEATURES.get(feature, FREE)
        return _TIER_RANK.get(self.tier(now=now), 0) >= _TIER_RANK[required]

    # -- metering --------------------------------------------------------

    def _usage(self) -> dict[str, dict[str, Any]]:
        raw = self.storage.get_preference(_USAGE_KEY, {}) or {}
        return raw if isinstance(raw, dict) else {}

    def _write_usage(self, usage: dict[str, dict[str, Any]]) -> None:
        self.storage.set_preference(_USAGE_KEY, usage)

    def _window(self, period: str, moment: datetime) -> str:
        return _week_key(moment) if period == "week" else "lifetime"

    def _counted(self, feature: str, period: str,
                 moment: datetime) -> int:
        """Uses recorded in the CURRENT window (a new week reads as 0)."""
        record = self._usage().get(feature) or {}
        if record.get("period") != self._window(period, moment):
            return 0
        return int(record.get("count", 0))

    def quota(self, feature: str, *, now: Optional[datetime] = None) -> Quota:
        """How much of `feature` is left. Paid tiers are unlimited; the
        free tier is metered per FREE_QUOTAS."""
        moment = now or _now()
        tier = self.tier(now=moment)
        spec = FREE_QUOTAS.get(feature) or {}
        label = str(spec.get("label") or feature.replace("_", " "))
        period = str(spec.get("period") or "lifetime")
        used = self._counted(feature, period, moment)
        if tier != FREE:
            return Quota(feature, True, used=used, limit=None, period=period,
                         remaining=None, label=label, tier=tier)
        limit_int = int(spec.get("limit") or 0)
        remaining = max(0, limit_int - used)
        return Quota(feature, used < limit_int, used=used, limit=limit_int,
                     period=period, remaining=remaining, label=label,
                     tier=tier)

    def used(self, feature: str, *, now: Optional[datetime] = None) -> int:
        return self.quota(feature, now=now).used

    def consume(self, feature: str, amount: int = 1, *,
                now: Optional[datetime] = None) -> Quota:
        """Record `amount` uses of a metered feature (free tier only;
        paid usage is still counted — the numbers feed the upgrade copy
        and the MRR-per-installer metric, they never block anything)."""
        moment = now or _now()
        spec = FREE_QUOTAS.get(feature) or {}
        period = str(spec.get("period") or "lifetime")
        count = self._counted(feature, period, moment)
        usage = self._usage()
        usage[feature] = {"period": self._window(period, moment),
                          "count": count + int(amount)}
        self._write_usage(usage)
        after = self.quota(feature, now=moment)
        logger.info("Usage %s: %d (+%d) — %s", feature, after.used, amount,
                    "unlimited" if after.remaining is None
                    else f"{after.remaining} left")
        return after

    def reset_usage(self, feature: Optional[str] = None) -> None:
        """Clear counters for one feature or all of them (support tool)."""
        if feature is None:
            self._write_usage({})
            return
        usage = self._usage()
        usage.pop(feature, None)
        self._write_usage(usage)

    # -- reporting -------------------------------------------------------

    def summary(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        """Everything the UI needs for the license panel, in one read."""
        status = self.status(now=now)
        quotas = {name: self.quota(name, now=now).as_dict()
                  for name in FREE_QUOTAS}
        return {
            **status.as_dict(),
            "quotas": quotas,
            "features": {name: self.has(name, now=now)
                         for name in PRO_ONLY_FEATURES},
            "upgrade_url": UPGRADE_URL,
            "prices": TIER_PRICES,
        }


# --------------------------------------------------------------------------
# Issuer CLI — how the seller mints keys (Gumroad/Lifetime/Campaign).
#   python -m storage.licensing issue --tier pro --days 365 --licensee "A"
#   python -m storage.licensing issue --tier campaign --monthly --licensee "B"
#   python -m storage.licensing verify LDCC1....
# --------------------------------------------------------------------------

_DAY_COUNTS = {"monthly": 30, "yearly": 365, "year": 365}


def _cmd_issue(args: argparse.Namespace) -> int:
    days = args.days
    if args.plan:
        days = _DAY_COUNTS[args.plan]
    if args.lifetime:
        days = None
    token = issue_license(args.tier, licensee=args.licensee, days=days,
                          machine_id=args.machine_id, note=args.note,
                          secret=args.secret)
    print(token)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    status = verify_token(args.token, secret=args.secret,
                          machine_id=args.machine_id)
    print(json.dumps(status.as_dict(), indent=2))
    return 0 if status.valid else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="licensing",
        description="Offline license-key issuer/verifier for "
                    "L&D Command Center.")
    sub = parser.add_subparsers(dest="command", required=True)

    issue = sub.add_parser("issue", help="mint a license key")
    issue.add_argument("--tier", choices=list(TIERS), default=PRO)
    issue.add_argument("--licensee", default="", help="buyer name/email")
    issue.add_argument("--days", type=int, default=None,
                       help="validity in days (omit for lifetime)")
    issue.add_argument("--plan", choices=sorted(_DAY_COUNTS), default=None,
                       help="monthly=30d, yearly=365d")
    issue.add_argument("--lifetime", action="store_true",
                       help="never expires (lifetime / founder keys)")
    issue.add_argument("--note", default="",
                       help="seller memo, e.g. 'founder key #7'")
    issue.add_argument("--machine-id", default=None,
                       help="lock the key to one machine id")
    issue.add_argument("--secret", default=None,
                       help="private signing key (else $LDCC_LICENSE_SECRET "
                            "or the public default)")
    issue.set_defaults(func=_cmd_issue)

    check = sub.add_parser("verify", help="check a license key offline")
    check.add_argument("token")
    check.add_argument("--machine-id", default=None)
    check.add_argument("--secret", default=None)
    check.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    raise SystemExit(main())
