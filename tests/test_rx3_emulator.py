from __future__ import annotations

import json
import pathlib
import struct
import tempfile
import unittest

from tools.rx3_emulator.framebuffer import (
    FramebufferError,
    encode_png,
    export_png,
    read_metadata,
)
from tools.rx3_emulator.cli import docker_command


class FramebufferTests(unittest.TestCase):
    def test_exports_little_endian_rgb565(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            raw = root / "framebuffer.raw"
            metadata = root / "framebuffer.json"
            output = root / "framebuffer.png"
            raw.write_bytes(struct.pack("<HHH", 0xF800, 0x07E0, 0x001F))
            metadata.write_text(json.dumps({
                "width": 3,
                "height": 1,
                "virtual_height": 1,
                "bpp": 16,
                "stride": 6,
                "yoffset": 0,
            }))
            result = export_png(raw, metadata, output)
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(result["non_black_pixels"], 3)

    def test_rejects_incomplete_framebuffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "framebuffer.raw").write_bytes(b"\x00")
            (root / "framebuffer.json").write_text(json.dumps({
                "width": 1,
                "height": 1,
                "virtual_height": 1,
                "bpp": 16,
                "stride": 2,
                "yoffset": 0,
            }))
            with self.assertRaises(FramebufferError):
                export_png(
                    root / "framebuffer.raw",
                    root / "framebuffer.json",
                    root / "framebuffer.png",
                )

    def test_rejects_visible_page_outside_virtual_framebuffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata = pathlib.Path(directory) / "framebuffer.json"
            metadata.write_text(json.dumps({
                "width": 1,
                "height": 2,
                "virtual_height": 2,
                "bpp": 16,
                "stride": 2,
                "yoffset": 1,
            }))
            with self.assertRaises(FramebufferError):
                read_metadata(metadata)

    def test_png_encoder_checks_payload_length(self) -> None:
        with self.assertRaises(FramebufferError):
            encode_png(b"\x00", 1, 1)


class RunnerTests(unittest.TestCase):
    def test_container_is_named_for_touch_injection(self) -> None:
        command = docker_command(
            pathlib.Path("/private/sysroot"),
            pathlib.Path("/private/output"),
            "all",
            60,
            "rx3-test",
        )
        self.assertIn("rx3-test", command)
        self.assertEqual(command[command.index("--name") + 1], "rx3-test")


if __name__ == "__main__":
    unittest.main()
