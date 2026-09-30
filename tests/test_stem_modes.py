# SPDX-License-Identifier: MPL-2.0
"""The two stem modes a DJ can prepare, from the computer to the deck's loader.

VOCAL + INST and VOCAL + DRUMS + INST. INST is never a file: the deck rebuilds
it from the original mix, so it carries whatever was not separated, bass
included. Each mode is produced by the automatic job and by the manual import,
then read back by the real C loader.
"""
import array
import json
import pathlib
import random
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch

from package_fixture import isolate
from app.localization import LocalizedError, catalogs
from app.services import stems as service
from app.stems import (audition, importing, job, limits, mixing, package, provisioning,
                       rekordbox, safety, separation, stem, waveform)

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = shutil.which("clang") or shutil.which("cc")
FFMPEG = shutil.which("ffmpeg")
MODES = {"vocal": ("vocals",), "drums": ("vocals", "drums")}


def c_function(path, name):
    text = path.read_text()
    start = text.index("static unsigned int " + name + "(")
    level, end = 1, text.index("{", start) + 1
    while level:
        level += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


LOADER = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#define RX3_PLATFORM_H
#include "core/api/rx3_module_api.h"
#include "stems/rx3_stems_decl.h"
static unsigned long available_kb;
static unsigned long memory_available_kb(void) { return available_kb; }
static int mock_reserve(const void *o, unsigned long bytes, unsigned long floor_kb) {
    (void)o; unsigned long kb = bytes / 1024u + (bytes %% 1024u != 0u), have = available_kb;
    return !floor_kb || (have > floor_kb && have - floor_kb >= kb);
}
static void mock_move(const void *o, unsigned long b) { (void)o; (void)b; }
static unsigned long mock_held(void) { return 0; }
static const struct rx3_memory_service memory_mock={mock_reserve,mock_move,mock_move,mock_move,memory_available_kb,mock_held};
static const struct rx3_services stem_services={.memory=&memory_mock};
static const struct rx3_services *framework=&stem_services;
#include "stems/rx3_stems_package.h"
%s
int main(int argc, char **argv) {
    (void)argc;
    int fd = open(argv[1], O_RDONLY);
    unsigned int other = (unsigned int)strtoul(argv[2], 0, 0);
    available_kb = strtoul(argv[3], 0, 0);
    struct stem_payload next[3] = {0};
    unsigned int count = stems_package_load(fd, next, other, 0);
    printf("{\"roles\": %%u", count);
    if (count) {
        /* What the loader publishes once a package is accepted. */
        struct stems_deck_context *c = &stems_decks[0];
        memcpy(c->payloads, next, sizeof(next));
        c->payload_count = count; c->armed = 1; c->reader = c;
        c->selection = ((2u << count) - 1u) * 17u;
        const struct rx3_wave_header *w = (const void *)next[0].wave;
        uint8_t *out = malloc(w->count * 3u);
        printf(", \"available\": %%u, \"wave\": [", stems_available(c));
        for (unsigned int mask = 1; mask < 16u; mask++)
            printf("%%s%%u", mask > 1 ? ", " : "", stems_waveform(0, mask, w->version==4u?(w->stride==3u?3u:w->stride-1u):0u, out, w->count) == w->count);
        printf("]");
        free(out);
    }
    printf("}\n");
    return 0;
}
'''


def build_loader(directory):
    source = directory / "loader.c"
    exe = directory / "loader"
    functions = (c_function(ROOT / "mod/modules/stems/rx3_stems_audio.h", "stems_available") + "\n" +
                 c_function(ROOT / "mod/modules/stems/rx3_stems_feature.h", "stems_waveform"))
    source.write_text(LOADER % functions)
    subprocess.run([COMPILER, "-std=c11", "-I" + str(ROOT / "mod/modules"), str(source), "-o", str(exe)],
                   check=True, capture_output=True)
    return exe


def load(exe, path, other=0, available_kb=1 << 22):
    result = subprocess.run([str(exe), str(path), str(other), str(available_kb)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def write_wav(path, samples):
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


def write_pcm(path, samples):
    path.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, len(samples) // 2, b"\0" * 32)
                     + samples.tobytes())


class LimitTests(unittest.TestCase):
    """The limits the computer applies are the loader's own."""

    @unittest.skipUnless(COMPILER, "a native C compiler is required")
    def test_python_limits_are_the_c_header_values(self):
        names = ("MIN_FRAMES", "MAX_FRAMES", "RESIDENT_BYTES", "PLAYER_RESERVE_KIB",
                 "MANIFEST_BYTES", "MAX_COLUMNS")
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "limits.c"
            source.write_text('#include <stdio.h>\n#include "stems/rx3_stems_limits.h"\nint main(void){' +
                              "".join(f'printf("%u\\n", RX3_STEMS_{name});' for name in names) + "return 0;}")
            exe = pathlib.Path(directory) / "limits"
            subprocess.run([COMPILER, "-I" + str(ROOT / "mod/modules"), str(source), "-o", str(exe)],
                           check=True, capture_output=True)
            values = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
        self.assertEqual([int(value) for value in values], [getattr(limits, name) for name in names])

    def test_each_mode_has_one_duration_limit_and_one_shared_risk(self):
        # Vocal alone is bounded by the frame count, drums by the 512 MiB package.
        self.assertEqual(limits.max_frames(1), limits.MAX_FRAMES)
        self.assertEqual(limits.clock(limits.max_frames(1)), "31 min 42 s")
        # Seven waveform combinations of six bytes per column add to the PCM.
        self.assertEqual(limits.clock(limits.max_frames(2)), "24 min 54 s")
        for roles in (1, 2):
            last = limits.max_frames(roles)
            self.assertEqual(limits.assess(last, roles).refused, False)
            self.assertEqual(limits.assess(last + 1, roles).reason, "duration" if roles == 1 else "size")
        self.assertEqual(limits.assess(limits.MIN_FRAMES, 1).status, "ok")
        self.assertEqual(limits.assess(limits.MIN_FRAMES - 1, 1).reason, "short")

    def test_shared_ceiling_is_a_risk_not_a_refusal(self):
        low, high = limits.MIN_FRAMES, limits.MAX_FRAMES
        while low < high:
            middle = (low + high) // 2
            low, high = (middle + 1, high) if limits.package_bytes(middle, 2) <= limits.SHARED_BYTES else (low, middle)
        frames = low
        self.assertEqual(limits.assess(frames - 1, 2).status, "ok")
        verdict = limits.assess(frames, 2)
        self.assertEqual(verdict.status, "shared")
        self.assertEqual(verdict.message(2).key, "stems.limitShared")

    def test_listed_duration_refuses_only_what_every_decoded_length_would(self):
        limit = limits.MAX_FRAMES / 44100
        self.assertEqual(limits.estimate(limit - 3, 1).status, "shared")
        self.assertEqual(limits.estimate(limit, 1).status, "near")
        self.assertEqual(limits.estimate(limit + 3, 1).status, "refused")
        self.assertEqual(limits.estimate(0, 1).status, "unknown")
        self.assertEqual(limits.estimate(26 * 60, 2).reason, "size")
        self.assertEqual(limits.estimate(26 * 60, 1).status, "shared")

    def test_package_size_is_computed_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for roles in (1, 2):
                inputs = {}
                for role in stem.ROLE_ORDER[:roles]:
                    inputs[role] = root / role
                    write_pcm(inputs[role], array.array("h", [1, -1] * 4410))
                template = waveform.analysis.Template(b"PWV5", b"", 15, (), "00" * 32)
                wave_path = root / "wave"
                columns = {mask: (bytes([1, 0, 4, 1, 1, 1]) * 15, "11" * 32)
                           for mask in range(1, 4 if roles == 1 else 8)}
                waveform.write_combinations(wave_path, template, 4410, "22" * 32, columns)
                output = package.write(root / "out.rx3stem", inputs, wave_path, {"title": "t"})
                manifest = package.read(output)["members"][-1].length
                self.assertEqual(output.stat().st_size, limits.package_bytes(4410, roles, manifest=manifest))

    def test_writer_refuses_with_a_readable_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            write_pcm(root / "short", array.array("h", [1, -1] * 4409))
            with self.assertRaises(limits.LimitError) as caught:
                package.write(root / "out", {"vocals": root / "short"}, root / "missing", {})
            self.assertEqual(caught.exception.message.key, "stems.limitShort")
            self.assertFalse((root / "out").exists())


@unittest.skipUnless(COMPILER, "a native C compiler is required")
class LoaderBoundaryTests(unittest.TestCase):
    """The loader at, below and above each of its limits."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.directory.name)
        cls.exe = build_loader(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def package(self, frames, roles=1):
        inputs = {}
        for role in stem.ROLE_ORDER[:roles]:
            inputs[role] = self.root / f"{role}-{frames}"
            write_pcm(inputs[role], array.array("h", [3, -3] * frames))
        count = (frames + 293) // 294
        template = waveform.analysis.Template(b"PWV5", b"", count, (), "00" * 32)
        wave_path = self.root / f"wave-{frames}"
        columns = {mask: (bytes([1, 0, 4, 1, 1, 1]) * count, "11" * 32)
                   for mask in range(1, 4 if roles == 1 else 8)}
        waveform.write_combinations(wave_path, template, frames, "22" * 32, columns)
        output = self.root / f"track-{frames}-{roles}.rx3stem"
        # The writer refuses a short track itself; the loader is tested alone.
        with patch.object(limits, "require"), patch.object(package, "read"):
            return package.write(output, inputs, wave_path, {})

    def test_minimum_length(self):
        with patch.object(waveform, "read", side_effect=lambda path, count=None: dict(
                frames=limits.MIN_FRAMES - 1, available=3, version=2, source_sha256="22" * 32,
                format=b"MULTI", roles=[])):
            short = self.package(limits.MIN_FRAMES - 1)
        self.assertEqual(load(self.exe, short)["roles"], 0)
        self.assertEqual(load(self.exe, self.package(limits.MIN_FRAMES))["roles"], 1)

    def test_shared_ceiling_counts_the_other_deck(self):
        path = self.package(limits.MIN_FRAMES, 2)
        size = path.stat().st_size
        self.assertEqual(load(self.exe, path, limits.RESIDENT_BYTES - size)["roles"], 2)
        self.assertEqual(load(self.exe, path, limits.RESIDENT_BYTES - size + 1)["roles"], 0)

    def test_player_reserve_is_kept(self):
        path = self.package(limits.MIN_FRAMES)
        needed = limits.PLAYER_RESERVE_KIB + (path.stat().st_size + 1023) // 1024
        self.assertEqual(load(self.exe, path, 0, needed)["roles"], 1)
        self.assertEqual(load(self.exe, path, 0, needed - 1)["roles"], 0)


@unittest.skipUnless(COMPILER, "a native C compiler is required")
class PadTests(unittest.TestCase):
    """SLIP LOOP pads 5 to 8 and the touch controls read one table."""

    def test_order_colours_and_native_pad_eight(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "pads.c"
            source.write_text(r'''
