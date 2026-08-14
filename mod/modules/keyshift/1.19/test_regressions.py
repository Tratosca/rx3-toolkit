#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for the key shift module, all of them measured facts."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parent
KEYSHIFT = (ROOT / "rx3_keyshift.h").read_text()
DECL = (ROOT / "rx3_keyshift_decl.h").read_text()
SHIFTER = (ROOT / "rx3_pitch_shift.h").read_text()
MODULE = (ROOT / "module.sh").read_text()
FEATURE = (ROOT / "rx3_keyshift_feature.h").read_text()
PANEL = (ROOT / "rx3_keyshift_panel.h").read_text()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "register_prepare_hook keyshift_prepare" in MODULE
    and "export RX3_KEYSHIFT=1" in MODULE,
    "the module must announce itself to the core through the environment",
)
require(
    MANIFEST["requires"] == ["core"]
    and "rx3_keyshift_feature.h" in MANIFEST["build_files"]
    and "rx3_keyshift_panel.h" in MANIFEST["build_files"],
    "key shift must declare its core dependency and own its adapters",
)
require(
    "librx3_core.so" in MODULE,
    "the module must decline when the performance core is not selected",
)
require(
    "keyshift_feature_install" in FEATURE
    and "stems" not in FEATURE.lower()
    and "rx3_keyshift_change" in PANEL,
    "key shift must implement only its own lifecycle and panel contracts",
)

# -- where the pitch stage sits ------------------------------------------------

require(
    "#define TIMESTRETCH_OPERATE ((unsigned long)0x000a22a0)" in DECL
    and "#define TIMESTRETCH_FGPR_OPERATE ((unsigned long)0x000a73bc)" in DECL,
    "the stage must sit on both resamplers: the second one replaces the first "
    "while Master Tempo is on, which is why the shift used to vanish",
)
require(
    "GET_STREAM_AT" not in DECL and "GET_STREAM_AT" not in KEYSHIFT,
    "the stage must not return to PcmReader::getStreamAt, a random-access read "
    "shared with the BPM and waveform scan",
)
require(
    "deck_index_for_reader(" in KEYSHIFT,
    "the deck must be identified by the resampler's own PcmReader",
)
require(
    "struct rx3_keyshift_deck" in DECL
    and "keyshift_decks[2]" in DECL
    and "struct deck_context" not in KEYSHIFT,
    "key shift must own its per-deck state instead of sharing stems state",
)

# -- the two engines, and why each direction gets the one it does --------------

require(
    "#define RX3_HYBRID_PITCH 1" in DECL
    and "context->semitones < 0" in KEYSHIFT,
    "lowering pitch must use rbp's engine and raising must use ours: measured "
    "on a 440 Hz tone, the stock one leaves 15.8% of the energy on the note at "
    "+7 semitones and ours leaves 97.3%, while below zero the ranking reverses",
)
require(
    "#define PITCH_ADJUST_PARAMETER ((unsigned long)0x000b5b38)" in DECL
    and "#define PITCH_UNITY_LEVEL_DEPTH 0.5f" in DECL
    and "PITCH_PARAM_LEVEL_DEPTH" in KEYSHIFT,
    "the stock engine must be driven through adjustParameter, including the "
    "level/depth without which it stays bypassed",
)
require(
    "static const signed char semitone_percent[25] = {" in KEYSHIFT
    and "-50, -47, -44, -41, -37, -33, -29, -25, -21, -16, -11, -6, 0," in KEYSHIFT,
    "the stock engine's semitone table must hold the measured percentages",
)
require(
    "object + 0x10u) = PITCH_MAX_FRAMES" in KEYSHIFT,
    "initialize() sizes its buffers from +0x10, so it must cover every block "
    "the hook can pass",
)
require(
    "keyshift_decks[deck].pitch_pending = 1;" in KEYSHIFT
    and "context->pitch_pending = 0;" in KEYSHIFT,
    "key changes must reach the engines on an audio-thread block boundary, not "
    "from the touch thread",
)

# -- our shifter ---------------------------------------------------------------

require(
    "#define RX3_SHIFT_HEADS 2u" in SHIFTER,
    "two heads: three make the power sum constant on paper but the per-head "
    "correlation offsets stop summing coherently, and purity at +5 semitones "
    "fell from 99.0% to 0.6%",
)
require(
    "#define RX3_SHIFT_GRAIN_UP 512u" in SHIFTER
    and "#define RX3_SHIFT_GRAIN_DOWN 2048u" in SHIFTER,
    "the grain must depend on direction: raising pitch repeats material, and a "
    "2048-frame grain returned sixteen hits from an eight-hit impulse train "
    "against nine at 512, while lowering skips material and needs the long grain "
    "for purity",
)
require(
    "rx3_align_head" in SHIFTER and "best_score" in SHIFTER,
    "splices must be aligned by correlation: without it the whole shift came "
    "out at 97.9% of what was asked, a 36 cent error at -12 semitones",
)
require(
    "rx3_sine_table" not in SHIFTER,
    "the crossfade must stay amplitude-complementary: the power-complementary "
    "sine removed about a decibel of pumping and cost four spurious onsets",
)
require(
    "unsigned long whole = (unsigned long)delay;" in SHIFTER,
    "the read position must keep its integer part exact; forming it as one "
    "float rounds away the fraction that carries the shift",
)
require(
    "math.h" not in SHIFTER and "rx3_cos" in SHIFTER,
    "the shifter must stay free of libm: it is compiled -nostdlib",
)

print("Key shift regression guards: OK")
