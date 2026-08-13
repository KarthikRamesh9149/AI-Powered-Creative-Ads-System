import json

import pytest

from services.auth import access_granted
from services.llm import _call_groq
from services.video import create_video_task


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_auth_fails_closed_and_accepts_exact_token():
    assert not access_granted("", "configured")
    assert not access_granted("candidate", "")
    assert not access_granted("wrong", "configured")
    assert access_granted("configured", "configured")


def test_groq_transient_failure_is_retried_without_network(monkeypatch):
    responses = iter([Response(503, {}), Response(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})])
    monkeypatch.setattr("services.llm.requests.post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("services.llm.time.sleep", lambda *_: None)
    assert json.loads(_call_groq({"model": "mock"}, "test-key")) == {"ok": True}


def test_groq_provider_error_is_generic(monkeypatch):
    monkeypatch.setattr("services.llm.requests.post", lambda *args, **kwargs: Response(401, {"secret": "provider detail"}))
    with pytest.raises(RuntimeError, match="Creative provider request failed") as exc:
        _call_groq({}, "test-key")
    assert "provider detail" not in str(exc.value)


def test_video_task_contract_is_mocked(monkeypatch):
    monkeypatch.setattr(
        "services.video.requests.request",
        lambda method, url, **kwargs: Response(200, {"code": 200, "data": {"taskId": "task-1"}}),
    )
    assert create_video_task("safe prompt", "test-key") == "task-1"
