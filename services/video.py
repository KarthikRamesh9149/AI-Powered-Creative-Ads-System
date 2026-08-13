import time

import requests

RUNWAY_GENERATE_URL = "https://api.kie.ai/api/v1/runway/generate"
RUNWAY_STATUS_URL = "https://api.kie.ai/api/v1/runway/record-detail"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _request(method: str, url: str, **kwargs):
    response = None
    for attempt in range(2):
        try:
            response = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if attempt == 0:
                time.sleep(0.2)
                continue
            raise RuntimeError("Video provider is temporarily unavailable.") from exc
        if response.status_code not in TRANSIENT_STATUS_CODES or attempt == 1:
            return response
        time.sleep(0.2)
    raise RuntimeError("Video provider request failed.")


def create_video_task(prompt: str, api_key: str, callback_url: str = "") -> str:
    if not api_key:
        raise RuntimeError("Missing video API key.")

    payload = {
        "prompt": prompt,
        "duration": 5,
        "quality": "720p",
        "aspectRatio": "9:16",
        "waterMark": "",
    }
    if callback_url:
        payload["callBackUrl"] = callback_url

    response = _request(
        "POST",
        RUNWAY_GENERATE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code >= 300:
        raise RuntimeError("Video provider request failed.")

    data = response.json()
    if data.get("code") and data.get("code") != 200:
        raise RuntimeError("Video provider request failed.")
    task_id = data.get("data", {}).get("taskId")
    if not task_id:
        raise RuntimeError("Video task ID missing.")
    return task_id


def get_video_status(task_id: str, api_key: str):
    if not api_key:
        raise RuntimeError("Missing video API key.")

    response = _request(
        "GET",
        RUNWAY_STATUS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        params={"taskId": task_id},
        timeout=15,
    )
    if response.status_code >= 300:
        raise RuntimeError("Video provider status request failed.")

    data = response.json()
    if data.get("code") and data.get("code") != 200:
        raise RuntimeError("Video provider status request failed.")
    state = data.get("data", {}).get("state")
    if state in {"success", "SUCCESS"}:
        video_info = data.get("data", {}).get("videoInfo", {}) or {}
        video_url = (
            video_info.get("videoUrl")
            or video_info.get("url")
            or data.get("data", {}).get("videoUrl")
        )
        if not video_url:
            return "fail", None, "Missing video URL."
        return "success", video_url, None
    if state in {"fail", "failed", "FAIL"}:
        return "fail", None, data.get("data", {}).get("error") or "Video failed."
    return "pending", None, None
