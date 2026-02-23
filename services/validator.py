from typing import Dict, Tuple


FUNNEL_STAGES = {"Awareness", "Mid", "Conversion", "Full"}
REQUIRED_TOP_LEVEL = {"set_id", "inputs", "videos", "creatives"}
REQUIRED_VIDEO_KEYS = {"video_id", "prompt"}
REQUIRED_CREATIVE_KEYS = {
    "ad_label",
    "funnel_stage",
    "language",
    "headline",
    "primary_text",
    "cta",
    "video_id",
    "reused",
}


EXPECTED_MAPPING = {
    "A": {"funnel_stage": "Awareness", "language": "EN", "video_id": "V1", "reused": False},
    "B": {"funnel_stage": "Awareness", "language": "EN", "video_id": "V2", "reused": False},
    "C": {"funnel_stage": "Awareness", "language": "EN", "video_id": "V3", "reused": False},
    "D": {"funnel_stage": "Mid", "language": "EN", "video_id": "V4", "reused": False},
    "E": {"funnel_stage": "Mid", "language": "EN", "video_id": "V4", "reused": True},
    "F": {"funnel_stage": "Conversion", "language": "EN", "video_id": "V5", "reused": False},
    "G": {"funnel_stage": None, "language": "ES", "video_id": "V4", "reused": True},
}


def _ensure_keys(obj: Dict, required_keys: set) -> bool:
    return set(obj.keys()) == required_keys


def validate_payload(
    payload: Dict,
    expected_inputs: Dict,
    expected_set_id: str,
) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "Response is not a JSON object."

    if set(payload.keys()) != REQUIRED_TOP_LEVEL:
        return False, "JSON schema mismatch."

    if payload.get("set_id") != expected_set_id:
        return False, "Set ID mismatch."

    inputs = payload.get("inputs", {})
    if set(inputs.keys()) != {"persona", "market", "funnel_stage"}:
        return False, "Inputs schema mismatch."

    if inputs.get("persona") != expected_inputs.get("persona"):
        return False, "Persona mismatch."
    if inputs.get("market") != expected_inputs.get("market"):
        return False, "Market mismatch."
    if inputs.get("funnel_stage") != expected_inputs.get("funnel_stage"):
        return False, "Funnel stage mismatch."

    videos = payload.get("videos")
    if not isinstance(videos, list) or len(videos) != 5:
        return False, "Videos array must contain exactly 5 items."

    video_ids = []
    prompts = []
    for video in videos:
        if not isinstance(video, dict) or not _ensure_keys(video, REQUIRED_VIDEO_KEYS):
            return False, "Video schema mismatch."
        video_ids.append(video.get("video_id"))
        prompt = video.get("prompt")
        prompts.append(prompt)
        if not isinstance(prompt, str) or not prompt.strip():
            return False, "Video prompt missing."

    if sorted(video_ids) != ["V1", "V2", "V3", "V4", "V5"]:
        return False, "Video IDs must be V1-V5."
    if len(set(prompts)) != len(prompts):
        return False, "Video prompts must be distinct."

    creatives = payload.get("creatives")
    if not isinstance(creatives, list) or len(creatives) != 7:
        return False, "Creatives array must contain exactly 7 items."

    labels = []
    for creative in creatives:
        if not isinstance(creative, dict) or not _ensure_keys(creative, REQUIRED_CREATIVE_KEYS):
            return False, "Creative schema mismatch."
        labels.append(creative.get("ad_label"))
        if creative.get("funnel_stage") not in FUNNEL_STAGES:
            return False, "Invalid funnel stage in creative."
        if creative.get("language") not in {"EN", "ES"}:
            return False, "Invalid language in creative."
        for field in ["headline", "primary_text", "cta"]:
            if not isinstance(creative.get(field), str) or not creative.get(field).strip():
                return False, f"Missing creative field: {field}."

    if sorted(labels) != ["A", "B", "C", "D", "E", "F", "G"]:
        return False, "Creatives must be labeled A-G."

    for creative in creatives:
        label = creative["ad_label"]
        expected = EXPECTED_MAPPING[label]
        if expected["language"] != creative["language"]:
            return False, f"Language mismatch for Ad {label}."
        if expected["video_id"] != creative["video_id"]:
            return False, f"Video mapping mismatch for Ad {label}."
        if expected["reused"] != creative["reused"]:
            return False, f"Reused flag mismatch for Ad {label}."
        if expected["funnel_stage"] and expected["funnel_stage"] != creative["funnel_stage"]:
            return False, f"Funnel stage mismatch for Ad {label}."

    return True, ""


def validate_single_creative(data: Dict, ad_label: str) -> Tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Response is not a JSON object."

    required = {"ad_label", "funnel_stage", "language", "headline", "primary_text", "cta", "video_id", "reused"}
    if not required.issubset(set(data.keys())):
        missing = required - set(data.keys())
        return False, f"Missing fields: {', '.join(missing)}"

    if data.get("ad_label") != ad_label:
        return False, f"Expected ad_label '{ad_label}', got '{data.get('ad_label')}'."

    expected = EXPECTED_MAPPING.get(ad_label)
    if not expected:
        return False, f"Unknown ad label: {ad_label}"

    if expected["language"] != data.get("language"):
        return False, f"Language mismatch for Ad {ad_label}."
    if expected["video_id"] != data.get("video_id"):
        return False, f"Video mapping mismatch for Ad {ad_label}."
    if expected["reused"] != data.get("reused"):
        return False, f"Reused flag mismatch for Ad {ad_label}."
    if expected["funnel_stage"] and expected["funnel_stage"] != data.get("funnel_stage"):
        return False, f"Funnel stage mismatch for Ad {ad_label}."

    for field in ["headline", "primary_text", "cta"]:
        if not isinstance(data.get(field), str) or not data.get(field).strip():
            return False, f"Missing creative field: {field}."

    return True, ""
