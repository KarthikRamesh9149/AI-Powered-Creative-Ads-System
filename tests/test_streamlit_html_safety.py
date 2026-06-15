from app import _css_slug, _html_text


def test_html_text_escapes_provider_controlled_values() -> None:
    assert _html_text("<img src=x onerror=alert(1)>") == "&lt;img src=x onerror=alert(1)&gt;"
    assert _html_text('"quoted" & raw') == "&quot;quoted&quot; &amp; raw"


def test_css_slug_removes_class_breakout_characters() -> None:
    assert _css_slug("Winner' onclick='alert(1)") == "winner-onclick-alert-1"
    assert _css_slug("Needs Revision") == "needs-revision"
