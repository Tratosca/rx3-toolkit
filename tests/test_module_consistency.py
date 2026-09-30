# SPDX-License-Identifier: MPL-2.0
"""Cross-checks for facts that are stated twice in two different languages.

The stem container is written by Python but parsed by C on the deck, and
every module's shell contract has to step aside the same way. Nothing in the
build makes the copies agree, so these tests do.

Modules are located through their manifest rather than by path, so moving a
module directory does not silently disable a test.
"""

import re
import struct
import unittest
from pathlib import Path

from app.runtime.build import discover_patches
from app.stems import stem

REPOSITORY = Path(__file__).parents[1]

C_FIELD = re.compile(r"^\s*(\w+)\s+(\w+)\s*(?:\[(\d+)\])?\s*;", re.MULTILINE)
C_SCALARS = {"uint8_t": "B", "uint32_t": "I", "uint64_t": "Q"}


def modules_by_id():
    return {patch.patch_id: patch for patch in discover_patches()}


class StemHeaderTests(unittest.TestCase):
    """The `.rx3stem` header is declared in Python and parsed in C."""

    def test_declared_layout_matches_the_device_struct(self):
        declaration = modules_by_id()["stems"].directory / "rx3_stems_decl.h"
        text = declaration.read_text(encoding="utf-8")
        body = re.search(
            r"struct\s+__attribute__\(\(packed\)\)\s+stem_header\s*\{(.*?)\}",
            text, re.DOTALL,
        )
        self.assertIsNotNone(body, "stem_header is no longer declared in C")

        fields = []
        for ctype, _name, count in C_FIELD.findall(body.group(1)):
            if ctype == "char":
                fields.append(f"{count or 1}s")
            else:
                self.assertIn(ctype, C_SCALARS, f"unmapped C type {ctype}")
                code = C_SCALARS[ctype]
                # A uint8_t array is an opaque blob on both sides, not a count.
                fields.append(f"{count}s" if count and code == "B" else code * int(count or 1))

        self.assertEqual(
            "<" + "".join(fields), stem.HEADER.format,
            "the C struct and stem.HEADER no longer describe the same bytes",
        )
        self.assertEqual(struct.calcsize("<" + "".join(fields)), stem.HEADER.size)

    def test_magic_is_the_one_the_core_compares(self):
        hook = (modules_by_id()["stems"].directory / "rx3_stems_loader.h").read_text(
            encoding="utf-8"
        )
        compared = re.search(r'memcmp\(header\.magic,\s*"([^"]+)",\s*(\d+)u?\)', hook)
        self.assertIsNotNone(compared, "the core no longer compares the stem magic")
        literal, length = compared.group(1), int(compared.group(2))
        self.assertEqual(stem.MAGIC[:length], literal.encode("ascii").decode("unicode_escape").encode("ascii"))
        self.assertLessEqual(length, len(stem.MAGIC))


if __name__ == "__main__":
    unittest.main()


