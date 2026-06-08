"""Tests for itch.io publishing via butler (subprocess + adapter mocked)."""

from __future__ import annotations

import subprocess

import pytest
from typer.testing import CliRunner

from playsmith.cli.main import app
from playsmith.publish import ItchPublisher, PublishError, PublishResult, publish_itch
from playsmith.publish import itch as itch_mod
from tests.conftest import FakeAdapter


class _FakePublisher:
    def __init__(self, *, available: bool = True, ok: bool = True) -> None:
        self._available = available
        self._ok = ok
        self.pushed = None

    def available(self) -> bool:
        return self._available

    def push(self, build_dir, target, *, channel="web") -> PublishResult:
        self.pushed = (build_dir, target, channel)
        return PublishResult(["butler", "push"], 0 if self._ok else 1, stdout="pushed")


# -- ItchPublisher (butler subprocess mocked) ------------------------------------
def test_available_true(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "butler v15")
    )
    assert ItchPublisher().available()


def test_available_false_when_missing(monkeypatch) -> None:
    def boom(*a, **k):
        raise FileNotFoundError("butler")

    monkeypatch.setattr(subprocess, "run", boom)
    assert not ItchPublisher().available()


def test_push_builds_butler_command(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="pushed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = ItchPublisher().push(tmp_path / "build", "me/game", channel="web")
    assert res.ok
    assert captured["cmd"] == ["butler", "push", str(tmp_path / "build"), "me/game:web"]


# -- publish_itch orchestration --------------------------------------------------
def test_publish_itch_exports_then_pushes(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    pub = _FakePublisher()
    result = publish_itch(adapter.project_dir, "me/mygame", adapter=adapter, publisher=pub)
    assert result.ok
    # A web build was produced and handed to butler.
    assert (adapter.project_dir / "build" / "index.html").exists()
    assert pub.pushed[1] == "me/mygame"
    assert pub.pushed[2] == "web"


def test_publish_itch_missing_butler_raises(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    with pytest.raises(PublishError, match="butler not found"):
        publish_itch(
            adapter.project_dir, "me/g", adapter=adapter, publisher=_FakePublisher(available=False)
        )


def test_publish_itch_rejects_bad_target(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    with pytest.raises(PublishError, match="user/game"):
        publish_itch(adapter.project_dir, "no-slash", adapter=adapter, publisher=_FakePublisher())


def test_publish_itch_push_failure_raises(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    with pytest.raises(PublishError, match="butler push failed"):
        publish_itch(
            adapter.project_dir, "me/g", adapter=adapter, publisher=_FakePublisher(ok=False)
        )


def test_compliance_note_surfaces_disclosure() -> None:
    note = itch_mod.itch_compliance_note()
    assert "AI-generated" in note
    assert "mass-submit" in note


def test_cli_publish_requires_target() -> None:
    result = CliRunner().invoke(app, ["publish"])
    assert result.exit_code == 1
