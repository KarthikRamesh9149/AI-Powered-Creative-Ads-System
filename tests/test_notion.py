import pytest

from services.notion import (
    DEFAULT_PROPERTY_TYPES,
    NotionClient,
    build_notion_properties,
    build_tag_update_properties,
    build_update_properties,
    database_url,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_query_database_collects_all_pages(monkeypatch):
    pages = [
        _FakeResponse({"results": [{"id": "one"}], "has_more": True, "next_cursor": "cursor-1"}),
        _FakeResponse({"results": [{"id": "two"}], "has_more": False, "next_cursor": None}),
    ]
    bodies = []

    def fake_post(url, headers, json, timeout):
        bodies.append(json)
        return pages.pop(0)

    monkeypatch.setattr("services.notion.requests.post", fake_post)
    client = NotionClient("token", "database", None, "2022-06-28")

    assert client.query_database() == [{"id": "one"}, {"id": "two"}]
    assert bodies == [{}, {"start_cursor": "cursor-1"}]


def test_query_database_rejects_repeating_cursor(monkeypatch):
    response = _FakeResponse({"results": [], "has_more": True, "next_cursor": "same"})
    monkeypatch.setattr("services.notion.requests.post", lambda *args, **kwargs: response)
    client = NotionClient("token", "database", None, "2022-06-28")

    with pytest.raises(RuntimeError, match="cursor did not advance"):
        client.query_database()


def test_query_database_enforces_page_cap(monkeypatch):
    monkeypatch.setattr("services.notion.MAX_QUERY_PAGES", 2)
    responses = iter(
        [
            _FakeResponse({"results": [], "has_more": True, "next_cursor": "cursor-1"}),
            _FakeResponse({"results": [], "has_more": True, "next_cursor": "cursor-2"}),
        ]
    )
    monkeypatch.setattr("services.notion.requests.post", lambda *args, **kwargs: next(responses))
    client = NotionClient("token", "database", None, "2022-06-28")

    with pytest.raises(RuntimeError, match="exceeded pagination limit"):
        client.query_database()


def test_build_notion_properties_uses_configured_property_types():
    creative = {
        "funnel_stage": "Awareness",
        "ad_label": "A",
        "language": "EN",
        "headline": "Sharper creative",
        "primary_text": "Launch faster.",
        "cta": "Try it",
        "video_id": "V1",
        "reused": False,
    }
    inputs = {"persona": "marketer", "market": "DTC"}
    property_types = DEFAULT_PROPERTY_TYPES | {"Tag": "select", "Iteration": "number"}

    properties = build_notion_properties(
        creative=creative,
        inputs=inputs,
        set_id="SET-ABC",
        video_url="https://example.com/video.mp4",
        status="Generated",
        property_types=property_types,
        tag="Testing",
        iteration=2,
    )

    assert properties["Set ID"] == {"title": [{"type": "text", "text": {"content": "SET-ABC"}}]}
    assert properties["Headline"]["rich_text"][0]["text"]["content"] == "Sharper creative"
    assert properties["Video URL"] == {"url": "https://example.com/video.mp4"}
    assert properties["Reused?"] == {"checkbox": False}
    assert properties["Tag"] == {"select": {"name": "Testing"}}
    assert properties["Iteration"] == {"number": 2}


def test_build_update_properties_omits_empty_url():
    properties = build_update_properties(video_url=None, status="Iterating", property_types=None)

    assert "Video URL" not in properties
    assert properties["Status"] == {"status": {"name": "Iterating"}}


def test_build_tag_update_properties_allows_notes_without_tag():
    properties = build_tag_update_properties(
        property_types={"Tag": "select", "Notes": "rich_text", "Iteration": "number"},
        notes="Needs a tighter hook.",
        iteration=3,
    )

    assert "Tag" not in properties
    assert properties["Notes"]["rich_text"][0]["text"]["content"] == "Needs a tighter hook."
    assert properties["Iteration"] == {"number": 3}


def test_database_url_strips_dashes():
    assert database_url("12345678-1234-5678-1234-567812345678") == (
        "https://www.notion.so/12345678123456781234567812345678"
    )
