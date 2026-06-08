# Build Plan — start here

This is the step-by-step order to build Playsmith with **Claude Code**. Each step is a prompt
you can paste, plus a checkpoint that tells you when it's done. Build in order — every step
ends in something runnable. Don't jump ahead; the reality loop (step 6) is the heart of the
product and everything before it exists to enable it.

> **How to use this file:** open this repo in Claude Code. Claude Code will read `CLAUDE.md`
> automatically. Then paste the prompts below one at a time, verify the checkpoint, commit,
> and move on. The prompts are deliberately small so the model stays accurate and you stay
> in control.

---

## Prerequisites (do these once, before Claude Code)

1. **Install Godot 4.x** (the standard build is fine; you'll also want the export templates
   for HTML5/desktop later). Confirm `godot --version` prints a 4.x version.
2. **Install a local model runner.** Easiest is **Ollama**:
   ```bash
   # install Ollama (see ollama.com), then pull a coding model:
   ollama pull qwen2.5-coder:7b      # modest hardware
   # or, for a stronger machine:
   ollama pull qwen3-coder           # larger, agentic-tuned, big context
   ```
   Ollama serves an OpenAI-compatible endpoint at `http://localhost:11434/v1`.
   > ⚠️ Set a large context window when you call it (16K–32K). The 4K default will break
   > agentic file editing. We handle this in the LLM Gateway config (`num_ctx`).
3. **Python 3.11+** and **git**. (`pip`, `venv`.)
4. **(Optional, for later) butler** (itch.io CLI) and **ComfyUI** — not needed for Phase 0.
5. Open this folder in **Claude Code**.

---

## The build, step by step

### Step 0 — Orient Claude Code
**Paste:**
> Read `CLAUDE.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` in full. Summarize back to
> me, in 5 bullets, what we're building and the Phase 0 Definition of Done. Then list the
> module files you expect to create for Phase 0. Don't write any code yet.

**Checkpoint:** the summary matches the docs and the file list lines up with `playsmith/`'s
subfolders. If it drifts (e.g. suggests a cloud backend, or Godot 3.x), correct it now.

---

### Step 1 — Repo skeleton + config + license
**Paste:**
> Set up the Python package skeleton for Playsmith: `pyproject.toml` (package name
> `playsmith`, Python 3.11+, deps: a minimal HTTP client, `typer`, `rich`, `pyyaml`, `pytest`,
> `ruff`), an Apache-2.0 `LICENSE`, a `.gitignore`, and `config/playsmith.example.yaml` with a
> documented LLM provider config (provider, base_url, model, api_key optional, num_ctx) plus
> a `workspace_dir` for generated games. Add empty `__init__.py` files in each `playsmith/`
> subpackage. Wire `ruff` and a trivial `pytest` that passes. Don't implement features yet.

**Checkpoint:** `pip install -e .` works, `ruff check` passes, `pytest` passes, and copying
the example to `config/playsmith.yaml` gives a readable config.

---

### Step 2 — LLM Gateway (any model via OpenAI-compatible /v1)
**Paste:**
> Implement `playsmith/llm/` per `docs/ARCHITECTURE.md` §1. A `LLMGateway.chat(messages,
> tools=None, task=GENERAL)` that calls an OpenAI-compatible `/v1/chat/completions` endpoint,
> reading provider/model/base_url/api_key/num_ctx from `config/playsmith.yaml`. Support tool
> (function) calling in the request/response shape. Add a `playsmith models` CLI command that
> sends a one-line "say hi" to the configured model and prints the reply, so I can confirm my
> local Ollama model responds. Keep a clean seam for a future model router; don't build the
> router yet. Add unit tests with the HTTP layer mocked.

**Checkpoint:** with Ollama running, `playsmith models` gets a real reply from your local model.
This proves the whole "any local model" foundation works.

---

### Step 3 — Godot adapter v1 (create / write / run / screenshot / export)
**Paste:**
> Implement `playsmith/engines/` with the `EngineAdapter` interface from `docs/ARCHITECTURE.md`
> §3, and a `GodotAdapter` for Godot 4.x that drives the `godot` CLI: `create_project` (writes
> a minimal `project.godot`), `write_scene`/`write_script` (write `.tscn`/`.gd` files under the
> workspace), `run(headless, timeout_s)` (runs the project, captures stdout/stderr, returns a
> RunResult with logs + exit code), `screenshot(out_path)`, and `export(target, out_path)` for
> the "Web" target. Enforce the Godot 4 conventions in `CLAUDE.md` §6. Generated games go in
> `workspace_dir`, never in this repo. Add a CLI smoke test `playsmith engine-check` that
> creates a trivial empty project and runs it headless to confirm Godot is wired up. Tests
> with the Godot binary mocked.

**Checkpoint:** `playsmith engine-check` creates a tiny Godot project in your workspace dir and
runs it headless without errors. You can open that project in the Godot editor.

---

