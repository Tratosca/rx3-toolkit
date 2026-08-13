# Beat Jump +/-32

Changes the two outer Beat Jump pads from -8/+8 to -32/+32 on RX3 firmware
1.19. The patch also updates the availability guard, LED threshold, and
on-screen pad images.

`module.sh` registers the guarded words with the volatile runtime orchestrator.
`tools/rx3_patcher/beatjump_32bars.py` applies the same words offline, to an
extracted `rbp` on a workstation. The two tables are compared word by word by
`tests/test_module_consistency.py`, so neither is the reference: they must agree.

```sh
python3 -m tools.rx3_patcher.beatjump_32bars rbp --check
python3 -m tools.rx3_patcher.beatjump_32bars rbp -o rbp.32bars
python3 -m tools.rx3_patcher.beatjump_32bars rbp.32bars \
  --revert -o rbp.restored
```

The VFP immediate at the negative jump site cannot encode 32.0. The patch
loads the IEEE-754 value through `r5` and uses a single-precision absolute-value
path. The GUI has no directional 32 image, so the non-directional 32 image from
Beat Loop is reused. The jog display is not modified.
