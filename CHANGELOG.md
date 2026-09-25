<!-- SPDX-License-Identifier: MPL-2.0 -->
# Changelog

## Unreleased

- Now playing: a new module sends what each deck is playing to the computer on the rear USB port, as one JSON datagram on UDP 50123 whenever a deck changes and every two seconds: title, track id, BPM, tempo, play mode and on-air state for both decks. `scripts/now_playing.py` prints it. It merges the event hooks from evanpurkhiser's USB telemetry prototype (#32) with the UDP transport from jacksight's Now Playing export (#20), runs inside the performance core and stops its worker when removed. Off by default. Not yet run on hardware.
- Compute optional per-role Blue/RGB waveform columns from published stems on the exported analysis axis, including the reconstructed instrumental, with strict counts and verified publication. The player renderer is unchanged.

- Stem audition reconstructs the instrumental and every available selection from final drive PCM using a single host mixer checked against native C output. Bounded float-audio excerpts carry the 256-frame ramp state across selection changes, with waveform seeking, Original and imported-versus-drive views. Preparation stays asynchronous and may briefly pause playback while a new selection is prepared.

- Manual lossless stems can be assigned per library track and imported after duration, multi-window alignment and heuristic gain checks. Constant offsets and trimming are reported, gain is never silently changed, and uncertain gain is not presented as certified. Imports preserve the existing PCM format and verified drive publication; assignments survive restarts.

- Multi-role loading now counts earlier roles in the pending set against the shared 512 MiB ceiling, as well as the other deck. Native tests cover missing prerequisites, mismatched lengths, residual reconstruction and the exact 256-frame ramp. Preparation shows size per role and track, warns above 256 MiB, and includes drums whenever bass is requested. The README describes both library inputs and all four unchanged pads. Not yet run on hardware.

- Prepared stems are reused only when the full source SHA-256, effective processing signature and verified final audio match. A version 2 manifest retains legacy entries without inventing provenance, and completed tracks are recorded individually. A bounded local LRU cache and mounted-drive lookup avoid repeated separation; the cache limit and clear action are available in the Stems screen.

- Stem preparation checks free space before separation, detects source changes, refuses symbolic-link destinations and verifies staged files by SHA-256 before replacing them. File and supported directory syncs precede completion, and metadata cleanup stays inside RX3_STEMS. The manifest now lives there too. Library reads and batches stop while the library application is open, with a persistent warning and an explicit recheck.

- Cap sampler polyphony at four voices total across both decks and all playback modes. Reject a fifth start without interrupting active sounds; apply the same ceiling to desktop playback, including pending conversions. Not yet validated on hardware.

- Correct sampler input ownership across decks, ignore hold-repeat events, stop sustained voices when leaving the sample page, and honor SHIFT-only silence. Add a 32-frame loop edge ramp. Match that ramp and the squared bank-volume curve in desktop preview, using buffer playback for continuous loops. ARM build, host behavior tests and firmware 1.19 byte guards pass; these changes have not yet been validated on hardware.

- Move desktop UI translations into UTF-8 English and French JSON catalogs shared with Python. Localize module metadata, validation errors, progress and native file filters; add plural and number formatting, persisted locale selection, packaged catalog checks and translation integrity tests.

- Move and zoom the logo directly on the RX3 mock, with arrow-key positioning; remove the separate framing panel. Export retains the same placement coordinates.

- Add a rounded schematic RX3 screen to the logo and sampler editors, reflecting logo framing, display theme and active sample pads. Keep precise logo framing available in an expandable editor.

- Keep continuous player output in RAM with ordinary logging; add opt-in verbose USB logging and restart when changing output destinations. Not yet run on hardware.
- Simulate eight simultaneous sample pads with mouse or keys 1-8, four playback modes, per-pad and bank gain, and stop-all. Prepare sample excerpts from longer audio, audition saved pads, and use the same excerpt conversion for preview and export. Preview applies pad and bank gain, handles release during loading, and protects unsaved bank edits when switching banks.
- Preview both logo themes from the actual RGB565 export and retain the image path and framing between application sessions.

- Fix partial theme transitions by switching at the native render boundary, invalidating windows once and redrawing the header child groups after the root pass. Automated queued transitions on RX3 1.19 preserve the background, header and eight hot-cue cells on unloaded decks. Physical shortcut confirmation, Utility switching, loaded tracks and audio remain unverified.

- Reapplying session logging no longer stops module preparation when the running player already has the requested log path. Confirmed from the 1.19 device session; the setting's unchanged status is handled as success.

- Clarify recovery around DJ capabilities and retained improvements, update the source mapping after the shared pad-row rewrite, and record the 1.19 static checks and differential ARM pixel-conversion evidence. Device validation remains pending.

### Added

- **A pad can be heard before the drive leaves the desk, and it behaves the way it is set.** Choosing between four modes meant choosing blind: nothing in this project reaches a deck, so a pad set to hold or to latch could only be tried by carrying a stick to one. The pad editor plays it now, and the button obeys the mode rather than just playing the file -- once runs through, hold sounds only while the pointer is down, loop and latch are stopped by a second press, and the pad's trim is the volume. What plays is the converted sound rather than the source: the same `convert_pad` a save performs, so the eight second cap and the resampling are heard too, and there is no second conversion to drift from the first.

- **A pad can be stopped by the pad that started it, without looping.** The three modes covered a long sound badly: `once` plays right through and ignores the release, `hold` needs a thumb held down for the length of it, and only `loop` could be stopped, at the cost of repeating. So a bed or a vocal phrase fired by mistake could be taken back only with SHIFT, which silences the other seven with it. `latch` is the missing square: press to start, press again to stop, and it runs out on its own if you leave it. The mixer needed no change, because it already tells a loop from everything else by one test; what changed is that both modes that hold are now stopped by their own pad. `settings.ini` accepts `padN.mode=3`, the deck says so in the line the computer reads its capabilities from, and the pad editor offers a fourth choice. **Not yet run on hardware.**

- **The mod can say something to the person standing in front of the deck, starting with "do not remove the USB".** It never could. Everything it had to report went to `/tmp/rx3-stems.log`, which nobody reads during a set, and the one thing an operator actually lives through -- the player freezing, restarting, then taking a few seconds before the drive is usable -- happened with no explanation on screen. That window is also the one in which pulling the drive costs a folder on a FAT stick, and the operator sees the wait whatever we do. So the notice spends its one line on the warning rather than on narrating the wait: it says do not remove the USB key, in their language, and nothing else. It does not suggest that removal becomes safe when it clears, because the player holds its output file open for as long as it plays whenever logging is on. The logging module's report already had to be corrected once for saying the reassuring version of that. It says so now, in the operator's own language, and it says it the way the player says its own things rather than by painting a rectangle over the top. `EMERGENCY LOOP` turns out to be one entry in a table of notices the player raises for itself, and the method that shows one takes the text as a pointer, so a message needs no artwork and no overlay. **Not yet run on hardware.**

- **The notice borrows one of the player's own, chosen on evidence.** The player builds seventy-two of these objects at start-up and never raises twenty of them. Establishing which twenty took two passes: counting the literal pools finds twenty-two, and four more references are built with `movw`/`movt` pairs instead, so `B046` and `B059` look free until those are counted too. The one borrowed is `B051`, an info-bar notice with a three second life and no other reader. Building an object instead was rejected: it means modelling a C++ object with bitfields and multiple inheritance, and a wrong field is a frozen player mid-set. That is not a hypothetical. A build predating this repository had caution workers of its own and the only record left of them is the line that disabled them, "invoking that path froze rbp", with no note of why. Everything in this feature that looks like caution rather than ceremony is that sentence.

- **The language is read, not assumed.** One byte holds it, and it counts from one while the tables count from zero -- the Utility row that renders the setting reads it and subtracts one, which is the off-by-one that would otherwise show an operator the language listed next to theirs. The conversion and the range check are compiled on the computer and walked over every value a byte can hold, because both failures are silent: one shows the wrong language, the other indexes past the end of a table and hands the player a pointer to nothing. All eighteen are written, in `mod/modules/core/rx3_messages.h`, which holds nothing but the prose so that correcting one is a one line change and needs no reading of byte guards or thread rules. They are readable in the file rather than encoded as code points, because UTF-16 literals compile to exactly what the player's notice method wants. English and French are the author's; the other sixteen are written with care and none has been read by a native speaker or seen on a deck set to that language, which the file says plainly. A test refuses an empty line, a language that repeats another word for word, and one longer than anything the player shows in that position.

- **`RX3_MESSAGES=0` and `/tmp/rx3-messages.off` turn it off.** The second matters more than the first: if this freezes a deck, the symptom arrives in the middle of a set, and the operator should not need to build another drive to stop it.

- **Firmware 1.20 is supported, and it cost one checksum.** Somebody else's build claimed it; their artefact did not carry it, so the claim was checked against the firmware instead of against them. The official 1.20 update decrypts with the same key and the same container, and its player binary is the same size as 1.19 with **three bytes** different, all of them constants beside `setScreenSaverOn` and `BacklightPwm`. Every one of the 23 guarded addresses the mod hooks still holds its eight expected prologue bytes, all 14 registered patch words still hold their stock values, and the waveform opcode still matches. Outside the player, `decrypt_autoexec.sh` -- which is what runs the mod at all -- is identical, as are BusyBox, every tool `autoexec.sh` calls, the udev rule that triggers it, and every real shared library; the rest of the update is build dates and an SVN revision. So there was nothing to port. **Not yet run on hardware**, and the acceptance sequence is the only thing that will change that: this says nothing has moved, not that the mod behaves.

- **A module is one directory again, and says for itself which firmwares it serves.** Every module lived under a level named after a firmware version, which read as though the tree held one set of addresses per version. It never did: there is one set, thirteen directories asserted otherwise, and the version in their name went out of date the moment a second firmware turned out to carry the same addresses. The level is gone. A module is `mod/modules/<id>/`, its manifest lists the `firmwares` it is built against, and `mod/compatibility.sh` holds every accepted player checksum in one list, commented by version. That removed a directory level from thirteen modules, nineteen hand-written `../../<module>/1.19/` includes from the core, and a `firmware` field that had to equal the name of the directory it sat in. The application needed no change: its version list was already read from the build rather than written down, and it now offers 1.19 and 1.20 because the manifests do. A test refuses a module that claims a version one of its dependencies does not, which is the one way this shape can go wrong quietly.

- **`scripts/check_addresses.py` answers the firmware question in a minute.** It reads the address constants and the eight-byte guards out of the core's own sources and checks them against a player binary given on the command line, so it cannot drift from what the deck will do, and it ships no firmware. Several guards at one address are read as alternatives rather than as separate checks, which is what the image-table lookup needs: it is hooked with the word the launch patch writes and again with the stock word underneath. Judging the next firmware is now a command rather than an afternoon.

- **The pad row is a framework rather than three panels that each drew their own.** KEY laid out three controls from coordinates written by hand, STEMS declared one control and then drew two to four from a table of widths and gaps, and SAMPLES drew a slider of its own; each of them then worked out what a finger had hit by repeating the same arithmetic somewhere else, with nothing making the two copies agree. A feature now declares what its controls are -- a button, a toggle, a stepper, a slider -- and the core solves the row, paints it and hit-tests it from the one set of rectangles. The three-controls-per-deck ceiling goes with it: that was the six Beat FX touch objects the row used to repurpose, and it hit-tests its own rectangles now, so those are parked while a custom panel is up and handed back untouched on the way out. Eight guarded inline hooks and their eight prologue guards are removed. **Not yet run on hardware.**

- **A press now looks like a press, on every control rather than one of them.** Only KEY had a pressed state, because only KEY went through the touch objects that report a release; STEMS and SAMPLES saw a press and nothing else. Press, slide off, slide back on and release are one state machine now, and it does what a button does: sliding off cancels without firing, sliding back on restores, and only a release still inside the control acts. A control that fired on contact would go off under a thumb passing over it on the way somewhere else.

- **The row is lettered in Pioneer's face, from artwork, one image per character.** The controls used to be lettered by cloning one of the player's own text objects, on the assumption that the clone carried the typeface. It does not, and it cannot: the pad subtree issues no text draw at all, because Pioneer's own pad labels are images, so there was never a label there to clone and the row fell back to the header glyph at twice the size it wanted. `build_labels.py` writes a glyph atlas instead and the deck composes a string from it. One image per whole caption was written first and cannot spell what the row says: the KEY centre carries a key and a move, `*3A +2`, which is twenty-four tonalities times twenty-five transpositions, and the sample row carries a level. **Not yet run on hardware.**

- **The pad colours are read off the artwork instead of being written down twice.** Two measured palettes disagreed in the tree: the core called an orange the reference build's own value, and `build_labels.py` had measured Pioneer's own captions and found blue, noting that the interface is monochrome and blue is what marks a selection. The atlas carries the ground each set of glyphs was drawn on, and the row paints that same colour underneath, so there is one palette and it is the measured one. A selected control is now blue on white rather than orange, and the light row takes the measured grey rather than pure white. The two theme flags the row read also disagreed: the controls followed the mode chosen at boot while the stems strip followed the live toggle, so on a deck started dark and switched mid-set one row moved and the other did not. Both follow the toggle now.

- **A picture of the pad row, drawn on the computer.** Nothing in this repository reaches a deck, so a change to the row could not be looked at before someone carried a stick to one. `python -m app.rx3_preview` composites the artwork that ships at the geometry the deck solves and writes one image per panel, theme, state and control count. It is not a simulator and does not try to be. The layout it draws from is the deck's own: `rx3_pad_layout.h` is free of player types, globals and libc so the test compiles it and runs it against the preview's copy, over every count and both spans, rather than reading it as text.

- **A level per pad, written beside the sound rather than into it.** The bank had one volume for all eight, so a kick and an airhorn arrived at the same setting and at nowhere near the same loudness, and the only correction was riding the on-screen strip mid-set. `settings.ini` gains `padN.gain`, a percentage of the sound as it was recorded, and the mixer spends it on top of the bank volume. It is plain amplitude rather than squared like the bank volume, because this is a trim to match levels, where half means half, and the bank volume is the knob. Keeping it in the file that already sits beside the audio means a level can be corrected later without re-encoding anything, and the sound on the drive stays the sound the operator chose. The trim is copied into the voice when the pad is hit, so a bank reloaded mid-sound cannot step the level of something already playing. **Not yet run on hardware.**

- **The KEY row offers the shift that puts two decks in key, and lights up when they already are.** It read one deck's key and showed where a shift would land it, which is the arithmetic and not the question: what a DJ wants to know mid-blend is whether these two work together, and if not, how far to move. Both keys are already on screen and both shifts are already known, so the deck can answer. The middle control carries the move beside the key, `*3A +2`, and pressing it takes it; with nothing left to match it still puts the deck back where it started, which is what it always did. The search runs outward from where the deck is now rather than from zero, because mid-blend the nearest key matters more than the tidiest one. A test pins the wheel rule and the search: a wrong answer here moves a playing track into a key that clashes, which is the failure the feature exists to prevent. **Not yet run on hardware.**

- **The sample pads are a page of SLIP LOOP rather than a chord.** They were on SHIFT + HOT CUE, which cost the DJ their hot cues for as long as a bed was looping: the one thing a pad mode must never do. SLIP LOOP already steps the pads through the player's own pages, so the samples are the page after them. Same button, same thumb, one more press. Every other pad-mode button puts the count back to zero on its way past, and a deck carrying no samples never reaches the extra page, so the button behaves exactly as it did before.

- **The performance row holds a refresh window instead of asking once.** One repaint loses a race the player starts on its own: it redraws the stock row from a path of its own, the custom controls go with it, and nothing asks again, so a change made at the wrong moment flickers and reverts. The request now repeats for a second. It is throttled to about eleven repaints rather than run on every intercepted draw, because painting the row per draw was measured at 331 paints where 6 were wanted.

- **The display starts in the mode the operator asked for, and light can wait for the player.** `RX3_THEME` carried two states, light and global dark, and anything else fell through to switchable without saying so. It carries four now, and the module picks one from a word in `RX3_RUNTIME/display` on the drive: `dark`, `light`, `wait` or `switch`. `wait` is the one that is new in kind: the deck starts dark, the player paints its own first frame, and only then is the display taken over, because switching during that first paint leaves half the chrome in one theme and half in the other with no way back but a toggle. The arming becomes an ordinary toggle request rather than a second way of switching, so the tab artwork, the image table and the waveform palette still move together through the one path that already does it. Each of the four says which it is in the session file. A test reads the letters the module can export and the letters the core compares against, and fails when one sends a mode the other does not read: that failure is a deck that starts, reports the mode it thinks it chose, and never changes the display. **Not yet run on hardware.**

- **A separation screen.** Whether this machine is set up and what it would run on, the music read from an export or from the drive itself, a playlist with what the run would cost before anyone commits to it, three speed and quality trade-offs named in the terms of this machine, and the run itself on the same job slot as everything else. `stems_library` used to throw away the collection it had just parsed, so a forecast and a run were both unreachable; it is kept now, and neither parses the export twice.

- **A pad editor.** Eight tiles in the deck's own order, each showing the colour the button will light, the sound on it, how long it runs against the eight seconds a pad holds, and how it plays. Beside them, one pad at a time: its sound, its name, its colour from the eight the format has always carried or any other, and once, while held, or loop. The bank's name, its starting volume and whether SHIFT stops everything sit under it, with what is unsaved said plainly, because nothing reaches the drive until it is saved. Every limit it obeys arrives from `samples_defaults()` rather than being written down again in the interface.

- **A logo framer.** Drag to move the artwork, scroll to zoom, fit or fill, and see it on a dark screen or a light one. The drag runs in the interface because the encoder is a per-pixel loop in Python that costs about 700 ms for the largest pane, which is a slideshow rather than a drag; once the pointer stops, Python answers with where the artwork really lands and whether it is too dark to read. The framing arithmetic therefore exists twice, so a test lifts the interface's copy out of the file that ships it and runs it against the encoder over both panes, both fits, eight shapes, nine zooms and nine offsets. It found the difference between rounding halves away from zero and `Math.round` on the first run.

- **Pad modes, on the deck and in the file that carries them.** A pad plays once, plays while it is held, or loops until it is pressed again, and SHIFT can stop every pad at once. `settings.ini` gains `padN.mode` and `shift.silence`, and `padN.name` for a label the deck passes over and the computer shows. The pad handler already saw the release event and threw it away; it is what stops a held pad now. The mixer walks a running index rather than a modulo, because this arm has no hardware integer divide and a modulo there is one division per frame per pad, and a loop deliberately fills the whole block so a short sound has no gap after each wrap. **Not yet run on hardware.**

- The samples module says what it can do, so the computer can offer exactly that. `app/rx3_session/log.py` has looked for `SAMPLE pad modes:` and `SAMPLE shift.silence:` in the session file since it was written, and nothing has ever emitted either, so three of its five capability fields could never read anything but "declared". The module writes both lines when it is ready.

- The window can build a key. `mod_build` validates what an operator can get wrong on the thread that called it, so a refusal is the answer to the button rather than a job that fails a second later, and runs the build on one job slot with progress and cancellation. There is one slot rather than one per kind: a build and a separation both write the same drive, so two at once damages a stick, and one slot makes cancelling mean exactly one thing. Progress is polled rather than pushed, which is what lets the whole of it be proven by a self-test with no window and no display.

- The window can choose a file. `app/shell.py` created its window and threw the handle away, and the chooser is the window's, so no screen could turn what an operator picked into a path a service can open. That is why `app/rx3_service/samples.py:save()` and `app/rx3_service/logo.py:files()` had been finished and correct for months with no caller.

- The interface speaks French and English, switched while it is running. One catalogue with every language on the line that has the key, so a gap shows up in a diff beside what is missing rather than as blank space nobody notices. Sentences that come back from the toolkit itself stay in English for now: they are written by the service layer as prose, and translating them means a code beside every message rather than a message.

- `make new-module ID=<id>` writes the manifest, the shell contract and the README a module is made of, namespaced and ordered. `CORE=1` writes the performance-core variant as well, with the feature header and the `module.sh` that declines when the core is not selected. These names and the order field were discoverable only by reading a neighbouring module.

- A pull request template carrying the sections a reviewer reads, Summary, Changes, Testing and Legal, and the two prose rules a contribution is most often sent back for.

- `make payload` assembles the mods into a runnable payload directory: a manifest, the preloaded hook and the assets. That directory is the whole of what this project exposes to anything that runs it. No import, no path and no target reaches the other way. A test reads the performance-row geometry back out of the hook's C and fails if the two copies drift.

- The complete `ui::KeyInput::KeyCode` table, 146 codes with their names, in REFERENCES.md appendix A. Extracted statically from `keyCodeAsText()`, which is a comparison tree over the same 16-bit field the stems feature already reads: decompile it, take the (code, pointer) pairs, resolve the pointers in `.rodata`. The four pad-mode selectors are `0x4113`-`0x4116` and the eight pads `0x4117`-`0x411e`; the extraction independently reproduces `Pad7 = 0x411d` and `Pad8 = 0x411e`, the two values the mod already had hard-coded from an unrelated route. Six codes the decompiler folded into range comparisons were read off their guards rather than guessed.

- Pioneer's bitmap font format, decoded, in REFERENCES.md under "The bitmap font". `NS_FONT_ID_ISO8859_w.bin` has no header and no offset table: it is a flat array of 189-byte cells, 14 x 27 pixels at **4 bpp**, 422 glyphs indexed by `codepoint - 0x20`, covering ASCII, Latin-1, Greek, Cyrillic and the euro sign. The file is 42 bytes short of 422 full cells because the last glyph's all-zero descender rows are not written. Earlier attempts read it as 1 bpp and 4 bpp at several widths and got noise; the cell height was the missing piece, and 210 leading zero bytes looked like a 30-row cell when they are a 27-row space followed by the first three blank rows of `!`.
- The typeface is named rather than guessed: **Helvetica Neue LT W1G**. rekordbox 7 declares `font-family="HelveticaNeueLTW1G"` in three of its own skin SVGs, and W1G (Linotype's "World 1 Glyph set", Latin plus Greek plus Cyrillic) is exactly the repertoire of the firmware's font file. Two unrelated artefacts, one answer. It is licensed and not shipped: scanning all 2144 files in the rekordbox bundle for genuine sfnt table directories finds four, all Chromium's `SpiderSymbol` icon font.

### Fixed

- The performance hook announced itself as "native ZOOM/GRID replacement and wait caution". It has neither, and has not had either for as long as this repository has existed: the line was inherited from a build that predates the first commit. It now says what it is.

- **A logo previewed where it would not land.** Asking where artwork would go measured the file the operator picked, while writing it measured the artwork cropped to what it actually draws. For any image exported with a transparent margin, and that is most of them, the two disagreed, so the answer a screen would have shown was not the pane the deck would get. Both now measure the same image, through one function.

- **A sample bank is now assembled beside the one it replaces and moved into place in one rename.** It used to be converted straight into the bank directory, with the size limit checked only after every conversion had already run. A save that failed at pad five left four new pads, four old ones and the old settings over them: a bank nobody assembled, still marked active, which the deck would play during a set. Two renames inside one directory, because the drive is FAT and has no atomic directory swap, and a name starting with a dot is not offered as a bank because that is what a swap caught half way looks like.

- A pad carried over from a save is checked against what the deck reads rather than copied on trust. The deck skips a pad it cannot parse and writes one line to a log nobody is looking at, so the pad is simply silent at the moment it is pressed.

- `app/rx3_service/samples.py:save()` never set a pad colour, so the eight colours the format has always carried were unreachable through the only function that writes a bank. It now carries the colour, the name and the mode.

- The logging module's on-deck report claimed that nothing held the drive open and that ejecting was a formality. The player's own output is still redirected to `RX3_RUNTIME/rbp_stdout.txt` for as long as it plays, so the report says again what the README and the manifest say: eject the drive, never pull it. It was the reassuring direction of a wrong statement, the one that costs a folder on a FAT stick.
- The `beatjump-32bars` manifest said bars where the module jumps beats, a factor of four in the name and description the application shows. It now says what the module's README says: pads 7 and 8 become -32 and +32 beats.
- Two module names carried a leading space that the application rendered as such (`logging`, `telnet`).
- Two manifests under-declared their headers in `build_files` (`theme-white` without `rx3_theme_pixels.h`, `core` without `rx3_probe_format.h`). The frozen application bundles only what is declared, so a compile from source inside it would have failed on a missing header; the CI hid it by always supplying the prebuilt hook.
- The README told Linux users to install WebKit for an application that still draws its window with Tkinter. That paragraph now promises the coming interface instead of describing it as shipped.

- **The hook stopped loading, silently, and every run fell back to stock behaviour.** At `-O2` clang rewrites `memcmp(a, b, n) == 0` into a call to `bcmp`, which rbp's libc does not export; the library then fails to load with no link error and no warning, because the rewrite happens in the optimiser, after every diagnostic the front end could have produced. The symptom looked nothing like the cause: a run painted 17 730 non-black pixels, exactly the stock figure, which reads as a startup problem rather than a missing mod. `-fno-builtin-memcmp` suppresses the rewrite, and `tests/test_hook_symbols.py` now reads the `.dynsym` of both builds, with its own small ELF parser so no external tool is needed, and fails on `bcmp`, on any import outside the set rbp is known to export, and on the flag being dropped from the Makefile. This is the second time an unresolved symbol has cost this project a long debugging round; it is the first time a test will catch it.
- The label generator's typeface was refitted against ground truth and is now Helvetica Neue **Regular at 22**, not Light at 24. The fourteen BEAT FX captions in the caption artwork segment cleanly into individual letters, giving nineteen of Pioneer's own capitals. Cap height is a consistent 16 px with `O C G S` overshooting to 17, which is itself evidence they are font renderings rather than hand artwork. Sweeping face against size over those glyphs, Regular 22 gives 29.3 mean absolute error per pixel where Light 24 gives 61.3. The earlier fit matched whole-word ink extents, which is a weaker signal because weight and size trade against each other and still fit a box.
- The reference said the pad blink uses a 50 ms period; it is 500 ms, and that is a half-period: one second on, one second off.
- The performance row is painted once per pass instead of once per intercepted draw: 6 draws where there were 331 over the same run. Deciding what to replace was also keyed on the deck's window, which a deck shares with its info strip; it now keys on the widget subtree that actually owns the pads, so nothing outside the row is intercepted on the way past.

### Changed

- **The window drawn with the system's own webview is the application.** `app/toolkit.spec` freezes `app/shell.py`, ships `app/web/` as the page it loads, and excludes nothing. The Tkinter window and its two panes are retired to `.attic/`. Three things had to be true first, and all three are: the spec put the page under `_MEIPASS` where `shell.resources()` looks for it, so the frozen application had a page at all; `excludes=["ssl", ...]` went, because `webview.http` imports `ssl` when webview is imported and the excluded build could not have opened a window, which is safe now that cryptography's wheels link their OpenSSL statically and `scripts/check_macos_bundle.py` proves the bundle carries one and not two; and nothing imports `app/theme.py` any more, which is what actually kept Tk out of the bundle. Verified by packaging on macOS and running the bundled executable's self-test.

- The one requirement this adds is on Linux, where the desktop has to have WebKit. Most do. The README said so as a promise about a coming version; it says so as a requirement now.

- Pillow is a plain requirement rather than a release-only one. It was declared for the packaged application alone while the logo screen had no way in, so neither the tests here nor the CI source job could run a single line that opens an image. The screen is the way in.

- The window is rebuilt around what an operator does rather than around what the toolkit contains: a rail of screens instead of a strip of tabs, one colour per theme spent as alpha steps so both themes stay consistent, and the contrast of every text step measured rather than assumed. The system's own typeface, because no third-party font ships from here.

- `app/shell.py` no longer imports the Tkinter theme module for one Windows call about pixel density. That import is what would have put Tk in the frozen application even after the interface stopped using it.

- The README's module table lists the five ported modules the application already offers (sample pads, stem waveform, light display mode, accent-insensitive search, logo), each marked as not yet run on hardware. CONTRIBUTING, REFERENCES and the third-party notices describe the tree as it is: one `app/` directory, two windows of which one ships, no guards, no payload, pywebview and Pillow declared.
- One word for the file a deck reads beside a track: a stem. "Sidecar" is gone from the Python (`write_stem`, `Stem`, `StemResult`, the `stems` field of a track result, the module `app/rx3_stems/stem.py`), from the C (`struct stem_header`, `enum stem_format`, `pending_has_stem`, `stem_path_for_track`), from the shell messages of the stems module and from the documentation. The stems manifest the application writes beside its output names the vocal file under `stem` rather than `sidecar`; nothing reads that file back. One log line of the hook changed with it, so the library no longer hashes the same. **Not yet run on hardware.**
- "Stem Studio", the name of an application that no longer exists, is gone from the code: the tab is `app/stems_preparation.py` and `StemsPreparationPane`, its test `tests/test_stems.py`. The per-user data directory and `RX3_STEM_STUDIO_HOME` keep the old name on purpose, so a runtime already installed is found rather than downloaded again.

- Everything that runs on the computer lives under `app/`: the window (`main.py`, `mod_generator.py`, `stem_studio.py`, `theme.py`, the coming `shell.py` and `bridge.py`) and the engines it drives (`rx3_runtime`, `rx3_firmware`, `rx3_stems`, `rx3_session`, `rx3_service`, `rx3_logo`, `rx3_samples`), imported as `app.*`. `apps/rx3-toolbox/` and `tools/` are gone; `make autoexec`, `make new-module` and `make app` run the same code through `python -m app...`. The label generator moved beside the assets it draws, `mod/modules/core/1.19/build_labels.py`; it never ships to a deck. The packaged application's smoke test is one line of the CI workflow rather than a script.

- The test suite is cut a second time, to what fails when a deck would misbehave, when a stick or a track would be damaged, when the mod would load and silently do nothing, or when a commitment in LEGAL.md would break: 213 tests to 61, in 12 files. The eight per-module `test_regressions.py` guards are gone with the `make test` loop that ran them and the template `make new-module` wrote: they pinned the text of the C and failed on every edit of it without a deck behaving any differently. `make test` is the unit tests alone. A module is now three files, not four.

- `tests/test_mod_generator.py` no longer holds the list of modules. It derives what it expects from the directories on disk and checks the properties that matter, that every manifest is discovered and that the load order puts a dependency before its dependent. CONTRIBUTING.md promised that adding a module needed no edit elsewhere; that list was the edit, and it failed on the first outside contribution that added one.

- The `PATCHED` badge is gone. The `KEY` and `STEMS` tabs already answer the question it was there to answer, and the header is Pioneer's again.

- The payload build finishes a browse key the way rbp does, so the emulator can drive the browse section without a front panel. `BrowseUiIf::InputKey` (`0x000cfc58`) marks the record with `UiKey_KeyPush` and, if it is accepted, posts an eventflag with `set_flg(*0x032671f4, 1)`; `Ui_EventTask` (`0x001e79a0`) consumes it and runs `BrowseKeyProcessing` inside the rest of the transaction: `CheckBrowseRequestCancelCommand`, a 300 ms repeat window, `BrowseCommandCancel`, and the `KeyComplete`/repaint. Calling the handler directly skipped all of that, so the hook now posts the flag and falls back to the direct pump only when the flag id looks uncreated. Whether this moves the browse mode on screen is not demonstrated.

- The update-container codec is gone from `tools/rx3_firmware/`, along with its description in the documentation. The toolkit authors `autoexec.bin` and nothing else, which is what the build engine has always used; a test asserts the removed symbols stay removed, and another fails the build if the container format is described in prose again.

- The scripts that model the player left this repository, for the unpublished one that holds the emulator: the pitch and UI harnesses, the shifter measurement, the image-table model, the Ghidra scripts, and the resolver that fed them. Nothing here imported any of it. What stays in `tools/rx3_firmware/` is `firmware_image.py`, which the build uses to author `autoexec.bin`.

- `RX3_KEY` is read where the key is needed: `make autoexec` takes it when `KEY=` is absent, and the application opens with that path already filled in and its file dialog pointed at the right directory. Nothing writes the location down, and `KEY=` still wins.

- The three largest emulator-only blocks of the hook move into their own headers, included at the point they used to sit and only when `RX3_EMULATOR_BUILD` is defined. `rx3_core_hook.c` drops from 2981 lines to 2310, and what a deck compiles is now most of what is left rather than three quarters of it. Both libraries hash the same before and after.

- The two teardown paths of the hook are one function. The installer's error exit and the destructor each carried their own copy of the same twenty calls, in the same order, so adding a hook and updating one copy left that hook installed on the path that only runs once something has already gone wrong. **Not yet run on hardware:** the generated code changes, so the acceptance sequence in CONTRIBUTING.md applies before this ships.

- Three constants the hook defined and never used are gone: an LED state, a visibility timeout, and a file mode. Both libraries hash the same before and after, so nothing on a deck can tell the difference.

- The test suite is cut to what it is for: 143 tests to 64, 3807 lines to 2424, and under six seconds to run. What stays fails when a deck would misbehave, when a stick or a track would be damaged, when the mod would load and silently do nothing, or when a commitment in LEGAL.md would break. What went was coverage: an estimator for a progress bar, a matrix of accelerator profiles restating a table the code reads, window theming, and a set of interface closures that replayed the dependency resolution already pinned elsewhere.

- A name that asserts where a file came from now fails the build. The resolver carried that rule and left with the scripts, so `tests/test_names.py` applies it to every tracked path and every Python name in the repository.

- The emulator moved to its own repository. What remains here is the payload format it consumes.

- The root filesystem documentation no longer sends everyone through `make_rootfs`. The published source package carries the built `initramfs.tar.gz` beside the sources, so reading the filesystem is archive handling on any of the three operating systems, and WSL2 is needed only by someone who wants to rebuild it. Reported in #23. The document still stops at an unpacked filesystem: it does not say what inside it the app is later pointed at, and it says plainly that a manufacturer-built archive stays on the machine that unpacked it.

### Removed

- `make payload`, the payload assembler under `tools/rx3_payload/`, and the emulator variant of the hook: the eighteen `RX3_EMULATOR_BUILD` blocks in `rx3_core_hook.c` and the three `rx3_core_emulator_*.h` headers. The emulator left this repository and nothing here ran them; `librx3_core.so` hashes the same before and after, so a deck cannot tell the difference. `tests/test_hook_symbols.py` reads one library now.
- The offline patchers under `tools/rx3_patcher/`. Their only reader was a test that compared them with the tables in `module.sh`, and those tables are what runs.
- `tools/rx3_stems/make_sidecar.py`, a command line over the encoder the application already drives, and `tools/rx3_runtime/patch_r38_ui.py`, an experiment on a build that predates this repository.

### Known issues

- **The pad row draws no text at all**, so the pad-label template can never be captured as designed. Measured: twelve window subtrees issue text draws (`0x01 0x02 0x03 0x06 0x07 0x08 0x09 0x0b 0x0c 0x10 0x11 0x16`), and the pad subtree `0x17`/`0x18` is not among them. Those labels are images. The comment in the source describing the template as a clone of "the stock deck-2 KEY label" describes something that does not exist.

- **Pioneer's own artwork settles the style.** The image table is a run of 44-byte records at offset 0 followed by pixel data, the same record layout the mod already manipulates in memory, with width at `+4`, height at `+6`, format at `+0x18` and the pixel offset at `+0x20`. The first pixel offset is exactly 5581 x 44, and format 2 is RGB565 with the palette offset set to the file length as a no-palette sentinel. Reading it needs nothing new.

Ids `0x1439..0x1470` hold the BEAT FX captions at 160x40, and every caption ships four variants: dim or white lettering on a black or blue ground. That is the whole colour language of this interface. It is monochrome, and blue marks the selected item. Measured exactly: ground `(0,0,0)` or `(0,125,230)`, ink `(98,101,98)` or `(255,255,255)`.

The firmware ships fonts, and they are the wrong ones. `gui/system/fontdata` holds `decker.ttf` ("Decker Bold") and `sazanami-gothic.ttf`; measured against the real captions they are 11.1 px and 14.8 px out, so Decker is a display face and sazanami the CJK fallback. The UI font is `gui/pset/fontdata/NS_FONT_ID_ISO8859_w.bin`, 79 758 bytes in Pioneer's own format, since decoded above.

Rasterisation was matched rather than the file. Pioneer's glyphs quantise to sixteen grey levels, which is 4-bit anti-aliasing, and their vertical stems are solid with the anti-aliasing only on curves, which is hinting. Supersampling matched the pixel totals but softened the stems and looked wrong at zoom, so the lettering is drawn once at final size, hinted, to reach their stroke mass, with the coverage quantised to sixteen steps.

- **Cloning does not carry the font.** With the donor made selectable, four different donor subtrees were captured successfully and every one rendered the control label at exactly 19 px, the same as the header donor and the same 2x-stock size the labels have always had. So the long-standing premise that the cloned glyph determines the face is false, at least for size: either the font follows the window the draw is retargeted into, or it lives outside the 0x54 bytes that are copied. Fixing the font therefore needs a different mechanism, and drawing the labels as images the way Pioneer does is now the more likely route.

- The on-screen controls still wear the header's typeface, at twice the size of a stock label, and selected still looks like unselected. Both come from the same place: the controls are drawn by cloning one of rbp's own text objects, and the colour fields on that object are not plain RGB. `NS_PALRender_DrawText` decodes them three different ways depending on the pixel format of the window being drawn into, which it takes from `DS_GR_GetWindowInfo` rather than from the object. Feeding it RGB888 painted magenta lettering on green; RGB565 painted green; sweeping all 256 low-byte values moved the green channel alone and never lifted red or blue off zero. Until the format reported for the pad layers is identified, the drawing code inherits those colours rather than guessing at them. That is also the explanation for an older note in the source that every literal colour "looked foreign".

The eight prepared tab bitmaps are still shipped and still loaded at run time, because that colour question is what stands between the row and being drawn entirely from the host's own model. They go when it is answered.

## 0.5.2

A runtime built on Windows loads its modules again.

### Fixed

- An `autoexec.bin` built on Windows stopped with `STOP: one or more runtime modules violate their contract`, one `FAILED: unsafe runtime module directory` per selected module. The index naming the modules to load was written with the building machine's line endings, and the shell that reads it took the trailing carriage return as part of the directory name. Affects 0.5.0 and 0.5.1 built on Windows; 0.4.0 predates the index.

## 0.5.1

Reinserting the drive works. It used to be refused, and before that it was what the deck made you do, because applying a module emptied the media list. The runtime also stops writing to the drive unless you ask it to.

### Fixed

- Reinserting a drive without a power cycle no longer stops with `STOP: unsupported rbp SHA-1`. The check hashes the whole player binary, so a session this runtime had already patched no longer matched the state it started from. The guarded words are put back to their stock values before the comparison, which answers the question the check means to ask (is this the binary I know?) without being fooled by our own writes. A guarded word holding neither value still survives normalisation, and the word-by-word audit that follows still rejects it before anything is written.
- Reinserting a drive no longer restarts the player. A drive pulled out as `sda` comes back as `sdb`, so it mounts somewhere else; the sidecar directory is read once at load time, so a moved path meant stopping and relaunching. That froze the screen and emptied the media list, which is what made the drive get pulled again. The player is handed one fixed path, re-pointed on each insertion, and a reinsertion now changes nothing.
- A player that exits straight after being relaunched is rolled back to the stock binary instead of to the previous bytes. On a reinsertion those previous bytes are the patched ones, so the rollback relaunched exactly what had just died. The runtime's shared objects come out of `LD_PRELOAD` with it.
- The log of the run that applied the patch survives the next insertion, in `session-previous.txt`. The player's cumulative output carries a marker per launch, so one run's crash no longer reads as the next run's.

### Added

- **Session logging** is a module of its own, and it is not selected by default: an ordinary build now writes nothing to the drive at all. Tick it to get `RX3_RUNTIME/session.txt` and the player's output. Eject the drive rather than pulling it out while that build is in use, because the player keeps the log open for as long as it plays. That open handle is also what stopped the kernel releasing the device, which is why a drive came back under another name.
- The log names what forced a restart, and each module says what it saw that made it ask.

### Changed

- A relaunched player is given up to the same eight seconds, but the wait ends as soon as every module has written its readiness file, a second in practice. The media that is already mounted is announced to it as soon as the process is alive, rather than after the readiness verdict.
- Everything the RX3 executes moved from `runtime/` to `mod/`. The word said *when* the code runs, which the directory above it does too: `apps/` and `tools/` are runtimes of their own, and two of them are literally named `rx3_runtime`. `mod/` says what the directory holds and matches the word the documentation already uses when it speaks to a DJ. The `runtime_directory` key in a module manifest, the `RX3_RUNTIME/` folder written to the drive, and the separation runtime are unrelated names and keep theirs.

### Known issues

- A drive still takes several seconds to reappear after a module is applied. The runtime announces it about a second after the player is relaunched, so what remains is on the device side: the player is seen to crash twice before a third launch sticks, and the log reports `rejected: unexpected PcmReader::load prologue` on those attempts. The binary patch that widens the image table stays applied even when the hook gives up installing it, which leaves the player accepting identifiers it has no records for. Under investigation.

## 0.5.0

The two applications became one, and the stems half answers the questions it used to leave the operator guessing at.

### Changed

- `RX3 Mod Generator` and `RX3 Stem Studio` ship as a single application, `XDJ-RX3 Toolkit`, with a **USB Runtime** tab and a **Vocal Stems** tab. One download per platform replaces two; the `XDJ-RX3-Mod-Generator-*` and `XDJ-RX3-Stem-Studio-*` archives are retired in favour of `XDJ-RX3-Toolkit-*`. `make gui` and `make stems-gui` become `make app`. The per-user data directory keeps its old name, so an installed separation runtime is found rather than downloaded again.
- Secondary text follows the desktop appearance instead of a fixed `#555555` chosen against a light window. On a dark desktop the help text in Advanced options was grey on grey at roughly 1.6:1; it is now above 8:1 in both appearances, and follows a mid-session appearance change.
- The progress line says which track is being worked on (*track 3 of 20*) rather than how many are behind it, which read one short of reality.
- A preset resolves to an architecture rather than to a fixed model, and picks it from what the machine accelerates. The best models in the catalogue are roformers, which are PyTorch checkpoints; the ones that reach a GPU without PyTorch are MDX-Net, which are ONNX graphs. Where PyTorch runs on the GPU (CUDA, Apple Silicon, ROCm) both presets now run the roformer, and **Fast** is the same model over fewer passes rather than a weaker one. Where it does not (DirectML, whose PyTorch backend is pinned far behind what a roformer needs, and any CPU-only build) both run MDX-Net, giving up about 2.4 dB of vocal SDR to reach the hardware that is there. The summary under the selector states which of the two you are getting, because one preset is no longer one offer.
- **Fast** no longer overrides the segment size. It used to ask for 512 against the model's own 256 on Apple Silicon and ROCm, which is what selected the PyTorch route for an ONNX model, at the cost of running it at double the context its weights were trained for, blurring the mask in both directions. The architecture split does that job now, so every model runs at its own segment size. On a Mac, this also lifts MDX-Net's 17.6 kHz band limit, above which nothing was ever separated and the air of a vocal stayed in the instrumental.
- CoreML is still not used on a Mac: it is offered and enabled, but cannot take an MDX-Net graph whole: it claims 151 of 178 nodes across 28 partitions, so the work stays interleaved with the CPU, which is what the activity monitor was showing. An Intel Mac reaches no GPU at all, since audio-separator gates MPS on the processor being ARM.
- The `mdxc_overlap` help text said "Higher is better and slower". It is the opposite on a roformer: the option is a step in seconds, so a higher value advances the prediction window further and stitches the result from fewer passes. For `vocals_mel_band_roformer` the chunk is 11.0 s, which makes the default of 8 a 27% overlap and anything from 11 up a single pass with none at all. Anyone who raised it for quality was lowering it.
- Measured throughput is keyed by preset as well as by architecture and accelerator. Both presets run the same model on most machines and differ by roughly a factor of two in passes, so one shared rate was wrong for each of them in turn. Rates recorded under the old key are re-measured.
- Modules sit at one level, `runtime/modules/<id>/<firmware>/`, named after the `id` their manifest declares. Three of them were a level deeper, under an `access/`, `buffer/` or `beatjump/` category that no document described, so the path could not be guessed from a `requires` entry. Manifests are unchanged and the on-device layout is unaffected.
- The offline beat jump patchers moved out of `runtime/` to `tools/rx3_patcher/`, invoked as `python3 -m tools.rx3_patcher.<name>`. They run on a workstation, not on the deck, which is the line `runtime/` draws.
- `make hook` and `make test` discover module headers and regression guards instead of listing them. Adding a module no longer means editing the Makefile.
- Both Beat Jump modules now declare `requires: ["decoder-sleep"]`, so selecting either one brings the faster decoder polling with it. `decoder-sleep` moves from manifest order 30 to 8, because the build engine loads a dependency before what needs it; it can still be selected on its own.
- The feature list shows every module, including internal ones. The performance core appears greyed out and ticks itself when Key Shift or Stems is selected. Ticking a module ticks what it requires, and unticking one unticks whatever would be left requiring it. The propagation reads the manifests, so a new dependency needs no interface change.

### Added

- **Fast** and **High quality** presets, and **Custom** for anything tuned by hand. Both run the best-scoring vocal model and differ in `mdxc_overlap`, so switching between them needs no second download. Editing a model or parameter in Advanced options switches the setting to Custom rather than leaving a preset name on a configuration it no longer describes.
- A duration estimate, stated before the run from the playlist's own track lengths and corrected from the machine's measured speed as it goes. Measured speeds are kept in `throughput.json` per architecture and accelerator, so later runs start calibrated.
- A standing notice that separation occupies the machine, and a confirmation before any run estimated at more than ten minutes.

## 0.4.0

Two reasons a sidecar was ignored or left the vocal in the instrumental. Both affect tracks prepared by any earlier version, which have to be generated again.

### Fixed

- Sidecars are named with the truncation Rekordbox applies when it exports a track to a drive, keeping the first 44 characters of the stem. A track whose library filename is longer reached the drive shortened while its sidecar kept the full name, and the deck never matched the two. Two tracks that collide only once truncated are now reported as ambiguous, as they always should have been.
- Stems for mp3 and AAC sources are aligned to the deck's decoder rather than FFmpeg's. Those containers declare the samples their encoder prepended; FFmpeg drops them and the deck plays them, which left the stem 25 ms early and the vocal fully audible in the instrumental while the vocal pad still worked. Existing sidecars for such sources have to be generated again. Delete them, or the run keeps them as already generated. WAV, AIFF and FLAC sources were never affected.

The manifest gained `encoderDelayFrames`, the padding each stem was pushed back by.

## 0.3.0

First tagged release. Git history was reset to a single commit at this point, so there is nothing before it to compare against. The tables below translate names used in earlier unreleased builds and in any external tutorial written against them.

### Renamed

Modules and applications were renamed so that each name describes what the code actually does. There is no compatibility alias anywhere: a path from an older tutorial will simply not exist. Use this table to translate.

| Old | New |
|---|---|
| `XDJ-RX3 Toolkit Builder` (application) | `RX3 Mod Generator` |
| `apps/xdj-rx3-toolkit-builder/` | `apps/rx3-mod-generator/` |
| `apps/xdj-rx3-toolkit-builder/builder.spec` | `apps/rx3-mod-generator/mod_generator.spec` |
| `org.xdjrx3.toolkit.builder` (macOS bundle id) | `org.xdjrx3.mod.generator` |
| `XDJ-RX3-Toolkit-*.zip` / `.tar.gz` (release archives) | `XDJ-RX3-Mod-Generator-*.zip` / `.tar.gz` |
| `tools/rx3_runtime/builder.py` | `tools/rx3_runtime/build.py` |
| `tools/rx3_runtime/build_runtime.py` | `tools/rx3_runtime/cli.py` |
| `tools/rx3_stems/engine.py` | `tools/rx3_stems/provisioning.py` |
| `tools/rx3-firmware/` | `tools/rx3_firmware/` |
| `patches/` | `runtime/modules/` |
| `patches/beatjump/32bars/` | `runtime/modules/beatjump/beatjump-32bars/` |
| `patches/beatjump/no_quantize/` | `runtime/modules/beatjump/beatjump-no-quantize/` |
| `patches/buffer/decoder_sleep/` | `runtime/modules/buffer/decoder-sleep/` |
| `patches/access/telnet/` | `runtime/modules/access/telnet/` |
| `patches/stems/` | `runtime/modules/stems/` |
| `autoexec.sh` (repository root) | `runtime/autoexec.sh` |
| `tests/test_toolkit_builder.py` | `tests/test_mod_generator.py` |

Module identifiers are unchanged. `beatjump-32bars`, `beatjump-no-quantize`, `decoder-sleep`, `stems` and `telnet` still select the same modules on the command line and in the manifests. The name of the project itself, XDJ-RX3 Toolkit, is unchanged.

Everything the RX3 executes now lives under `runtime/`. Everything above it runs on your computer.

### Changed

Documentation was rewritten. The single README became a short landing page plus `docs/`, with a Quick Start that runs from a bare computer to a track playing in stems without a forward reference. See `docs/`.

Two corrections to earlier documentation, both resolved against the code:

- The accelerator table in `apps/rx3-stem-studio/README.md` claimed CUDA used the default PyTorch wheels. It uses an explicit index, `cu130`, or `cu126` on cards below compute capability 7.5 (`tools/rx3_stems/provisioning.py`).
- The count of guarded words for Beat Jump was stated as thirteen in one file and twelve in another. The count is no longer documented; the offsets in `runtime/modules/beatjump/beatjump-32bars/1.19/patch.py` are the reference.

### Note on earlier versions

The troubleshooting table used to carry a fix attributed to "v0.2.1". No tag or release corresponds to that version, so the fix is described without it.
