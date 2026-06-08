# Architecture

This document describes how Playsmith is structured and the interfaces between its parts.
It is the technical companion to [`../CLAUDE.md`](../CLAUDE.md) (the canonical source of truth)
and the phased plan in [`ROADMAP.md`](ROADMAP.md). When you change a module boundary or an
interface here, update `CLAUDE.md` §3 too.

> **2026-06-09 re-founding.** Playsmith is now **Unreal Engine 5.x only** (UE 5.7.4). The Godot
> engine, the GDScript genre skills, the web studio UI, and the `publish/`, `assets/`, `studio.py`,
> and Docker subsystems were **removed** (`CLAUDE.md` §0). The `EngineAdapter` abstraction stays so
> more engines can be added later, but Unreal is the only implementation today.

## What exists today vs. what is planned

Be honest about this. The doc below marks each part. In short:

**Exists today (code-complete, tested):**
- The `EngineAdapter` interface + the **Unreal adapter** (`create_project` → `scaffold` → `verify`
  via `UnrealEditor-Cmd` headless + UE Python; a `RemoteControlClient`; a royalty calculator).
- The **agent loop** (plan → act via tools → observe → iterate) with diff approval.
- The **tiered LLM gateway + router** (OpenAI-compatible `/v1` and native Anthropic `/v1/messages`,
  per-task routing, local→cloud fallback with a warning, and a reliability eval).
- The **skills system** (SKILL.md loader with progressive disclosure, a prompt→skill router, and a
  secure marketplace registry).
- The **CLI** (`version`, `config-check`, `models`, `skills …`, `unreal …`).
- The headless **`PLAYSMITH_ASSERT` reality loop** (`engines/base.py::parse_assert_lines` +
  `KNOWN_ASSERTIONS`) and the UE verify harness that emits it.

**Planned (described as future stages, NOT implemented):**
- **Build ON a shipping UE template** (clone `TP_ThirdPersonBP`/`FirstPersonBP`/`TopDownBP`). Today
  the adapter scaffolds a deterministic lit level from primitives via `scaffold()` — the template
  clone is stage 1.
- The **director → critic loop**: a critic agent that scores rendered screenshots + real PIE
  metrics against a quality rubric and sends work back. Today there is a *level director*
  (`unreal/level_director.py`) that plans a level spec from a prompt, and structural asserts — but
  no critic and no quality gate. (Stage 3.)
- **Editor-in-the-loop rendering / PIE**: dropping `-nullrhi`, running the editor on the GPU, and
  pinning a UE MCP (e.g. `remiphilippe/mcp-unreal`) for real authoring + screenshots. The
  `RemoteControlClient` and `screenshot()` exist but assume an editor is already up. (Stage 2.)
- A **UE-native package/publish path** (`RunUAT BuildCookRun`). `export()` is an experimental
  headless cook stub. (Stage 4.)

Stage numbering follows `CLAUDE.md` §0.

## Design principles

1. **One agent, many tools.** Playsmith is fundamentally an agentic loop that calls tools. The
   engine is a tool behind a clean interface.
2. **Abstract the engine.** Nothing outside `playsmith/engines/<engine>/` knows engine specifics.
   Skills and the agent loop talk to an `EngineAdapter`.
3. **Abstract the model.** Nothing outside `playsmith/llm/` knows which provider is in use, or
   whether it is local or cloud, OpenAI-shaped or Anthropic-shaped.
4. **Build on a foundation, don't generate from scratch.** Quality comes from starting on a
   shipping UE template and *dressing/tuning* it — not from an LLM laying primitives in an empty
   scene. This is the #1 quality lever (`CLAUDE.md` §0, §2).
5. **Close the loop on reality.** The agent runs the project, reads machine-readable assertions
   (and later renders + critiques), and self-corrects on what actually happened.

## Component map

```
playsmith/
├── llm/        LLM gateway + router + Anthropic adapter + eval   (the "brain access")
│     gateway.py · anthropic.py · eval.py · types.py · __init__.py
├── agent/      agentic loop, tool definitions, diff approval     (the "hands")
│     loop.py · tools.py · approval.py
├── engines/    EngineAdapter interface + unreal/                 (the "workshop")
│     base.py · unreal/{adapter,level_director,templates}.py
├── skills/     SKILL.md loader, prompt router, secure marketplace (the "playbooks")
│     loader.py · router.py · registry.py
├── cli/        Typer/Rich entrypoints                            (the "front desk")
│     main.py
└── config.py   one resolved config from config/playsmith.yaml
```

