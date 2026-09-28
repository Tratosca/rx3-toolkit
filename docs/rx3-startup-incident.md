# RX3 startup incident, 2026-09-28

The operator reported that inserting DJ FRANCOIS restarted rbp, briefly showed the mod, then returned to an unmodified player without any control input. No audio or player restart was initiated during this investigation.

## Evidence and limits

The mounted drive's manifest selects firmware 1.19 and eleven modules: core, decoder-sleep, beatjump-32bars, beatjump-no-quantize, keyshift, key-match, key-sync, browse-columns, stems, search-latin and logo. It selects neither logging nor telnet. The 2,664,448-byte autoexec.bin matches its manifest SHA-256, `3bc8fe52649079d50dd3c139656d2b6e889aabda84e8d0aef40794d32262cd02`.

The surviving USB files are mod-previous.txt, rbp_stdout-previous.txt and rbp_stdout.txt. They contain an active-hook message, repeated PcmReader::load guard refusals, two unqualified Segmentation fault lines, and a separate launch with no preload. They do not identify the crashed process or prove that these records describe the latest image. They must not be presented as a backtrace or a confirmed cause of this incident. The full session log for the latest insertion is absent.

After the direct network was reconnected, 169.254.177.105 refused TCP port 23. RAM logs, the current player mappings, and kernel diagnostics could not be read. The fifty checks performed by scripts/check_addresses.py against the owner-local stock 1.19 player all passed; this does not verify live device memory or the installed hook binary.

## Confirmed source defect and correction

The performance-core constructor previously ran whenever the shared library was loaded, including in utilities launched with an inherited LD_PRELOAD. Before checking any player prologue it configured the shared log and truncated /tmp/rx3-performance.ready. It could then attempt firmware-specific accesses inside a different executable. This makes guard refusals and child-process faults plausible, and a missing readiness marker can cause the orchestrator to restore the previous player. It is a concrete defect, but remains an unconfirmed explanation of this particular restart.

The constructor now reads /proc/self/comm and proceeds only for rbp. A missing, unreadable or different process identity returns before logs, readiness files, modules or firmware addresses are touched. The destructor also returns unless initialization was admitted for the player. No new dynamic imports were added. Host tests execute the real constructor and destructor control flow with stubbed firmware boundaries, check utility names and read failures, preserve an existing readiness marker in the rejected process, and retain player cleanup ordering.

## Initial hardware check

The operator rebuilt the drive with the corrected core, Telnet and verbose logging. The new manifest identifies a 2,678,784-byte image with SHA-256 `d98ee04d19ffe1cf9736ed38af2358ad48d0a83d57401f26e5e3933acc3a50af`. No firmware key was accessed by the investigation.

Read-only Telnet checks on the reconnected device found rbp PID 3491 unchanged from uptime 129.82 to 373.65 seconds (244 seconds of direct observation). Its mappings include /root/pdj/librx3_core.so, LD_PRELOAD names that object, and /tmp/rx3-performance.ready contains ready. Device and corrected local core share MD5 `d7f15200df255436a4faa0839ce96ebb`. Current player stdout contains no segmentation fault, and a kernel-log search found no segfault, oops, killed-process or out-of-memory report. The reported thermal value increased from 59 to 61 degrees Celsius. No audio, player restart or deployment was initiated by the investigator; operator interaction appears in the keyshift logs. This confirms the corrected hook remains loaded during this short hardware observation, not a prolonged thermal or stems-playback validation, nor a retrospective proof of the original crash cause.

The repeated startup pass also exposed two independent prepare-hook failures: Key Match and Browse Columns leaked module_export's no-change return status when settings were already present. Their prepare hooks now explicitly return success after exporting settings. A shell regression exercises initial application, unchanged reapplication without restart, and genuine missing-core failure for both modules. All 25 module API, Key Match and Browse Columns tests passed. This shell correction is local only and was not deployed into the running session.

The first startup log's inactive-core warning conflicts with the live ready marker, mappings and active-hook log. Its exact logging/lifecycle timing remains unresolved. Preserve session.txt, mod.txt, rbp_stdout.txt and rbp_restore.txt together with process mappings and kernel diagnostics if a restart recurs.

Owner-local copies and artifact hashes are under local/research/rx3-restart-20260928/. The mounted USB contents were not changed.
The follow-up Telnet transcript is preserved as local/research/rx3-restart-20260928/reconnected-session.txt.
