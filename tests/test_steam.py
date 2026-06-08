"""Tests for Steam publishing + the AI-content disclosure (subprocess mocked)."""

from __future__ import annotations

import subprocess

import pytest

from playsmith.publish import (
    PublishError,
    PublishResult,
    SteamPublisher,
    build_app_vdf,
    publish_steam,
    steam_ai_disclosure,
)
from tests.conftest import FakeAdapter


class _FakeSteam:
    def __init__(self, *, available=True, ok=True) -> None:
        self._available = available
        self._ok = ok
        self.pushed = None

    def available(self) -> bool:
        return self._available

    def push(self, vdf_path, *, account=None) -> PublishResult:
        self.pushed = vdf_path
        return PublishResult(["steamcmd"], 0 if self._ok else 1, stdout="uploaded")


# -- AI disclosure ---------------------------------------------------------------
def test_disclosure_exempts_code_assistant() -> None:
    note = steam_ai_disclosure(uses_code_assistant=True)
    assert "EXEMPT" in note
    assert "No player-facing AI-generated content" in note


def test_disclosure_lists_generated_assets() -> None:
    note = steam_ai_disclosure(pre_generated=["sprites"], live_generated=["dialogue"])
    assert "Pre-generated" in note and "sprites" in note
    assert "Live-generated" in note and "dialogue" in note


# -- VDF -------------------------------------------------------------------------
def test_build_app_vdf_sets_branch_not_live() -> None:
    vdf = build_app_vdf("480", "481", __import__("pathlib").Path("/content"), branch="beta")
    assert '"appid" "480"' in vdf
    assert '"481"' in vdf
    assert '"setlive" "beta"' in vdf  # never the default/live branch


# -- orchestration ---------------------------------------------------------------
def test_publish_steam_exports_writes_vdf_and_uploads(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    pub = _FakeSteam()
    result = publish_steam(adapter.project_dir, "480", adapter=adapter, publisher=pub, account="me")
    assert result.ok
    assert (adapter.project_dir / "build" / "steam" / "game.exe").exists()  # windows export
    assert (adapter.project_dir / "build" / "app_build_480.vdf").exists()
    assert pub.pushed is not None


def test_publish_steam_refuses_live_branch(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    with pytest.raises(PublishError, match="default/live"):
        publish_steam(
            adapter.project_dir, "480", branch="default", adapter=adapter, publisher=_FakeSteam()
        )


def test_publish_steam_missing_steamcmd(tmp_path) -> None:
    adapter = FakeAdapter(tmp_path / "game")
    with pytest.raises(PublishError, match="steamcmd not found"):
        publish_steam(
            adapter.project_dir, "480", adapter=adapter, publisher=_FakeSteam(available=False)
        )


def test_steam_publisher_available_false_when_missing(monkeypatch) -> None:
    def boom(*a, **k):
        raise FileNotFoundError("steamcmd")

    monkeypatch.setattr(subprocess, "run", boom)
    assert not SteamPublisher().available()


def test_steam_publisher_push_requires_account() -> None:
    with pytest.raises(PublishError, match="No Steam account"):
        SteamPublisher().push(__import__("pathlib").Path("/x.vdf"))
