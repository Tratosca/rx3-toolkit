#!/usr/bin/env python3
"""Emulate small ARM UI primitives from the RX3 rbp ELF.

This is intentionally independent from the runtime hook.  It validates the
firmware ABI and object-layout assumptions before another device build is made.
"""

from __future__ import annotations

import argparse
import pathlib
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)
from unicorn.unicorn_const import UC_HOOK_CODE


PAGE = 0x1000
OBJECT = 0x10000000
TEXT = 0x10001000
STACK = 0x10010000
STOP = 0x10020000
CALLBACK = 0x10021000
TRAMPOLINE = 0x10022000


def align_down(value: int) -> int:
    return value & ~(PAGE - 1)


def align_up(value: int) -> int:
    return (value + PAGE - 1) & ~(PAGE - 1)


class Elf32:
    def __init__(self, path: pathlib.Path) -> None:
        self.data = path.read_bytes()
        if self.data[:5] != b"\x7fELF\x01":
            raise ValueError(f"not an ELF32 file: {path}")
        self.segments: list[tuple[int, int, int, int]] = []
        phoff = struct.unpack_from("<I", self.data, 28)[0]
        phentsize, phnum = struct.unpack_from("<HH", self.data, 42)
        for index in range(phnum):
            entry = phoff + index * phentsize
            p_type, offset, vaddr, _paddr, filesz, memsz = struct.unpack_from(
                "<IIIIII", self.data, entry
            )
            if p_type == 1:  # PT_LOAD
                self.segments.append((offset, vaddr, filesz, memsz))

    def bytes_at(self, address: int, size: int) -> bytes:
        for offset, vaddr, filesz, _memsz in self.segments:
            relative = address - vaddr
            if 0 <= relative and relative + size <= filesz:
                return self.data[offset + relative : offset + relative + size]
        raise ValueError(f"0x{address:x}+0x{size:x} is not file-backed")


def new_emulator(elf: Elf32, ranges: list[tuple[int, int]]) -> Uc:
    emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mapped: set[tuple[int, int]] = set()
    for address, size in ranges:
        start = align_down(address)
        end = align_up(address + size)
        key = (start, end)
        if key not in mapped:
            emulator.mem_map(start, end - start)
            mapped.add(key)
        emulator.mem_write(address, elf.bytes_at(address, size))
    for start, size in (
        (OBJECT, PAGE * 2),
        (STACK, PAGE),
        (STOP, PAGE * 4),
    ):
        emulator.mem_map(start, size)
    emulator.reg_write(UC_ARM_REG_SP, STACK + PAGE - 0x100)
    return emulator


def return_at_lr(emulator: Uc, _address: int, _size: int, _data: object) -> None:
    emulator.reg_write(UC_ARM_REG_PC, emulator.reg_read(UC_ARM_REG_LR))


def run_function(emulator: Uc, address: int, registers: dict[int, int]) -> None:
    for register, value in registers.items():
        emulator.reg_write(register, value)
    emulator.reg_write(UC_ARM_REG_LR, STOP)
    emulator.emu_start(address, STOP)


def u32(emulator: Uc, address: int) -> int:
    return struct.unpack("<I", emulator.mem_read(address, 4))[0]


def test_text_setter(elf: Elf32) -> None:
    print("RUN text setter", flush=True)
    address, size = 0x279DA8, 0x5C
    emulator = new_emulator(elf, [(address, size)])
    emulator.mem_write(OBJECT + 4, b"\x09")
    run_function(
        emulator,
        address,
        {UC_ARM_REG_R0: OBJECT, UC_ARM_REG_R1: TEXT, UC_ARM_REG_R2: 7},
    )
    assert u32(emulator, OBJECT + 0x34) == TEXT
    assert emulator.mem_read(OBJECT + 0x38, 1) == b"\x07"

    # A type-20 ancestor is the dirty/root boundary used by the firmware.
    ancestor = OBJECT + 0x100
    emulator.mem_write(OBJECT + 8, struct.pack("<I", ancestor))
    emulator.mem_write(ancestor + 4, b"\x14")
    emulator.mem_write(ancestor + 0x58, b"\0\0\0\0")
    run_function(
        emulator,
        address,
        {UC_ARM_REG_R0: OBJECT, UC_ARM_REG_R1: TEXT + 0x20, UC_ARM_REG_R2: 3},
    )
    assert u32(emulator, ancestor + 0x58) == 1
    print("PASS text setter: +0x34 pointer, +0x38 length, type-20 dirty +0x58")


