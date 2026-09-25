# SPDX-License-Identifier: MPL-2.0
"""What a bank on a drive must survive.

A bank is written onto the stick an operator plays from. The failures worth a
test here are the ones that reach a set: a bank half replaced by a save that
went wrong, and a pad the deck cannot read, which is silent at the moment it is
pressed and says so only in a log nobody is looking at.
"""

import hashlib
import pathlib
import shutil
import struct
import tempfile
import unittest
import wave

from app.samples import bank as bank_module
from app.services import samples as samples_service


def tone(path, seconds=0.25, rate=bank_module.RATE, channels=bank_module.CHANNELS):
    """A sound file, in the deck's form unless a test asks for another."""
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack("<h", 4096) * frames * channels)
    return path


def fingerprint(directory):
    return {
        entry.name: hashlib.sha256(entry.read_bytes()).hexdigest()
        for entry in sorted(directory.iterdir())
    }


class SampleBankTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.drive = self.root / "stick"
        self.addCleanup(self.temporary.cleanup)

    def banks(self):
        return bank_module.samples_root(self.drive) / bank_module.BANKS_DIRECTORY

    def written(self, name="live", pads=None, **rest):
        return samples_service.save(
            self.drive, name, pads or [{"source": str(tone(self.root / "a.wav"))}], **rest
        )

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg converts what a pad plays")
    def test_a_save_that_fails_leaves_the_bank_that_was_already_there(self):
        directory = self.written(pads=[{"source": str(tone(self.root / "a.wav"))}])
        before = fingerprint(directory)

        broken = self.root / "not-audio.wav"
        broken.write_bytes(b"this is not a RIFF file")
        with self.assertRaises(Exception):
            self.written(pads=[
                {"source": str(self.root / "a.wav")},
                {"source": str(broken)},
            ])

        self.assertEqual(fingerprint(directory), before)
        # And nothing half written is left where a bank would be looked for.
        self.assertEqual([entry.name for entry in self.banks().iterdir()], ["live"])
        self.assertEqual(samples_service.read(self.drive).names, ("live",))

    def test_a_pad_the_deck_cannot_read_is_refused_rather_than_carried(self):
        directory = self.written()
        # Something else on the drive left a pad in a form the deck skips. A
        # skipped pad is silence during a set, so keeping it must not be quiet.
        tone(directory / "2.wav", rate=48000)
        with self.assertRaises(ValueError):
            self.written(pads=[{"keep": True}, {"keep": True}])
        self.assertEqual(samples_service.read(self.drive).names, ("live",))

    def test_a_bank_being_assembled_is_not_a_bank(self):
        self.written()
        # The shape the swap leaves behind if the power goes while it runs.
        stalled = self.banks() / ".live.new.4711"
        stalled.mkdir()
        (stalled / bank_module.CONFIG_NAME).write_text("version=1\n", encoding="ascii")
        self.assertEqual(samples_service.read(self.drive).names, ("live",))

    def test_what_a_bank_says_survives_being_written_and_read_back(self):
        pads = [
            {"source": str(tone(self.root / "a.wav")), "name": "Kick",
             "mode": bank_module.MODE_LOOP, "colour": "#0A0B0C"},
        ] + [None] * 7
        self.written(pads=pads, volume=70, shift_silence=True)
        described = samples_service.describe(self.drive, "live")
        self.assertTrue(described["settingsOk"])
        self.assertEqual(described["volume"], 70)
        self.assertTrue(described["shiftSilence"])
        first = described["pads"][0]
        self.assertEqual(
            (first["name"], first["mode"], first["colour"], first["present"]),
            ("Kick", bank_module.MODE_LOOP, "#0A0B0C", True),
        )


if __name__ == "__main__":
    unittest.main()


class ExcerptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_preview_and_export_play_the_same_selected_excerpt(self):
        import base64
        import io
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "long.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(44100)
                audio.writeframes(struct.pack("<h", 1000) * 44100 * 2)
                audio.writeframes(struct.pack("<h", -2000) * 44100 * 2 * 9)
            measured = samples_service.analyse([source])[0]
            self.assertTrue(measured.accepted)
            exported = samples_service.save(root / "usb", "test", [{
                "source": str(source), "start": 2, "duration": 0.5,
            }]) / "1.wav"
            preview = samples_service.audition(source, start=2, duration=0.5)
            with wave.open(str(exported), "rb") as audio:
                frames = audio.readframes(audio.getnframes())
                self.assertEqual(audio.getnframes(), 22050)
            with wave.open(io.BytesIO(base64.b64decode(preview["audio"])), "rb") as audio:
                self.assertEqual(audio.readframes(audio.getnframes()), frames)
            self.assertEqual(struct.unpack_from("<h", frames)[0], -2000)
            described = samples_service.describe(root / "usb", "test")
            self.assertEqual(pathlib.Path(described["pads"][0]["path"]), exported)

    def test_invalid_excerpt_limits_are_rejected_before_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            for start, duration in ((-1, 1), (float("nan"), 1), (0, 9), (0, 0), (0, float("inf"))):
                with self.subTest(start=start, duration=duration), self.assertRaises(ValueError):
                    bank_module.convert_pad(path / "input.wav", path / "out.wav",
                                            start=start, duration=duration)


class LogoPreviewTests(unittest.TestCase):
    def test_both_previews_show_the_exported_pixels(self):
        import base64
        import io
        from PIL import Image
        from app.services import logo
        from app.logo import container
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "logo.png"
            art = Image.new("RGBA", (30, 10), (255, 255, 255, 255))
            art.putpixel((2, 2), (250, 20, 60, 255))
            art.save(path)
            preview = logo.render(path)
            exported = logo.files(path)
            for key, filename in (("canvas", logo.DARK_NAME), ("lightCanvas", logo.LIGHT_NAME)):
                png = Image.open(io.BytesIO(base64.b64decode(preview[key].split(",", 1)[1]))).convert("RGBA")
                expected = container.decode(exported[filename])
                self.assertEqual(png.size, expected.size)
                self.assertEqual(png.tobytes(), expected.tobytes())
