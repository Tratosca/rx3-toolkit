#!/usr/bin/env python3
"""Model the RX3 secondary image table and its widened ARM ID bound."""

from pathlib import Path
from struct import pack_into, unpack_from


RBP = Path("/tmp/rx3-rbp-live")
IMAGE_DATA = Path(
    "local/firmware/rx3/extracted/119/gui/pset/imagedata/imagedata.dat"
)
FUNCTION_FILE_OFFSET = 0x001C992C
STOCK_COUNT = 0x15CD
EXTENDED_COUNT = 0x1604
PRIVATE_FIRST = 0x1600
STOCK_BASE = 0x50000000
SECONDARY_BASE = 0x30000000
PRIVATE_PIXELS = 0x71000000


def main() -> None:
    rbp = RBP.read_bytes()
    assert rbp[FUNCTION_FILE_OFFSET : FUNCTION_FILE_OFFSET + 4] == bytes.fromhex(
        "cc3501e3"
    )
    # movw r3,#0x15cc -> movw r3,#0x1603 (little-endian ARM words).
    assert int.from_bytes(bytes.fromhex("033601e3"), "little") == 0xE3013603

    source = IMAGE_DATA.read_bytes()
    official_end = STOCK_COUNT * 44
    assert min(
        unpack_from("<I", source, image * 44 + 0x20)[0]
        for image in range(STOCK_COUNT)
    ) == official_end

    table = bytearray(EXTENDED_COUNT * 44)
    table[:official_end] = source[:official_end]
    relocation = (STOCK_BASE - SECONDARY_BASE) & 0xFFFFFFFF
    for image in range(STOCK_COUNT):
        record = image * 44
        old_data = unpack_from("<I", table, record + 0x20)[0]
        pack_into("<I", table, record + 0x20, (old_data + relocation) & 0xFFFFFFFF)
        if table[record + 0x19]:
            old_palette = unpack_from("<I", table, record + 0x24)[0]
            pack_into(
                "<I",
                table,
                record + 0x24,
                (old_palette + relocation) & 0xFFFFFFFF,
            )
        new_data = unpack_from("<I", table, record + 0x20)[0]
        assert (SECONDARY_BASE + new_data) & 0xFFFFFFFF == (
            STOCK_BASE + old_data
        ) & 0xFFFFFFFF

    template = table[0x1598 * 44 : 0x1599 * 44]
    for index in range(4):
        record = (PRIVATE_FIRST + index) * 44
        table[record : record + 44] = template
        pack_into("<HH", table, record + 4, 180, 50)
        table[record + 0x18] = 1
        table[record + 0x19] = 0
        pixel_address = PRIVATE_PIXELS + index * 18000
        pack_into(
            "<I",
            table,
            record + 0x20,
            (pixel_address - SECONDARY_BASE) & 0xFFFFFFFF,
        )
        resolved = SECONDARY_BASE + unpack_from("<I", table, record + 0x20)[0]
        assert resolved & 0xFFFFFFFF == pixel_address

    assert len(table) == EXTENDED_COUNT * 44
    print("Secondary image table model: OK")


if __name__ == "__main__":
    main()
