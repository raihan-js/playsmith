"""Native Anthropic Messages API adapter (``/v1/messages``).

Why a separate path instead of Anthropic's OpenAI-compat endpoint: the compat shim ignores
strict function-calling schemas and drops prompt caching, which makes it unreliable for our
multi-turn tool loop. So we translate to/from Anthropic's native shape here, behind the same
``ChatResponse`` the rest of Playsmith consumes. All Anthropic specifics live in this file.
"""

from __future__ import annotations

import json

from playsmith.config import LLMConfig
from playsmith.llm.types import ChatResponse, Message, ToolCall

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 8192  # output budget; Anthropic requires max_tokens to be set


def _content_blocks(message: Message) -> list[dict]:
    """Translate one Playsmith Message into Anthropic content blocks."""
    if message.role == "tool":
        return [
            {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id or "",
                "content": message.content or "",
            }
        ]
    blocks: list[dict] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls:
        blocks.append(
            {"type": "tool_use", "id": call.id or "", "name": call.name, "input": call.arguments}
        )
    return blocks


def to_anthropic_messages(messages: list[Message]) -> tuple[str, list[dict]]:
    """Return (system_prompt, anthropic_messages).

    System messages are hoisted to the top-level ``system`` field. Tool roles map to user-turn
    ``tool_result`` blocks. Consecutive same-role turns are coalesced so the conversation stays
    valid (Anthropic expects alternating user/assistant turns).
    """
    system_parts: list[str] = []
    out: list[dict] = []
    for message in messages:
        if message.role == "system":
            if message.content:
                system_parts.append(message.content)
            continue
        role = "assistant" if message.role == "assistant" else "user"
        blocks = _content_blocks(message)
        if not blocks:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})
    return "\n".join(system_parts), out


def _tool_choice(tool_choice: str | None) -> dict:
    if tool_choice in ("required", "any"):
        return {"type": "any"}
    return {"type": "auto"}


def build_request(
    cfg: LLMConfig,
    messages: list[Message],
    tools=None,
    temperature: float | None = None,
    tool_choice: str | None = None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str, dict, dict]:
    """Build (url, headers, payload) for an Anthropic ``/v1/messages`` call."""
    system, anthropic_messages = to_anthropic_messages(messages)
    url = cfg.base_url.rstrip("/") + "/messages"
    headers = {"content-type": "application/json", "anthropic-version": ANTHROPIC_VERSION}
    if cfg.api_key:
        headers["x-api-key"] = cfg.api_key
    payload: dict = {"model": cfg.model, "max_tokens": max_tokens, "messages": anthropic_messages}
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        payload["tool_choice"] = _tool_choice(tool_choice)
    if temperature is not None:
        payload["temperature"] = temperature
    return url, headers, payload


def parse_response(data: dict, fallback_model: str) -> ChatResponse:
    """Translate an Anthropic Messages response into a ChatResponse."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            args = block.get("input") or {}
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(
                ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=args,
                    raw_arguments=json.dumps(args),
                )
            )
    content = "".join(text_parts) or None
    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=data.get("stop_reason"),
        model=data.get("model", fallback_model),
        raw=data,
    )
