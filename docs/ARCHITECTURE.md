# Architecture

This document describes how Playsmith is structured and the interfaces between its parts.
It is the technical companion to `CLAUDE.md`. When you change a module boundary or an
interface here, update `CLAUDE.md` §3 too.

## Design principles

1. **One agent, many tools.** Playsmith is fundamentally an agentic loop that calls tools.
   Engines and asset generators are tools behind clean interfaces.
2. **Abstract the engine.** Nothing outside `playsmith/engines/<engine>/` knows engine
   specifics. Skills and the agent loop talk to an `EngineAdapter`.
3. **Abstract the model.** Nothing outside `playsmith/llm/` knows which provider is in use.
   Everything is the OpenAI-compatible `/v1` shape.
4. **Close the loop on reality.** The agent runs the game, sees the result, and corrects.
5. **Optional things are optional.** Asset generation and publishing must degrade gracefully
   (placeholders; local-only build) so the core path always works offline.

## Component map

```
playsmith/
├── llm/        LLM Gateway + model router        (the "brain access")
├── agent/      Agentic loop, tools, diff approval (the "hands")
├── engines/    EngineAdapter + godot/ (+ unreal/) (the "workshop")
├── assets/     Image/3D generation clients        (the "art studio") [optional]
├── skills/     SKILL.md loader, progressive disclosure (the "playbooks")
├── publish/    Export + itch/steam/mobile + compliance (the "shipping dock")
└── cli/        Typer/Rich entrypoints             (the "front desk")
```

---

## 1. LLM Gateway — `playsmith/llm/`

**Job:** give the rest of the app one way to talk to *any* model, local or cloud.

**Universal interface:** every provider is reached through the OpenAI-compatible
`POST /v1/chat/completions` endpoint. A provider is just `{base_url, model, api_key?, num_ctx}`.

| Provider | base_url example | Notes |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | Set `num_ctx` ≥ 16K (4K default breaks agentic editing) |
| LM Studio | `http://localhost:1234/v1` | OpenAI-compatible server |
| vLLM | `http://localhost:8000/v1` | High-throughput local serving |
| LocalAI / llama.cpp | `http://localhost:8080/v1` | Drop-in OpenAI shape |
| Cloud (OpenAI/Anthropic/Gemini/OpenRouter) | provider URL | Optional fallback |

**Model router.** Some steps (large refactors, hard multi-step reasoning) exceed small local
models. The router picks a model per task type and may fall back to cloud — and must **warn
the user** whenever it does. Threshold heuristic: if a local model's tool-calling reliability
drops below ~80% on our eval set for a step type, default that step to cloud.

**Suggested interface:**
```python
class LLMGateway:
    def chat(self, messages: list[Message], tools: list[Tool] | None = None,
             task: TaskType = TaskType.GENERAL) -> ChatResponse: ...
    # router consults config to choose provider/model for `task`
```

Config lives in `config/playsmith.yaml`. Never hard-code endpoints or model names elsewhere.

---

## 2. Agent loop — `playsmith/agent/`

**Job:** turn a goal into actions, observe results, and iterate — with the user in the loop.

**The loop:** `plan → act (tool calls) → observe → iterate`, with human approval of diffs
before they hit disk.

**Core tools the agent exposes to the model:**
- `read_file(path)`, `write_file(path, content)`, `list_dir(path)` — scoped to the game workspace
- `apply_patch(path, find, replace)` — a targeted, unique find/replace edit (more reliable for small
  local models than unified diffs); preferred over whole-file writes
- `run_engine(headless, scene)` — via the EngineAdapter, never a raw shell to `godot`
- `verify_game(checks)` — run headless and assert gameplay (`player_on_floor`, `player_not_falling`,
  `no_errors`, …) via the `PLAYSMITH_ASSERT key=value` harness; the machine-readable reality check
- `read_logs()` — engine stdout/stderr and error output
- `screenshot()` — capture current frame (optional polish; blank under `--headless`)
- `generate_asset(spec)` — via the asset pipeline (optional)

