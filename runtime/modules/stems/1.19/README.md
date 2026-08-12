# RX3 stems runtime, firmware 1.19

Volatile stem component for XDJ-RX3 firmware 1.19. It loads the audio hook
through `LD_PRELOAD`; it does not write NAND.

## Files

- `module.sh`: prepares the shared object and registers the stem lifecycle
  hooks with the root runtime orchestrator.
- `rx3_stems_hook.c`: asynchronous sidecar loader, audio component mixer, pad
  handler, and deck-specific LED state.
- `test_regressions.py`: static guards for hardware-confirmed behavior.

Build and architecture details are in [docs/reference.md](../../../../docs/reference.md#stems-internals).

## USB layout

```text
autoexec.bin
RX3_STEMS/
  Artist - Title.rx3stem
```

The sidecar basename must match the audio basename exactly. Tracks without a
matching valid sidecar use the stock audio and Slip Loop paths.
