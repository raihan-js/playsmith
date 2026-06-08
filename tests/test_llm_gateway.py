"""Tests for the LLM Gateway with the HTTP layer mocked (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from playsmith.config import LLMConfig
from playsmith.llm import ChatResponse, LLMError, LLMGateway, Message, Tool


def _gateway(handler, cfg: LLMConfig | None = None) -> LLMGateway:
    cfg = cfg or LLMConfig(provider="ollama", base_url="http://localhost:11434/v1")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMGateway(cfg, client=client)


def test_chat_builds_openai_request_and_parses_reply() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5-coder:7b",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Hello there friend!"},
                    }
                ],
            },
        )

    gw = _gateway(handler)
    resp = gw.chat([Message.system("be brief"), Message.user("hi")])

    assert isinstance(resp, ChatResponse)
    assert resp.content == "Hello there friend!"
    assert resp.finish_reason == "stop"
    assert not resp.has_tool_calls
    # Endpoint is base_url + /chat/completions.
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    # Request carries the messages and the model.
    assert captured["body"]["model"] == "qwen2.5-coder:7b"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "be brief"}


def test_ollama_gets_num_ctx_option() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    cfg = LLMConfig(provider="ollama", base_url="http://localhost:11434/v1", num_ctx=32768)
    _gateway(handler, cfg).chat([Message.user("hi")])
    assert captured["body"]["options"]["num_ctx"] == 32768


def test_cloud_provider_does_not_send_num_ctx() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    cfg = LLMConfig(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-x",
        api_key="sk-test",
    )
    _gateway(handler, cfg).chat([Message.user("hi")])
    assert "options" not in captured["body"]  # would 400 a cloud endpoint
    assert captured["auth"] == "Bearer sk-test"


def test_tool_calls_are_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "write_file"
        assert body["tool_choice"] == "auto"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": '{"path": "a.gd", "content": "x"}',
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    tool = Tool(
        name="write_file",
        description="write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    )
    resp = _gateway(handler).chat([Message.user("make a file")], tools=[tool])
    assert resp.has_tool_calls
    call = resp.tool_calls[0]
    assert call.name == "write_file"
    assert call.arguments == {"path": "a.gd", "content": "x"}
    # The response round-trips back into an assistant message for the next turn.
    assert resp.to_assistant_message().tool_calls[0].id == "call_1"


def test_http_error_raises_llmerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMError):
        _gateway(handler).chat([Message.user("hi")])


def test_connection_error_raises_friendly_llmerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="Is the provider"):
        _gateway(handler).chat([Message.user("hi")])
