<!-- SPDX-License-Identifier: MPL-2.0 -->
# Key Sync

Optional automatic transposition in Harmonic mixing. Requires Key Shift for pitch changes and Key Match for compatibility rules. Key Shift and Key Match each remain usable alone.

The module exports the maximum adjustment (1-12 semitones) and mode from plain configuration files. The Key Shift panel exposes its sync action only when Key Sync is loaded and neither Key Sync nor Key Match is disabled. Deselecting Key Sync leaves manual transposition available. Configurations are applied through the common restart-aware environment helper.

The existing native solver, MASTER reference and accepted key set are described in [Transposition](../../../REFERENCES.md#doc-transposition). No hardware validation has been added by this separation.
