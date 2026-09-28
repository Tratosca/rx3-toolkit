# Browse Columns

Adds a third metadata column to the native Browse track list. The two native
columns keep their existing source and Rekordbox configuration. Folder/category
navigation remains native. While this module is active, the floating Browse
LOAD 1 / LOAD 2 buttons are hidden and their touch actions are disabled. The
selected row keeps all three values; use the physical LOAD buttons to load a
track. Other screens retain their native controls.

Tap a track-list column heading to sort the complete native list by that field;
tap the active heading again to reverse its order. A small arrow identifies the
active heading and direction. The selected track is retained by its database ID,
and sorting does not replace the configured columns. A drag away from the
heading cancels the tap. Folder/category lists and an open native menu do not
capture these gestures.

Overflowing text in the selected row reuses the two native scrolling surfaces.
It pauses for two seconds, moves at 50 pixels/second until the last character
has left the cell (plus 24 pixels of trailing space), then returns to the start
and pauses again. The added third field stays visible; it does not gain a
separate scrolling surface.

Choose **BPM** (default), **Key (Camelot)**, **Artist**, or **Duration** in the
Toolkit module settings. The build writes inert `column.txt` data; `module.sh`
validates the field and exports `RX3_BROWSE_FIELD`. No settings code is executed.

## USB settings

The inspected Rekordbox 7.2.16 export has `MYSETTING.DAT`, `MYSETTING2.DAT`, and
`DEVSETTING.DAT`. No third-column selection was identified. Rekordbox's existing
Column preference is distinct from player My Settings and is preserved.

- [Official Rekordbox 5.5 manual — device Column preference](https://cdn.rekordbox.com/files/20200214194946/rekordbox5.5.0_manual_EN.pdf)
- [rekordcrate settings structures](https://github.com/Holzhaus/rekordcrate/blob/main/src/setting.rs)

The third column is therefore selected in this module, not inferred from unused
USB bytes. Supporting a future export format requires identifying its actual
field; missing or unrecognised configuration defaults to BPM.

## Framework boundary

`core/services/rx3_browse.c` owns the native row hook, database record ownership,
UTF-16 transport, drawing and native sort dispatch. This module only chooses a
field and caption.
Key Match registers its own classification and image callbacks through the same
public service, so both modules can run without competing hooks.

Metadata queries run on the native database worker after its row stream has
finished. Bounded copies travel inside each queued row; no database work or
track-name matching occurs in the renderer. Native strings and records are freed
with their original allocators. No exported USB file is rewritten. Header touches enqueue a private native UI
message; the Browse worker issues the normal database request. A guarded database
dispatch hook preserves the direction across the native signed-byte conversion,
scoped to the current native task. The existing comparator performs the actual
sort, including cached requests; the renderer never reorders a visible page.

Firmware entry points are guarded against the examined rbp 1.19 image:
SHA-256 `60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`.
Compilation or emulator validation does not establish physical RX3 validation.

## Validation (2026-09-26)

- 90 host tests pass: inert configuration and shell export, Toolkit selection
  and persistence, shared hook ownership, UTF-16 bounds, marker coexistence,
  partial lifecycle cleanup, native sort handoff and comparator direction,
  packaged ARM build/imports, and runtime regressions.
- Native rbp 1.19 emulator: BPM values and Camelot values checked on the copied
  USB library; loading, playback, master-key changes, and the
  untouched Artist/Album navigation checked visually.
- Floating LOAD buttons removed with all three values visible on selected rows;
  tapping both former targets leaves decks unloaded. Physical LOAD 1 and LOAD 2
  successfully load separate tracks. Partial touch-hook failure rolls back cleanly.
- Header sorting checked in both directions for Title, Artist and BPM; the
  selected track remains selected and loads through physical LOAD 1.
- Toolkit settings rendered and exercised in a real browser at desktop and
  narrow widths; Impeccable detector reports no findings in the changed JS.
- Evidence and reproduction in the sibling emulator repository:
  `outputs/browse-columns-release-check/`, `outputs/browse-columns-pass/`, and
  `outputs/browse-columns-no-load/`, `outputs/browse-columns-sort-direction/`,
  `outputs/browse-columns-sort-final/`, and `outputs/browse-columns-sort-validated/`.
  No physical RX3 validation is claimed. Artist and Duration configuration are
  tested; dedicated native captures cover BPM and Camelot.
