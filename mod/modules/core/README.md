<!-- SPDX-License-Identifier: MPL-2.0 -->
# Shared runtime core

The application selects this dependency when a module needs shared in-process services. It builds one `librx3_core.so`, preloaded into rbp. Modules use the public service contract; the core owns shared mechanisms and firmware integration. Separate compilation does not isolate a module crash from the player.

## Source layout

| Directory | Responsibility |
| --- | --- |
| `api/` | Public module and service contracts, opaque handle types, DSP kernels and ARM ABI declarations. `rx3_feature_api.h` is the legacy panel contract pending migration. |
| `runtime/` | Module composition, startup, shutdown and lifecycle dispatch. |
| `services/` | Hook ownership, logging, notification queue, mix observations and reusable DSP implementations. |
| `firmware/` | ARM code patching and the adapter to rbp's native caution messages. |
| `ui/` | Panel layout, atlas, widgets and translated notice text. |
| `diagnostics/` | Render probe record format. |
| `assets/` | Artwork shipped to the player. `build_labels.py` builds it on the computer. |

`rx3_core_hook.c` remains at the root as the legacy performance integration entry point. It still contains native draw/input/audio coordination and includes the features awaiting migration. Moving its helpers into directories does not complete that migration.

`manifest.json` declares every packaged build input and additional compilation unit. Both the Makefile and application builder use it. Header rebuild dependencies and firmware-address inspection recurse into the service directories. `module.sh` owns the shell-side installation and launch contract.

## Native messages

rbp already renders notices such as EMERGENCY LOOP through `ui::Caution`. The adapter in `firmware/rx3_message.h` uses `ui::Caution::set` and the player's B051 caution object for toolkit messages. It does not overwrite the Emergency Loop message or introduce a separate text renderer.

`services/rx3_notice.c` only arbitrates toolkit requests: copied text, ownership, queue order, priority, duration and cancellation. Native placement and rendering stay with rbp, and calls run on its render thread. Toolkit queue priority does not override the player's own caution priority. The adapter's hardware behaviour is still awaiting acceptance on the RX3.

New modules call `services->notices->post(...)`. The legacy translated startup notice uses the same queue through a local adapter. `RX3_MESSAGES=0` or `/tmp/rx3-messages.off` disables toolkit notifications. This switch does not disable rbp's own warnings.

## Building and extending

Run `make hook test preflight PYTHON=.venv/bin/python`. The symbol test rejects imports outside the known player set; the framework tests compile modules without the performance implementation and rebuild from packaged manifest inputs.

New runtime modules include `api/rx3_module_api.h`, register a descriptor in `runtime/rx3_composition.c` and list their unit in the manifest. Do not add their implementation headers to the legacy entry point. See [the framework contract and migration status](../../../docs/runtime-framework.md) for ownership, calling rules, examples and pending services.