> There is **no** `llm/router.py` file — routing logic lives inside `llm/gateway.py`
> (`LLMGateway._resolve` / `_fallback_for`), and the router-maturity measurement is `llm/eval.py`.
> "Router" is a role split across those two, not a module.

---

## The mental model

Playsmith is **an agent that directs Unreal Engine and asset/skill systems, guided by skills.**

```
user prompt
   │
   ▼
[ Skills router ]  ── picks a genre skill (third-person | first-person | top-down)        [exists]
   │
   ▼
[ Director ]  ── frontier LLM plans the slice (objective, layout, mechanics, dressing)
   │              today: level_director plans a level spec from the prompt   [partial → stage 3]
   ▼
[ Agent loop ]  ── act (tool calls / later: UE MCP) → observe → iterate                   [exists]
   │   ├── [ LLM gateway + router ]  tiered: frontier director/critic + local sub-steps   [exists]
   │   └── [ EngineAdapter (Unreal) ] create / scaffold / run / verify / screenshot / export
   │            today: scaffold a lit level from primitives    [exists; clone-template → stage 1]
   ▼
[ Critic ]  ── scores rendered screenshots + PIE metrics vs. a rubric; loops back    [stage 3]
   │
   ▼
[ Package / publish ]  ── RunUAT BuildCookRun → store, with compliance helpers        [stage 4]
```

### Data flow, end to end

```
prompt
  → skills.SkillRouter.route(prompt) -> Skill                              [exists]
  → director plans the slice (level_director.plan_level today)            [partial]
  → AgentLoop.run(goal):                                                  [exists]
        loop: model -> tool calls -> execute -> observe -> repeat
        reality loop: run_engine -> read_logs -> verify_game -> fix
  → critic scores rendered screenshots + PIE metrics vs. a rubric         [stage 3]
  → engine.export(target) -> packaged build                              [stage 4 / stub today]
  → (UE-native) publish                                                   [stage 4]
```

Note: `cli/main.py`'s `unreal new` command currently wires `create_project → level_director.plan_level
→ scaffold → verify` directly (a deterministic build, not yet the full director→agent→critic loop).
`AgentLoop` exists and is tested, but is not yet the entrypoint for `unreal new`.

---

## 1. LLM gateway + router — `playsmith/llm/`

**Job:** give the rest of the app one way to talk to *any* model — and route per task between a
frontier model and local models.

**Tiered, two wire shapes.** A provider is `{provider, base_url, model, api_key?, num_ctx, kind}`
(`config.LLMConfig`). The `kind` field selects the wire protocol:

| `kind` | Endpoint | Used for |
|---|---|---|
| `openai` (default) | `POST {base_url}/chat/completions` | Local (Ollama, LM Studio, vLLM, LocalAI/llama.cpp) **and** most cloud (OpenAI, OpenRouter, Gemini-compat). |
| `anthropic` | `POST {base_url}/messages` | The frontier **director/critic** (Claude). Native Messages API in `llm/anthropic.py` — chosen over Anthropic's OpenAI-compat shim because that shim drops strict tool schemas + prompt caching, which breaks the multi-turn tool loop. |

Both shapes are normalized to one `ChatResponse` (`llm/types.py`); nothing downstream knows which
was used. For Ollama, `options.num_ctx` is injected (the 4K default breaks agentic editing); it is
*not* sent to cloud OpenAI endpoints (they 400 on it).

**Routing (in `gateway.py`).** `chat(..., task=TaskType.X)` labels *why* a call is made
(`GENERAL`, `CODING`, `REASONING`, `ROUTING`). `_resolve(task)` picks a per-task provider from
`config.llm_routes`, defaulting to `config.llm`. On a hard step (`CODING`/`REASONING`) the router
may fall back to a configured cloud provider — but **only when leaving a local model**, and it
**always warns the user** when the crossing sends their prompt/code to the cloud (`_warn_crossing`).
Fallback fires on two signals: the primary call raised, or a tool-using step came back with **no
tool call** (a common local-model failure).

**Router maturity (`eval.py`).** `evaluate_provider` turns the "~80% tool-call reliability"
heuristic into a measurement: run small tool-eliciting fixtures, count how often each provider
produces the expected tool call, and recommend whether to trust it locally or route hard steps to
cloud. Surfaced via `playsmith models --eval`.

```python
class LLMGateway:
    def chat(self, messages: list[Message], tools: list[Tool] | None = None,
             task: TaskType = TaskType.GENERAL, *,
             temperature: float | None = None,
             tool_choice: str | None = None) -> ChatResponse: ...