def test_visibility_setter(elf: Elf32) -> None:
    print("RUN visibility setter", flush=True)
    address, size = 0x27A110, 0x54
    emulator = new_emulator(elf, [(address, size)])
    emulator.mem_write(OBJECT + 4, b"\x0e")
    ancestor = OBJECT + 0x100
    emulator.mem_write(OBJECT + 8, struct.pack("<I", ancestor))
    emulator.mem_write(ancestor + 4, b"\x14")
    run_function(
        emulator,
        address,
        {UC_ARM_REG_R0: OBJECT, UC_ARM_REG_R1: 0},
    )
    assert u32(emulator, OBJECT + 0x0C) == 0
    assert u32(emulator, ancestor + 0x58) == 1
    print("PASS visibility setter: +0x0c value and type-20 dirty propagation")


def test_add_child_contract(elf: Elf32) -> None:
    print("RUN AddChild ABI", flush=True)
    address, size = 0x27A16C, 0x60
    emulator = new_emulator(elf, [(address, size)])
    child = OBJECT + 0x300
    vtable = OBJECT + 0x400
    observed: list[tuple[int, int]] = []
    emulator.mem_write(OBJECT + 4, b"\x0e")
    emulator.mem_write(OBJECT + 0x20, struct.pack("<I", vtable))
    emulator.mem_write(vtable + 8, struct.pack("<I", CALLBACK))
    emulator.mem_write(child + 8, struct.pack("<I", 0x12345678))

    def callback(uc: Uc, _address: int, _size: int, _data: object) -> None:
        observed.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
        return_at_lr(uc, _address, _size, _data)

    emulator.hook_add(UC_HOOK_CODE, callback, begin=CALLBACK, end=CALLBACK)
    run_function(
        emulator,
        address,
        {UC_ARM_REG_R0: OBJECT, UC_ARM_REG_R1: child},
    )
    assert observed == [(OBJECT + 0x20, child)]
    assert u32(emulator, child + 8) == 0x12345678
    print("PASS AddChild ABI: r0=&parent.children, r1=child; parent pointer untouched")


def test_native_list_add_is_not_append(elf: Elf32) -> None:
    print("RUN native NS_List_Add semantics", flush=True)
    address, size = 0x1D1A08, 0x24
    emulator = new_emulator(elf, [(address, size)])
    native_list = OBJECT
    children = OBJECT + 0x500
    child = OBJECT + 0x700
    emulator.mem_write(native_list + 4, struct.pack("<I", children))
    emulator.mem_write(native_list + 8, struct.pack("<HH", 0, 1))
    run_function(
        emulator,
        address,
        {UC_ARM_REG_R0: native_list, UC_ARM_REG_R1: child},
    )
    assert struct.unpack("<H", emulator.mem_read(native_list + 8, 2))[0] == 1
    assert struct.unpack("<H", emulator.mem_read(native_list + 10, 2))[0] == 1
    assert u32(emulator, children + 4) == child
    print(
        "PASS NS_List_Add finding: writes at cursor+1 but does not grow count; "
        "unsafe as a dynamic append on the static arena"
    )


def test_static_attachment_layout(elf: Elf32) -> None:
    print("RUN static parent/children attachment", flush=True)
    address, size = 0x1D5BB8, 0x10C
    emulator = new_emulator(elf, [(address, size)])
    parent = OBJECT
    child = OBJECT + 0x300
    children = OBJECT + 0x500
    initial_sp = emulator.reg_read(UC_ARM_REG_SP)
    emulator.mem_write(parent + 4, b"\x0e")  # NS_GlyphGroup
    emulator.mem_write(children, struct.pack("<I", child))

    # LoadResource does this itself before constructing the parent's list.
    emulator.mem_write(child + 8, struct.pack("<I", parent))
    # AAPCS arguments 5 and 6: child count and position, read after the push.
    emulator.mem_write(initial_sp, struct.pack("<II", 1, 0))
    run_function(
        emulator,
        address,
        {
            UC_ARM_REG_R0: OBJECT + 0x800,
            UC_ARM_REG_R1: parent,
            UC_ARM_REG_R2: children,
            UC_ARM_REG_R3: 0,
        },
    )
    assert u32(emulator, child + 8) == parent
    assert u32(emulator, parent + 0x20) == 0x443EF0
    assert u32(emulator, parent + 0x24) == children
    assert struct.unpack("<H", emulator.mem_read(parent + 0x2A, 2))[0] == 1
    print(
        "PASS attachment layout: child.parent=+0x08; "
        "parent list vtable=+0x20, array=+0x24, count=+0x2a"
    )


