"""Tests for the vision critic: image-carrying messages + score_render. No network, no Unreal."""

from __future__ import annotations

from playsmith.config import Config, LLMConfig
from playsmith.engines.unreal import critic
from playsmith.llm import ChatResponse, Message, TaskType, anthropic, catalog


def test_message_image_openai_shape() -> None:
    d = Message.user_with_image("rate this", "QUJD", "image/png").to_dict()
    assert isinstance(d["content"], list)
    assert d["content"][0] == {"type": "text", "text": "rate this"}
    assert d["content"][1]["type"] == "image_url"
    assert d["content"][1]["image_url"]["url"].startswith("data:image/png;base64,QUJD")


def test_message_image_anthropic_blocks() -> None:
    blocks = anthropic._content_blocks(Message.user_with_image("rate this", "QUJD"))
    kinds = [b["type"] for b in blocks]
    assert "image" in kinds and "text" in kinds
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["type"] == "base64" and img["source"]["data"] == "QUJD"


class _VisionGateway:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tasks: list = []

    def chat(self, messages, tools=None, task=TaskType.GENERAL, **kwargs) -> ChatResponse:
        self.tasks.append(task)
        assert any(getattr(m, "images", None) for m in messages)  # the frame was attached
        return ChatResponse(content=self.content, tool_calls=[], finish_reason="stop")


def test_score_render_parses_vision_json(tmp_path) -> None:
    img = tmp_path / "frame.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nDATA")
    gw = _VisionGateway('{"score": 82, "feedback": ["add cover", "brighter lighting"]}')
    c = critic.score_render(str(img), {"objective": "reach the goal"}, gw)
    assert c is not None and c.score == 82 and c.passed
    assert "add cover" in c.feedback and c.dimensions["vision"] == 0.82
    assert gw.tasks == [TaskType.REASONING]


def test_score_render_missing_image_returns_none() -> None:
    assert critic.score_render("/nope/x.png", {}, _VisionGateway("{}")) is None


def test_score_render_bad_reply_returns_none(tmp_path) -> None:
    img = tmp_path / "frame.png"
    img.write_bytes(b"x")
    assert critic.score_render(str(img), {}, _VisionGateway("no json here")) is None


def test_model_supports_vision() -> None:
    def cfg(provider, model):
        return Config(llm=LLMConfig(provider=provider, model=model))

    assert catalog.model_supports_vision(cfg("openai", "gpt-4o"))
    assert catalog.model_supports_vision(cfg("anthropic", "claude-opus-4-8"))
    assert catalog.model_supports_vision(cfg("nvidia", "meta/llama-3.2-90b-vision-instruct"))
    assert not catalog.model_supports_vision(cfg("nvidia", "meta/llama-3.3-70b-instruct"))
    assert not catalog.model_supports_vision(cfg("ollama", "qwen2.5-coder:7b"))
