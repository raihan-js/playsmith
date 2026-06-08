"""Router maturity — measure a provider's tool-call reliability per task.

The router (Phase 1) falls back local -> cloud on hard steps. This harness turns the ~80%
heuristic in docs/ARCHITECTURE.md §1 into a measurement: run a few fixtures that SHOULD elicit a
specific tool call, count how often the provider actually produces it, and recommend whether to
trust it locally or route hard steps to the cloud fallback.

We evaluate a single provider directly (``gateway._chat_once``) so the gateway's own fallback
does not mask the provider's true reliability.
"""

from __future__ import annotations

from dataclasses import dataclass

from playsmith.config import LLMConfig
from playsmith.llm.gateway import LLMError, LLMGateway
from playsmith.llm.types import Message, TaskType, Tool

_WRITE = Tool(
    "write_file",
    "Write a file.",
    {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
)
_READ = Tool(
    "read_file",
    "Read a file.",
    {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)

# (prompt, tool offered, expected tool name). Small, deterministic, tool-eliciting.
DEFAULT_FIXTURES: list[tuple[str, Tool, str]] = [
    (
        "Create a file hello.gd containing print('hi'). Use the write_file tool.",
        _WRITE,
        "write_file",
    ),
    ("Read the file project.godot. Use the read_file tool.", _READ, "read_file"),
    ("Write player.gd extending CharacterBody2D. Use write_file.", _WRITE, "write_file"),
    ("Read scripts/player.gd with read_file.", _READ, "read_file"),
]

_EVAL_SYSTEM = "You build games by calling tools. When asked, respond with the requested tool call."


@dataclass
class EvalResult:
    provider: str
    model: str
    is_local: bool
    trials: int
    successes: int
    threshold: float

    @property
    def reliability(self) -> float:
        return self.successes / self.trials if self.trials else 0.0

    @property
    def meets_threshold(self) -> bool:
        return self.reliability >= self.threshold

    @property
    def recommendation(self) -> str:
        if not self.is_local:
            return "cloud provider"
        if self.meets_threshold:
            return "local is reliable for tool calls"
        return "route hard (coding/reasoning) steps to the cloud fallback"


def evaluate_provider(
    gateway: LLMGateway,
    cfg: LLMConfig,
    *,
    fixtures: list[tuple[str, Tool, str]] | None = None,
    threshold: float = 0.8,
) -> EvalResult:
    """Measure how reliably ``cfg`` produces the expected tool call across the fixtures."""
    fixtures = fixtures or DEFAULT_FIXTURES
    successes = 0
    for prompt, tool, expected in fixtures:
        messages = [Message.system(_EVAL_SYSTEM), Message.user(prompt)]
        try:
            resp = gateway._chat_once(cfg, messages, [tool], 0.0, None)
        except LLMError:
            continue  # a failed call counts as unreliable
        if resp.has_tool_calls and any(tc.name == expected for tc in resp.tool_calls):
            successes += 1
    return EvalResult(
        provider=cfg.provider,
        model=cfg.model,
        is_local=cfg.is_local,
        trials=len(fixtures),
        successes=successes,
        threshold=threshold,
    )


def evaluate_targets(
    gateway: LLMGateway,
    targets: list[tuple[str, LLMConfig]],
    *,
    threshold: float = 0.8,
) -> list[tuple[str, EvalResult]]:
    """Evaluate several labelled providers (default + routes + fallback)."""
    out: list[tuple[str, EvalResult]] = []
    for label, cfg in targets:
        out.append((label, evaluate_provider(gateway, cfg, threshold=threshold)))
    return out


# TaskType is part of the routing vocabulary the eval informs; re-exported for callers.
__all__ = ["DEFAULT_FIXTURES", "EvalResult", "TaskType", "evaluate_provider", "evaluate_targets"]
