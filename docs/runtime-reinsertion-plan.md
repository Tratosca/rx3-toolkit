<!-- SPDX-License-Identifier: MPL-2.0 -->
# Runtime reinsertion and recovery plan

## Contract

Reinserting an unchanged mod must leave the running `rbp` PID, its loaded core,
its hook order and its audio state unchanged. The orchestrator may recheck the
drive and repoint drive-dependent links. A changed module set, core binary,
startup setting or resource consumed only at startup requires a planned restart
when the media guard permits one. Unknown firmware, patch words or process state
must stop before writes.

The first local branch merges PR #34 with the current core layout. It preserves
the same-boot removal of the former `librx3_stems.so` preload. A second commit
avoids replacing unchanged core/logo images and avoids recreating stems/sample
links when they already point at the selected directory. Those changes do not
establish the full contract below.

## Verified code observations

| Area | Current behavior | Consequence to test or change |
| --- | --- | --- |
| No-restart path | The core now publishes its PID on readiness; reuse requires that PID and an executable mapping of the installed core inode. The orchestrator also checks that the live `rbp` executable is the guarded file before proceeding, and a replacement launch checks its own PID marker. | Host tests cover stale markers, old/deleted mappings and executable mismatches; verify `/proc/<pid>/maps` and continuity on an RX3. |
| Core assets | `mod/modules/core/module.sh` installs art before the resident decision. Identical files are now left in place. | Changed art may not reach an already loaded image table. Compare the desired and resident resource generation before deciding. |
| Samples | `mod/modules/samples/module.sh` can repoint `/tmp/rx3-samples`, but `rx3_samples_feature.h` reads and stores the bank in memory in its loader. | A different active bank or bank contents cannot be considered live merely because the link changed. |
| Module removal | The current image loads modules from its index; `module_export` compares settings only for loaded modules. | Verify that removing a module causes the old process to stop using it. This transition lacks a dedicated test. |
| Recovery | Core binary and assets can be replaced during prepare, before `rbp` is stopped. Rollback restores guarded `rbp` words and the previous preload string. | Snapshot and restore the previous core/resource generation too; otherwise a rollback can relaunch previous words against newly installed files. |
| Concurrency | `mod/autoexec.sh` uses the fixed `/tmp/rx3-runtime` workspace and now claims `/tmp/rx3-runtime.lock` before clearing it. | A concurrent invocation stops; a lock left by SIGKILL fails closed until reboot or manual inspection. Host contention is tested; device launcher behavior remains to verify. |

## Decision matrix

| Event | Expected action |
| --- | --- |
| Same image, settings, startup resources and mount | Recheck state, keep PID and links unchanged. |
| Same image and settings, drive returns under another device name | Repoint drive-dependent links; keep PID. |
| New core, changed startup asset, changed sample bank or settings | Stage the new generation; restart only when the media guard says it is safe. |
| Module removed or disabled | Compare the complete desired module set with the live one; restart safely to withdraw the old feature. |
| Unexpected patch word, unrecognized binary or ambiguous live process | Stop without installing anything. |
| Another DJ drive mounted and restart required | Defer the change without stopping playback or replacing live resources. |
| Startup or readiness failure after a restart | Restore the prior binary, core, resources and preload together, then verify the restored player. |

## Work sequence

1. Record the desired and live generations: core hash, ordered module set,
   startup settings and startup resources. Keep drive-dependent stems paths out
   of that identity. Specify how older builds without a generation marker are
   upgraded once.
2. Split preparation into read-only planning, private staging and one committed
   transition. A no-op does not rewrite assets. A deferred restart does not
   replace files used by the current process.
3. Check the actual `rbp` executable, loaded core and current readiness. Avoid
   using a stale ready marker as sole evidence. State why a restart is requested
   in the session log. PID-bound readiness, executable identity and core
   mapping checks are implemented locally; device proof remains.
4. Make recovery generation-aware: preserve previous core/art files until the
   replacement process is ready, restore them on failure and test a second
   insertion after recovery.
5. Exercise unchanged, moved, changed, removed, interrupted and two-drive
   cases in host tests. Validate the active core, framebuffer and useful input
   response in the emulator, then verify PID and playback continuity on an RX3.

No hardware claim follows from host tests or the ARM build alone. The current
CI failure must also be resolved before release qualification.