class OptOutTests(unittest.TestCase):
    """Every module must step aside without stopping the session.

    `autoexec.sh` aborts the whole run when any prepare hook returns non-zero,
    and writes no guarded word at all. A kill switch is meant to remove one
    module; returning failure from it removes all of them.
    """

    def test_no_module_fails_the_session_to_opt_out(self):
        offenders = []
        for patch in discover_patches():
            module = patch.directory / "module.sh"
            if not module.is_file():
                continue
            for number, line in enumerate(module.read_text().splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("module_disabled_by_switch") and \
                        not stripped.endswith("return 0"):
                    offenders.append(f"{patch.patch_id}:{number}")
        self.assertEqual(offenders, [], "a kill switch must opt out with return 0")




class LogoFramingTests(unittest.TestCase):
    """The framing arithmetic exists twice, in Python and in JavaScript.

    The interface has to move the artwork while the operator drags, and the
    encoder is a per-pixel loop that takes most of a second for the largest
    pane, so it cannot be asked. The two therefore compute the same rectangle
    from the same numbers, and this runs the shipped JavaScript against the
    Python to make sure they still do. Both use IEEE 754 doubles and nothing
    but multiply, divide, floor and ceil, so agreement is exact and any
    difference is an edit rather than rounding.
    """

    MARKERS = ("// PLACEMENT BEGIN", "// PLACEMENT END")

    def framing(self):
        source = (REPOSITORY / "app/ui/web/logo.js").read_text(encoding="utf-8")
        begin, end = self.MARKERS
        self.assertIn(begin, source, "the framing is no longer marked for lifting")
        return source[source.index(begin) + len(begin):source.index(end)]

    def cases(self):
        from app.logo import container

        for geometry in (container.CLASSIC, container.FULL):
            for mode in ("contain", "cover"):
                for art in ((1, 1), (16, 9), (400, 120), (1200, 630), (4000, 40),
                            (40, 4000), (867, 424), (869, 426)):
                    for zoom in (0.2, 0.25, 0.5, 0.9999, 1.0, 1.5, 3.0, 6.0, 6.5):
                        for offset in (0, 1, -1, 23, -23, 5000, -5000, 0.5, -0.5):
                            yield geometry, mode, art, zoom, offset

    def test_the_interface_frames_a_logo_exactly_where_the_encoder_puts_it(self):
        import json
        import shutil
        import subprocess

        from app.logo import container

        node = shutil.which("node")
        if not node:
            self.skipTest("node runs the interface's own copy of the framing")

        wanted, given = [], []
        for geometry, mode, art, zoom, offset in self.cases():
            frame = {"mode": mode, "zoom": zoom, "offsetX": offset, "offsetY": -offset}
            given.append({
                "art": art,
                "ink": {"width": geometry.ink_width, "height": geometry.ink_height},
                "frame": frame,
            })
            x, y, width, height = container.placement(
                art[0], art[1], geometry,
                mode=mode, zoom=zoom, offset_x=offset, offset_y=-offset,
            )
            wanted.append([x, y, width, height])

        driver = (
            self.framing()
            + "\nvar limits = {zoomMin: %r, zoomMax: %r, minVisible: %d};\n"
            % (container.ZOOM_MIN, container.ZOOM_MAX, container.MIN_VISIBLE)
            + "var cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
            + "var out = cases.map(function (c) {\n"
            + "  var box = placement(c.art[0], c.art[1], c.ink, c.frame, limits);\n"
            + "  return [box.x, box.y, box.width, box.height];\n"
            + "});\n"
            + "process.stdout.write(JSON.stringify(out));\n"
        )
        answer = subprocess.run(
            [node, "-e", driver], input=json.dumps(given),
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(answer.stdout), wanted)


class DisplayModeTests(unittest.TestCase):
    """The display mode is one letter, chosen in shell and read in C.

    The module picks a letter from a word on the drive and exports it; the core
    compares the first character of RX3_THEME against its own set. Nothing makes
    the two agree, and a letter one side sends that the other does not read is
    the worst kind of failure here: the deck starts, the module reports the mode
    it thinks it chose, and the display never changes.
    """

    MODULE = REPOSITORY / "mod/modules/theme-white/module.sh"
    # The module reads its own letter now; the core never sees it.
    CORE = REPOSITORY / "mod/modules/theme-white/rx3_theme_feature.h"

    def exported(self):
        """Every letter the module can export."""
        source = self.MODULE.read_text(encoding="utf-8")
        return set(re.findall(r"letter=([a-z])\b", source))

    def understood(self):
        """Every letter the runtime compares the mode against."""
        source = self.CORE.read_text(encoding="utf-8")
        return set(re.findall(r"theme\[0\]\s*==\s*'([a-z])'", source))

    def test_every_mode_the_module_offers_is_one_the_core_reads(self):
        exported = self.exported()
        understood = self.understood()
        self.assertTrue(exported, "the module exports no display mode at all")
        # The fallthrough mode is the one the core reaches by comparing against
        # nothing, so it is exported without ever being compared.
        unread = exported - understood - {"s"}
        self.assertEqual(unread, set(), f"the module exports {unread}, which the core ignores")

    def test_every_mode_the_core_reads_can_be_asked_for(self):
        unreachable = self.understood() - self.exported()
        self.assertEqual(
            unreachable, set(),
            f"the core handles {unreachable}, and nothing on a drive can ask for it",
        )


class PadRowLayoutTests(unittest.TestCase):
    """The pad row's geometry is solved in C on the deck and in Python here.

    The row has no other verification before hardware: the preview is the only
    way to see what a control will look like, and a preview that quietly
    disagrees with the deck is a deck misbehaving with nothing to catch it. So
    the C is compiled and run rather than read, the way the interface's framing
    is run under node above. Reading it as text is what this repository stopped
    doing, because every edit of the C broke a text assertion without a deck
    behaving differently.

    The block is lifted between its markers, which is also what keeps it honest:
    it has to stay free of player types, globals and libc to compile here at all.
    """

    MARKERS = ("/* RX3 PAD LAYOUT BEGIN */", "/* RX3 PAD LAYOUT END */")

    def block(self):
        source = (
            modules_by_id()["core"].directory / "ui/rx3_pad_layout.h"
        ).read_text(encoding="utf-8")
        begin, end = self.MARKERS
        self.assertIn(begin, source, "the layout is no longer marked for lifting")
        return source[source.index(begin) + len(begin):source.index(end)]

    def cases(self):
        """Every shape the three panels ask for, and a few they do not."""
        spans = ((19, 595), (20, 1240))
        weights = (
            [1], [1, 1], [1, 1, 1], [1, 1, 1, 1],
            [1] * 5, [1] * 6, [1] * 7, [1] * 8,
            [9, 1], [1, 9], [1, 2, 2, 2, 2], [3, 1, 1], [2, 1, 2], [1, 2, 3, 4],
        )
        for origin, span in spans:
            for weight in weights:
                yield origin, span, weight

    def test_the_deck_and_the_preview_solve_the_same_row(self):
        import shutil
        import subprocess
        import tempfile

        from app.preview import layout

        compiler = shutil.which("cc") or shutil.which("clang")
        if not compiler:
            self.skipTest("a C compiler runs the deck's own copy of the layout")

        lines, wanted = [], []
        for origin, span, weight in self.cases():
            lines.append(
                "S %d %d %d %s" % (len(weight), origin, span,
                                   " ".join(str(value) for value in weight))
            )
            wanted.append(
                " ".join("%d,%d" % (cell.x1, cell.x2)
                         for cell in layout.solve(weight, origin, span))
            )
        for width in (60, 120, 183, 203, 288, 391, 595, 1240):
            lines.append("P 19 %d" % (19 + width - 1))
            wanted.append(
                " ".join("%d,%d" % (part.x1, part.x2)
                         for part in layout.stepper_parts(
                             layout.Cell(19, 19 + width - 1)))
            )
        track = layout.Cell(20, 1117)
        for value in range(0, 101):
            lines.append("X 20 1117 %d 100" % value)
            wanted.append(str(layout.slider_x(track, value, 100)))
        for x in range(0, 1280, 7):
            lines.append("V 20 1117 %d 100" % x)
            wanted.append(str(layout.slider_value(track, x, 100)))

        driver = self.block() + r"""
#include <stdio.h>
#include <string.h>
int main(void)
{
    char line[512];
    while (fgets(line, sizeof line, stdin)) {
        struct rx3_pad_cell cells[RX3_PAD_CELL_MAX], parts[3], cell;
        unsigned char weights[RX3_PAD_CELL_MAX];
        int count, origin, span, i, x, maximum, offset, read;
        if (line[0] == 'S') {
            sscanf(line + 1, " %d %d %d%n", &count, &origin, &span, &offset);
            for (i = 0; i < count; i++) {
                int weight;
                sscanf(line + 1 + offset, " %d%n", &weight, &read);
                offset += read;
                weights[i] = (unsigned char)weight;
            }
            count = rx3_pad_solve(weights, count, origin, span, cells);
            for (i = 0; i < count; i++)
                printf(i ? " %d,%d" : "%d,%d", cells[i].x1, cells[i].x2);
            printf("\n");
        } else if (line[0] == 'P') {
            sscanf(line + 1, " %d %d", &cell.x1, &cell.x2);
            rx3_pad_stepper_parts(cell, parts);
            for (i = 0; i < 3; i++)
                printf(i ? " %d,%d" : "%d,%d", parts[i].x1, parts[i].x2);
            printf("\n");
        } else if (line[0] == 'X') {
            sscanf(line + 1, " %d %d %d %d", &cell.x1, &cell.x2, &x, &maximum);
            printf("%d\n", rx3_pad_slider_x(cell, x, maximum));
        } else if (line[0] == 'V') {
            sscanf(line + 1, " %d %d %d %d", &cell.x1, &cell.x2, &x, &maximum);
            printf("%d\n", rx3_pad_slider_value(cell, x, maximum));
        }
    }
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as workspace:
            source = Path(workspace) / "layout.c"
            binary = Path(workspace) / "layout"
            source.write_text(driver, encoding="utf-8")
            build = subprocess.run(
                [compiler, "-std=c99", "-O2", "-o", str(binary), str(source)],
                capture_output=True, text=True,
            )
            self.assertEqual(
                build.returncode, 0,
                "the lifted layout no longer compiles on its own, which means "
                "it has grown a dependency it must not have:\n" + build.stderr,
            )
            answer = subprocess.run(
                [str(binary)], input="\n".join(lines) + "\n",
                capture_output=True, text=True, check=True,
            )
        self.assertEqual(answer.stdout.strip().splitlines(), wanted)

    def test_the_row_is_solved_without_overlaps_or_gaps_at_the_ends(self):
        """A cell drawn where nothing can be touched, or two cells over one
        pixel, is the failure this whole layer exists to prevent."""
        from app.preview import layout

        for count in range(1, layout.CELL_MAX + 1):
            with self.subTest(count=count):
                cells = layout.solve([1] * count)
                self.assertEqual(cells[0].x1, layout.DECK_ORIGIN)
                self.assertEqual(
                    cells[-1].x2,
                    layout.DECK_ORIGIN + layout.DECK_SPAN - 1,
                    "the row must end on the same pixel whatever the count",
                )
                for earlier, later in zip(cells, cells[1:]):
                    self.assertLess(earlier.x2, later.x1)
                for index, cell in enumerate(cells):
                    for x in (cell.x1, (cell.x1 + cell.x2) // 2, cell.x2):
                        self.assertEqual(layout.hit(cells, x), index)

    def test_the_solver_reproduces_the_strip_it_replaces(self):
        """The stems strip's measured widths, which the gap table carries."""
        from app.preview import layout

        measured_width = {1: 595, 2: 288, 3: 187, 4: 139}
        measured_gap = {1: 0, 2: 19, 3: 17, 4: 13}
        for count, width in measured_width.items():
            with self.subTest(count=count):
                stride = width + measured_gap[count]
                cells = layout.solve([1] * count)
                for index, cell in enumerate(cells):
                    self.assertEqual(cell.x1, 19 + index * stride)
                    self.assertEqual(cell.width, width)


def _octal_bytes(escaped: str) -> bytes:
    """The byte string a module.sh patch argument stands for."""
    return bytes(int(part, 8) for part in escaped.split("\\") if part)


def _movw(word: int) -> tuple[int, int]:
    """Decode an ARM `movw rD, #imm16`, or say it is not one."""
    if word & 0x0FF00000 != 0x03000000:
        raise AssertionError(f"not a movw: {word:#010x}")
    return ((word >> 16) & 0xF) << 12 | (word & 0xFFF), (word >> 12) & 0xF


class ImageTableBoundTests(unittest.TestCase):
    """The private image bound is one fact written down in three files.

    The player rejects an image id past a bound compiled into it, so the mod
    rewrites that bound with a guarded launch patch before rbp starts, and the
    core hooks the same instruction using the patched word as its guard. The
    number therefore appears in `module.sh`, in `EXTENDED_IMAGE_COUNT` and in
    `image_info_guard`, and every way of getting them out of step is silent: the
    hook falls back to the stock guard, that fails too, one warning is logged
    and the row comes up blank with the rest of the mod working.
    """

    def core(self):
        return modules_by_id()["core"].directory

    def hook(self):
        """The core's sources, which is where all of these constants live: the
        bound in the hook, the glyph ids beside the artwork that uses them."""
        return "\n".join(
            (self.core() / name).read_text(encoding="utf-8")
            for name in ("rx3_core_hook.c", "ui/rx3_pad_atlas.h", "api/rx3_image_api.h")
        )

    def patch_words(self):
        text = (self.core() / "module.sh").read_text(encoding="utf-8")
        found = re.search(
            r"register_patch\s+\d+\s+'([^']+)'\s+'([^']+)'\s+image-table-private-ids",
            text,
        )
        self.assertIsNotNone(found, "the image-table patch is no longer registered")
        return (int.from_bytes(_octal_bytes(found.group(1)), "little"),
                int.from_bytes(_octal_bytes(found.group(2)), "little"))

    def define(self, name):
        found = re.search(rf"#define {name}\s+(0x[0-9a-fA-F]+)u?", self.hook())
        self.assertIsNotNone(found, f"{name} is gone")
        return int(found.group(1), 16)

    def test_the_patch_rewrites_the_bound_the_core_expects(self):
        stock, patched = self.patch_words()
        stock_bound, stock_register = _movw(stock)
        patched_bound, patched_register = _movw(patched)
        self.assertEqual(stock_register, patched_register,
                         "the patch writes to a different register than it read")
        self.assertEqual(stock_bound, self.define("RX3_NATIVE_IMAGE_COUNT") - 1,
                         "the stock word no longer matches RX3_NATIVE_IMAGE_COUNT")
        self.assertEqual(
            patched_bound, self.define("EXTENDED_IMAGE_COUNT") - 1,
            "module.sh admits a different number of private ids than the core "
            "allocates records for",
        )

    def test_the_image_lookup_guard_carries_the_patched_word(self):
        """The core hooks the instruction the patch just wrote, so its guard is
        that same word. A stale guard is a silent fallback to stock output."""
        _, patched = self.patch_words()
        found = re.search(
            r"static const uint8_t image_info_guard\[8\] = \{\s*([^}]+)\}", self.hook()
        )
        self.assertIsNotNone(found, "the image-info guard is gone")
        guard = [int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]+)",
                                                        found.group(1))]
        self.assertEqual(int.from_bytes(bytes(guard[:4]), "little"), patched)

        stock_found = re.search(
            r"static const uint8_t stock_image_info_guard\[8\] = \{\s*([^}]+)\}",
            self.hook(),
        )
        self.assertIsNotNone(stock_found, "the stock fallback guard is gone")
        stock_guard = [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)",
                                                      stock_found.group(1))]
        self.assertEqual(int.from_bytes(bytes(stock_guard[:4]), "little"),
                         self.patch_words()[0])

    def test_the_artwork_fits_the_ids_that_were_reserved(self):
        """More glyphs than reserved ids writes records past the table's end."""
        from app.preview.atlas import Atlas

        base = self.define("RX3_PAD_GLYPH_IMAGE_BASE")
        found = re.search(r"#define RX3_PAD_GLYPH_IMAGE_MAX\s+(\d+)u?", self.hook())
        self.assertIsNotNone(found, "the glyph id reserve is gone")
        reserve = int(found.group(1))
        self.assertLessEqual(
            base + reserve, self.define("EXTENDED_IMAGE_COUNT"),
            "the glyph reserve runs past the table the core allocates",
        )
        for theme in ("dark", "light"):
            atlas = Atlas.load(self.core() / f"assets/glyph-atlas-{theme}.rgb565")
            with self.subTest(theme=theme):
                self.assertLessEqual(
                    len(atlas.glyphs) * atlas.state_count, reserve,
                    "the shipped artwork wants more image ids than are reserved",
                )


