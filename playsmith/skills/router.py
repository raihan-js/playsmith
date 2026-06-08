"""Route a user prompt to the best-matching skill.

Primary path: ask the LLM Gateway to pick by the skills' ``description`` fields (the
"pushy" trigger text). Fallback: a deterministic keyword overlap score, so routing still
works offline / when the model is flaky (and so tests don't need a live model).
"""

from __future__ import annotations

import re

from playsmith.llm import LLMError, LLMGateway, Message, TaskType
from playsmith.skills.loader import Skill, SkillLoader

# Words too common to carry routing signal.
_STOPWORDS = frozenset(
    """a an and the of to in on for with where that this game games make build create
    want like simple just any some my our your it its as at by or be is are runs run""".split()
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class SkillRouter:
    """Selects a :class:`Skill` for a prompt."""

    def __init__(
        self, loader: SkillLoader | None = None, gateway: LLMGateway | None = None
    ) -> None:
        self.loader = loader or SkillLoader()
        self.gateway = gateway

    def route(self, prompt: str) -> Skill | None:
        skills = self.loader.discover()
        if not skills:
            return None
        if len(skills) == 1:
            return skills[0]
        if self.gateway is not None:
            chosen = self._route_with_llm(prompt, skills)
            if chosen is not None:
                return chosen
        return self._route_with_keywords(prompt, skills)

    # -- LLM routing -----------------------------------------------------------
    def _route_with_llm(self, prompt: str, skills: list[Skill]) -> Skill | None:
        catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        names = ", ".join(s.name for s in skills)
        system = (
            "You route a game request to exactly one game-generation skill. "
            "Reply with ONLY the skill's name (one of the listed names) and nothing else. "
            "If none fit, reply 'none'."
        )
        user = f"Skills:\n{catalog}\n\nUser request: {prompt!r}\n\nBest skill ({names}, or none):"
        try:
            resp = self.gateway.chat(
                [Message.system(system), Message.user(user)],
                task=TaskType.ROUTING,
                temperature=0,
            )
        except LLMError:
            return None
        return self._match_name(resp.content or "", skills)

    @staticmethod
    def _match_name(reply: str, skills: list[Skill]) -> Skill | None:
        reply_l = reply.lower()
        # Prefer the longest matching name (avoids a substring of another name winning).
        for skill in sorted(skills, key=lambda s: len(s.name), reverse=True):
            if skill.name.lower() in reply_l:
                return skill
        return None

    # -- keyword fallback ------------------------------------------------------
    def _route_with_keywords(self, prompt: str, skills: list[Skill]) -> Skill | None:
        prompt_tokens = set(_tokens(prompt)) - _STOPWORDS
        best: Skill | None = None
        best_score = 0
        for skill in skills:
            vocab = (set(_tokens(skill.name)) | set(_tokens(skill.description))) - _STOPWORDS
            score = len(prompt_tokens & vocab)
            if score > best_score:
                best, best_score = skill, score
        return best if best_score > 0 else None