```

Config lives in `config/playsmith.yaml` (`llm`, `llm.routes`, `llm.fallback`). Never hard-code
endpoints or model names elsewhere.

---

## 2. Agent loop — `playsmith/agent/`

**Job:** turn a goal into actions, observe results, and iterate — with the user in the loop.

**The loop (`loop.py`):** `AgentLoop.run(goal)` seeds a system prompt + the goal, then repeatedly
calls `gateway.chat(messages, tools=all_tools(), task=TaskType.CODING)`, executes every returned
tool call, feeds results back as `tool` messages, and stops when the model calls `task_complete`
(the sentinel tool), emits no tool calls, or hits `max_iterations`. The reality loop is enforced in
the system prompt: after changing the project, run the engine, read logs, then `verify_game`, and
only `task_complete` once every assertion PASSes.

**Tools the model may call (`tools.py`).** Each handler returns a short string fed back to the model:

| Tool | What it does |
|---|---|
| `read_file(path)` / `list_dir(path)` | Read/list inside the workspace (escapes refused). |
| `write_file(path, content)` | Full write — **requires diff approval** (`approval.py`). |
| `apply_patch(path, find, replace)` | Targeted unique-substring edit; more reliable than unified diffs for small models; also approval-gated. |
| `run_engine(headless?, scene?)` | Run via the `EngineAdapter` (never a raw shell). Returns status + error lines + logs. |
| `screenshot(scene?)` | Capture via the adapter (needs an editor up with Remote Control — stage 2). |
| `read_logs()` | The logs from the last `run_engine`. |
| `verify_game(checks?, scene?)` | Run headless and report each `PLAYSMITH_ASSERT` PASS/FAIL — the load-bearing reality check. |
| `task_complete(summary)` | Sentinel; ends the loop. Only valid once `verify_game` is all-PASS. |

**Safety.** `ToolContext.resolve` confines all filesystem tools to the adapter's `project_dir`
(never this repo). Writes/patches go through an `Approver` that shows a diff first.

---

## 3. Engine adapter — `playsmith/engines/`

**Job:** a uniform way to drive an engine. Unreal Engine 5.x today; the interface stays so others
can be added behind it.

### The interface (`engines/base.py`) — exists

Every engine implements this `Protocol`. The adapter is **bound to one project directory** at
construction, so `run`/`screenshot`/`export`/`verify` take no path:

```python
@runtime_checkable
class EngineAdapter(Protocol):
    project_dir: Path
    def version(self) -> str: ...
    def create_project(self, name: str, main_scene: str | None = None) -> None: ...
    def write_scene(self, scene: SceneSpec) -> Path: ...      # text-scene engines only
    def write_script(self, rel_path: str, code: str) -> Path: ...
    def add_asset(self, src: str, dest: str) -> Path: ...
    def set_main_scene(self, res_path: str) -> None: ...
    def run(self, *, headless=True, timeout_s=30, scene=None) -> RunResult: ...
    def screenshot(self, out_path: str, *, scene=None) -> RunResult: ...
    def export(self, target: ExportTarget, out_path: str, *, debug=False) -> RunResult: ...
    def import_assets(self) -> RunResult: ...
    def verify(self, checks: list[str] | None = None, *, scene=None) -> VerifyResult: ...
```

Supporting types: `SceneSpec` (text path+content — Unreal rejects these, see below); `RunResult`
(command/returncode/stdout/stderr/timed_out, plus `.logs`, `.ok`, and `.error_lines()` which scans
for `_ERROR_MARKERS` while skipping `_BENIGN_MARKERS` like headless RHI/shutdown chatter);
`VerifyResult` (the run + a `{assertion: bool}` map, `.ok` true only when ≥1 check and all pass).

### The reality loop + assertions — exists

The in-engine verify harness prints lines like `PLAYSMITH_ASSERT player_exists=true`. This is the
machine-readable half of the loop a text model can read, and it works **headless** (no vision model).
`parse_assert_lines(logs)` turns them into the `VerifyResult` map. The vocabulary is fixed:

```python
KNOWN_ASSERTIONS = {
    "no_errors", "level_loads", "player_start_exists",
    "floor_exists", "player_exists", "goal_exists", "obstacles_exist",
}
```

Skills must declare checks from this set; the marketplace validates installed skills against it.
Richer playability/quality gates (PIE metrics, rendered-screenshot scoring) are layered on by the
**director/critic loop** (stage 3), *on top of* these structural asserts — never instead of them.

### The Unreal adapter (`engines/unreal/`) — exists

`UnrealAdapter` drives `UnrealEditor-Cmd` headless and exposes a `RemoteControlClient` for the
HTTP Remote Control API (default `http://localhost:30010`).

