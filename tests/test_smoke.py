"""Trivial smoke tests: the package imports and the CLI is wired."""

from __future__ import annotations

import playsmith
from playsmith.cli.main import app, main


def test_version_is_a_string() -> None:
    assert isinstance(playsmith.__version__, str)
    assert playsmith.__version__


def test_cli_app_exists() -> None:
    assert app is not None
    assert callable(main)
