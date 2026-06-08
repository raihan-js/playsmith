"""The agentic loop: plan -> act (tool calls) -> observe -> iterate.

This is the heart of Playsmith (CLAUDE.md §4). The loop hands the model a goal plus the
tool schemas, executes the tool calls it returns, feeds the results back, and repeats
until the model calls ``task_complete``, stops emitting tool calls, or hits a cap.

The reality loop lives in the instructions: after changing code the model must run the
engine, read the logs/screenshot, and fix until it actually works.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from rich.console import Console

from playsmith.agent.tools import ToolContext, all_tools, execute, is_sentinel
from playsmith.engines.base import RunResult
from playsmith.llm import ChatResponse, Message, TaskType, Tool

DEFAULT_SYSTEM_PROMPT = """\
You are Playsmith, an agent that builds a REAL, EDITABLE game in Unreal Engine 5.

You work by calling tools. All file paths are relative to the game project. You can only
touch files inside the project workspace.

CLOSE THE LOOP ON REALITY. This is non-negotiable (CLAUDE.md §4):
- After changing the project, call run_engine and READ the logs. Do not guess that it works.
- If there are errors, FIX them and run again.
- Then call verify_game to check the gameplay assertions actually hold (e.g. the level loads,
  a PlayerStart and the player pawn exist, no errors). If any assertion FAILS, fix it and re-verify.
- Use read_file before editing so your patches match the real file.
- Only call task_complete once verify_game reports every assertion PASS.

Unreal correctness:
- Build ON the project's existing template/level — dress and tune it; do NOT rebuild from an
  empty scene. Maps and assets are binary (.umap/.uasset): author them via the editor, the UE
  Python API, or the Remote Control API — never by writing those files as text.
- Keep edits small; after each change, run_engine + verify_game.

Prefer small, verifiable steps. A runnable, playable slice beats an ambitious one that doesn't run.
"""


class ChatClient(Protocol):
    """The subset of the LLM Gateway the loop needs (so it is trivially mockable)."""

    def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        task: TaskType = TaskType.GENERAL,
        **kwargs,
    ) -> ChatResponse: ...


@dataclass
class AgentResult:
    done: bool
    reason: str
    iterations: int
    summary: str | None = None
    files_written: list[str] = field(default_factory=list)
    last_run: RunResult | None = None


class AgentLoop:
    def __init__(
        self,
        gateway: ChatClient,
        context: ToolContext,
        *,
        max_iterations: int = 24,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        console: Console | None = None,
        verbose: bool = True,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        self.gateway = gateway
        self.context = context
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.console = console or Console()
        self.verbose = verbose
        # Optional event sink (e.g. the web UI) — receives {type, ...} dicts as the loop runs.
        self.on_event = on_event

    def run(self, goal: str) -> AgentResult:
        messages: list[Message] = [
            Message.system(self.system_prompt),
            Message.user(goal),
        ]
        for iteration in range(1, self.max_iterations + 1):
            response = self.gateway.chat(messages, tools=all_tools(), task=TaskType.CODING)
            messages.append(response.to_assistant_message())

            if not response.has_tool_calls:
                # The model produced a final message with no action — treat as completion.
                self._say(f"[dim]agent finished after {iteration} iteration(s)[/]")
                return self._result(
                    done=True,
                    reason="model returned no tool calls",
                    iterations=iteration,
                    summary=response.content,
                )

            done_summary: str | None = None
            for call in response.tool_calls:
                self._announce(call.name, call.arguments)
                self._event({"type": "tool", "name": call.name, "args": call.arguments})
                result = execute(call, self.context)
                self._observe(result)
                self._event({"type": "observe", "name": call.name, "text": result})
                messages.append(Message.tool_result(call.id, result, name=call.name))
                if is_sentinel(call.name):
                    done_summary = result

            if done_summary is not None:
                return self._result(
                    done=True,
                    reason="task_complete",
                    iterations=iteration,
                    summary=done_summary,
                )

        return self._result(
            done=False,
            reason=f"hit max_iterations ({self.max_iterations})",
            iterations=self.max_iterations,
            summary=None,
        )

    # -- helpers ---------------------------------------------------------------
    def _result(self, **kwargs) -> AgentResult:
        return AgentResult(
            files_written=list(self.context.files_written),
            last_run=self.context.last_run,
            **kwargs,
        )

    def _announce(self, name: str, args: dict) -> None:
        if not self.verbose:
            return
        preview = ", ".join(f"{k}={self._short(v)}" for k, v in args.items())
        self.console.print(f"[cyan]→ {name}[/]({preview})")

    def _observe(self, result: str) -> None:
        if not self.verbose:
            return
        first = result.strip().splitlines()[0] if result.strip() else ""
        self.console.print(f"  [dim]{self._short(first, 160)}[/]")

    def _event(self, payload: dict) -> None:
        if self.on_event is not None:
            try:
                self.on_event(payload)
            except Exception:  # noqa: BLE001 - a broken sink must never break the agent
                pass

    def _say(self, message: str) -> None:
        if self.verbose:
            self.console.print(message)

    @staticmethod
    def _short(value, limit: int = 60) -> str:
        text = str(value).replace("\n", " ")
        return text if len(text) <= limit else text[: limit - 1] + "…"
