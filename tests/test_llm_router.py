"""Tests for the model router, provider kinds, and cloud fallback (HTTP mocked)."""

from __future__ import annotations

import json

import httpx
import pytest

from playsmith.config import LLMConfig
from playsmith.llm import LLMGateway, Message, TaskType, Tool
from playsmith.llm.anthropic import parse_response, to_anthropic_messages

LOCAL = LLMConfig(provider="ollama", base_url="http://localhost:11434/v1", model="local-7b")
CLOUD = LLMConfig(
    provider="openai", base_url="https://api.openai.com/v1", model="cloud-x", api_key="sk-test"
)
TOOL = Tool("write_file", "write a file", {"type": "object", "properties": {}, "required": []})


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# -- is_local detection ----------------------------------------------------------
def test_is_local_detection() -> None:
    assert LOCAL.is_local
    assert not CLOUD.is_local
    assert LLMConfig(provider="x", base_url="http://192.168.1.9:1234/v1").is_local
    assert not LLMConfig(provider="openrouter", base_url="https://openrouter.ai/api/v1").is_local


# -- route resolution ------------------------------------------------------------
def test_resolve_routes_per_task() -> None:
    gw = LLMGateway(LOCAL, routes={"coding": CLOUD})
    assert gw._resolve(TaskType.CODING) is CLOUD
    assert gw._resolve(TaskType.GENERAL) is LOCAL  # unset task -> default


# -- anthropic provider kind -----------------------------------------------------
def test_anthropic_request_shape_and_parse() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "Sure."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "write_file",
                        "input": {"path": "a.gd"},
                    },
                ],
            },
        )

    cfg = LLMConfig(
        provider="anthropic",
        base_url="https://api.anthropic.com/v1",
        model="claude-sonnet-4-6",
        api_key="sk-ant",
        kind="anthropic",
    )
    gw = LLMGateway(cfg, client=_client(handler))
    resp = gw.chat([Message.system("be brief"), Message.user("make a file")], tools=[TOOL])

    # Native Messages endpoint + headers.
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["anthropic-version"]
    assert captured["headers"]["x-api-key"] == "sk-ant"
    # System hoisted out of messages; tools use input_schema; max_tokens set.
    assert captured["body"]["system"] == "be brief"
    assert captured["body"]["messages"][0]["role"] == "user"
    assert captured["body"]["tools"][0]["input_schema"] == TOOL.parameters
    assert captured["body"]["max_tokens"] > 0
    # Response translated back into the common shape.
    assert resp.content == "Sure."
    assert resp.tool_calls[0].name == "write_file"
    assert resp.tool_calls[0].arguments == {"path": "a.gd"}


def test_to_anthropic_messages_coalesces_and_hoists_system() -> None:
    system, msgs = to_anthropic_messages(
        [
            Message.system("S1"),
            Message.system("S2"),
            Message.tool_result("t1", "result one"),
            Message.tool_result("t2", "result two"),
        ]
    )
    assert system == "S1\nS2"
    # Two consecutive tool results coalesce into a single user turn (valid alternation).
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert [b["type"] for b in msgs[0]["content"]] == ["tool_result", "tool_result"]


def test_parse_response_text_only() -> None:
    resp = parse_response({"content": [{"type": "text", "text": "hi"}]}, "m")
    assert resp.content == "hi"
    assert not resp.has_tool_calls


# -- cloud fallback --------------------------------------------------------------
def _host_router(local_response, cloud_response):
    """A handler that answers differently for the local vs cloud endpoint."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "localhost":
            return local_response(request)
        return cloud_response(request)

    return handler


def test_no_tool_call_falls_back_local_to_cloud_with_warning() -> None:
    def local(_req):  # OpenAI shape, no tool call — a common local-model failure
        return httpx.Response(200, json={"choices": [{"message": {"content": "I cannot."}}]})

    def cloud(_req):  # cloud returns a proper tool call
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "write_file", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    gw = LLMGateway(LOCAL, fallback=CLOUD, client=_client(_host_router(local, cloud)))
    resp = gw.chat([Message.user("build it")], tools=[TOOL], task=TaskType.CODING)

    assert resp.has_tool_calls  # the cloud result was used
    assert gw.warnings and "cloud" in gw.warnings[0]


def test_hard_failure_falls_back_to_cloud() -> None:
    def local(_req):
        return httpx.Response(500, text="local model crashed")

    def cloud(_req):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok from cloud"}}]})

    gw = LLMGateway(LOCAL, fallback=CLOUD, client=_client(_host_router(local, cloud)))
    resp = gw.chat([Message.user("hi")], tools=[TOOL], task=TaskType.REASONING)
    assert resp.content == "ok from cloud"
    assert gw.warnings


def test_no_fallback_for_general_task() -> None:
    def local(_req):
        return httpx.Response(200, json={"choices": [{"message": {"content": "no tools used"}}]})

    def cloud(_req):  # pragma: no cover - must not be reached
        raise AssertionError("fallback should not fire for GENERAL")

    gw = LLMGateway(LOCAL, fallback=CLOUD, client=_client(_host_router(local, cloud)))
    resp = gw.chat([Message.user("hi")], tools=[TOOL], task=TaskType.GENERAL)
    assert resp.content == "no tools used"
    assert not gw.warnings


def test_no_fallback_when_primary_is_cloud() -> None:
    def cloud(_req):  # default is cloud; no tool call, but no fallback should trigger
        return httpx.Response(200, json={"choices": [{"message": {"content": "no tool"}}]})

    def other(_req):  # pragma: no cover
        raise AssertionError("should not reach a second provider")

    gw = LLMGateway(CLOUD, fallback=LOCAL, client=_client(_host_router(other, cloud)))
    resp = gw.chat([Message.user("hi")], tools=[TOOL], task=TaskType.CODING)
    assert resp.content == "no tool"
    assert not gw.warnings


def test_existing_single_provider_path_unaffected() -> None:
    def handler(_req):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    gw = LLMGateway(LOCAL, client=_client(handler))
    assert gw.chat([Message.user("hi")]).content == "hello"


@pytest.mark.filterwarnings("ignore")
def test_warning_emitted_without_console() -> None:
    def local(_req):
        return httpx.Response(500, text="down")

    def cloud(_req):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    gw = LLMGateway(LOCAL, fallback=CLOUD, client=_client(_host_router(local, cloud)))
    gw.chat([Message.user("hi")], task=TaskType.CODING)
    assert len(gw.warnings) == 1
