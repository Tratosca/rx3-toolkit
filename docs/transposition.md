<!-- SPDX-License-Identifier: MPL-2.0 -->
# Transposition reference and compatibility

The Harmonic mixing category contains independent Key Shift and Key Match modules. Key Sync requires both and owns the automatic mode and range settings. Key Shift alone exposes only the manual stepper. BROWSE suggestions and KEY SYNC share the optional Key Match rule mask. New desktop preferences use compatible mode, a one-semitone allowance and no extensions. Saved preferences are retained. Old runtime packages without settings keep their historical defaults; newly generated packages always contain explicit values.

## Reference contract

The BROWSE service publishes a copied local MASTER index, effective Camelot key and 24-bit native compatibility set. KEY SYNC consumes this contract; it does not infer that the other deck is MASTER. The reference deck has an inert MASTER status. No local MASTER, unknown reference data or a stale source key produces no sync action.

The native set is captured when BROWSE processes its track list. If BROWSE has not supplied a usable set yet, KEY SYNC waits for that data. A load notification clears the corresponding published key and native snapshot. A reference-deck change rejects the previous deck's snapshot. A published source key inconsistent with the snapshot also rejects it. The service carries source keys separately from shifts and rotates the accepted set with a transposed MASTER. The native Traffic Light display flag remains in control of BROWSE highlighting. Native green classifications remain authoritative; the module no longer adds presumed classic matches independently.

The stored music-ID device byte identifies a storage source, not a deck. Both decks may load from the same USB source. MASTER association uses the explicit native per-deck flag and never derives a deck number from that byte. Network or ambiguous MASTER states are unavailable to KEY SYNC.

## Static firmware evidence

The inspected 1.19 rbp SHA-256 is `60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`. `GetTrafficTargetTrackInfo` at `0x001c7da8` calls `CmnFunc_CmnInfo_GetSyncMasterPlayerNo`, checks local MASTER flags via `CmnFunc_CmnInfo_IsMasterON` at `0x0018579c`, and then obtains the playing music ID. Its native fallback can consult the on-air player; the modification requires an unambiguous local MASTER for sync offers.

`UpdateTrafficLightKeySet.part.0` at `0x001c7e9c` populates the four key IDs at BROWSE context offsets `0x10b08` through `0x10b14`. `GetTrafficLightOnFlg` compares candidates against those values. The shared service copies those actual values instead of substituting a generic wheel formula. IDs are one-based, interleaved A/B; the public contract is zero-based. The MASTER accessor's first eight instruction bytes are checked before use on ARM.

This is static 1.19 evidence and host-test coverage, not hardware validation or proof of other firmware versions. On an unsupported MASTER accessor, the service returns an unavailable reference.

## Preview and checks

The preview reads no USB drive, player or music library. Its fictional MASTER is 8A, with a declared native example set of 7A, 8A, 8B and 9A. All candidate colours and KEY SYNC results are calculated by the Python service using the current controls. The pure C solver and Python implementation are compared across 82,944 combinations of source key, reference key, selected rules, mode, range and existing shift. Native-set tests include an observed set that differs from classic wheel adjacency, MASTER changes, source-device independence, pitch changes and load invalidation. WebKit verification covers both languages at 880x560.

Not yet run on hardware. Hardware acceptance must check changing MASTER while KEY is open, loading a new MASTER track, transposing MASTER before reopening BROWSE, source-drive changes, native Traffic Light settings and the absence of an actionable KEY SYNC on MASTER.

## Deck key metadata

Key Shift observes `UiBrowseComm_SetPlayTitleLine` and `UiBrowseComm_ConvInfoListToDeckList` after the native browse communication task updates its deck cache. `getUiPlayKeyLinePointer` uses deck indices 0 and 1; category 15 contains the UTF-16 key. The observer performs no database request or drawing. An empty or invalid key clears the previous value. Decoder loading still resets pitch, but does not erase newer metadata. Text observation remains a fallback if the guarded native hooks cannot be installed.

The machine emulator reproduced a missing DECK 2 key with DECK 1 empty: the native panel showed 1A and Key Shift showed KEY --. Observing the native deck cache made Key Shift show 1A for that same load. Hardware validation remains pending.

MASTER changes also use the latest published deck key immediately. If the native Browse compatibility snapshot still belongs to the previous MASTER or track, Key Sync temporarily uses the classic Camelot set (same key, relative major/minor, adjacent wheel numbers). A matching native snapshot takes precedence once available, preserving its exact key set. No MASTER or an unknown key yields no automatic action.