class GlyphAtlasTests(unittest.TestCase):
    """The pad row's lettering is artwork, and a character with no artwork is
    drawn as nothing at all: a caption silently missing a letter."""

    def atlases(self):
        from app.preview.atlas import Atlas

        directory = modules_by_id()["core"].directory
        for theme in ("dark", "light"):
            yield theme, Atlas.load(directory / f"assets/glyph-atlas-{theme}.rgb565")

    def test_the_shipped_artwork_describes_itself(self):
        for theme, atlas in self.atlases():
            with self.subTest(theme=theme):
                self.assertTrue(atlas.glyphs)
                self.assertEqual(atlas.state_count, 3)
                self.assertTrue(atlas.cell_height)
                for glyph in atlas.glyphs.values():
                    size = glyph.width * atlas.cell_height * 2
                    end = glyph.offset + size * atlas.state_count
                    self.assertLessEqual(
                        end, len(atlas.blob),
                        "a glyph points past the end of the file, which on a "
                        "deck is an image record aimed at unmapped memory",
                    )

    def test_every_character_a_control_can_show_has_a_glyph(self):
        # Where each of these comes from, so the list can be checked against the
        # panels by reading rather than by trusting a regex over C.
        spellable = set(
            "0123456789%"         # keys, shifts and volume percentages
            "ABCDEFG"             # Camelot letters and note names
            "<>*+- "              # the KEY row's arrows, match mark and signs
            "DRUMSBASVOCLINTE"    # DRUMS BASS VOCAL INST INSTRUMENTAL
            "NOSTEMRR"            # NO STEMS, STEMS ERR
            "VOL"                 # the sample level readout
        )
        for theme, atlas in self.atlases():
            with self.subTest(theme=theme):
                missing = sorted(
                    character for character in spellable
                    if character != " " and atlas.glyph(character) is None
                )
                self.assertEqual(missing, [], "a caption would render a hole")
                self.assertTrue(atlas.space_advance, "a space must still advance")

    def test_the_grounds_are_the_measured_palette(self):
        """The artwork carries the ground it was drawn on, and the row paints
        that same colour underneath it. Blue marks a selection in both rooms."""
        for theme, atlas in self.atlases():
            with self.subTest(theme=theme):
                self.assertEqual(atlas.ground(2), (0, 125, 230))
                self.assertNotEqual(atlas.ground(0), (0, 125, 230))
        dark = dict(self.atlases())["dark"]
        light = dict(self.atlases())["light"]
        self.assertEqual(dark.ground(0), (0, 0, 0))
        self.assertEqual(light.ground(0), (222, 219, 222))