**The reality loop (critical):** after any code change, the agent must
`run_engine(...) → read_logs() → verify_game() → evaluate → fix`. Verification is **assertion-based**:
an injected in-engine harness prints `PLAYSMITH_ASSERT key=value` lines a text model can read, and it
works headless (unlike screenshots). A game is never "done" until `verify_game` reports every gameplay
assertion PASS. Skills declare their checks (Engine adapters implement `verify()` → `VerifyResult`).
This lives here and is reused by every skill.

**Safety:** all file ops are confined to the user's game workspace dir (never this repo).
Show diffs; ask before destructive actions.

---

## 3. Engine adapters — `playsmith/engines/`

**Job:** a uniform way to drive any engine. Godot at MVP; Unreal in Phase 2.

**Interface (every engine implements this).** As shipped in Phase 0, the adapter is **bound to one
project directory** at construction, so `run`/`screenshot`/`export` take no path — a small refinement
of the original sketch that keeps call sites clean:
```python
class EngineAdapter(Protocol):
    project_dir: Path
    def version(self) -> str: ...
    def create_project(self, name: str, main_scene: str | None = None) -> None: ...
    def write_scene(self, scene: SceneSpec) -> Path: ...
    def write_script(self, rel_path: str, code: str) -> Path: ...
    def add_asset(self, src: str, dest: str) -> Path: ...
    def set_main_scene(self, res_path: str) -> None: ...
    def run(self, *, headless: bool = True, timeout_s: int = 30,
            scene: str | None = None) -> RunResult: ...                 # returns logs + exit code
    def screenshot(self, out_path: str, *, scene: str | None = None) -> RunResult: ...
    def export(self, target: ExportTarget, out_path: str, *, debug: bool = False) -> RunResult: ...
```
> Phase 1 (Step 1.5) adds `verify(checks) -> VerifyResult` for the assertion-based reality loop.

### Godot adapter (`engines/godot/`) — MVP
- **Version:** Godot **4.x** only. (4.x APIs differ from 3.x — see conventions below.)
- **Projects are text:** `project.godot`, `.tscn` scenes, `.gd` scripts. Easy to generate/diff.
- **Control options:** (a) drive the Godot CLI directly (`godot --headless ...`,
  `godot --export-release ...`), and/or (b) use the **Godot MCP** ecosystem — e.g.
  `Coding-Solo/godot-mcp` (original), `tugcantopaloglu/godot-mcp` (149-tool fork),
  `GDAI MCP Plugin`, `GodotIQ` (screenshots/spatial). Prefer bundling GDScript operations to
  avoid temp-file churn. Start with direct CLI + file writing; layer MCP in as needed.
- **Run/verify:** `godot --headless` for logic checks; short windowed run + screenshot for visuals.
- **Export:** `godot --headless --export-release "Web" build/index.html` (HTML5), plus desktop targets.
- **Godot 4 correctness (enforce in generated code):**
  - `CharacterBody2D` (not `KinematicBody2D`)
  - `velocity` is a built-in property; call `move_and_slide()` with **no arguments**
  - `@export var speed := 200.0` for inspector-exposed vars
  - gravity via `ProjectSettings.get_setting("physics/2d/default_gravity")`
  - input via `Input.get_axis("ui_left", "ui_right")`, `Input.is_action_just_pressed("ui_accept")`

### Unreal adapter (`engines/unreal/`) — Phase 2
- More complex: C++/Blueprints (partly binary), heavier builds, needs the Remote Control API
  (port 30010) + a plugin. Mature MCP servers exist (`remiphilippe/mcp-unreal` — 49 tools,
  UE 5.7, headless builds/tests; `flopperam/unreal-engine-mcp` — 50+ tools).
- **EULA matters:** 5% royalty on lifetime gross revenue **above the first $1M per product**
  (3.5% if launched via Epic Games Store "Launch Everywhere with Epic"; EGS revenue is
  royalty-exempt). Surface a royalty calculator to users. Godot has no royalties, ever.

---

## 4. Asset pipeline — `playsmith/assets/` (optional)

**Job:** generate game art locally. Degrades to placeholder rectangles/sprites if unavailable.

- **2D:** ComfyUI (node graph, OpenAI-style API call) with SDXL/Flux; `Pixel-Art-XL` for
  sprites; sprite-sheet and VN-character workflows. ~6–12GB VRAM typical.