- **`create_project(name)`** — writes a **Blueprint-only** `.uproject` (Python plugin enabled, no
  C++ modules → nothing to compile) + `Config/DefaultEngine.ini` pointing at the level map
  (`templates.py`).
- **`scaffold(spec)`** *(UE-specific, not on the Protocol)* — runs a UE Python script that builds a
  lit, themed, playable level (ground + sun/sky/atmosphere/fog + tagged obstacle boxes + a tagged
  goal sphere + a `PlayerStart` + a flyable `DefaultPawn`). `spec` is an optional LLM-authored
  layout; absent it, a safe default is built. **This is today's "make a level" path; stage 1
  replaces it with cloning a shipping UE template.**
- **`verify(checks)`** — runs the UE Python verify harness (`templates.verify_script`), which loads
  the level, counts key actors / tags, and writes `PLAYSMITH_ASSERT` lines; the adapter parses them
  into a `VerifyResult`. `no_errors` is only evaluated when explicitly requested (UE startup logs
  are noisy); the structural asserts are the load-bearing signal.
- **`run` / `screenshot` / `export`** — `run` launches `-game` headless (`-nullrhi`) or windowed;
  `screenshot` calls Remote Control `HighResShot` (**needs the editor up** — stage 2); `export` is
  an **experimental** headless cook stub (full packaging is `RunUAT BuildCookRun` — stage 4).
- **`write_scene`** raises: **Unreal maps/assets are binary** (`.umap`/`.uasset`). Author levels via
  the editor, the UE Python API, or Remote Control — **never by writing those files as text.**

**Headless realities baked into the adapter (learned the hard way):** runs pass
`-unattended -nullrhi -nosound -nosplash -nopause -stdout -NoLogTimes -notrace -noxgecontroller`
(`-notrace`/`-noxgecontroller` avoid a shutdown-daemon hang). The `pythonscript` commandlet does
**not** reliably surface `print()`/`unreal.log()` on stdout, so scripts write results to a file
exposed as `$PLAYSMITH_UE_OUT` and the adapter reads it back. First builds are slow (shader DDC);
do not `pkill -9` UE repeatedly.

**Unreal EULA royalties.** `royalty_estimate()` (and `playsmith unreal royalty`) compute Epic's
5% of lifetime gross **above the first $1M per product** (3.5% via the Epic Games Store; revenue
earned on EGS is exempt). Surface this to users — unlike Godot, Unreal has royalties.

### The level director (`engines/unreal/level_director.py`) — partial (→ stage 3 critic)

`plan_level(prompt, gateway)` asks the LLM for a themed level spec (lighting mood + obstacle layout
+ goal) as strict JSON, **clamps every value to safe/reachable ranges** (`_sanitize`), and falls
back to `templates.default_spec()` on any failure — level direction must never break a build. This
is the seed of the "director"; the **critic** half (score renders/PIE vs. a rubric, loop back) is
not built yet.

---

## 4. Skills system — `playsmith/skills/`

**Job:** map a user prompt to the right game-generation playbook, load it efficiently, and let the
community publish more — safely. Full contract: [`SKILL_SPEC.md`](SKILL_SPEC.md); contributor guide:
[`CONTRIBUTING_SKILLS.md`](CONTRIBUTING_SKILLS.md).

**Format.** The open **SKILL.md** standard (interoperable with Claude Code / Codex / Cursor — no
bespoke format). A skill is a folder: `SKILL.md` (YAML frontmatter `name` + `description` +
`assertions`, then a markdown body) plus optional `scripts/`, `references/`, `starter/`.

**Progressive disclosure (`loader.py`), three levels:**
1. **Metadata** (name + description + assertions) — parsed at scan time, tiny, used for routing.
2. **Body** — loaded only when a skill is selected (`Skill.body()`).
3. **Bundled resources** — `scripts()` / `references()` / `starter_files()` expose **paths**;
   contents are read only when a step needs them (`read_script`).

`SkillLoader` discovers skills under the first-party `game-skills/` dir + the user's
`~/.playsmith/skills/`. (The old Godot genre skills were removed in the re-founding; UE genre
skills — third-person, first-person, top-down — are authored on the new rails.)

