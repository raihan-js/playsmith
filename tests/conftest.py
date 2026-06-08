"""Shared test doubles: a scripted gateway and a fake engine adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from playsmith.engines.base import RunResult, SceneSpec, VerifyResult
from playsmith.llm import ChatResponse, ToolCall


def text_response(content: str) -> ChatResponse:
    """A model turn with plain text and no tool calls (a natural stop)."""
    return ChatResponse(content=content, tool_calls=[], finish_reason="stop")


def tool_response(name: str, arguments: dict, *, call_id: str = "call_1") -> ChatResponse:
    """A model turn that calls a single tool."""
    return ChatResponse(
        content=None,
        tool_calls=[
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                raw_arguments=json.dumps(arguments),
            )
        ],
        finish_reason="tool_calls",
    )


class FakeGateway:
    """Replays a scripted list of ChatResponses and records the prompts it received."""

    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list] = []

    def chat(self, messages, tools=None, task=None, **kwargs) -> ChatResponse:
        self.calls.append(messages)
        if not self._responses:
            # If the script runs dry, end cleanly rather than looping forever.
            return text_response("(no more scripted responses)")
        return self._responses.pop(0)


@dataclass
class FakeAdapter:
    """An EngineAdapter stand-in: real file writes under project_dir, canned runs."""

    project_dir: Path
    run_results: list[RunResult] = field(default_factory=list)
    screenshot_result: RunResult | None = None
    verify_results: list[VerifyResult] = field(default_factory=list)
    runs: int = 0
    screenshots: int = 0
    verifies: int = 0

    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def version(self) -> str:
        return "Godot Engine v4.3.stable"

    def create_project(self, name: str, main_scene: str | None = None) -> None:
        (self.project_dir / "project.godot").write_text(f'config/name="{name}"\n')

    def set_main_scene(self, res_path: str) -> None:  # pragma: no cover - trivial
        pass

    def write_scene(self, scene: SceneSpec) -> Path:
        p = self.project_dir / scene.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(scene.content)
        return p

    def write_script(self, rel_path: str, code: str) -> Path:
        p = self.project_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)
        return p

    def run(self, *, headless: bool = True, timeout_s: int = 30, scene=None) -> RunResult:
        self.runs += 1
        if self.run_results:
            return self.run_results.pop(0)
        return RunResult(command=["godot"], returncode=0, stdout="ok")

    def screenshot(self, out_path: str, *, scene=None) -> RunResult:
        self.screenshots += 1
        Path(out_path).write_bytes(b"\x89PNG\r\n")  # pretend PNG
        return self.screenshot_result or RunResult(command=["godot"], returncode=0)

    def verify(self, checks=None, *, scene=None) -> VerifyResult:
        self.verifies += 1
        if self.verify_results:
            return self.verify_results.pop(0)
        passed = {c: True for c in (checks or ["no_errors"])}
        return VerifyResult(
            run=RunResult(command=["godot"], returncode=0, stdout="ok"), assertions=passed
        )
