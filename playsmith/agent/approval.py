"""Diff approval — the human stays in the loop for every file write (CLAUDE.md §5).

The agent proposes a change; an :class:`Approver` decides whether it hits disk. ``--yes``
swaps in :class:`AutoApprover`. Read-only and engine-run actions don't need approval.
"""

from __future__ import annotations

import difflib
from typing import Protocol

from rich.console import Console
from rich.syntax import Syntax


def make_diff(path: str, old: str, new: str) -> str:
    """A unified diff between old and new content for a path."""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


class Approver(Protocol):
    """Decides whether a proposed file change should be applied."""

    def approve(self, path: str, diff: str) -> bool: ...


class AutoApprover:
    """Approves everything (the ``--yes`` flag)."""

    def approve(self, path: str, diff: str) -> bool:  # noqa: D102
        return True


class DenyApprover:
    """Rejects everything (useful in tests / dry runs)."""

    def approve(self, path: str, diff: str) -> bool:  # noqa: D102
        return False


class InteractiveApprover:
    """Shows the diff and asks the user to approve it."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def approve(self, path: str, diff: str) -> bool:
        self.console.print(f"\n[bold]Proposed change to[/] [cyan]{path}[/]:")
        if diff.strip():
            self.console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
        else:
            self.console.print("[dim](no textual diff — new or binary file)[/]")
        answer = self.console.input("[bold yellow]Apply this change? [y/N] [/]").strip().lower()
        return answer in ("y", "yes")
