"""LLM Gateway — one way to talk to any model via the OpenAI-compatible /v1 API.

Nothing outside this package should know which provider is in use (CLAUDE.md §6,
docs/ARCHITECTURE.md §1). A provider is just ``{base_url, model, api_key?, num_ctx}``.
"""

from __future__ import annotations

import httpx

from playsmith.config import Config, LLMConfig, load_config
from playsmith.llm.types import ChatResponse, Message, TaskType, Tool, ToolCall


class LLMError(Exception):
    """Raised when a chat completion call fails."""


class LLMGateway:
    """Calls an OpenAI-compatible ``POST /v1/chat/completions`` endpoint.

    The ``task`` argument on :meth:`chat` is the seam for a future model router; today
    every task resolves to the single configured provider via :meth:`_resolve`.
    """

    def __init__(
        self,
        config: LLMConfig,
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._timeout = timeout
        # An injectable client makes the HTTP layer trivially mockable in tests.
        self._client = client

    @classmethod
    def from_config(cls, config: Config | None = None, **kwargs) -> LLMGateway:
        cfg = config or load_config()
        return cls(cfg.llm, **kwargs)

    # -- router seam -----------------------------------------------------------
    def _resolve(self, task: TaskType) -> LLMConfig:
        """Pick the provider for a task. Single-provider today; router lands in Phase 2."""
        return self.config

    # -- request building ------------------------------------------------------
    @staticmethod
    def _is_ollama(cfg: LLMConfig) -> bool:
        return "ollama" in cfg.provider.lower() or ":11434" in cfg.base_url

    def _url(self, cfg: LLMConfig) -> str:
        return cfg.base_url.rstrip("/") + "/chat/completions"

    def _headers(self, cfg: LLMConfig) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        return headers

    def _build_payload(
        self,
        cfg: LLMConfig,
        messages: list[Message],
        tools: list[Tool] | None,
        temperature: float | None,
        tool_choice: str | None,
    ) -> dict:
        payload: dict = {
            "model": cfg.model,
            "messages": [m.to_dict() for m in messages],
        }
        if tools:
            payload["tools"] = [t.to_dict() for t in tools]
            payload["tool_choice"] = tool_choice or "auto"
        if temperature is not None:
            payload["temperature"] = temperature
        # Local runners need a large context window; the 4K default breaks agentic
        # editing (CLAUDE.md §5). Only Ollama accepts `options.num_ctx`; sending it to a
        # cloud OpenAI endpoint would 400, so we gate on the provider.
        if self._is_ollama(cfg):
            payload["options"] = {"num_ctx": cfg.num_ctx}
        return payload

    # -- the call --------------------------------------------------------------
    def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        task: TaskType = TaskType.GENERAL,
        *,
        temperature: float | None = None,
        tool_choice: str | None = None,
    ) -> ChatResponse:
        cfg = self._resolve(task)
        payload = self._build_payload(cfg, messages, tools, temperature, tool_choice)
        url = self._url(cfg)
        headers = self._headers(cfg)

        try:
            if self._client is not None:
                resp = self._client.post(url, json=payload, headers=headers, timeout=self._timeout)
            else:
                resp = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach the model at {url}. "
                f"Is the provider '{cfg.provider}' running? ({exc})"
            ) from exc

        if resp.status_code >= 400:
            raise LLMError(
                f"Model endpoint {url} returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"Model endpoint {url} returned non-JSON: {resp.text[:200]}") from exc

        return self._parse(data, fallback_model=cfg.model)

    @staticmethod
    def _parse(data: dict, fallback_model: str) -> ChatResponse:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"Model response had no choices: {data}")
        choice = choices[0]
        msg = choice.get("message", {}) or {}
        tool_calls = [ToolCall.from_response(tc) for tc in (msg.get("tool_calls") or [])]
        return ChatResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", fallback_model),
            raw=data,
        )