- **3D:** Hunyuan3D 2.1 (Apache-2.0, PBR, ~6GB VRAM shape / ~16GB shape+texture, ~30s),
  TRELLIS.2 (MIT), TripoSR (fast but lower quality). **Expect cleanup** — AI 3D output
  usually needs topology/UV/rigging work before it's truly game-ready. Set expectations.
- **Interface:**
  ```python
  class AssetGenerator(Protocol):
      def image(self, prompt: str, kind: AssetKind, out_path: str) -> None: ...
      def mesh(self, prompt_or_image: str, out_path: str) -> None: ...
      def available(self) -> bool: ...   # if False, agent uses placeholders
  ```

---

## 5. Skills engine — `playsmith/skills/`

**Job:** map a user prompt to the right game-generation playbook and load it efficiently.

**Format:** the open **SKILL.md** standard (Anthropic Agent Skills, an open standard since
Dec 18, 2025; interoperable with Claude Code/Codex/Cursor). A skill is a folder:
```
2d-platformer/
├── SKILL.md            # YAML frontmatter (name, description) + markdown instructions
├── scripts/            # deterministic scaffolding (e.g. player.gd template)
├── references/         # engine API notes loaded on demand
└── assets/             # template assets
```

**Progressive disclosure (3 levels):**
1. **Metadata** (name + description) — always loaded, tiny. Used for routing.
2. **SKILL.md body** — loaded only when the skill is selected (<500 lines ideal).
3. **Bundled resources** — loaded/executed only when that step needs them.

**Routing:** match the user's prompt against skill `description`s (the "pushy" description
field is the trigger). The selected skill's body becomes the agent's plan; its `scripts/`
provide deterministic scaffolding; `references/` are read as needed.

**Sources:** local `game-skills/` dir at MVP; a remote community registry/marketplace in Phase 2.

---

## 6. Publish pipeline — `playsmith/publish/`

**Job:** turn a project into a build and get it onto a platform.

- **MVP:** headless export → **itch.io** via `butler` (the `butler push` flow; GitHub Actions
  recipes like `firebelley/godot-export` + butler actions exist to copy).
- **Phase 3:** Steam (with an **AI-disclosure helper** — Steam requires disclosing
  player-facing AI content; per Valve's Jan 2026 rewrite, dev tools like code assistants are
  *exempt*, but generated player-facing assets are not), Android/iOS exports.
- **Compliance helpers (built in, surfaced to user):**
  - Steam AI-content disclosure generator (pre-generated vs live-generated).
  - Apple Guideline **4.2.6** warning (template/app-generation submissions are rejected unless
    submitted by the content provider) and 4.3/spam guidance.
  - Google Play "**repetitive content**" warning (mass near-identical games are banned).
  - Unreal royalty calculator.
  - Copyright caveat for purely AI-generated assets (limited protection per US Copyright Office,
    March 2025 guidance).

---

## 7. CLI — `playsmith/cli/`

Typer commands, Rich/Textual for output. Indicative surface:
```
playsmith new "<prompt>"        # pick skill, scaffold, generate, run-verify
playsmith run                   # run the current game project
playsmith edit "<change>"       # iterate on the current game in natural language
playsmith assets "<prompt>"     # generate/replace an asset
playsmith export --target web   # headless export
playsmith publish --itch u/g    # publish (with compliance prompts)
playsmith models                # list/test configured providers
playsmith skills                # list installed skills
```

A Tauri/Electron GUI for non-coders is Phase 2+.

## Data flow, end to end

```
prompt
  → skills.route(prompt) -> skill
  → agent.run(goal=skill.body, tools=[fs, engine, assets])
       loop: plan → write code → engine.run() → screenshot()/read_logs() → fix
  → engine.export(target) -> build/
  → publish.itch(build/) [optional]
```

## Open technical risks (track these)

- **Local model capability** is the #1 risk: small models lag on multi-step tool-calling and
  long-context reasoning. Mitigate with the model router + cloud fallback + large `num_ctx`.
- **AI asset quality** needs human cleanup, especially 3D. Don't promise "one prompt → finished 3D game."
- **MCP ecosystem is young** and changes monthly (engine versions, server APIs). Pin versions.
- **App-store policy** (Apple 4.2.6, Google repetitive-content) constrains the "publish anywhere"
  dream — position publishing as shipping *a* polished game.
