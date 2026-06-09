"""The director→critic refine loop — iterate a dressing until it clears the quality bar.

This is the "automated agent in the background" (CLAUDE.md §0 Stage 3/4): plan a dressing, apply
it in-engine, have the critic score the *result*, and — if it's below the bar and iterations
remain — feed the critique back to the director for a richer pass, then re-apply and re-score.

The loop is pure orchestration over **injected callables** (``plan``/``apply``/``critique``/
``improve``), so it runs the same way from the CLI, from the web (streaming each step over the
socket), and from tests (with fakes) — nothing here touches Unreal directly. Each step emits a
structured event via ``on_event`` so a UI can show the agent working iteration by iteration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from playsmith.engines.unreal.critic import Critique

# A step's event, e.g. {"kind": "critiqued", "iter": 2, "score": 78, ...}.
Event = dict
OnEvent = Callable[[Event], None]


@dataclass
class RefineResult:
    """The outcome of a refine run: the final dressing, its critique, and per-iteration history."""

    spec: dict
    critique: Critique | None
    iterations: int
    history: list[Critique] = field(default_factory=list)


def refine(
    *,
    plan: Callable[[], dict],
    apply: Callable[[dict], dict | None],
    critique: Callable[[dict, dict | None], Critique],
    improve: Callable[[dict, Critique], dict],
    max_iters: int = 3,
    on_event: OnEvent | None = None,
) -> RefineResult:
    """Run plan → (apply → critique → improve)* until the critique passes or iterations run out.

    ``apply`` returns the engine's ``PLAYSMITH_ASSERT`` results (or ``None``); ``critique`` scores
    the spec against them; ``improve`` returns a richer spec for the next pass. Stops early the
    moment a critique passes. Always returns the best (latest) spec — never raises for an empty run.
    """
    emit = on_event or (lambda _ev: None)
    max_iters = max(1, int(max_iters))

    spec = plan()
    emit({"kind": "planned", "objects": len(spec.get("placements") or [])})

    history: list[Critique] = []
    final: Critique | None = None
    iterations = 0
    for i in range(1, max_iters + 1):
        iterations = i
        assertions = apply(spec)
        emit({"kind": "applied", "iter": i, "assertions": assertions or {}})

        crit = critique(spec, assertions)
        history.append(crit)
        final = crit
        emit(
            {
                "kind": "critiqued",
                "iter": i,
                "score": crit.score,
                "passed": crit.passed,
                "feedback": crit.feedback,
                "dimensions": crit.dimensions,
                "summary": crit.summary,
            }
        )
        if crit.passed or i == max_iters:
            break

        emit({"kind": "improving", "iter": i})
        spec = improve(spec, crit)

    return RefineResult(spec=spec, critique=final, iterations=iterations, history=history)
