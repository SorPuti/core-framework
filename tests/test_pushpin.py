"""Pushpin GRIP helpers e publicação (sem broker real)."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from strider.pushpin import (
    PushpinPublishError,
    build_http_stream_item,
    build_publish_body,
    grip_stream_headers,
    grip_stream_response,
    publish_pushpin_items,
    qualify_channel,
    qualify_channel_from_settings,
)


def test_qualify_channel():
    assert qualify_channel("events", prefix="app") == "app.events"
    assert qualify_channel("events") == "events"


def test_grip_stream_headers():
    h = grip_stream_headers("my-channel", timeout="30")
    assert h["Grip-Hold"] == "stream"
    assert h["Grip-Channel"] == "my-channel"
    assert h["Grip-Timeout"] == "30"


def test_grip_stream_response():
    r = grip_stream_response("ch", content="")
    assert r.headers["Grip-Channel"] == "ch"
    assert r.headers["Grip-Hold"] == "stream"


def test_build_http_stream_item():
    item = build_http_stream_item("test", "hello\n")
    assert item["channel"] == "test"
    assert item["formats"]["http-stream"]["content"] == "hello\n"


def test_build_publish_body_roundtrip():
    body = build_publish_body([build_http_stream_item("c", "x")])
    d = json.loads(body.decode())
    assert len(d["items"]) == 1


@pytest.mark.asyncio
async def test_publish_pushpin_items_http_error():
    def boom(*_a, **_k):
        raise urllib.error.HTTPError("http://x", 500, "Internal", hdrs=None, fp=None)

    with patch("strider.pushpin.publish.urllib.request.urlopen", side_effect=boom):
        with pytest.raises(PushpinPublishError, match="HTTP 500"):
            await publish_pushpin_items(
                [build_http_stream_item("c", "hi")],
                url="http://127.0.0.1:5561/publish/",
                timeout=1.0,
            )


@pytest.mark.asyncio
async def test_publish_pushpin_items_ok():
    resp = MagicMock()
    resp.read.return_value = b"{}"
    resp.getcode.return_value = 200
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__.return_value = None

    with patch("strider.pushpin.publish.urllib.request.urlopen", return_value=ctx):
        await publish_pushpin_items(
            [build_http_stream_item("c", "line\n")],
            url="http://127.0.0.1:5561/publish/",
            timeout=1.0,
        )


def test_qualify_channel_from_settings(monkeypatch):
    class S:
        pushpin_default_channel_prefix = "api"

    monkeypatch.setattr("strider.config.get_settings", lambda: S())
    assert qualify_channel_from_settings("live") == "api.live"
