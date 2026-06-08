"""Tests for the router-maturity eval harness (providers mocked)."""

from __future__ import annotations

import json

import httpx

from playsmith.config import LLMConfig
from playsmith.llm import LLMGateway
from playsmith.llm.eval import evaluate_provider, evaluate_targets

LOCAL = LLMConfig(provider="ollama", base_url="http://localhost:11434/v1", model="local-7b")
CLOUD = LLMConfig(provider="openai", base_url="https://api.openai.com/v1", model="cloud-x")


def _gw(handler, cfg=LOCAL) -> LLMGateway:
    return LLMGateway(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))


def _tool_response(name: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c",
                                "type": "function",
                                "function": {"name": name, "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        },
    )


def _perfect(request: httpx.Request) -> httpx.Response:
    # Echo back exactly the tool the request offered — a perfectly reliable model.
    name = json.loads(request.content)["tools"][0]["function"]["name"]
    return _tool_response(name)


def _always_write(request: httpx.Request) -> httpx.Response:
    return _tool_response("write_file")  # wrong for the read_file fixtures


def _no_tools(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "I won't."}}]})


def test_perfect_provider_is_fully_reliable() -> None:
    res = evaluate_provider(_gw(_perfect), LOCAL)
    assert res.reliability == 1.0
    assert res.meets_threshold
    assert "local is reliable" in res.recommendation


def test_flaky_provider_below_threshold_recommends_fallback() -> None:
    # 2 of 4 default fixtures expect write_file; always answering write_file => 50%.
    res = evaluate_provider(_gw(_always_write), LOCAL)
    assert res.reliability == 0.5
    assert not res.meets_threshold
    assert "fallback" in res.recommendation


def test_no_tool_calls_is_zero_reliability() -> None:
    res = evaluate_provider(_gw(_no_tools), LOCAL)
    assert res.reliability == 0.0
    assert not res.meets_threshold


def test_failed_calls_count_as_unreliable() -> None:
    def boom(_req):
        raise httpx.ConnectError("refused")

    res = evaluate_provider(_gw(boom), LOCAL)
    assert res.reliability == 0.0


def test_cloud_provider_recommendation() -> None:
    res = evaluate_provider(_gw(_perfect, CLOUD), CLOUD)
    assert not res.is_local
    assert "cloud provider" in res.recommendation


def test_evaluate_targets_labels_results() -> None:
    results = evaluate_targets(_gw(_perfect), [("default", LOCAL), ("route:coding", CLOUD)])
    assert [label for label, _ in results] == ["default", "route:coding"]
    assert all(r.meets_threshold for _, r in results)