class FirmwareCoverageTests(unittest.TestCase):
    """Each module says which firmware versions it is built against.

    That is a fact about the module, and with no directory to infer it from it
    has to be written down. Writing it down thirteen times is what invites
    drift, so this is what catches it: a module claiming a version its own
    dependency does not carry builds a drive missing a module, quietly, because
    discovery filters before dependencies are resolved.
    """

    def modules(self):
        return {patch.patch_id: patch for patch in discover_patches(REPOSITORY)}

    def test_every_module_declares_at_least_one_firmware(self):
        for name, patch in self.modules().items():
            with self.subTest(module=name):
                self.assertTrue(patch.firmwares)
                for version in patch.firmwares:
                    self.assertRegex(version, r"^[0-9]+\.[0-9]+$")

    def test_a_module_does_not_outrun_what_it_requires(self):
        """Claiming a version your dependency does not have is a module that
        vanishes from the build rather than one that fails it."""
        modules = self.modules()
        for name, patch in modules.items():
            for required in patch.requires:
                with self.subTest(module=name, requires=required):
                    self.assertIn(required, modules)
                    missing = sorted(
                        set(patch.firmwares) - set(modules[required].firmwares)
                    )
                    self.assertEqual(
                        missing, [],
                        f"{name} claims {', '.join(missing)} but {required} does not",
                    )

    def test_every_declared_firmware_can_actually_be_built(self):
        """A version some module names but nothing else supports is a version an
        operator can pick and get an empty or broken drive from."""
        from app.runtime.build import available_versions, resolve_patches

        versions = available_versions(REPOSITORY)
        self.assertTrue(versions, "no firmware is offered at all")
        for version in versions:
            with self.subTest(firmware=version):
                definitions = discover_patches(REPOSITORY, version)
                self.assertTrue(definitions, f"no module is built for {version}")
                defaults = [
                    patch.patch_id for patch in definitions
                    if patch.selectable and patch.default
                ]
                # resolve_patches raises on a dependency this version cannot meet.
                resolve_patches(definitions, defaults)

    def test_the_accepted_player_binaries_are_declared_once(self):
        """One list, because the deck asks one question: is this a binary I
        know? It hashes the player and looks the answer up, and a drive built
        for one version still recognises the other."""
        compatibility = REPOSITORY / "mod/compatibility.sh"
        self.assertTrue(compatibility.is_file())
        checksums = re.findall(
            r"^register_rbp_sha1 ([0-9a-f]{40})$",
            compatibility.read_text(encoding="utf-8"), re.MULTILINE,
        )
        self.assertTrue(checksums)
        self.assertEqual(len(checksums), len(set(checksums)), "a checksum is listed twice")

    def test_no_module_keeps_a_version_directory(self):
        """The directory level named after a firmware version is gone: a module
        is one directory, and the manifest says which versions it serves."""
        for manifest in sorted((REPOSITORY / "mod/modules").glob("**/manifest.json")):
            with self.subTest(manifest=str(manifest.relative_to(REPOSITORY))):
                self.assertEqual(
                    manifest.parent.parent.name, "modules",
                    "a module directory sits directly under mod/modules/",
                )


