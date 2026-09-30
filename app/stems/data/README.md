# OverCue reference resampling table

`overcue-44100-96000.f32` is the numerical coefficient table from the local OverCue Desktop 2.1.9 reference described in the [OverCue static analysis](../../../REFERENCES.md#doc-overcue-static-analysis). It is not a filter designed independently by the Toolkit. Its inclusion was requested for the experimental compatible exporter; no OverCue executable or installed application is needed at export time.

The table contains 320 phases with 59 taps each, stored as 18,880 little-endian float32 values in tap-major order (75,520 bytes). SHA-256: `df98a625978e21767f978986565ab5a6f6b345bf0a0a576f57b64d14e0006713`. `NativePreparation` verifies this hash before using either the bundled table or an explicit override. A changed or missing table disables the experimental export rather than selecting another filter silently.

The application packaging specification includes the table as `stems/overcue-44100-96000.f32`. Build the independent helper with `make overcue-audio` before packaging to include it as well. This data is used on the computer only; RX3 playback remains native `.rx3stem`.
