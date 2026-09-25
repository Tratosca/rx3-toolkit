---
paths:
  - "mod/**"
---

# Editing what runs on the deck

- `module.sh` starts with `module_begin <id> <namespace>`; the build checks it against the manifest with a regex (`app/runtime/build.py`, `validate`). `runtime_directory` is one path segment of `[a-z0-9-]`.
- Sourcing a `module.sh` may only register contracts. Mutation belongs in a registered lifecycle hook, and a module that cannot apply steps aside with `return 0`: failing the session to opt out shipped once and cost a session on hardware (`mod/lib/module-api.sh`, the comment above `module_disabled_by_switch`).
- The deck reads `modules/index`, written by the build in dependency order. It never reads `manifest.json`.
- The orchestrator keeps `rbp_stdout.txt` open while the player plays whenever logging is on. Anything that tells the operator ejecting is optional is wrong.
- `build_labels.py` beside the core's assets runs on the computer and needs Pillow; it is the only Python under `mod/`.
- A change here is verified on hardware only. Say so in the changelog entry.
