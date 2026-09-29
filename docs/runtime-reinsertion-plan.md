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
| Core assets | Core binary and artwork are now compared and staged without changing live paths. Changed assets request a restart; unchanged files retain their inode. | Device validation must show that an unchanged insertion keeps the PID and that changed artwork appears only after a safe restart. |
| Samples | The active bank name, settings and numbered WAV contents now form a startup generation. A moved bank with identical bytes may repoint the live link; a changed or disabled bank stages its link transition and requests a restart. | Host tests cover moved, changed-name and changed-audio banks. Measure hashing cost and validate pad state/playback on the device. |
| Module removal | The ordered module index and active deck switches are now exported as `RX3_RUNTIME_MODULE_SET`. Removing or disabling a feature while Core remains selected requests a restart. | Host tests cover that comparison; removing Core itself still needs an explicit unload and guarded-word migration. |
| Recovery | Core and Logo changes are published after `rbp` stops. Old files remain in a private same-filesystem stage until the replacement is ready, and rollback restores them before relaunching the previous process. | Host tests cover deferred, partial-commit and optional-file rollback. Device and launch-failure validation remain; Samples links and module removal are not yet transactional. |
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
   of that identity. Module selection and Samples content markers are
   implemented; an older build without them restarts once. Core removal still
   needs an explicit unload path.
2. Split preparation into read-only planning, private staging and one committed
   transition. A no-op does not rewrite assets. A deferred restart does not
   replace files used by the current process. Core/Logo and changed Samples
   links use private staging; a moved identical bank can repoint its live link.
3. Check the actual `rbp` executable, loaded core and current readiness. Avoid
   using a stale ready marker as sole evidence. State why a restart is requested
   in the session log. PID-bound readiness, executable identity and core
   mapping checks are implemented locally; device proof remains.
4. Make recovery generation-aware: preserve previous core/art files until the
   replacement process is ready, restore them on failure and test a second
   insertion after recovery. Core/Logo rollback and a subsequent file commit
   are host-tested; full orchestrator and device tests remain.
5. Exercise unchanged, moved, changed, removed, interrupted and two-drive
   cases in host tests. Validate the active core, framebuffer and useful input
   response in the emulator, then verify PID and playback continuity on an RX3.

No hardware claim follows from host tests or the ARM build alone. The current
CI failure must also be resolved before release qualification.