**Routing (`router.py`).** `SkillRouter.route(prompt)` first asks the LLM Gateway to pick by the
skills' `description` fields (the "pushy" trigger text), with a deterministic keyword-overlap
fallback so routing still works offline / when the model is flaky.

### Marketplace security (`registry.py`) — the moat must ship safe

A community skill is **code and prompt the user is trusting**: its bundled `scripts/` get written
into the user's game, and its `SKILL.md` body is injected into the agent's prompt (a
prompt-injection vector). A skill is distributed as one JSON "skillpack"
(`{name, version, skill_md, scripts{}}`); the index lists `url` + `sha256` per entry. `install`
enforces, by construction:

1. **Integrity** — the fetched skillpack's SHA-256 must match the index entry, or install is refused.
2. **Untrusted-by-default** — third-party/untrusted skills require an explicit `--allow-untrusted`.
3. **No auto-execution** — installing only writes files; **no post-install hooks, ever.** Script
   filenames are reduced to their basename (no path traversal out of the skill dir).
4. **Provenance** — `source`/`author`/`version`/`sha256`/`trusted` are written to a
   `.provenance.json` next to the skill; the loader flags untrusted skills, and diff-approval shows
   every script before it is written into a project.

`validate_skillpack` checks frontmatter and that all declared `assertions` are in `KNOWN_ASSERTIONS`.

---

## 5. CLI — `playsmith/cli/`

Typer + Rich (`main.py`). Current command surface:

```
playsmith version                  # print version
playsmith config-check             # show the resolved config (providers, routes, fallback, engine)
playsmith models [--eval]          # route table + round-trip the default model (--eval: reliability)
playsmith skills [list|search|install|remove]   # the secure skill marketplace
playsmith unreal new "<name>"      # create_project -> plan_level -> scaffold -> verify (real UE)
playsmith unreal check             # editor binary + Remote Control availability
playsmith unreal royalty <gross>   # Unreal EULA royalty estimate (--egs, --egs-exempt)
```

A GUI is a later concern (the old web studio UI was removed in the re-founding).

---

## 6. Configuration — `config.py`

One resolved `Config` from `config/playsmith.yaml` (priority: explicit `--config` >
`$PLAYSMITH_CONFIG` > `config/playsmith.yaml` > `config/playsmith.example.yaml`). A
`playsmith.runtime.yaml` override file (UI-managed settings / secrets) is deep-merged on top.
Key sections: `workspace_dir` (generated games live here, **never** in this repo), `llm` (+
`llm.routes`, `llm.fallback`), `engine` (default `unreal`, `engine.unreal.editor_cmd`), and
`skills` (`registry_url`, install `dir`). `LLMConfig.is_local` decides when a router crossing must
warn (local providers/hosts vs. cloud). Never hard-code model names, endpoints, or paths elsewhere.

---

## Open risks (track these) — and: **pin your MCP version**

- **MCP ecosystem is young and moves monthly.** The editor-in-the-loop authoring/rendering path
  (stage 2) depends on a UE MCP (e.g. `remiphilippe/mcp-unreal`, UE 5.7) whose tool set and engine
  support change between releases. **Pin a specific version when you wire one in**, and re-test
  after any UE upgrade. Until then, authoring goes through `UnrealEditor-Cmd` + UE Python + Remote
  Control, which we control directly.
- **Frontier-model dependency.** The director/critic need a frontier model (`ANTHROPIC_API_KEY`).
  This relaxes the original "any local LLM, fully headless" purity (a deliberate trade for quality —
  `CLAUDE.md` §0). Local models still do cheap sub-steps; the router warns on every local→cloud
  crossing so the user knows when prompts/code leave the machine.
- **Quality is unproven without rendering.** The critic loop (stage 3) and real rendered
  screenshots/PIE (stage 2) do not exist yet. Structural asserts confirm "it runs," not "it's
  good" — do not claim quality the harness can't yet measure.
- **Binary assets resist text diffing.** `.umap`/`.uasset` can't be written/reviewed as text. The
  adapter authors them via UE Python; diff-approval covers the *automation scripts*, not the binary
  results — keep edits small and verifiable, and lean on `verify_game`.
- **UE build cost & flakiness.** Source-build editor boots are slow; first cooks churn the shader
  DDC; headless shutdown can hang without `-notrace`/`-noxgecontroller`. The adapter encodes the
  known-good flags — don't strip them.
- **App-store policy** (Apple Guideline 4.2.6, Google repetitive-content) constrains the "publish
  anywhere" dream — position publishing (stage 4) as shipping *a* polished game, not mass-submission.
