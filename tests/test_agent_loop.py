"""Tests for the agent loop, tools, and approval — gateway and engine mocked."""

from __future__ import annotations

from playsmith.agent import AgentLoop, AutoApprover, DenyApprover, ToolContext
from playsmith.engines.base import RunResult
from tests.conftest import FakeAdapter, FakeGateway, text_response, tool_response


def _loop(tmp_path, responses, approver=None, **kwargs):
    adapter = FakeAdapter(tmp_path / "game", **kwargs)
    ctx = ToolContext(adapter=adapter, approver=approver or AutoApprover())
    loop = AgentLoop(FakeGateway(responses), ctx, verbose=False)
    return loop, ctx, adapter


def test_write_run_then_complete(tmp_path) -> None:
    loop, ctx, adapter = _loop(
        tmp_path,
        [
            tool_response("write_file", {"path": "hello.gd", "content": "print('hi')\n"}),
            tool_response("run_engine", {"headless": True}),
            tool_response("task_complete", {"summary": "Built and verified."}),
        ],
    )
    result = loop.run("make a hello script and run it")

    assert result.done
    assert result.reason == "task_complete"
    assert "hello.gd" in result.files_written
    assert (adapter.project_dir / "hello.gd").read_text() == "print('hi')\n"
    assert adapter.runs == 1  # it actually ran the engine (closed the loop)


def test_denied_write_is_not_applied(tmp_path) -> None:
    loop, ctx, adapter = _loop(
        tmp_path,
        [
            tool_response("write_file", {"path": "a.gd", "content": "x"}),
            text_response("Understood, I won't write it."),
        ],
        approver=DenyApprover(),
    )
    result = loop.run("write a file")
    assert not (adapter.project_dir / "a.gd").exists()
    assert result.files_written == []
    assert result.done  # ended via the natural-stop text turn


def test_path_escape_is_blocked(tmp_path) -> None:
    loop, ctx, adapter = _loop(
        tmp_path,
        [
            tool_response("write_file", {"path": "../escape.gd", "content": "x"}),
            text_response("ok"),
        ],
    )
    loop.run("try to escape")
    assert not (tmp_path / "escape.gd").exists()


def test_reality_loop_self_corrects_on_error(tmp_path) -> None:
    # First run reports a parse error; the agent patches and the second run is clean.
    bad = RunResult(command=["godot"], returncode=0, stderr="SCRIPT ERROR: Parse Error")
    good = RunResult(command=["godot"], returncode=0, stdout="clean")
    loop, ctx, adapter = _loop(
        tmp_path,
        [
            tool_response("write_file", {"path": "p.gd", "content": "extends Node\nbroken"}),
            tool_response("run_engine", {}),  # -> error
            tool_response(
                "apply_patch", {"path": "p.gd", "find": "broken", "replace": "func _ready(): pass"}
            ),
            tool_response("run_engine", {}),  # -> clean
            tool_response("task_complete", {"summary": "Fixed and verified."}),
        ],
        run_results=[bad, good],
    )
    result = loop.run("build and verify")
    assert result.done
    assert adapter.runs == 2
    assert "func _ready" in (adapter.project_dir / "p.gd").read_text()


def test_verify_game_drives_fix_until_assertions_pass(tmp_path) -> None:
    from playsmith.engines.base import VerifyResult

    bad = VerifyResult(
        run=RunResult(command=["g"], returncode=0),
        assertions={"player_on_floor": False, "no_errors": True},
    )
    good = VerifyResult(
        run=RunResult(command=["g"], returncode=0),
        assertions={"player_on_floor": True, "no_errors": True},
    )
    loop, ctx, adapter = _loop(
        tmp_path,
        [
            tool_response("write_file", {"path": "Main.tscn", "content": "[gd_scene format=3]\n"}),
            tool_response("verify_game", {}),  # player_on_floor FAILS
            tool_response(
                "apply_patch", {"path": "Main.tscn", "find": "format=3", "replace": "format=3 "}
            ),
            tool_response("verify_game", {}),  # passes
            tool_response("task_complete", {"summary": "verified"}),
        ],
        verify_results=[bad, good],
    )
    result = loop.run("build and verify the platformer")
    assert result.done
    assert adapter.verifies == 2  # it re-verified after fixing
    assert ctx.last_verify is not None and ctx.last_verify.ok


def test_apply_patch_requires_unique_find(tmp_path) -> None:
    loop, ctx, adapter = _loop(tmp_path, [text_response("done")])
    (adapter.project_dir / "d.gd").write_text("aa")
    from playsmith.agent.tools import execute
    from playsmith.llm import ToolCall

    call = ToolCall(
        id="1", name="apply_patch", arguments={"path": "d.gd", "find": "a", "replace": "b"}
    )
    msg = execute(call, ctx)
    assert "appears 2 times" in msg


def test_max_iterations_cap(tmp_path) -> None:
    # The model keeps calling read_file forever; the cap must stop it.
    responses = [tool_response("read_file", {"path": "project.godot"}) for _ in range(100)]
    adapter = FakeAdapter(tmp_path / "game")
    (adapter.project_dir / "project.godot").write_text("x")
    ctx = ToolContext(adapter=adapter, approver=AutoApprover())
    loop = AgentLoop(FakeGateway(responses), ctx, max_iterations=5, verbose=False)
    result = loop.run("loop forever")
    assert not result.done
    assert "max_iterations" in result.reason
    assert result.iterations == 5
