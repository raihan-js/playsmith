# Run Playsmith in Docker (with Godot + OpenAI)

This is the fastest way to actually run the full pipeline — **prompt → real Godot game → verified
→ ready to edit** — without installing Godot on your machine. The image bakes in Godot 4.x; you
bring an OpenAI API key (or any OpenAI-compatible endpoint).

## 1. Configure your key

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...
```

## 2. Build the image

```bash
docker compose build          # downloads Godot 4.3 + installs Playsmith (a few minutes, once)
```

## 3. Prove the two halves work

```bash
docker compose run --rm playsmith engine-check    # REAL headless Godot run (no mocks)
docker compose run --rm playsmith models          # round-trips a message to OpenAI (your key)
docker compose run --rm playsmith skills          # lists built-in + installed community skills
```

If `engine-check` prints "engine-check passed" and `models` returns a reply, you're ready.

## 4. Make a game

```bash
docker compose run --rm playsmith new "a 2D platformer where a cat collects fish and avoids spikes" --yes
# or a story game:
docker compose run --rm playsmith new "a short branching mystery about a lighthouse keeper" --yes
# or a 3D game:
docker compose run --rm playsmith new "a simple 3D platformer where a robot collects orbs" --yes
```

The agent scaffolds a real Godot 4 project, writes the code, runs it headless, and **verifies the
gameplay assertions** (`player_on_floor`, `no_errors`, …), fixing until they pass. The finished
project appears in **`./playsmith-games/<game>/`** on your host — open it in the Godot editor and
keep editing.

## 5. Iterate, install community skills, export

```bash
docker compose run --rm playsmith edit "make the player jump higher and add a second platform"
docker compose run --rm playsmith skills install endless-runner    # from the live registry, sha256-verified
docker compose run --rm playsmith new "an endless runner where a robot dodges spikes" --yes
docker compose run --rm playsmith export --target web              # needs HTML5 export templates (see note)
```

## Tips & notes

- **Cost:** `gpt-4o` is the default (reliable at the agent's tool loop). For cheaper runs, set
  `llm.model: gpt-4o-mini` in `config/playsmith.docker.yaml` and rebuild (or mount your own config).
- **Any OpenAI-compatible endpoint** works — change `llm.base_url`/`model` (e.g. OpenRouter). For a
  local model instead, point `base_url` at your host's Ollama (`http://host.docker.internal:11434/v1`).
- **HTML5 export** needs Godot's export templates, which aren't in the base image. For a runnable
  game you don't need them; add them only when you want `export --target web`.
- **Screenshots** are blank headless (verification is assertion-based, which works headless). For a
  real screenshot, run on a desktop or add `xvfb`.
- **Open the game on your host:** `godot --editor --path ./playsmith-games/<game>` (host Godot), or
  just open the folder in the Godot editor.
- **File ownership:** the container runs as root, so generated games under `./playsmith-games/` are
  root-owned on the host. To edit them as your user: `sudo chown -R $USER:$USER playsmith-games`.

## Validated

Built and confirmed in-container (no mocks): Godot 4.3 runs headless (`engine-check` passes), the
assertion reality loop emits real `PLAYSMITH_ASSERT` results in Godot (player lands on the floor),
and `skills install` fetches + SHA-256-verifies from the live registry. Only the LLM steps
(`models`/`new`/`edit`) need your OpenAI key.
