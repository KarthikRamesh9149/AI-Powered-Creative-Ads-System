from services.notion import (
    DEFAULT_PROPERTY_TYPES,
    build_notion_properties,
    build_tag_update_properties,
    build_update_properties,
    database_url,
)


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
