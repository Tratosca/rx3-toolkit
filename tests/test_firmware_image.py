# SPDX-License-Identifier: MPL-2.0
import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools/rx3_firmware/firmware_image.py"
SPEC = importlib.util.spec_from_file_location("firmware_image", MODULE_PATH)
firmware_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(firmware_image)


class FirmwareImageTests(unittest.TestCase):
    def test_key_matches_xstrncpy_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.key"
            path.write_bytes(b"123456789012345678901234567890123456\nignored")
            self.assertEqual(
                firmware_image.load_key(path),
                b"1234567890123456789012345678901\0",
            )

    def test_sector_crypto_round_trip(self):
        key = bytes(range(32))
        plain = bytes(range(256)) * 4
        encrypted = firmware_image.crypt(plain, key, False)
        self.assertNotEqual(encrypted, plain)
        self.assertEqual(firmware_image.crypt(encrypted, key, True), plain)

    def test_container_crc_and_metadata(self):
        body = bytes(1024)
        blob = firmware_image.build(body, "1.19")
        parsed, model, version, stored, actual = firmware_image.split(blob)
        self.assertEqual(parsed, body)
        self.assertEqual(model, b"XDJ-RX3")
        self.assertEqual(version, "1.19")
        self.assertEqual(stored, actual)

    def test_autoexec_iso_metadata(self):
        plain = bytearray(68 * firmware_image.SECTOR)
        plain[64 * firmware_image.SECTOR + 1:64 * firmware_image.SECTOR + 6] = b"CD001"
        plain[64 * firmware_image.SECTOR + 40:64 * firmware_image.SECTOR + 47] = b"UsbAuto"
        self.assertEqual(firmware_image.autoexec_iso_metadata(bytes(plain)), "UsbAuto")

    def test_autoexec_rejects_missing_iso_signature(self):
        with self.assertRaisesRegex(ValueError, "ISO 9660 signature is missing"):
            firmware_image.autoexec_iso_metadata(bytes(65 * firmware_image.SECTOR))


if __name__ == "__main__":
    unittest.main()
