"""Tests for the skill marketplace — focused on security (integrity, trust, no-exec)."""

from __future__ import annotations

import hashlib
import json

import pytest
from typer.testing import CliRunner

from playsmith.cli.main import app
from playsmith.skills import SkillLoader, SkillRegistry, SkillRegistryError, validate_skillpack


def _skillpack(name, *, assertions=("no_errors",), scripts=None, description="a test skill"):
    md = (
        f"---\nname: {name}\ndescription: {description}\nassertions:\n"
        + "".join(f"  - {a}\n" for a in assertions)
        + "---\n\n# "
        + name
        + "\n\nbody\n"
    )
    return {"name": name, "version": "1.0.0", "skill_md": md, "scripts": scripts or {}}


def _write_registry(tmp_path, packs):
    """packs: list of (pack_dict, trusted). Returns the index path. Checksums are computed."""
    entries = []
    for pack, trusted in packs:
        raw = json.dumps(pack)
        pack_path = tmp_path / f"{pack['name']}.json"
        pack_path.write_text(raw)
        entries.append(
            {
                "name": pack["name"],
                "description": pack["skill_md"][:30],
                "url": str(pack_path),
                "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "trusted": trusted,
                "author": "tester",
                "version": "1.0.0",
            }
        )
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"skills": entries}))
    return index


def _registry(tmp_path, packs):
    return SkillRegistry(str(_write_registry(tmp_path, packs)), tmp_path / "install")


# -- validation ------------------------------------------------------------------
def test_validate_rejects_unknown_assertions() -> None:
    errors = validate_skillpack(_skillpack("x", assertions=["does_not_exist"]))
    assert any("unknown assertions" in e for e in errors)


def test_validate_accepts_good_pack() -> None:
    assert validate_skillpack(_skillpack("x", assertions=["player_on_floor", "no_errors"])) == []


# -- install: integrity + trust --------------------------------------------------
def test_install_validates_writes_files_and_provenance(tmp_path) -> None:
    reg = _registry(
        tmp_path,
        [
            (
                _skillpack(
                    "top-down-rpg", assertions=["player_exists"], scripts={"rpg.gd": "extends Node"}
                ),
                True,
            )
        ],
    )
    skill = reg.install("top-down-rpg")
    assert skill.name == "top-down-rpg" and skill.trusted
    inst = tmp_path / "install" / "top-down-rpg"
    assert (inst / "SKILL.md").exists()
    assert (inst / "scripts" / "rpg.gd").read_text() == "extends Node"
    assert json.loads((inst / ".provenance.json").read_text())["trusted"] is True


def test_install_refuses_on_checksum_mismatch(tmp_path) -> None:
    pack = _skillpack("x")
    pack_path = tmp_path / "x.json"
    pack_path.write_text(json.dumps(pack))
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "skills": [
                    {"name": "x", "url": str(pack_path), "sha256": "deadbeef", "trusted": True}
                ]
            }
        )
    )
    reg = SkillRegistry(str(index), tmp_path / "install")
    with pytest.raises(SkillRegistryError, match="Checksum mismatch"):
        reg.install("x")
    assert not (tmp_path / "install" / "x").exists()  # nothing written on refusal


def test_install_rejects_invalid_schema(tmp_path) -> None:
    reg = _registry(tmp_path, [(_skillpack("bad", assertions=["totally_made_up"]), True)])
    with pytest.raises(SkillRegistryError, match="validation"):
        reg.install("bad")


def test_untrusted_requires_explicit_optin(tmp_path) -> None:
    reg = _registry(tmp_path, [(_skillpack("sketchy"), False)])
    with pytest.raises(SkillRegistryError, match="UNTRUSTED"):
        reg.install("sketchy")
    skill = reg.install("sketchy", allow_untrusted=True)
    assert not skill.trusted
    # The loader independently sees it as untrusted via provenance.
    loaded = SkillLoader([tmp_path / "install"]).get("sketchy")
    assert loaded is not None and not loaded.trusted


def test_install_never_executes_bundled_scripts(tmp_path) -> None:
    # A "malicious" script must land as inert text — never run during install.
    sentinel = tmp_path / "pwned"
    script = f'extends Node\nfunc _init():\n\tOS.execute("touch", ["{sentinel}"])\n'
    reg = _registry(tmp_path, [(_skillpack("evil", scripts={"evil.gd": script}), True)])
    reg.install("evil")
    assert (tmp_path / "install" / "evil" / "scripts" / "evil.gd").read_text() == script
    assert not sentinel.exists()  # the registry executed nothing


def test_install_strips_path_traversal_in_script_names(tmp_path) -> None:
    reg = _registry(tmp_path, [(_skillpack("trav", scripts={"../../escape.gd": "x"}), True)])
    reg.install("trav")
    assert (tmp_path / "install" / "trav" / "scripts" / "escape.gd").exists()
    assert not (tmp_path / "escape.gd").exists()  # did not escape the install dir


# -- search / remove -------------------------------------------------------------
def test_search_filters_index(tmp_path) -> None:
    reg = _registry(
        tmp_path,
        [(_skillpack("tower-defense"), True), (_skillpack("match-3"), True)],
    )
    assert {e.name for e in reg.search("tower")} == {"tower-defense"}
    assert len(reg.search("")) == 2


def test_remove_only_touches_install_dir(tmp_path) -> None:
    reg = _registry(tmp_path, [(_skillpack("temp"), True)])
    reg.install("temp")
    assert reg.remove("temp")
    assert not (tmp_path / "install" / "temp").exists()
    assert not reg.remove("temp")  # already gone
    assert not reg.remove("../../etc")  # traversal refused


# -- CLI wiring ------------------------------------------------------------------
def test_cli_install_via_local_index(tmp_path) -> None:
    index = _write_registry(tmp_path, [(_skillpack("tower-defense"), True)])
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(f"skills:\n  registry_url: {index}\n  dir: {tmp_path / 'install'}\n")
    result = CliRunner().invoke(app, ["skills", "install", "tower-defense", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "install" / "tower-defense" / "SKILL.md").exists()
