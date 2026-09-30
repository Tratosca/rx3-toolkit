<!-- SPDX-License-Identifier: MPL-2.0 -->
# Shared runtime core

The application selects this dependency when a module needs shared in-process services. It builds one `librx3_core.so`, preloaded into rbp. Modules use the public service contract; the core owns shared mechanisms and firmware integration. Separate compilation does not isolate a module crash from the player.

## Source layout

| Directory | Responsibility |
| --- | --- |
| `api/` | Public module and service contracts, opaque handle types, DSP kernels and ARM ABI declarations. Modules include nothing else from the core. |
| `runtime/` | Module composition, startup, shutdown and lifecycle dispatch. |
| `services/` | Hook ownership, logging, notification queue, mix observations, reusable DSP, and the shared input, audio, image, memory and loading services. |
| `firmware/` | ARM code patching and the adapter to rbp's native caution messages. |
| `ui/` | Panel layout, atlas, widgets and translated notice text. |
| `diagnostics/` | Render probe record format. |
| `assets/` | Shared glyph atlases and native neutral STATUS frame only. Module-specific artwork belongs to the module; `build_labels.py` builds the shared atlases. |

`rx3_core_hook.c` is the performance entry point: the constructor and destructor, the PcmReader::load deck-identity adapter, the native draw, touch and tab adapters, the private image tables and the panel painter. It names no feature and includes no module file; every feature is a separate module unit that reaches it through `api/`.

`manifest.json` declares every packaged build input and additional compilation unit. Both the Makefile and application builder use it. Header rebuild dependencies and firmware-address inspection recurse into the service directories. `module.sh` owns the shell-side installation and launch contract.

## Native messages

rbp already renders notices such as EMERGENCY LOOP through `ui::Caution`. The adapter in `firmware/rx3_message.h` uses `ui::Caution::set` and the player's B051 caution object for toolkit messages. It does not overwrite the Emergency Loop message or introduce a separate text renderer.

`services/rx3_notice.c` only arbitrates toolkit requests: copied text, ownership, queue order, priority, duration and cancellation. Native placement and rendering stay with rbp, and calls run on its render thread. Toolkit queue priority does not override the player's own caution priority. The adapter's hardware behaviour is still awaiting acceptance on the RX3.

New modules call `services->notices->post(...)`. The translated startup notice uses the same queue through a local adapter. `RX3_MESSAGES=0` or `/tmp/rx3-messages.off` disables toolkit notifications. This switch does not disable rbp's own warnings.

## Building and extending

Run `make hook test preflight PYTHON=.venv/bin/python`. The symbol test rejects imports outside the known player set; the framework tests compile modules without the performance implementation and rebuild from packaged manifest inputs.

New runtime modules include `api/rx3_module_api.h`, register a descriptor in `runtime/rx3_composition.c` and list their unit in the manifest. See [the framework contract](../../../REFERENCES.md#doc-runtime-framework) for ownership, calling rules and examples.

`tests/test_module_boundaries.py` rejects any include outside `api/` from a module and any module include from the core, with no exception. `tests/test_extracted_modules.py` links every module unit alone and checks it imports libc names only. See the [asset ownership contract](../../../REFERENCES.md#doc-runtime-framework--asset-ownership-and-enforced-boundary).