class MessageLanguageTests(unittest.TestCase):
    """A message is one string per language, and the player names the language.

    The deck reads a byte that counts from one and indexes a table that counts
    from zero, so the selection is one subtraction away from showing an operator
    the language next to theirs, and one bounds check away from handing the
    player a pointer past the end of a table. Neither failure says anything on
    its own, so the selection is compiled here and walked.
    """

    MARKERS = ("/* RX3 MESSAGE SELECT BEGIN */", "/* RX3 MESSAGE SELECT END */")
    LANGUAGES = 18

    def block(self):
        source = (
            modules_by_id()["core"].directory / "firmware/rx3_message.h"
        ).read_text(encoding="utf-8")
        begin, end = self.MARKERS
        self.assertIn(begin, source, "the selection is no longer marked for lifting")
        return source[source.index(begin) + len(begin):source.index(end)]

    def test_every_language_selects_a_string_that_exists(self):
        import shutil
        import subprocess
        import tempfile

        compiler = shutil.which("cc") or shutil.which("clang")
        if not compiler:
            self.skipTest("a C compiler runs the deck's own copy of the selection")

        driver = """
#include <stdint.h>
#include <stdio.h>
#define RX3_LANGUAGE_COUNT %du
struct rx3_message { const uint16_t *const *by_language; unsigned char count; };
""" % self.LANGUAGES + self.block() + """
int main(void) {
    static const uint16_t a[] = {'A', 0}, b[] = {'B', 0}, c[] = {'C', 0};
    const uint16_t *const one[] = {a};
    const uint16_t *const two[] = {a, b};
    const uint16_t *const gap[] = {a, 0, c};
    struct rx3_message m1 = {one, 1}, m2 = {two, 2}, m3 = {gap, 3};
    struct rx3_message empty = {one, 0}, null = {0, 1};
    for (unsigned int language = 0; language < 64u; language++) {
        const uint16_t *r1 = rx3_message_text_for(&m1, language);
        const uint16_t *r2 = rx3_message_text_for(&m2, language);
        const uint16_t *r3 = rx3_message_text_for(&m3, language);
        printf("%u %c %c %c\\n", language,
               r1 ? (char)r1[0] : '-', r2 ? (char)r2[0] : '-', r3 ? (char)r3[0] : '-');
    }
    printf("empty %s\\n", rx3_message_text_for(&empty, 0) ? "text" : "none");
    printf("null %s\\n", rx3_message_text_for(&null, 0) ? "text" : "none");
    printf("nothing %s\\n", rx3_message_text_for(0, 0) ? "text" : "none");
    /* The player counts languages from one; the tables count from zero. */
    for (unsigned int n = 0; n < 260u; n++)
        printf("lang %u %u\\n", n, rx3_message_language_from(n));
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as workspace:
            source = Path(workspace) / "select.c"
            binary = Path(workspace) / "select"
            source.write_text(driver, encoding="utf-8")
            build = subprocess.run(
                [compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-o", str(binary), str(source)],
                capture_output=True, text=True,
            )
            self.assertEqual(
                build.returncode, 0,
                "the lifted selection no longer compiles on its own, so it has "
                "grown a dependency it must not have:\n" + build.stderr,
            )
            answer = subprocess.run([str(binary)], capture_output=True, text=True,
                                    check=True)

        lines = answer.stdout.strip().splitlines()
        for line in lines[:64]:
            language, one, two, gap = line.split()
            index = int(language)
            # A table of one always answers with its only entry.
            self.assertEqual(one, "A")
            # A table of two answers B for language 1 and A for everything else.
            self.assertEqual(two, "B" if index == 1 else "A")
            # A hole in a table falls back rather than returning the hole.
            self.assertEqual(gap, {0: "A", 1: "A", 2: "C"}.get(index, "A"))
        self.assertIn("empty none", answer.stdout)
        self.assertIn("null none", answer.stdout)
        self.assertIn("nothing none", answer.stdout)

        # The player counts from one, the tables from zero, and the byte can
        # hold anything at all before the player has set it.
        seen = {}
        for line in lines:
            if line.startswith("lang "):
                _, number, index = line.split()
                seen[int(number)] = int(index)
        self.assertEqual(seen[0], 0, "an unset byte must fall back to English")
        for number in range(1, self.LANGUAGES + 1):
            self.assertEqual(
                seen[number], number - 1,
                "the language number counts from one and the tables from zero",
            )
        for number in range(self.LANGUAGES + 1, 256):
            self.assertEqual(
                seen[number], 0,
                f"language number {number} is not one the player knows",
            )


class MessageTranslationTests(unittest.TestCase):
    """Every language the player offers gets its own line, or it gets English.

    The fallback is deliberate and it is also the hazard: a table with a hole in
    it works, shows English to whoever set that language, and says nothing about
    it. So the count, the gaps and the duplicates are checked here rather than
    discovered by an operator who does not read English.
    """

    def table(self):
        source = (
            modules_by_id()["core"].directory / "ui/rx3_messages.h"
        ).read_text(encoding="utf-8")
        return source, re.findall(r'RX3_TEXT\("((?:[^"\\]|\\.)*)"\)', source)

    def test_every_language_has_its_own_line(self):
        source, entries = self.table()
        found = re.search(r"#define RX3_LANGUAGE_COUNT (\d+)u", (
            modules_by_id()["core"].directory / "firmware/rx3_message.h"
        ).read_text(encoding="utf-8"))
        self.assertIsNotNone(found, "the language count is gone")
        languages = int(found.group(1))
        self.assertEqual(
            len(entries), languages,
            f"{languages} languages are offered and {len(entries)} are written",
        )
        for index, text in enumerate(entries, start=1):
            with self.subTest(language=index):
                self.assertTrue(text.strip(), "an empty line shows nothing at all")

    def test_no_language_quietly_repeats_another(self):
        """Two identical lines means one of them was never translated."""
        _, entries = self.table()
        seen = {}
        for index, text in enumerate(entries, start=1):
            if text in seen:
                self.fail(
                    f"language {index} repeats language {seen[text]} word for "
                    f"word: {text!r}. Leave it out to fall back to English "
                    f"rather than copying a language nobody set."
                )
            seen[text] = index

    def test_the_notice_stays_about_as_short_as_the_player_s_own(self):
        """The player's own notices in this position run to about twenty-two
        characters. What it does with a longer one has not been tried."""
        _, entries = self.table()
        for index, text in enumerate(entries, start=1):
            with self.subTest(language=index):
                self.assertLessEqual(
                    len(text), 34,
                    f"{text!r} is longer than anything the player shows there",
                )
