"""Mobile export helpers (Phase 3) — Android signing + iOS host checks.

Mobile publishing is **guided, manual** (CLAUDE.md §8): Playsmith produces a signed build and
surfaces the store rules (Google "repetitive content", Apple 4.2.6/4.3), but the developer does
the actual submission. We never auto-submit, and never mass-submit near-identical games.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable
from pathlib import Path


def is_macos() -> bool:
    """iOS export requires macOS + Xcode (Apple's tooling is macOS-only)."""
    return platform.system() == "Darwin"


def ensure_android_keystore(
    keystore_path: str | Path,
    *,
    keytool: str = "keytool",
    alias: str = "playsmith",
    store_pass: str = "android",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Create a *debug* keystore via ``keytool`` if one doesn't exist. Returns True if present.

    A debug keystore is fine for testing; ship with your own release keystore. Returns False (with
    no exception) if ``keytool`` is unavailable, so the caller can surface guidance and continue.
    """
    path = Path(keystore_path).expanduser()
    if path.exists():
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        keytool, "-genkeypair", "-v",
        "-keystore", str(path),
        "-alias", alias,
        "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
        "-storepass", store_pass, "-keypass", store_pass,
        "-dname", "CN=Playsmith, OU=Dev, O=Playsmith, L=NA, S=NA, C=US",
    ]  # fmt: skip
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return path.exists() and result.returncode == 0
