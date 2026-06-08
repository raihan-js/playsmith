"""LLM Gateway + model router — one way to talk to any model, local or cloud.

Nothing outside this package knows which provider is in use (CLAUDE.md §6, docs/ARCHITECTURE.md
§1). A provider is ``{base_url, model, api_key?, num_ctx, kind}``. The router picks a provider per
:class:`TaskType` and may fall back to a configured cloud provider on hard CODING/REASONING steps —
**always warning the user** when it crosses from local to cloud (CLAUDE.md §5).
"""

from __future__ import annotations

import warnings

import httpx
from rich.console import Console

from playsmith.config import Config, LLMConfig, load_config
from playsmith.llm import anthropic
from playsmith.llm.types import ChatResponse, Message, TaskType, Tool, ToolCall

# Tasks for which a local failure / no-tool-call may fall back to the cloud provider.
_FALLBACK_TASKS = frozenset({TaskType.CODING, TaskType.REASONING})


class LLMError(Exception):
    """Raised when a chat completion call fails."""


class LLMGateway:
    """Calls a configured provider, routing per task with an optional cloud fallback."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        routes: dict[str, LLMConfig] | None = None,
        fallback: LLMConfig | None = None,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
        console: Console | None = None,
    ) -> None:
        self.config = config  # the default provider
        self.routes = routes or {}
        self.fallback = fallback
        self._timeout = timeout
        self._client = client  # injectable for tests
        self.console = console
        self.warnings: list[str] = []

    @classmethod
    def from_config(cls, config: Config | None = None, **kwargs) -> LLMGateway:
        cfg = config or load_config()
        return cls(cfg.llm, routes=cfg.llm_routes, fallback=cfg.llm_fallback, **kwargs)

    # -- routing ---------------------------------------------------------------
    def _resolve(self, task: TaskType) -> LLMConfig:
        """Pick the provider for a task; unset tasks use the default provider."""
        return self.routes.get(task.value, self.config)

    def _fallback_for(self, cfg: LLMConfig, task: TaskType) -> LLMConfig | None:
        """A cloud fallback is offered only when leaving a *local* model on a hard step."""
        if self.fallback is None or task not in _FALLBACK_TASKS or not cfg.is_local:
            return None
        return self.fallback

    def _warn_crossing(self, primary: LLMConfig, fb: LLMConfig, reason: str) -> None:
        msg = (
            f"Router: {reason}; falling back from '{primary.model}' ({primary.provider}) "
            f"to '{fb.model}' ({fb.provider})."
        )
        if not fb.is_local:
            msg += " Your prompt and generated code are being sent to a cloud provider."
        self.warnings.append(msg)
        if self.console is not None:
            self.console.print(f"[yellow]⚠ {msg}[/]")
        else:
            warnings.warn(msg, stacklevel=2)

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
        try:
            response = self._chat_once(cfg, messages, tools, temperature, tool_choice)
        except LLMError:
            fb = self._fallback_for(cfg, task)
            if fb is None:
                raise
            self._warn_crossing(cfg, fb, "the primary model call failed")
            return self._chat_once(fb, messages, tools, temperature, tool_choice)

        # A tool-using step that came back with no tool call is a common local-model failure.
        if tools and not response.has_tool_calls:
            fb = self._fallback_for(cfg, task)
            if fb is not None:
                self._warn_crossing(cfg, fb, "the local model returned no tool call")
                return self._chat_once(fb, messages, tools, temperature, tool_choice)
        return response

    def _chat_once(
        self,
        cfg: LLMConfig,
        messages: list[Message],
        tools: list[Tool] | None,
        temperature: float | None,
        tool_choice: str | None,
    ) -> ChatResponse:
        if cfg.kind == "anthropic":
            url, headers, payload = anthropic.build_request(
                cfg, messages, tools, temperature, tool_choice
            )
            data = self._post(url, payload, headers, cfg.provider)
            return anthropic.parse_response(data, cfg.model)

        url = self._url(cfg)
        headers = self._headers(cfg)
        payload = self._build_payload(cfg, messages, tools, temperature, tool_choice)
        data = self._post(url, payload, headers, cfg.provider)
        return self._parse(data, cfg.model)

    def _post(self, url: str, payload: dict, headers: dict, provider: str) -> dict:
        try:
            poster = self._client.post if self._client is not None else httpx.post
            resp = poster(url, json=payload, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach the model at {url}. Is the provider '{provider}' running? ({exc})"
            ) from exc
        if resp.status_code >= 400:
            raise LLMError(
                f"Model endpoint {url} returned HTTP {resp.status_code}: {resp.text[:500]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise LLMError(f"Model endpoint {url} returned non-JSON: {resp.text[:200]}") from exc

    # -- OpenAI-compatible request/response ------------------------------------
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
        # Local runners need a large context window; only Ollama accepts options.num_ctx.
        # Sending it to a cloud OpenAI endpoint would 400, so we gate on the provider.
        if self._is_ollama(cfg):
            payload["options"] = {"num_ctx": cfg.num_ctx}
        return payload

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
