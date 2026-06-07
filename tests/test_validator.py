from services.validator import validate_payload, validate_single_creative


def _valid_payload() -> dict:
    videos = [{"video_id": f"V{i}", "prompt": f"Distinct prompt {i}"} for i in range(1, 6)]
    creatives = [
        {
            "ad_label": "A",
            "funnel_stage": "Awareness",
            "language": "EN",
            "headline": "Hook A",
            "primary_text": "Copy A",
            "cta": "Learn More",
            "video_id": "V1",
            "reused": False,
        },
        {
            "ad_label": "B",
            "funnel_stage": "Awareness",
            "language": "EN",
            "headline": "Hook B",
            "primary_text": "Copy B",
            "cta": "Learn More",
            "video_id": "V2",
            "reused": False,
        },
        {
            "ad_label": "C",
            "funnel_stage": "Awareness",
            "language": "EN",
            "headline": "Hook C",
            "primary_text": "Copy C",
            "cta": "Learn More",
            "video_id": "V3",
            "reused": False,
        },
        {
            "ad_label": "D",
            "funnel_stage": "Mid",
            "language": "EN",
            "headline": "Consider D",
            "primary_text": "Copy D",
            "cta": "See How",
            "video_id": "V4",
            "reused": False,
        },
        {
            "ad_label": "E",
            "funnel_stage": "Mid",
            "language": "EN",
            "headline": "Consider E",
            "primary_text": "Copy E",
            "cta": "See How",
            "video_id": "V4",
            "reused": True,
        },
        {
            "ad_label": "F",
            "funnel_stage": "Conversion",
            "language": "EN",
            "headline": "Buy F",
            "primary_text": "Copy F",
            "cta": "Start Now",
            "video_id": "V5",
            "reused": False,
        },
        {
            "ad_label": "G",
            "funnel_stage": "Full",
            "language": "ES",
            "headline": "Compra G",
            "primary_text": "Texto G",
            "cta": "Empieza",
            "video_id": "V4",
            "reused": True,
        },
    ]
    return {
        "set_id": "SET-123",
        "inputs": {
            "persona": "founder",
            "market": "SaaS",
            "funnel_stage": "Full",
        },
        "videos": videos,
        "creatives": creatives,
    }


def test_validate_payload_accepts_expected_mapping():
    payload = _valid_payload()

    ok, message = validate_payload(
        payload,
        expected_inputs={"persona": "founder", "market": "SaaS", "funnel_stage": "Full"},
        expected_set_id="SET-123",
    )

    assert ok is True
    assert message == ""


def test_validate_payload_rejects_duplicate_video_prompts():
    payload = _valid_payload()
    payload["videos"][1]["prompt"] = payload["videos"][0]["prompt"]

    ok, message = validate_payload(
        payload,
        expected_inputs={"persona": "founder", "market": "SaaS", "funnel_stage": "Full"},
        expected_set_id="SET-123",
    )

    assert ok is False
    assert message == "Video prompts must be distinct."


def test_validate_single_creative_rejects_wrong_video_mapping():
    creative = _valid_payload()["creatives"][0] | {"video_id": "V2"}

    ok, message = validate_single_creative(creative, "A")

    assert ok is False
    assert message == "Video mapping mismatch for Ad A."