def test_hook_trampoline(elf: Elf32) -> None:
    print("RUN generic hook trampoline", flush=True)
    function, size = 0x1331FC, 0x10
    emulator = new_emulator(elf, [(function, size)])
    first_eight = elf.bytes_at(function, 8)
    # Same trampoline emitted by install_hook(): replay 8 bytes, absolute jump.
    trampoline = first_eight + struct.pack("<II", 0xE51FF004, function + 8)
    emulator.mem_write(TRAMPOLINE, trampoline)

    # movw/movt resolves the actual destination before the replayed STR.
    destination = 0x0216B398 + 0x1F8
    emulator.mem_map(align_down(destination), PAGE)
    run_function(emulator, TRAMPOLINE, {UC_ARM_REG_R0: 1})
    assert u32(emulator, destination) == 1
    print("PASS generic hook trampoline: replayed prologue reaches original +8 safely")


def test_native_touch_hook_prologues(elf: Elf32) -> None:
    print("RUN native touch hook prologues", flush=True)
    functions = (
        ("BeatFxAndXPad ctor", 0x35B0F8),
        ("Button on", 0x360594),
        ("Button hold", 0x360610),
        ("Toggle on", 0x3606DC),
        ("Toggle off", 0x360728),
        ("XPad on", 0x360A00),
        ("XPad off", 0x360A44),
        ("XPad hold", 0x360E5C),
        ("Button off", 0x363280),
    )
    for index, (name, address) in enumerate(functions):
        emulator = new_emulator(elf, [(address, 0x10)])
        trampoline = TRAMPOLINE + index * 0x20
        replay = elf.bytes_at(address, 8) + struct.pack(
            "<II", 0xE51FF004, address + 8
        )
        emulator.mem_write(trampoline, replay)
        emulator.mem_write(OBJECT, b"\0" * 0x100)
        reached: list[int] = []

        def stop_at_join(uc: Uc, pc: int, _size: int, _data: object) -> None:
            reached.append(pc)
            uc.emu_stop()

        emulator.hook_add(
            UC_HOOK_CODE, stop_at_join, begin=address + 8, end=address + 8
        )
        emulator.reg_write(UC_ARM_REG_R0, OBJECT)
        emulator.reg_write(UC_ARM_REG_R1, 10)
        emulator.reg_write(UC_ARM_REG_R2, 20)
        emulator.reg_write(UC_ARM_REG_LR, STOP)
        emulator.emu_start(trampoline, STOP)
        assert reached == [address + 8], name
    print("PASS native touch hooks: all nine 8-byte prologues replay to original +8")


def print_disassembly(elf: Elf32) -> None:
    decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    for name, address, size in (
        ("SetStringAndLength", 0x279DA8, 0x5C),
        ("Set_bShow", 0x27A110, 0x54),
        ("AddChild", 0x27A16C, 0x60),
    ):
        instructions = list(decoder.disasm(elf.bytes_at(address, size), address))
        print(f"INFO {name}: {len(instructions)} ARM instructions")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rbp", type=pathlib.Path)
    args = parser.parse_args()
    elf = Elf32(args.rbp)
    print_disassembly(elf)
    test_text_setter(elf)
    test_visibility_setter(elf)
    test_static_attachment_layout(elf)
    test_add_child_contract(elf)
    test_native_list_add_is_not_append(elf)
    test_hook_trampoline(elf)
    test_native_touch_hook_prologues(elf)


if __name__ == "__main__":
    main()
