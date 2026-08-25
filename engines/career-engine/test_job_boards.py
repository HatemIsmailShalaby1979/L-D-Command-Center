# engines/career-engine/test_job_boards.py
#
# WHAT: Contract tests for keyless job-board search (Greenhouse, Lever,
#       Ashby, RemoteOK), keyword matching and cross-source dedupe.
# WHY:  The career agent's hunting layer must parse each board's real
#       response shape, survive one dead source without killing the
#       search, dedupe cross-posted roles, and rank by title hits. All
#       proven against canned JSON via injected transports — network
#       never required.
# BREAKS IF DELETED: Board shape changes or silent merge bugs would feed
#       the watchlist garbage.

from __future__ import annotations

import json

import pytest

from engines.career_engine.job_boards import (
    JobListing,
    match_listings,
    search_all,
    search_ashby,
    search_greenhouse,
    search_lever,
    search_remoteok,
)


def transport_returning(payload):
    def t(url):
        return payload
    return t


def transport_recording(payload):
    calls = []
    def t(url):
        calls.append(url)
        return payload
    t.calls = calls
    return t


def failing(url):
    raise RuntimeError("board down")


GREENHOUSE_JSON = {"jobs": [
    {"title": "Senior Customer Support Manager",
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
     "location": {"name": "Berlin"},
     "content": "<p>Own the <b>support</b> queue &amp; coach agents.</p>"},
    {"title": "Backend Engineer",
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
     "location": {"name": "Remote"},
     "content": "Go services."},
]}

LEVER_JSON = [{
    "text": "Customer Support Lead",
    "categories": {"location": "Munich", "team": "Ops"},
    "hostedUrl": "https://jobs.lever.co/acme/abc",
    "descriptionPlain": "Lead our support team.",
}]

ASHBY_JSON = {"jobs": [
    {"title": "Support Engineer", "location": "Remote EU",
     "jobUrl": "https://jobs.ashbyhq.com/acme/1",
     "descriptionPlain": "Debug with customers."},
]}

REMOTEOK_RAW = [
    {"legal": "notice"},
    {"slug": "x", "position": "Customer Support Specialist",
     "company": "WidgetCo", "location": "Worldwide",
     "url": "https://remoteok.com/x", "description": "<p>Email queues.</p>",
     "apply_url": "https://remoteok.com/apply/x"},
]


class TestSources:
    def test_greenhouse_filters_and_cleans(self):
        listings = search_greenhouse(["acme"], transport=transport_returning(GREENHOUSE_JSON),
                                     title_query="support")
        assert len(listings) == 1
        assert listings[0].company == "acme"
        assert listings[0].location == "Berlin"
        assert "&amp;" not in listings[0].snippet
        assert listings[0].url.endswith("/1")

    def test_lever_shape(self):
        listings = search_lever(["acme"], transport=transport_returning(LEVER_JSON),
                                title_query="support")
        assert listings[0].title == "Customer Support Lead"
        assert listings[0].source == "lever"

    def test_ashby_shape(self):
        listings = search_ashby(["acme"], transport=transport_returning(ASHBY_JSON))
        assert listings[0].url == "https://jobs.ashbyhq.com/acme/1"

    def test_remoteok_skips_legal_notice(self):
        listings = search_remoteok(transport=transport_returning(REMOTEOK_RAW))
        assert len(listings) == 1
        assert listings[0].company == "WidgetCo"
        assert "(remote)" in listings[0].location

    def test_search_all_survives_one_dead_source(self):
        def factory():
            return transport_returning(LEVER_JSON)
        # make greenhouse+ashby transports fail while lever succeeds:
        calls = {"n": 0}
        def flaky(url):
            calls["n"] += 1
            if "/postings/" in url:
                return LEVER_JSON
            raise RuntimeError("dead")
        merged = search_all(
            greenhouse_companies=["acme"], lever_companies=["acme"],
            ashby_companies=["acme"], include_remote=False,
            transport_factory=lambda: flaky)
        assert merged["lever"] and not merged["greenhouse"] \
            and not merged["ashby"]

    def test_dedupe_across_sources_keeps_first(self):
        duped_lever = [dict(LEVER_JSON[0], hostedUrl="https://x/job/9")]
        gh_payload = {"jobs": [
            {"title": "Customer Support", "absolute_url": "https://x/job/9",
             "location": {"name": "Berlin"}, "content": ""}]}
        def t(url):
            if "greenhouse" in url: return gh_payload
            return duped_lever
        merged = search_all(greenhouse_companies=["a"], lever_companies=["b"],
                            ashby_companies=[], include_remote=False,
                            transport_factory=lambda: t)
        urls = [l.url for lst in merged.values() for l in lst]
        assert urls.count("https://x/job/9") == 1


class TestMatching:
    LISTINGS = [
        JobListing("c", "Senior Customer Support Manager", "Berlin", "u1", "gh",
                   "own the support queue"),
        JobListing("c", "Backend Engineer", "Remote", "u2", "gh",
                   "go services"),
    ]

    def test_title_hits_rank_above_snippet_hits(self):
        scored = match_listings(self.LISTINGS, ["customer support"])
        assert scored[0][0].title.startswith("Senior")
        assert scored[0][1] >= 3

    def test_no_keyword_hit_is_excluded(self):
        assert match_listings(self.LISTINGS, ["devops"]) == []

    def test_multi_keyword_accumulates(self):
        score = match_listings(self.LISTINGS, ["customer", "support"])[0][1]
        assert score >= 6  # both keywords hit the title
