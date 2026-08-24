# engines/playground-bridge/test_connectors_pollinations.py
#
# WHAT: Contract tests for the Pollinations keyless adapter (P7.11).
# WHY:  The whole value is zero-friction keyless generation; URL shape,
#       defaults, and fail-soft behavior must be pinned so the service
#       contract survives UI wiring.
# BREAKS IF DELETED: Broken URLs or in-band error pages saved as images
#       would go unnoticed.

from __future__ import annotations

import pytest

from engines.playground_bridge.connectors_pollinations import (
    FakeResponse,
    PollinationsConnector,
)


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, method, url):
        self.calls.append((method, url))
        return self.response


def make_connector(response):
    return PollinationsConnector(transport=RecordingTransport(response))


class TestSend:
    def test_keyless_get_returns_image_bytes(self):
        connector = make_connector(FakeResponse(content=b"IMGBYTES"))
        job = connector.send({"prompt": "a lighthouse"})
        assert job.status == "done"
        result = connector.poll(job)
        assert result.ok and result.media_bytes == b"IMGBYTES"

    def test_url_shape_prompt_encoded_defaults_present(self):
        transport = RecordingTransport(FakeResponse(content=b"x"))
        PollinationsConnector(
            transport=transport).send({"prompt": "blue bird sky"})
        method, url = transport.calls[0]
        assert (method, transport.calls) and method == "GET"
        assert url.startswith("https://image.pollinations.ai/prompt/")
        assert "blue+bird+sky" in url
        assert "width=1024&height=1024&nologo=true" in url
        assert "seed=" not in url and "model=" not in url

    def test_optional_params_flow_into_query(self):
        transport = RecordingTransport(FakeResponse(content=b"x"))
        PollinationsConnector(transport=transport).send({
            "prompt": "p", "width": 512, "height": 256,
            "model": "flux", "seed": 42})
        _, url = transport.calls[0]
        for fragment in ("width=512", "height=256", "model=flux", "seed=42"):
            assert fragment in url, fragment

    def test_special_characters_urlencoded(self):
        transport = RecordingTransport(FakeResponse(content=b"x"))
        PollinationsConnector(transport=transport).send({"prompt": "a & b?"})
        _, url = transport.calls[0]
        assert "a+%26+b%3F" in url

    def test_empty_prompt_fails_without_network_call(self):
        transport = RecordingTransport(FakeResponse())
        connector = PollinationsConnector(transport=transport)
        result = connector.poll(connector.send({"prompt": "  "}))
        assert not result.ok and "non-empty 'prompt'" in result.error
        assert transport.calls == []

    def test_non_200_is_failed_job(self):
        connector = make_connector(FakeResponse(status_code=502))
        result = connector.poll(connector.send({"prompt": "p"}))
        assert not result.ok and "502" in result.error

    def test_empty_body_rejected(self):
        connector = make_connector(FakeResponse(content=b""))
        result = connector.poll(connector.send({"prompt": "p"}))
        assert not result.ok and "empty response body" in result.error

    def test_non_image_content_type_rejected(self):
        connector = make_connector(FakeResponse(
            content=b"<html>slow down</html>",
            headers={"content-type": "text/html"}))
        result = connector.poll(connector.send({"prompt": "p"}))
        assert not result.ok and "content-type" in result.error

    def test_transport_exception_becomes_failed_job(self):
        def boom(method, url):
            raise ConnectionError("no route to host")
        connector = PollinationsConnector(transport=boom)
        result = connector.poll(connector.send({"prompt": "p"}))
        assert not result.ok and "ConnectionError" in result.error


class TestCapabilities:
    def test_declares_none_auth_with_honest_quota_note(self):
        caps = PollinationsConnector().capabilities()
        assert caps.connector == "pollinations"
        assert caps.auth == "none"
        assert "No account at all" in caps.items[0].quota_note
