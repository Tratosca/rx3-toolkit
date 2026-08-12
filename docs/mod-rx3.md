# The RX3 mod

What the modules do, how the runtime is applied, and how to read what it left
behind. For a first run, follow the [Quick Start](quickstart.md) instead.

## The modules

| Module | Id | What changes | On by default |
|---|---|---|:--:|
| Beat Jump ±32 | `beatjump-32bars` | Beat Jump pads 7 and 8 become -32 and +32 beats instead of -8 and +8. The availability guard, the LED threshold and the pad images follow. | yes |
| Immediate Beat Jump | `beatjump-no-quantize` | Repeated jumps fire at once instead of waiting for the stock half-bar grid quantization. Global Quantize, Hot Cues, loops and Beat FX are untouched. | yes |
| Faster decoder polling | `decoder-sleep` | The decoder thread checks for decoded audio every 0.1 ms instead of every 1 ms, so large jumps can be repeated sooner. No control, no display. | yes |
| Vocal and instrumental controls | `stems` | Slip Loop pads 7 and 8 become independent instrumental and vocal switches on tracks that have a `.rx3stem` sidecar. | yes |
| Diagnostic Telnet access | `telnet` | Starts a BusyBox telnet service for inspection. | no |

Tracks without a matching sidecar keep their normal dotted Slip Loop behaviour.

Telnet is unencrypted and reachable only through the rear computer USB type-B
port, which exposes an Ethernet interface in the APIPA `169.254.x.y` range. Use
it on an isolated link, or leave it off, which is the default.

## What actually happens on insertion

The RX3 looks for `autoexec.bin` on every drive you insert. If it decrypts, the
device mounts the ISO image inside it and runs the `autoexec.sh` it contains as
root. That path is the manufacturer's, not this project's.

```text
RX3 powered on
USB insertion
  /etc/udev/rules.d/12-usb-memory-auto-mount.rules
  /root/pdj/decrypt_autoexec.sh <usb-mount>
    decrypts autoexec.bin with the key and mounts the ISO
    runs ./autoexec.sh <usb-mount> as root
```

`runtime/autoexec.sh` holds the shared lifecycle: discovery, RAM-root
validation, guarded writes, process restart, rollback and logging. Each module
owns its own adapter and payload. Adding or removing one requires no change to
the orchestrator.

Nothing is flashed. The modules patch the copy of the player application, `rbp`,
held in the RAM root filesystem the RX3 assembles at boot. Power cycling
discards it.

## Applying it

1. Make sure the drive is disconnected.
2. Power the RX3 on and wait until the interface is fully loaded.
3. Insert the drive.
4. Leave the controls alone while the interface stops and restarts.
5. Wait for the interface before loading a track.

Reinserting a drive on a session that is already patched costs nothing. The
orchestrator restarts `rbp` only for a word still holding its stock value, or a
module whose runtime part is not already live, so the interface neither freezes
nor rescans the drive. That run logs `nothing to apply: rbp already runs every
selected module`. A drive carrying a newer build of the stems component, or a
different `RX3_STEMS` location, is applied normally.

## Reading the session log

Every run writes `RX3_RUNTIME/session.txt` to the drive. Read it from your
computer.

| Line | Meaning |
|---|---|
| `=== complete ===` | The run finished. This is the last line of a good run. |
| `OK: rbp active` | The player was restarted and came back. Present whenever a restart was needed. |
| `nothing to apply: ...` | Everything selected was already live. Not an error. |
| `STOP: ...` | A precondition failed and nothing was modified. |
| `FAILED: ...` | Something went wrong during modification, and the previous state was restored. |

On `STOP:` or `FAILED:`, delete `autoexec.bin` from the drive before using the
RX3 again, then see [Troubleshooting](troubleshooting.md#the-session-log-says-stop-or-failed).

The stems component keeps its own log on the device at `/tmp/rx3-stems.log`,
which is only reachable with the Telnet module enabled.

## Before it touches anything

The orchestrator verifies all of the following, and refuses the whole run if any
of them fails:

1. the effective root mount is `tmpfs`, `ramfs` or `rootfs`;
2. `/root/pdj` is not a separate mount;
3. the `rbp` SHA-1 is one it explicitly supports;
4. every word it intends to change currently holds either its stock or its
   already-patched value;
5. `rbp` is stopped before its backing file is written;
6. every write is read back and compared;
7. the replacement process stays alive for eight seconds, or the previous bytes
   and preload state are restored and `rbp` is started again.

Stopping the process first is not optional: writing the backing file while its
executable pages are mapped can kill it with `SIGBUS`.

## Removing it

1. Stop playback and power off.
2. Remove the drive.
3. Power on without it, and confirm stock behaviour.
4. Delete `autoexec.bin` from the drive if it should stop applying on insertion.

Power cycling clears the RAM changes on its own, but leaving the drive connected
re-applies `autoexec.bin` at the next boot. Remove it before verifying stock
behaviour or testing a different module selection.

## Safety

- Firmware `1.19` only.
- Keep a second, unmodified Rekordbox drive available.
- Start the RX3 completely before inserting the runtime drive.
- Never disconnect the drive or cut power while the runtime is being applied or
  a track is loading.
- To clear every modification: power off, remove the drive, power on.
- Read `RX3_RUNTIME/session.txt` before reporting a problem.
- Telnet traffic is unencrypted. Isolated links only.
