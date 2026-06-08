"""Shared publish types."""

from __future__ import annotations

from dataclasses import dataclass


class PublishError(Exception):
    """A recoverable publishing failure (missing tool, failed export/push, bad target)."""


@dataclass
class PublishResult:
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def logs(self) -> str:
        return "\n".join(p for p in (self.stdout, self.stderr) if p)
