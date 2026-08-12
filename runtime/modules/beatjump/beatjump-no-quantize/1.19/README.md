# Direct Beat Jump

Replaces the branch to `startPlayQuantizeForJump()` with an ARM NOP on RX3
firmware 1.19. Execution continues through the adjacent direct Beat Jump path.
Global Quantize, Hot Cues, loops, and Beat FX are unchanged.

`patch.py` applies the guarded word offline. `module.sh` registers the same
word with the volatile runtime orchestrator.

```sh
python3 runtime/modules/beatjump/beatjump-no-quantize/1.19/patch.py rbp --check
python3 runtime/modules/beatjump/beatjump-no-quantize/1.19/patch.py rbp -o rbp.direct
python3 runtime/modules/beatjump/beatjump-no-quantize/1.19/patch.py rbp.direct \
  --revert -o rbp.restored
```
