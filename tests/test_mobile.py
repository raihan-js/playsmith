"""Tests for mobile export helpers + guardrails (Android signing, iOS host check)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from playsmith.cli.main import app
from playsmith.publish import ensure_android_keystore, is_macos


def test_is_macos_returns_bool() -> None:
    assert isinstance(is_macos(), bool)


def test_keystore_generated_when_missing(tmp_path) -> None:
    ks = tmp_path / "debug.keystore"

    def fake_keytool(cmd, **kwargs):
        Path(cmd[cmd.index("-keystore") + 1]).write_bytes(b"KEYSTORE")  # keytool creates the file
        return subprocess.CompletedProcess(cmd, 0)

    assert ensure_android_keystore(ks, runner=fake_keytool)
    assert ks.exists()


def test_keystore_existing_does_not_reinvoke_keytool(tmp_path) -> None:
    ks = tmp_path / "k.keystore"
    ks.write_bytes(b"x")
    called = []

    def runner(cmd, **kwargs):  # pragma: no cover - must not be called
        called.append(1)
        return subprocess.CompletedProcess(cmd, 0)

    assert ensure_android_keystore(ks, runner=runner)
    assert not called


def test_keystore_false_when_keytool_missing(tmp_path) -> None:
    def runner(cmd, **kwargs):
        raise FileNotFoundError("keytool")

    assert not ensure_android_keystore(tmp_path / "k.keystore", runner=runner)


def test_cli_export_ios_requires_macos(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("playsmith.cli.main.is_macos", lambda: False)
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("x")
    result = CliRunner().invoke(app, ["export", "--target", "ios", "--project", str(project)])
    assert result.exit_code == 1
    assert "macOS" in result.output  # surfaced the requirement, never touched the engine
