<!-- SPDX-License-Identifier: MPL-2.0 -->
# Offline OverCue audio prototype

Build with `make overcue-audio` using a Rust toolchain. `Cargo.lock` pins the dependencies, including `ebur128` 0.1.10. The executable is `build/overcue-audio/release/rx3-overcue-audio` (with `.exe` on Windows). Application packaging includes it when built for the current platform. It is never part of the RX3 firmware.

The helper reads stereo little-endian float32 and provides three commands:

```
rx3-overcue-audio resample INPUT OUTPUT COEFFICIENTS
rx3-overcue-audio measure INPUT
rx3-overcue-audio quantize INPUT OUTPUT GAIN
```

Resampling accepts 44.1 kHz input and produces 96 kHz output with floor frame count, 320 phases and 59 coefficients per phase. Coefficients are a local float32 profile in tap-major order, with phases contiguous. Accumulation is sequential float64 without fused multiply-add; boundary accumulation proceeds in the opposite order to interior accumulation, following the inspected reference. No delay compensation is added. Measurement uses 100 ms blocks, reconstructs the momentary and short-term windows from their energies, and reports whether the final block is complete. Quantization multiplies in float32, clamps to [-1, 1], scales by 32767 and rounds halves away from zero. Existing output files are refused.

The validated coefficient profile SHA-256 is `df98a625978e21767f978986565ab5a6f6b345bf0a0a576f57b64d14e0006713`. The 75,520-byte numerical reference table is now included at `app/stems/data/overcue-44100-96000.f32` and in the application resources. Its origin is the numeric table at preferred address `0x100d5db88` in the identified Desktop 2.1.9 binary documented in `docs/overcue-static-analysis.md`; it is not an independently designed Toolkit filter. The Python adapter selects the bundled table and checks its hash before invoking this helper. Export does not execute or require an installed copy of OverCue.

Integration and numerical acceptance results are in `docs/overcue-prototype.md`. The Python tests in `tests/test_overcue_exact.py` exercise the native executable when built, including phase ordering, frame count, signed rounding, partial measurement windows and invalid input. They do not establish cross-platform bit identity or CDJ playback.