#define RX3_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef struct rx3_stereo Float2;
#include "core/api/rx3_panel_api.h"
#include "stems/rx3_stems_decl.h"
#define TAB_IMAGE_STEMS 0x1601u
static int blink_phase_is_on(void){return 1;}
static int stems_any_deck_loading(void){return 0;}
static void stems_blink_idle(void){}
static unsigned int now_ms(void){return 0;}
#include "stems/rx3_stems_panel.h"
int main(void){
    for(unsigned int pad=0;pad<4;pad++)
        printf("%u %u %u %u\n",stems_display_order[pad],stems_pad_colour[pad].red,
               stems_pad_colour[pad].green,stems_pad_colour[pad].blue);
    struct stems_deck_context *c=&stems_decks[0];
    c->status=2u;
    for(unsigned int count=1;count<=3;count++) {
        c->selection=((2u<<count)-1u)*17u;
        printf("%u %u",stems_available(c),stems_live_count(0));
        for(unsigned int w=0;w<stems_live_count(0);w++) {
            const uint16_t *text=stems_caption(0,w,0); char name[16]={0};
            for(unsigned int i=0;text[i]&&i<15;i++) name[i]=(char)text[i];
            printf(" %s:%04x",name,stems_widget_colour(0,w));
        }
        printf("\n");
    }
    return 0;
}''')
            exe = pathlib.Path(directory) / "pads"
            subprocess.run([COMPILER, "-std=c11", "-I" + str(ROOT / "mod/modules"), str(source), "-o", str(exe)],
                           check=True, capture_output=True)
            lines = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
        # Pad 5 INST red, pad 6 VOCAL green, pad 7 DRUMS blue, pad 8 no role.
        self.assertEqual(lines[:4], ["1 255 0 0", "2 0 255 0", "4 120 200 255", "0 0 0 0"])
        self.assertEqual(lines[4], "3 2 INSTRUMENTAL:f800 VOCAL:07e0")
        self.assertEqual(lines[5], "7 3 INST:f800 VOCAL:07e0 DRUMS:001f")
        # A legacy package with bass shows the same three controls.
        self.assertEqual(lines[6], "7 3 INST:f800 VOCAL:07e0 DRUMS:001f")


def noise(frames, seed, scale):
    generator = random.Random(seed)
    return [int(generator.uniform(-scale, scale)) for _ in range(frames)]


def stereo(values):
    return array.array("h", [value for value in values for _ in (0, 1)])


@unittest.skipUnless(FFMPEG and COMPILER, "ffmpeg and a native C compiler are required")
class ModeTests(unittest.TestCase):
    """Both modes, automatic and imported, end with a package the deck loads."""

    frames = 200_000

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.exe = build_loader(pathlib.Path(cls.directory.name))
        cls.parts = {"vocals": noise(cls.frames, 1, 6000), "drums": noise(cls.frames, 2, 6000),
                     "bass": noise(cls.frames, 3, 3000)}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        isolate(self)
        closed = patch.object(safety, "require_library_closed")
        closed.start()
        self.addCleanup(closed.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.source = self.root / "track.wav"
        write_wav(self.source, stereo([sum(values) for values in zip(*self.parts.values())]))
        self.track = rekordbox.Track("1", "Track", "Artist", 5, self.source, True)
        self.drive = self.root / "drive"
        self.drive.mkdir()

    def check_package(self, roles):
        path = self.drive / "RX3_STEMS" / "track.rx3stem"
        parsed = package.read(path)
        self.assertEqual(parsed["roles"], roles)
        # Combination waveforms, whatever their current version, never role curves.
        self.assertGreaterEqual(parsed["waveform"]["version"], 3)
        self.assertEqual([p.name for p in path.parent.glob("*.rx3*")], ["track.rx3stem"])
        deck = load(self.exe, path)
        available = 3 if roles == ("vocals",) else 7
        self.assertEqual((deck["roles"], deck["available"]), (len(roles), available))
        # A waveform for every audible selection, none for a role that is absent.
        self.assertEqual(deck["wave"], [int(mask <= available) for mask in range(1, 16)])

    def test_automatic_preparation_of_each_mode(self):
        playlist = rekordbox.Playlist("1", "List", "List", (self.track,))
        collection = rekordbox.Collection(self.root / "library.xml", 1, (playlist,))
        for mode, roles in MODES.items():
            with self.subTest(mode=mode):
                def encode(source, target, **kwargs):
                    role = "drums" if target.suffix == ".rx3drums" else "vocals"
                    write_pcm(target, stereo(self.parts[role]))
                    return stem.StemResult(target, self.frames, self.frames / 44100, self.frames * 4)
                current = job.StemJob(provisioning.detect(), collection, playlist, self.drive, roles=roles)
                separated = {role: self.source for role in roles}
                with patch.object(current, "_separate", return_value=separated), \
                        patch.object(job, "write_stem", side_effect=encode):
                    state = current.run()
                self.assertEqual((state.state, state.errors), ("done", ()))
                self.assertEqual(state.results[0].status, "created")
                self.check_package(roles)

    def test_manual_import_of_each_mode(self):
        for mode, roles in MODES.items():
            with self.subTest(mode=mode):
                inputs = {}
                for role in roles:
                    inputs[role] = self.root / f"{role}.wav"
                    write_wav(inputs[role], stereo(self.parts[role]))
                entry = importing.publish(self.track, inputs, self.drive)
                self.assertEqual([item["role"] for item in entry["stems"]], list(roles))
                self.check_package(roles)

    def test_quality_and_accelerator_never_change_the_format(self):
        playlist = rekordbox.Playlist("1", "List", "List", (self.track,))
        collection = rekordbox.Collection(self.root / "library.xml", 1, (playlist,))
        written = []
        for model, accelerator in (("vocals_mel_band_roformer.ckpt", "cpu"), ("htdemucs.yaml", "mps")):
            settings = separation.Settings(model=model, accelerator=accelerator)
            current = job.StemJob(provisioning.detect(), collection, playlist, self.root / model,
                                  settings=settings, roles=("vocals", "drums"))
            def encode(source, target, **kwargs):
                self.assertEqual(kwargs["sample_format"], "s16_gain")
                role = "drums" if target.suffix == ".rx3drums" else "vocals"
                write_pcm(target, stereo(self.parts[role]))
                return stem.StemResult(target, self.frames, self.frames / 44100, self.frames * 4)
            with patch.object(current, "_separate", return_value={"vocals": self.source, "drums": self.source}), \
                    patch.object(job, "write_stem", side_effect=encode):
                state = current.run()
            self.assertEqual(state.errors, ())
            parsed = package.read(self.root / model / "RX3_STEMS" / "track.rx3stem")
            written.append((parsed["roles"], parsed["frames"], parsed["waveform"]["version"],
                            [m.length for m in parsed["members"][:-1]]))
            # Settings reach the separator; the accelerator never enters the reuse key.
            self.assertNotIn("accelerator", json.dumps(current._signature))
        self.assertEqual(written[0], written[1])


class JobChecks(unittest.TestCase):
    """Refusals before separation, and reuse of what the drive already holds."""

    def setUp(self):
        isolate(self)
        closed = patch.object(safety, "require_library_closed")
        closed.start()
        self.addCleanup(closed.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.source = self.root / "track.wav"
        self.source.write_bytes(b"source")
        self.output = self.root / "RX3_STEMS"

    def run_job(self, seconds, roles=("vocals",), frames=None, waveforms=True):
        track = rekordbox.Track("1", "Track", "Artist", seconds, self.source, True)
        playlist = rekordbox.Playlist("1", "List", "List", (track,))
        collection = rekordbox.Collection(self.root / "library.xml", 1, (playlist,))
        current = job.StemJob(provisioning.detect(), collection, playlist, self.root, roles=roles, waveforms=waveforms)
        counted = patch.object(job, "count_frames", return_value=frames)
        with patch.object(current, "_separate", side_effect=AssertionError("separated")) as separate, counted as count:
            state = current.run()
        return state, separate, count

    def test_audio_only_import_is_reused_and_upgraded_without_separation(self):
        from package_fixture import wave_fixture
        path = self.package(("vocals",))
        package.write(path, {"vocals": self.root / "vocals"}, None,
                      {"source_sha256": safety.digest(self.source), "origin": "imported"})
        entry = {"stem": path.name, "origin": "imported", "source_sha256": safety.digest(self.source),
                 "processing": {"origin": "imported", "version": 1},
                 "stems": [{"role": "vocals", "file": path.name, "bytes": path.stat().st_size,
                            "sha256": safety.digest(path)}]}
        manifest = self.output / safety.MANIFEST_NAME
        manifest.write_text(json.dumps({"format": 2, "tracks": [entry]}))
        original = path.read_bytes()
        state, separate, _ = self.run_job(.1, frames=4410, waveforms=False)
        self.assertEqual(state.errors, ())
        separate.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        with patch.object(waveform, "build", side_effect=wave_fixture):
            state, separate, _ = self.run_job(.1, frames=4410)
        self.assertEqual(state.errors, ())
        separate.assert_not_called()
        self.assertEqual(package.read(path)["waveform"]["version"], 3)
        complete = path.read_bytes()
        state, separate, _ = self.run_job(.1, frames=4410, waveforms=False)
        self.assertEqual(state.errors, ())
        separate.assert_not_called()
        self.assertEqual(path.read_bytes(), complete)

    def test_certain_refusals_stop_before_separation(self):
        for seconds, roles, key in ((40 * 60, ("vocals",), "stems.limitDuration"),
                                    (26 * 60, ("vocals", "drums"), "stems.limitSize")):
            with self.subTest(key=key):
                state, separate, count = self.run_job(seconds, roles)
                self.assertEqual(state.errors[0].error.key, key)
                separate.assert_not_called()
                count.assert_not_called()
                self.assertFalse(list(self.output.glob("*.rx3stem")))

    def test_a_length_near_the_limit_is_counted_exactly_first(self):
        limit = limits.MAX_FRAMES / 44100
        state, separate, count = self.run_job(limit, frames=limits.MAX_FRAMES + 1)
        self.assertEqual(state.errors[0].error.key, "stems.limitDuration")
        count.assert_called_once()
        separate.assert_not_called()
        state, separate, count = self.run_job(0, frames=limits.MAX_FRAMES)
        count.assert_called_once()
        # Accepted: the job went on to separate.
        separate.assert_called_once()

    def package(self, roles):
        self.output.mkdir(exist_ok=True)
        inputs = {}
        for role in roles:
            inputs[role] = self.root / role
            write_pcm(inputs[role], array.array("h", [1, -1] * 4410))
        template = waveform.analysis.Template(b"PWV5", b"", 15, (), "00" * 32)
        wave_path = self.root / "wave"
        columns = {mask: (bytes([1, 0, 4, 1, 1, 1]) * 15, "11" * 32)
                   for mask in range(1, 4 if len(roles) == 1 else 8)}
        waveform.write_combinations(wave_path, template, 4410, "22" * 32, columns)
        return package.write(self.output / "track.rx3stem", inputs, wave_path, {})

    def test_a_v2_package_is_recognised_without_its_old_separate_files(self):
        self.package(("vocals", "drums"))
        state, separate, _ = self.run_job(60, ("vocals", "drums"))
        self.assertEqual((state.errors, state.results[0].status), ((), "existing"))
        separate.assert_not_called()
        self.assertEqual([s.role for s in state.results[0].stems], ["vocals", "drums"])

    def test_another_mode_is_prepared_again(self):
        self.package(("vocals",))
        state, separate, _ = self.run_job(60, ("vocals", "drums"))
        separate.assert_called_once()

    def test_imported_stems_are_not_replaced_by_a_separation(self):
        path = self.package(("vocals",))
        entry = {"stem": path.name, "origin": "imported", "source_sha256": safety.digest(self.source),
                 "processing": {"origin": "imported"},
                 "stems": [{"role": "vocals", "file": path.name, "bytes": path.stat().st_size,
                            "sha256": safety.digest(path)}]}
        (self.output / safety.MANIFEST_NAME).write_text(json.dumps({"format": 2, "tracks": [entry]}))
        state, separate, _ = self.run_job(60)
        separate.assert_not_called()
        self.assertEqual(state.results[0].status, "existing")
        self.assertEqual(state.notices[0].key, "stems.importedKept")

    def test_import_provenance_survives_repeated_reuse(self):
        path = self.package(("vocals",))
        entry = {"stem": path.name, "origin": "imported", "source_sha256": safety.digest(self.source),
                 "processing": {"origin": "imported", "version": 1},
                 "import_sha256": {"vocals": "original-import-hash"}, "checks": {"aligned": True},
                 "stems": [{"role": "vocals", "file": path.name, "bytes": path.stat().st_size,
                            "sha256": safety.digest(path)}]}
        manifest = self.output / safety.MANIFEST_NAME
        manifest.write_text(json.dumps({"format": 2, "tracks": [entry]}))
        original = path.read_bytes()
        for _ in range(2):
            state, separate, _ = self.run_job(60)
            self.assertEqual(state.errors, ())
            separate.assert_not_called()
            saved = json.loads(manifest.read_text())["tracks"][0]
            for key in ("origin", "processing", "import_sha256", "checks"):
                self.assertEqual(saved[key], entry[key])
            self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(FFMPEG, "ffmpeg is required")
    def test_imported_old_waveforms_upgrade_without_changing_pcm(self):
        write_wav(self.source, array.array("h", [3000, -3000] * 4410))
        for roles in (("vocals",), ("vocals", "drums")):
            with self.subTest(roles=roles):
                path = self.package(roles)
                wave_path = self.root / "wave"
                data = bytearray(wave_path.read_bytes())
                data[:8] = b"RX3WAV2\0"
                data[8:12] = (2).to_bytes(4, "little")
                wave_path.write_bytes(data)
                package.write(path, {role: self.root / role for role in roles}, wave_path,
                              {"origin": "imported", "checks": {"aligned": True}})
                entry = {"stem": path.name, "origin": "imported", "source_sha256": safety.digest(self.source),
                         "processing": {"origin": "imported", "version": 1},
                         "checks": {"aligned": True}, "import_sha256": {role: "input-hash" for role in roles},
                         "stems": [{"role": role, "file": path.name, "bytes": path.stat().st_size,
                                    "sha256": safety.digest(path)} for role in roles]}
                manifest = self.output / safety.MANIFEST_NAME
                manifest.write_text(json.dumps({"format": 2, "tracks": [entry]}))
                original = path.read_bytes()
                # A failed calculation must leave the operator's package intact.
                with patch.object(package, "build", side_effect=ValueError("waveform test failure")):
                    state, separate, _ = self.run_job(.1, roles, frames=4410)
                self.assertTrue(state.errors)
                self.assertIn("waveform test failure", str(state.errors[0].error))
                separate.assert_not_called()
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(json.loads(manifest.read_text())["tracks"], [entry])
                state, separate, _ = self.run_job(.1, roles, frames=4410)
                self.assertEqual(state.errors, ())
                separate.assert_not_called()
                result = package.read(path)
                self.assertEqual(result["waveform"]["version"], 3)
                self.assertEqual(result["manifest"]["origin"], "imported")
                self.assertEqual(result["manifest"]["checks"], entry["checks"])
                for role, member in zip(roles, result["members"]):
                    with member.open() as stream:
                        self.assertEqual(stream.read(), (self.root / role).read_bytes())
                saved = json.loads(manifest.read_text())["tracks"][0]
                for key in ("origin", "processing", "checks", "import_sha256"):
                    self.assertEqual(saved[key], entry[key])
                state, separate, _ = self.run_job(.1, roles, frames=4410)
                self.assertEqual((state.errors, state.results[0].status), ((), "existing"))
                separate.assert_not_called()


class Catalogue:
    def __init__(self, *models):
        self.models = {model.filename: model for model in models}

    def by_filename(self, name):
        return self.models.get(name)

    def best_of(self, architecture):
        return next((m for m in self.models.values() if m.architecture == architecture), None)

    def architecture_of(self, name):
        model = self.by_filename(name)
        return model.architecture if model else None


VOCAL = separation.Model("MDXC", "roformer", "vocals_mel_band_roformer.ckpt", ("Vocals", "Instrumental"), 12.6)
DEMUCS = separation.Model("Demucs", "htdemucs", "htdemucs.yaml", ("Vocals", "Drums", "Bass", "Other"), 8.0)
MDX = separation.Model("MDX", "kim", "Kim_Vocal_2.onnx", ("Vocals", "Instrumental"), 10.2)


class ServiceTests(unittest.TestCase):
    """What the interface is told before anything costly starts."""

    def test_drums_need_a_model_that_separates_them(self):
        vocal = separation.Settings(model=VOCAL.filename)
        self.assertIsNone(service.drums_blocked(separation.Settings(model=DEMUCS.filename),
                                                Catalogue(VOCAL, DEMUCS), True))
        blocked = service.drums_blocked(vocal, Catalogue(VOCAL, DEMUCS), True)
        self.assertEqual(blocked.key, "stems.preparationUnavailable")
        # Missing capability no longer suggests removed presets or imports.
        self.assertEqual(service.drums_blocked(vocal, Catalogue(VOCAL, DEMUCS, MDX), False).key,
                         "stems.preparationUnavailable")
        self.assertEqual(service.drums_blocked(vocal, None, True).key, "stems.drumsModelUnknown")

    def test_the_job_is_refused_before_it_is_built(self):
        library = service.Library(pathlib.Path("x"), 0, (), rekordbox.Collection(
            pathlib.Path("x"), 0, (rekordbox.Playlist("1", "List", "List", ()),)))
        with patch.object(safety, "require_library_closed"), \
                patch.object(provisioning, "detect", return_value=type("R", (), {"ready": True})()), \
                patch.object(service, "_catalogue", return_value=Catalogue(VOCAL)), \
                patch.object(service, "StemJob") as built:
            with self.assertRaises(LocalizedError) as caught:
                service.job(library, "1", pathlib.Path("."), settings=separation.Settings(model=VOCAL.filename),
                            roles=["vocals", "drums", "bass"])
            self.assertEqual(caught.exception.message.key, "stems.preparationUnavailable")
            built.assert_not_called()
            # A stale two-part request still needs the fixed three-stem model.
            with self.assertRaises(LocalizedError):
                service.job(library, "1", pathlib.Path("."), settings=separation.Settings(model=VOCAL.filename),
                            roles=["bass"])
            built.assert_not_called()

    def test_forecast_names_each_verdict(self):
        tracks = tuple(rekordbox.Track(str(i), f"T{i}", "A", seconds, pathlib.Path(f"/t{i}.wav"), True)
                       for i, seconds in enumerate((180, 20 * 60, 26 * 60, 0)))
        playlist = rekordbox.Playlist("1", "List", "List", tracks)
        library = service.Library(pathlib.Path("x"), 4, (), rekordbox.Collection(pathlib.Path("x"), 4, (playlist,)))
        with patch.object(service, "_catalogue", return_value=Catalogue(VOCAL, DEMUCS)), \
                patch.object(provisioning, "resolve_acceleration",
                             return_value=type("A", (), {"key": "cpu", "accelerates_torch": True})()):
            answer = service.forecast(library, "1", separation.Settings(model=VOCAL.filename), ["drums", "bass"])
        self.assertEqual(answer["roles"], ["vocals", "drums"])
        self.assertEqual([t["status"] for t in answer["memory"]], ["ok", "shared", "refused", "unknown"])
        self.assertEqual(answer["refused"], 1)
        self.assertEqual(answer["memory"][2]["message"].key, "stems.limitSize")
        self.assertIsNone(answer["blocked"])


class ImportChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        closed = patch.object(safety, "require_library_closed")
        closed.start()
        self.addCleanup(closed.stop)

    def test_a_refused_track_touches_neither_the_drive_nor_the_audio(self):
        track = rekordbox.Track("1", "Track", "Artist", 40 * 60, self.root / "track.wav", True)
        with patch.object(importing, "prepare") as prepare, patch.object(safety, "source_stamp") as stamp:
            with self.assertRaises(limits.LimitError) as caught:
                importing.publish(track, {"vocals": "v.wav"}, self.root)
        self.assertEqual(caught.exception.message.key, "stems.limitDuration")
        prepare.assert_not_called()
        stamp.assert_not_called()
        self.assertFalse((self.root / "RX3_STEMS").exists())

    def test_the_exact_length_is_checked_before_any_stem_is_decoded(self):
        decoded = []
        def decode(path, target, ffmpeg, **kwargs):
            decoded.append(path)
            return limits.MAX_FRAMES + 1
        with patch.object(importing, "lossless"), patch.object(importing, "decode", side_effect=decode):
            with self.assertRaises(limits.LimitError):
                importing.prepare(self.root / "mix.wav", {"vocals": "v.wav", "drums": "d.wav"}, self.root)
        self.assertEqual(decoded, [self.root / "mix.wav"])


@unittest.skipUnless(FFMPEG, "ffmpeg is required")
class LegacyBassTests(unittest.TestCase):
    """A package or files holding bass stay readable; the bass is part of INST."""

    frames = 4410

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.output = self.root / "RX3_STEMS"
        self.output.mkdir()
        # The mix is exactly vocal + bass; drums are silent.
        self.source = self.root / "track.wav"
        write_wav(self.source, array.array("h", [8192] * self.frames * 2))
        self.files = []
        for role, value in (("vocals", 4096), ("drums", 0), ("bass", 4096)):
            path = self.output / ("track" + stem.ROLE_SUFFIXES[role])
            write_pcm(path, array.array("h", [value] * self.frames * 2))
            self.files.append(path)

    def test_inst_audition_carries_the_bass(self):
        # Settled on INST alone: residual and the legacy bass at full level.
        settled = [1.0, 0.0, 0.0, 1.0]
        result = audition.on_drive(self.source, self.root, {"mask": 1, "state": mixing.MixState(
            settled, settled, settled).as_dict()}, seconds=0.05)
        self.assertEqual(result["available"], 7)
        import base64
        values = array.array("f", base64.b64decode(result["audio"])[44:])
        # Residual (mix - vocal - drums - bass) is silent; INST is the bass.
        self.assertAlmostEqual(values[100], 4096 / 32768, places=5)

    def test_inst_waveform_carries_the_bass(self):
        track = rekordbox.Track("1", "Track", "Artist", 1, self.source, True)
        template = waveform.analysis.Template(b"PWV5", b"", 15, (), "00" * 32)
        path = waveform.build(track, self.root, template, safety.digest(self.source), "ffmpeg",
                              self.root, lambda: None, files=self.files)
        info = waveform.read(path)
        self.assertEqual(info["available"], 7)
        data = path.read_bytes()
        heights = {mask: [v & 31 for v in data[start:start + length:6]]
                   for mask, start, length, _ in info["roles"]}
        self.assertTrue(any(heights[1]))
        self.assertFalse(any(heights[4]))


class MessageTests(unittest.TestCase):
    def test_every_new_message_exists_in_both_languages(self):
        keys = {"stems." + name for name in (
            "limitShort", "limitDuration", "limitSize", "limitNear", "limitNearShort", "limitShared",
            "limitFits", "sizeUnknown", "forecastRefused", "drumsModelPreset", "drumsModelImport",
            "drumsModelUnknown", "importedKept", "waveUpgrade", "trackNotice", "measuring",
            "stagePreparing", "stageChecking", "cpuFallback", "separatorFailed", "separatorOutput",
            "sourceMissing", "collision", "playlistEmpty", "outputGone", "outputUnavailable",
            "resultReady", "resultFailed")}
        for language in ("en", "fr"):
            self.assertLessEqual(keys, set(catalogs()[language]), language)
        for key in ("stems.roleBass", "stems.listenBass"):
            self.assertNotIn(key, catalogs()["en"])


if __name__ == "__main__":
    unittest.main()
