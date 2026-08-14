# Direct Beat Jump

Replaces the branch to `startPlayQuantizeForJump()` with an ARM NOP on RX3
firmware 1.19. Execution continues through the adjacent direct Beat Jump path.
Global Quantize, Hot Cues, loops, and Beat FX are unchanged.

`module.sh` registers the guarded word with the volatile runtime orchestrator.
`tools/rx3_patcher/beatjump_no_quantize.py` applies the same word offline, to an
extracted `rbp` on a workstation. `tests/test_module_consistency.py` compares
the two, so neither is the reference: they must agree.

```sh
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp --check
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp -o rbp.direct
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp.direct \
  --revert -o rbp.restored
```
