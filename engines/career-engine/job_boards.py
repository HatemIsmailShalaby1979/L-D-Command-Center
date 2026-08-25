# engines/career-engine/job_boards.py
#
# WHAT: Keyless job-board search — Greenhouse, Lever, Ashby and RemoteOK
#       unified into JobListing records with direct application URLs,
#       keyword matching, and a seen-set diff for saved searches (the
#       career agent's hunting layer).
# WHY:  Owner mandate: an agent that automatically searches job boards
#       for the desired role and provides DIRECT LINKS. Every source here
#       publishes public JSON endpoints that permit read access — no
#       scraping of protected pages, no credentials. Auto-SUBMITTING
#       applications is deliberately out of scope: boards terminate
#       accounts for bot-submits; the agent prepares packages, the human
#       clicks submit.
# BREAKS IF DELETED: The job-search/watchlist feature loses its data
#       layer; Career tab's search section has nothing to query.

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from html import unescape
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "JobListing", "search_greenhouse", "search_lever", "search_ashby",
    "search_remoteok", "search_all", "match_listings",
]

Transport = Callable[[str], Any]
_TIMEOUT = 30


def _default_transport(url: str) -> Any:
    resp = httpx.get(
        url, timeout=_TIMEOUT,
        headers={"User-Agent": "LDCC-career-agent/1.0 (local job search)"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()


@dataclass(frozen=True)
class JobListing:
    company: str
    title: str
    location: str
    url: str
    source: str
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean(html_or_text: str, limit: int = 280) -> str:
    text = re.sub(r"<[^>]+>", " ", html_or_text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _strip_html(content: str) -> str:
    return _clean(content, limit=100000)


def search_greenhouse(companies: list[str], *,
                      transport: Optional[Transport] = None,
                      title_query: str = "") -> list[JobListing]:
    """boards.greenhouse.io public job boards."""
    get = transport or _default_transport
    out: list[JobListing] = []
    q = title_query.lower().strip()
    for company in companies:
        try:
            data = get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs")
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if q and q not in title.lower():
                    continue
                out.append(JobListing(
                    company=company,
                    title=title,
                    location=(job.get("location") or {}).get("name", ""),
                    url=job.get("absolute_url", ""),
                    source="greenhouse",
                    snippet=_strip_html(job.get("content", "") or "")[:280],
                ))
        except Exception as exc:  # noqa: BLE001 — one dead board ≠ dead search
            logger.warning("Greenhouse %s failed: %s", company, exc)
    return out


def search_lever(companies: list[str], *,
                 transport: Optional[Transport] = None,
                 title_query: str = "") -> list[JobListing]:
    """api.lever.co public postings."""
    get = transport or _default_transport
    out: list[JobListing] = []
    q = title_query.lower().strip()
    for company in companies:
        try:
            data = get(f"https://api.lever.co/v0/postings/{company}?mode=json")
            for job in data:
                title = job.get("text", "")
                if q and q not in title.lower():
                    continue
                cats = job.get("categories") or {}
                out.append(JobListing(
                    company=company,
                    title=title,
                    location=cats.get("location", ""),
                    url=job.get("hostedUrl", ""),
                    source="lever",
                    snippet=_clean(job.get("descriptionPlain", ""))[:280],
                ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lever %s failed: %s", company, exc)
    return out


def search_ashby(companies: list[str], *,
                 transport: Optional[Transport] = None,
                 title_query: str = "") -> list[JobListing]:
    """api.ashbyhq.com public job boards."""
    get = transport or _default_transport
    out: list[JobListing] = []
    q = title_query.lower().strip()
    for company in companies:
        try:
            data = get(f"https://api.ashbyhq.com/posting-api/job-board/{company}")
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if q and q not in title.lower():
                    continue
                out.append(JobListing(
                    company=company,
                    title=title,
                    location=job.get("location", "") or
                             (job.get("secondaryLocations") or [{}])[0].get("location", "")
                             if job.get("secondaryLocations") else job.get("location", ""),
                    url=job.get("jobUrl", ""),
                    source="ashby",
                    snippet=_clean(job.get("descriptionPlain", ""))[:280],
                ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ashby %s failed: %s", company, exc)
    return out


REMOTEOK_URL = "https://remoteok.com/api"


def search_remoteok(*, transport: Optional[Transport] = None,
                    title_query: str = "",
                    location_query: str = "") -> list[JobListing]:
    """remoteok.com public API — remote-only roles worldwide."""
    get = transport or _default_transport
    q = title_query.lower().strip()
    loc_q = location_query.lower().strip()
    out: list[JobListing] = []
    try:
        data = get(REMOTEOK_URL)
        # first element is the legal notice, not a listing
        entries = [e for e in data if isinstance(e, dict) and e.get("position")]
        for job in entries:
            title = str(job.get("position", ""))
            if q and q not in title.lower():
                continue
            location = str(job.get("location", "") or "")
            if loc_q and loc_q not in location.lower():
                continue
            out.append(JobListing(
                company=str(job.get("company", "")),
                title=title,
                location=f"{location} (remote)" if "remote" not in location.lower() else location,
                url=str(job.get("url", "") or job.get("apply_url", "")),
                source="remoteok",
                snippet=_strip_html(str(job.get("description", "")))[:280],
            ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("RemoteOK failed: %s", exc)
    return out


def search_all(*,
               greenhouse_companies: list[str],
               lever_companies: list[str],
               ashby_companies: list[str],
               title_query: str = "",
               location_query: str = "",
               include_remote: bool = True,
               transport_factory: Optional[Callable[[], Transport]] = None,
               ) -> dict[str, list[JobListing]]:
    """
    Contract: run every configured source. Returns per-source listings so
    callers can show partial failures honestly ("greenhouse: 0, lever:
    down") instead of one merged blob hiding outages.

    transport_factory lets tests inject fakes per source call.
    """
    def t() -> Transport:
        return transport_factory() if transport_factory else _default_transport

    results = {
        "greenhouse": search_greenhouse(greenhouse_companies, transport=t(),
                                        title_query=title_query),
        "lever": search_lever(lever_companies, transport=t(),
                              title_query=title_query),
        "ashby": search_ashby(ashby_companies, transport=t(),
                              title_query=title_query),
    }
    if include_remote:
        results["remoteok"] = search_remoteok(
            transport=t(), title_query=title_query,
            location_query=location_query)

    # dedupe by URL across sources, keep first occurrence
    seen_urls: set[str] = set()
    merged: dict[str, list[JobListing]] = {}
    for source, listings in results.items():
        kept = []
        for listing in listings:
            if listing.url and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                kept.append(listing)
        merged[source] = kept
    total = sum(len(v) for v in merged.values())
    logger.info("Job search (%r @ %s): %d listings",
                title_query, location_query or "anywhere", total)
    return merged


def match_listings(listings: list[JobListing],
                   keywords: list[str]) -> list[tuple[JobListing, int]]:
    """
    Contract: score listings against role keywords (title hits weigh 3×,
    snippet hits 1×); keep positive scores, highest first. Pure function.
    """
    kws = [k.lower().strip() for k in keywords if k.strip()]
    scored = []
    for listing in listings:
        title = listing.title.lower()
        snippet = listing.snippet.lower()
        score = sum(3 for k in kws if k in title) + \
                sum(1 for k in kws if k in snippet)
        if score > 0:
            scored.append((listing, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
