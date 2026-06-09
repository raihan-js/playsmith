# Asset packs — dress your games with real Fab / Megascans assets

An **asset pack** tells Playsmith's director to place *real, photo-scanned meshes* (Megascans rocks,
ruins, foliage; Fab modular kits) instead of grey prototype cubes — the Phase 1 "looks like a real
game" leap (see [`docs/NEXTGEN_ROADMAP.md`](../../docs/NEXTGEN_ROADMAP.md)). This folder holds a
**starter** you copy and edit.

## Two ways to get real assets into a build

1. **Auto-discovery (easiest).** With the **editor-in-the-loop** on (a running editor + Remote
   Control — run `WebControl.StartServer` in the editor console; `playsmith unreal check` confirms
   it), Playsmith *scans your project* for installed Megascans/Fab content, buckets it by gameplay
   role, and dresses with it. No manifest needed — just import a kit via the **Fab** plugin and build.
2. **A manifest pack (curated control).** A JSON file like [`frozen.json`](frozen.json) that maps
   gameplay **roles** to the exact asset paths you want. Use this when you want to hand-pick the kit.

## Using the starter pack

1. **Import a frozen/Nordic asset kit** into a generated UE project (Fab plugin → Add to Project, or
   Quixel Bridge). A few ice cliffs, snow rocks, frozen props, a snow surface — anything.
2. **Get each asset's path:** right-click it in the Content Browser → **Copy Reference**, then keep
   just the `/Game/...` part (drop the `StaticMesh'` prefix and the trailing `.Name`). Example:
   `StaticMesh'/Game/Megascans/3D_Assets/Ice_Cliff_va/Ice_Cliff_va.Ice_Cliff_va'` →
   `/Game/Megascans/3D_Assets/Ice_Cliff_va/Ice_Cliff_va`.
3. **Edit `frozen.json`** — replace the example paths under each role with your real ones. Roles:
   `platform`, `obstacle`, `cover`, `hazard`, `collectible`, `goal`, `prop`, plus an optional
   `ground_material` (a surface for the floor). List several per role — the director rotates through
   them for variety.
4. **Activate it** — copy the file into `~/.playsmith/assetpacks/`:
   ```bash
   mkdir -p ~/.playsmith/assetpacks
   cp examples/assetpacks/frozen.json ~/.playsmith/assetpacks/
   ```
5. **Build** a frozen game — the director matches the `"theme": "frozen"` pack to a frozen prompt and
   dresses with your real assets (which keep their own photoreal materials), laying the
   `ground_material` on the floor:
   ```bash
   playsmith unreal new "a frozen ruined fortress"
   ```

## Good to know

- **Missing paths are safe.** Any path you haven't imported is skipped and that placement falls back
  to a prototype shape — so a half-filled manifest still produces a full level (it just gets better as
  you fill in real assets). Drop the example file in as-is and you'll get prototype shapes until you
  replace the paths.
- **Real assets keep their materials.** Playsmith does *not* tint real meshes (only the prototype
  fallback is role-coloured) — the photoreal look comes from the assets themselves.
- **Theme matching.** A pack's `theme` is matched against the prompt (substring/word match). Name it
  `frozen`, `volcanic`, `jungle`, `desert`, etc. A pack with an empty `theme` is used for any prompt
  that has no more specific match.
- **Share packs.** These are plain JSON — commit them, share them, or publish a community pack.