### Step 4 — Skills engine v1 (load + route SKILL.md)
**Paste:**
> Implement `playsmith/skills/` per `docs/ARCHITECTURE.md` §5: a loader that scans
> `game-skills/` for `SKILL.md` files, parses the YAML frontmatter (name, description), and
> implements progressive disclosure (metadata always available; body loaded only when a skill
> is selected; bundled `scripts/` paths exposed but not loaded until needed). Add a router that,
> given a user prompt, asks the LLM Gateway to pick the best-matching skill by its description
> (return the skill name). Add `playsmith skills` (list installed skills) and make routing
> testable. Use the existing `game-skills/genres/2d-platformer/SKILL.md` as the test fixture.

**Checkpoint:** `playsmith skills` lists the 2d-platformer skill, and routing a prompt like
"a jump-and-run game with a fox" selects `2d-platformer`.

---

### Step 5 — Agent loop v1 (plan → act → observe → iterate, with diff approval)
**Paste:**
> Implement `playsmith/agent/` per `docs/ARCHITECTURE.md` §2: an agentic loop that takes a goal
> (a skill body) plus the tools `read_file`, `write_file`, `apply_patch`, `list_dir`,
> `run_engine` (via the EngineAdapter), `screenshot`, and `read_logs`. The loop: send goal +
> tool schemas to the LLM Gateway, execute returned tool calls, feed results back, repeat until
> the model signals done or a max-iteration cap. Confine all file ops to the workspace dir.
> Show me each file write as a diff and require approval before applying (with a `--yes` flag to
> auto-approve). Don't build the asset pipeline yet — assets are placeholders.

**Checkpoint:** you can hand the agent a tiny goal ("create a file hello.gd that prints hello,
then run it") and watch it write, run, and report the output — asking for diff approval first.

---

### Step 6 — Wire it end to end: `playsmith new` + the reality loop ⭐
This is the milestone that makes Playsmith real. **Paste:**
> Implement the `playsmith new "<prompt>"` command that ties everything together: route the
> prompt to a skill (Step 4), load its body, run the agent loop (Step 5) with the GodotAdapter
> (Step 3) to scaffold and build the game following the skill's steps. Critically, implement
> the **reality loop** from `CLAUDE.md` §4 and the 2d-platformer SKILL.md step 9: after writing
> code, the agent must `run_engine()` headless, `read_logs()`, take a `screenshot()`, evaluate
> whether it actually worked (no parse/runtime errors; player on ground; can jump), and
> **fix-and-rerun** until it does, up to a cap. Then print where the project is and how to open
> it in Godot. Use the bundled `scripts/player.gd` as the movement template.

**Checkpoint (this is the Phase 0 win):**
```bash
playsmith new "a 2D platformer where a cat collects fish and avoids spikes"
```
produces a real Godot 4 project in your workspace that **runs**, the screenshot shows the
player standing on ground, and you can open and edit it in the Godot editor. If the model
struggles, see "If a local model struggles" below.

---

### Step 7 — Run + export commands
**Paste:**
> Add `playsmith run` (run the current/most-recent generated project windowed so I can play it)
> and `playsmith export --target web` (headless HTML5 export to a `build/` dir using the
> GodotAdapter). Confirm the exported `index.html` opens and the game is playable in a browser.

**Checkpoint:** you can play the generated game in a window and open the exported HTML5 build
in a browser. **Phase 0 Definition of Done is now met** (`CLAUDE.md` §7). Record a 60s demo.

---

### Step 8 — First polish + commit the demo
**Paste:**
> Tighten error messages and the CLI UX with Rich. Write a short `docs/QUICKSTART.md` that
> matches what actually works now. Update the Phase 0 checkboxes in `docs/ROADMAP.md`. Suggest
> the 3 highest-leverage things to do next from Phase 1.

**Checkpoint:** a newcomer could follow QUICKSTART and make a game. You're ready to plan the
Phase 1 push toward a public launch.

---

## If a local model struggles (expected, not a failure)

Small local models (7B) can be unreliable at multi-step tool-calling. Tactics, in order:
1. **Raise `num_ctx`** to 16K–32K in your config — this is the most common fix.
2. **Use a stronger local model** (e.g. `qwen3-coder`) if your hardware allows.
3. **Lean on the skill's bundled scripts** — deterministic scaffolding (like `player.gd`)
   reduces what the model has to invent.
4. **Temporarily point the config at a cloud model** to confirm the *pipeline* is correct,
   then return to local. (The model router in Phase 2 automates choosing per task.)
5. **Shrink the step** — give the agent smaller sub-goals.

The goal of Phase 0 is to prove the architecture end-to-end; perfect local reliability is a
Phase 2 concern.

---

## Working rhythm with Claude Code

- One step at a time; verify the checkpoint; `git commit`; then next step.
- If Claude Code proposes a big rewrite or a new dependency, ask it to justify the license and
  the boundary it's crossing (see `CLAUDE.md` §5–6) before approving.
- Keep generated games out of this repo (they belong in `workspace_dir`).
- When a step reveals a better design, update `docs/ARCHITECTURE.md` **and** `CLAUDE.md`
  together so the docs stay the source of truth.
