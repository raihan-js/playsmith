"""Compliance helpers — disclosures and policy briefings (Phase 3).

"Compliance as a feature": Playsmith helps a user ship *a* polished game with the right
disclosures, and surfaces the rules. It never helps mass-submit near-identical games or defeat
store review (CLAUDE.md §8). The Phase-3 ``publish --check`` command (Step 5) consolidates these.
"""

from __future__ import annotations

# Purely AI-generated assets have limited copyright protection (US Copyright Office, 2025).
AI_ASSET_COPYRIGHT_CAVEAT = (
    "Purely AI-generated assets have limited copyright protection (US Copyright Office, 2025). "
    "Add meaningful human authorship/editing to strengthen any claim."
)

# Apple App Store guidelines that matter for generated games.
APPLE_4_2_6 = (
    "Apple Guideline 4.2.6: apps created from a commercialized template or app-generation service "
    "are rejected unless submitted directly by the provider of the content. Submit your own game."
)
APPLE_4_3 = "Apple Guideline 4.3: spam / many similar apps are rejected. Ship one distinct game."

# Google Play policy.
GOOGLE_REPETITIVE = (
    "Google Play prohibits repetitive content: do not publish many near-identical games. "
    "Submit a single, distinct, polished game."
)

NO_MASS_SUBMIT = (
    "Ship ONE distinct, polished game. Never mass-submit near-identical games — stores reject it "
    "and it harms users (CLAUDE.md §8)."
)


def compliance_briefing(target: str = "all", *, used_unreal: bool = False) -> list[str]:
    """Return the policy notes that apply to a given publish target (advisory only)."""
    t = target.lower()
    notes: list[str] = []

    def add(note: str) -> None:
        if note not in notes:
            notes.append(note)

    if t in ("steam", "all"):
        add(steam_ai_disclosure())
    if t in ("apple", "ios", "all"):
        add(APPLE_4_2_6)
        add(APPLE_4_3)
    if t in ("google", "android", "all"):
        add(GOOGLE_REPETITIVE)
    if t in ("itch", "web", "all"):
        add("itch.io is lenient, but disclose AI-generated player-facing art on your page.")
    if used_unreal:
        add("Unreal royalties may apply — run `playsmith unreal royalty <gross>`.")
    add(AI_ASSET_COPYRIGHT_CAVEAT)
    add(NO_MASS_SUBMIT)
    return notes


_RATING_BANDS = {
    0: "Everyone (3+)",
    1: "Everyone 10+ (7+)",
    2: "Teen (12+)",
    3: "Mature (17+)",
}


def age_rating(
    *,
    violence: int = 0,
    language: int = 0,
    sexual_content: int = 0,
    fear: int = 0,
    gambling: bool = False,
    controlled_substances: bool = False,
) -> dict:
    """A rough IARC-style age-rating draft from 0–3 severities + flags.

    Advisory only — submit the official IARC questionnaire on each store for a binding rating.
    """
    score = max(violence, language, sexual_content, fear)
    if gambling or controlled_substances:
        score = max(score, 2)
    descriptors: list[str] = []
    if violence >= 2:
        descriptors.append("Violence")
    if language >= 2:
        descriptors.append("Strong Language")
    if sexual_content >= 2:
        descriptors.append("Sexual Content")
    if fear >= 2:
        descriptors.append("Fear")
    if gambling:
        descriptors.append("Simulated Gambling")
    if controlled_substances:
        descriptors.append("Use of Alcohol/Drugs")
    return {
        "rating": _RATING_BANDS[min(score, 3)],
        "descriptors": descriptors,
        "note": "Draft only — submit the official IARC questionnaire on each store to be binding.",
    }


def steam_ai_disclosure(
    *,
    pre_generated: list[str] | None = None,
    live_generated: list[str] | None = None,
    uses_code_assistant: bool = True,
) -> str:
    """Generate a Steam AI-content disclosure (per Valve's Jan-2026 policy rewrite).

    Player-facing AI-generated content (art/audio/text) must be disclosed, split into
    *pre-generated* (made during development) and *live-generated* (created at runtime, which has
    extra anti-abuse guardrail requirements). AI **development tools** like code assistants are
    **exempt** and need no disclosure.
    """
    pre = pre_generated or []
    live = live_generated or []
    lines = ["Steam AI-content disclosure:"]
    if not pre and not live:
        lines.append("  • No player-facing AI-generated content in this build.")
    if pre:
        lines.append("  • Pre-generated (made during development with AI): " + ", ".join(pre))
    if live:
        lines.append(
            "  • Live-generated (created at runtime): "
            + ", ".join(live)
            + " — you must guard against illegal/infringing live output."
        )
    if uses_code_assistant:
        lines.append(
            "  • AI coding assistants used to build the game are EXEMPT and need no disclosure "
            "(Valve, Jan 2026)."
        )
    return "\n".join(lines)
