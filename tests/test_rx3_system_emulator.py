from __future__ import annotations

import pathlib
import struct
import tempfile
import unittest

from tools.rx3_system_emulator.cli import evaluate, inspect_uimage, kernel_command


class SystemEmulatorTests(unittest.TestCase):
    def test_inspects_legacy_uimage_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "uImage"
            name = b"Linux-RX3".ljust(32, b"\0")
            image.write_bytes(struct.pack(
                ">7I4B32s",
                0x27051956, 0, 123, 4096, 0x10008000, 0x10008000, 0,
                5, 2, 2, 0, name,
            ))
            metadata = inspect_uimage(image)
            self.assertEqual(metadata["name"], "Linux-RX3")
            self.assertEqual(metadata["entry_point"], 0x10008000)

    def test_rejects_non_uimage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "uImage"
            image.write_bytes(bytes(64))
            with self.assertRaises(RuntimeError):
                inspect_uimage(image)

    def test_probe_requires_every_marker(self) -> None:
        self.assertTrue(evaluate("one two", ("one", "two"), 124)["passed"])
        self.assertFalse(evaluate("one", ("one", "two"), 124)["passed"])

    def test_kernel_command_loads_legacy_stub_and_payload(self) -> None:
        command = kernel_command(pathlib.Path("stub.bin"), pathlib.Path("kernel.bin"))
        joined = " ".join(command)
        self.assertIn("addr=0x10000000", joined)
        self.assertIn("addr=0x10008000", joined)

    def test_kernel_command_can_load_external_initramfs(self) -> None:
        command = kernel_command(
            pathlib.Path("stub.bin"),
            pathlib.Path("kernel.bin"),
            pathlib.Path("rootfs.cpio.gz"),
        )
        joined = " ".join(command)
        self.assertIn("rootfs.cpio.gz", joined)
        self.assertIn("addr=0x18000000", joined)


if __name__ == "__main__":
    unittest.main()
