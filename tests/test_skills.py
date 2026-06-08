"""Tests for the skills loader and router."""

from __future__ import annotations

import httpx

from playsmith.config import LLMConfig
from playsmith.llm import LLMGateway
from playsmith.skills import SkillLoader, SkillRouter, parse_frontmatter


def _make_skill(root, name, description, body="Do the thing.", script=None):
    d = root / name
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n# {name}\n\n{body}\n"
    )
    if script:
        (d / "scripts" / script[0]).write_text(script[1])
    return d


# -- frontmatter + progressive disclosure ----------------------------------------
def test_parse_frontmatter_splits_meta_and_body() -> None:
    meta, body = parse_frontmatter("---\nname: x\ndescription: hi\n---\n\nBody text\n")
    assert meta == {"name": "x", "description": "hi"}
    assert body.strip() == "Body text"


def test_loader_discovers_synthetic_skill(tmp_path) -> None:
    # The loader parses metadata eagerly; body/scripts load lazily on demand.
    _make_skill(
        tmp_path,
        "third-person",
        "an over-the-shoulder third-person Unreal game",
        body="BUILD AND VERIFY the level.",
        script=("notes.txt", "movement constants"),
    )
    skills = SkillLoader([tmp_path]).discover()
    assert {s.name for s in skills} == {"third-person"}
    skill = next(s for s in skills if s.name == "third-person")
    assert "BUILD AND VERIFY" in skill.body()
    assert "notes.txt" in skill.scripts()
    assert "movement constants" in skill.read_script("notes.txt")


def test_loader_skips_dirs_without_name(tmp_path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "SKILL.md").write_text("---\ndescription: no name\n---\nbody")
    assert SkillLoader([tmp_path]).discover() == []


# -- routing ---------------------------------------------------------------------
def test_router_single_skill_shortcut(tmp_path) -> None:
    _make_skill(tmp_path, "only-one", "the only skill")
    router = SkillRouter(SkillLoader([tmp_path]))
    assert router.route("anything at all").name == "only-one"


def test_keyword_fallback_picks_best_match(tmp_path) -> None:
    _make_skill(tmp_path, "2d-platformer", "a jump-and-run side-scroller platformer")
    _make_skill(tmp_path, "match-3", "a tile-swapping match three puzzle game")
    router = SkillRouter(SkillLoader([tmp_path]))  # no gateway -> keyword path
    assert router.route("a jump-and-run game with a fox").name == "2d-platformer"
    assert router.route("a swapping tile puzzle").name == "match-3"


def test_llm_routing_with_mocked_gateway(tmp_path) -> None:
    _make_skill(tmp_path, "2d-platformer", "side-scroller platformer")
    _make_skill(tmp_path, "tower-defense", "place towers to stop waves")

    def handler(request: httpx.Request) -> httpx.Response:
        # The model replies (chattily) with the chosen skill name.
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "I think tower-defense fits best."}}]},
        )

    gw = LLMGateway(LLMConfig(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    router = SkillRouter(SkillLoader([tmp_path]), gateway=gw)
    assert router.route("a game where I defend a base from monsters").name == "tower-defense"


def test_llm_failure_falls_back_to_keywords(tmp_path) -> None:
    _make_skill(tmp_path, "2d-platformer", "jump-and-run platformer")
    _make_skill(tmp_path, "match-3", "match three puzzle")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model down")

    gw = LLMGateway(LLMConfig(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    router = SkillRouter(SkillLoader([tmp_path]), gateway=gw)
    # LLM errors -> keyword fallback still routes correctly.
    assert router.route("a jump-and-run platformer with a cat").name == "2d-platformer"


def test_no_skills_returns_none(tmp_path) -> None:
    assert SkillRouter(SkillLoader([tmp_path])).route("anything") is None
