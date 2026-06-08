"""Provider-agnostic types for the LLM Gateway.

Everything here mirrors the OpenAI-compatible ``/v1/chat/completions`` shape so the rest
of Playsmith never has to know which provider (Ollama, LM Studio, vLLM, cloud) is in use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum


class TaskType(StrEnum):
    """The kind of work a request represents.

    This is the seam for a future model router (Phase 2): ``chat(task=...)`` lets callers
    label *why* they are calling, so the router can later pick a provider/model per task.
    For now every task resolves to the single configured provider.
    """

    GENERAL = "general"
    CODING = "coding"
    REASONING = "reasoning"
    ROUTING = "routing"


@dataclass
class Message:
    """A single chat message in the OpenAI shape."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    # Assistant messages may carry tool calls; tool messages reply to one.
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None  # function name for a "tool" role message

    def to_dict(self) -> dict:
        msg: dict = {"role": self.role}
        # OpenAI requires the key even when content is null for assistant tool-call turns.
        msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_request_dict() for tc in self.tool_calls]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg

    # Convenience constructors -------------------------------------------------
    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        return cls(role="assistant", content=content)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str, name: str | None = None) -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


@dataclass
class Tool:
    """A function tool the model may call."""

    name: str
    description: str
    parameters: dict  # JSON Schema for the arguments

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    """A tool call the model emitted."""

    id: str
    name: str
    arguments: dict
    raw_arguments: str = "{}"

    def to_request_dict(self) -> dict:
        """Serialize back into an assistant message (so multi-turn tool loops work)."""
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.raw_arguments},
        }

    @classmethod
    def from_response(cls, data: dict) -> ToolCall:
        fn = data.get("function", {}) or {}
        raw = fn.get("arguments") or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = {}
        return cls(
            id=data.get("id", ""),
            name=fn.get("name", ""),
            arguments=parsed,
            raw_arguments=raw if isinstance(raw, str) else json.dumps(raw),
        )


@dataclass
class ChatResponse:
    """A normalized response from any provider."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_assistant_message(self) -> Message:
        """Turn this response back into an assistant message for the next turn."""
        return Message(role="assistant", content=self.content, tool_calls=list(self.tool_calls))
