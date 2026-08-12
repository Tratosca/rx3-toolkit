# Beat Jump +/-32

Changes the two outer Beat Jump pads from -8/+8 to -32/+32 on RX3 firmware
1.19. The patch also updates the availability guard, LED threshold, and
on-screen pad images.

`patch.py` applies the guarded words offline. `module.sh` registers the same
words with the volatile runtime orchestrator. The offsets in `patch.py` are the
reference for both.

```sh
python3 runtime/modules/beatjump/beatjump-32bars/1.19/patch.py rbp --check
python3 runtime/modules/beatjump/beatjump-32bars/1.19/patch.py rbp -o rbp.32bars
python3 runtime/modules/beatjump/beatjump-32bars/1.19/patch.py rbp.32bars \
  --revert -o rbp.restored
```

The VFP immediate at the negative jump site cannot encode 32.0. The patch
loads the IEEE-754 value through `r5` and uses a single-precision absolute-value
path. The GUI has no directional 32 image, so the non-directional 32 image from
Beat Loop is reused. The jog display is not modified.
