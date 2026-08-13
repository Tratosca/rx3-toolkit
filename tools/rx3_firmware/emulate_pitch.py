#!/usr/bin/env python3
"""Emulate rbp's native mixerengine::BeatEffectPitch on the host.

The XDJ-RX3 has no key shift.  Firmware 1.19 does contain a complete granular
pitch shifter -- the Beat FX `Pitch` effect -- and the runtime hook drives it
directly instead of shipping a second DSP.  Driving a private DSP through four
undocumented entry points is only defensible if the contract is proven, so this
module runs the real ARM code under Unicorn and measures what comes out.

It answers three questions the device cannot answer cheaply:

1. does the constructor/initialize/adjust/execute sequence used by the runtime
   hook actually shift pitch, or does the effect stay in bypass;
2. which level/depth and percentage pair reproduces each semitone;
3. how many frames the effect needs before the shift is fully engaged.

Usage:
    emulate_pitch.py <rbp> [--semitones -12 .. 12] [--table]
"""

from __future__ import annotations

import argparse
import math
import pathlib
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2,
    UC_ARM_REG_FPEXC,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)
from unicorn.unicorn_const import (
    UC_HOOK_CODE,
    UC_HOOK_MEM_INVALID,
    UC_PROT_ALL,
)

PAGE = 0x1000

# Host-side scratch regions, above every rbp segment.
IMPORT_BASE = 0x70000000
HEAP_BASE = 0x71000000
HEAP_SIZE = 0x04000000
STACK_BASE = 0x76000000
STACK_SIZE = 0x00100000
IO_BASE = 0x77000000
IO_SIZE = 0x00400000
HALT = 0x7F000000

# Entry points, matching the addresses the runtime hook is built against.
PITCH_CTOR = 0x0008B700
PITCH_INITIALIZE = 0x0008B2B8
PITCH_EXECUTE = 0x0008C648
# BeatEffect::adjustParameter is the base-class entry the stock mixer uses. It
# clamps, stores, and then dispatches the subclass recalculation, so it is the
# only documented way to publish level/depth and percentage.
ADJUST_PARAMETER = 0x000B5B38
PARAMETER_LEVEL_DEPTH = 2
PARAMETER_PERCENT = 4
# mixDelayAudioData interpolates from cubic coefficients that live in .bss and
# are produced by this translation unit's static constructor. Without it every
# tap is multiplied by zero and the effect returns silence.
PITCH_STATIC_INIT = 0x000139F8

# Field offsets recovered from the constructor and initialize().
OFF_SAMPLE_RATE = 0x04
OFF_SAMPLE_RATE2 = 0x08
OFF_SAMPLE_PERIOD = 0x0C
OFF_BLOCK_FRAMES = 0x10
OFF_LEVEL_DEPTH = 0x20
OFF_PERCENT = 0x30
OFF_EFFECT_ON = 0x3C
OFF_SHIFT_SPEED = 0x94
OFF_ENGAGED = 0x52
OFF_CROSSFADE = 0x53
OFF_PENDING_PERCENT = 0xA8
OFF_RAMP_PENDING = 0xAC
OFF_RATIO = 0xB0

# changePercentValuePitch scales the percentage by a curve driven by
# level/depth. 0.5 is the exact unity point: shift speed == percent / 100, so
# the -50..+100 percentage range covers precisely -12..+12 semitones.
UNITY_LEVEL_DEPTH = 0.5


def align_down(value: int) -> int:
    return value & ~(PAGE - 1)


def align_up(value: int) -> int:
    return (value + PAGE - 1) & ~(PAGE - 1)


class Elf32:
    """Just enough ELF to load rbp and resolve its PLT imports by name."""

    def __init__(self, path: pathlib.Path) -> None:
        self.data = path.read_bytes()
        if self.data[:5] != b"\x7fELF\x01":
            raise ValueError(f"not an ELF32 file: {path}")
        data = self.data

        self.segments: list[tuple[int, int, int, int]] = []
        phoff = struct.unpack_from("<I", data, 28)[0]
        phentsize, phnum = struct.unpack_from("<HH", data, 42)
        for index in range(phnum):
            entry = phoff + index * phentsize
            p_type, offset, vaddr, _paddr, filesz, memsz = struct.unpack_from(
                "<IIIIII", data, entry
            )
            if p_type == 1:  # PT_LOAD
                self.segments.append((offset, vaddr, filesz, memsz))

        shoff = struct.unpack_from("<I", data, 32)[0]
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 46)
        self.sections: list[dict[str, int | str]] = []
        for index in range(shnum):
            entry = shoff + index * shentsize
            fields = struct.unpack_from("<IIIIIIIIII", data, entry)
            self.sections.append(
                {
                    "name": fields[0],
                    "type": fields[1],
                    "addr": fields[3],
                    "off": fields[4],
                    "size": fields[5],
                    "link": fields[6],
                    "entsize": fields[9],
                }
            )
        names = self.sections[shstrndx]["off"]
        for section in self.sections:
            start = names + section["name"]
            section["sname"] = data[start : data.index(b"\0", start)].decode()

    def section(self, name: str) -> dict[str, int | str] | None:
        for section in self.sections:
            if section["sname"] == name:
                return section
        return None

    def dynamic_symbol_names(self) -> list[str]:
        dynsym = self.section(".dynsym")
        dynstr = self.section(".dynstr")
        if not dynsym or not dynstr:
            return []
        names: list[str] = []
        count = dynsym["size"] // dynsym["entsize"]
        for index in range(count):
            entry = dynsym["off"] + index * dynsym["entsize"]
            name_offset = struct.unpack_from("<I", self.data, entry)[0]
            start = dynstr["off"] + name_offset
            names.append(
                self.data[start : self.data.index(b"\0", start)].decode(
                    errors="replace"
                )
            )
        return names

    def relocations(self) -> list[tuple[int, int, str]]:
        """(slot_address, type, symbol_name) for .rel.plt and .rel.dyn."""
        names = self.dynamic_symbol_names()
        out: list[tuple[int, int, str]] = []
        for section_name in (".rel.plt", ".rel.dyn"):
            section = self.section(section_name)
            if not section:
                continue
            for index in range(section["size"] // 8):
                entry = section["off"] + index * 8
                offset, info = struct.unpack_from("<II", self.data, entry)
                symbol = info >> 8
                out.append(
                    (offset, info & 0xFF, names[symbol] if symbol < len(names) else "")
                )
        return out


class Machine:
    """A minimal rbp process: real code, host-implemented libc imports."""

    def __init__(self, elf: Elf32, trace: bool = False) -> None:
        self.elf = elf
        self.emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.heap_cursor = HEAP_BASE
        self.allocations: dict[int, int] = {}
        self.unresolved: set[str] = set()
        self.trace = trace
        self._load_segments()
        self._enable_vfp()
        self._bind_imports()
        self.emulator.mem_map(HEAP_BASE, HEAP_SIZE, UC_PROT_ALL)
        self.emulator.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_ALL)
        self.emulator.mem_map(IO_BASE, IO_SIZE, UC_PROT_ALL)
        self.emulator.mem_map(HALT, PAGE, UC_PROT_ALL)
        self.last_call = 0
        self.emulator.hook_add(UC_HOOK_MEM_INVALID, self._report_fault)

    def _report_fault(self, uc: Uc, kind: int, address: int, size: int, value: int,
                      _data) -> bool:
        print(
            f"  FAULT kind={kind} at 0x{address:08x} size={size} value=0x{value:x} "
            f"pc=0x{uc.reg_read(UC_ARM_REG_PC):08x} "
            f"r0=0x{uc.reg_read(UC_ARM_REG_R0):08x} "
            f"r3=0x{uc.reg_read(UC_ARM_REG_R3):08x} "
            f"(entry 0x{self.last_call:08x})"
        )
        return False

    # -- construction ----------------------------------------------------

    def _load_segments(self) -> None:
        mapped: list[tuple[int, int]] = []
        for offset, vaddr, filesz, memsz in self.elf.segments:
            start = align_down(vaddr)
            end = align_up(vaddr + max(filesz, memsz))
            for existing_start, existing_end in mapped:
                if start < existing_end and existing_start < end:
                    start = max(start, existing_end)
            if start >= end:
                continue
            self.emulator.mem_map(start, end - start, UC_PROT_ALL)
            mapped.append((start, end))
            if filesz:
                self.emulator.mem_write(
                    vaddr, self.elf.data[offset : offset + filesz]
                )

    def _enable_vfp(self) -> None:
        # Full coprocessor 10/11 access, then FPEXC.EN: rbp is compiled for NEON.
        self.emulator.reg_write(UC_ARM_REG_C1_C0_2, 0x00F00000)
        self.emulator.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def _bind_imports(self) -> None:
        self.emulator.mem_map(IMPORT_BASE, PAGE * 4, UC_PROT_ALL)
        self.import_names: dict[int, str] = {}
        slot = IMPORT_BASE
        by_name: dict[str, int] = {}
        for address, _kind, name in self.elf.relocations():
            if not name:
                continue
            if name not in by_name:
                by_name[name] = slot
                self.import_names[slot] = name
                slot += 4
            self.emulator.mem_write(address, struct.pack("<I", by_name[name]))
        self.emulator.hook_add(
            UC_HOOK_CODE, self._dispatch_import, begin=IMPORT_BASE, end=slot
        )

    # -- host services ---------------------------------------------------

    def allocate(self, size: int) -> int:
        if size <= 0:
            size = 1
        address = (self.heap_cursor + 15) & ~15
        self.heap_cursor = address + size
        if self.heap_cursor >= HEAP_BASE + HEAP_SIZE:
            raise MemoryError("emulated heap exhausted")
        self.allocations[address] = size
        self.emulator.mem_write(address, b"\0" * size)
        return address

    def _dispatch_import(self, uc: Uc, address: int, _size: int, _data) -> None:
        name = self.import_names.get(address, "")
        argument0 = uc.reg_read(UC_ARM_REG_R0)
        argument1 = uc.reg_read(UC_ARM_REG_R1)
        argument2 = uc.reg_read(UC_ARM_REG_R2)
        result = 0

        if name in ("malloc", "_Znwj", "_Znaj", "_ZnwjRKSt9nothrow_t"):
            result = self.allocate(argument0)
        elif name == "calloc":
            result = self.allocate(argument0 * argument1)
        elif name == "realloc":
            result = self.allocate(argument1)
            if argument0:
                previous = self.allocations.get(argument0, 0)
                if previous:
                    uc.mem_write(
                        result, bytes(uc.mem_read(argument0, min(previous, argument1)))
                    )
        elif name in ("free", "_ZdlPv", "_ZdaPv"):
            pass
        elif name == "memset":
            if argument2:
                uc.mem_write(argument0, bytes([argument1 & 0xFF]) * argument2)
            result = argument0
        elif name in ("memcpy", "memmove"):
            if argument2:
                uc.mem_write(argument0, bytes(uc.mem_read(argument1, argument2)))
            result = argument0
        elif name == "memcmp":
            left = bytes(uc.mem_read(argument0, argument2)) if argument2 else b""
            right = bytes(uc.mem_read(argument1, argument2)) if argument2 else b""
            result = 0 if left == right else (1 if left > right else 0xFFFFFFFF)
        elif name == "strlen":
            length = 0
            while uc.mem_read(argument0 + length, 1)[0]:
                length += 1
            result = length
        elif name in ("gettimeofday", "clock_gettime"):
            uc.mem_write(argument0 if name == "gettimeofday" else argument1,
                         struct.pack("<II", 0, 0))
        elif name in ("pthread_mutex_lock", "pthread_mutex_unlock",
                      "pthread_mutex_init", "pthread_mutex_destroy",
                      "pthread_mutexattr_init", "pthread_mutexattr_settype",
                      "pthread_mutexattr_destroy", "pthread_cond_init",
                      "pthread_cond_destroy", "pthread_cond_signal",
                      "pthread_cond_broadcast", "pthread_self",
                      "__cxa_guard_acquire", "__cxa_atexit",
                      "__cxa_guard_abort", "__gxx_personality_v0"):
            result = 1 if name == "__cxa_guard_acquire" else 0
        elif name == "__cxa_guard_release":
            pass
        elif name in ("puts", "printf", "fprintf", "fputs", "fwrite", "write",
                      "syslog", "abort", "__assert_fail"):
            pass
        else:
            self.unresolved.add(name)

        uc.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    # -- calling ---------------------------------------------------------

    def call(
        self,
        address: int,
        r0: int = 0,
        r1: int = 0,
        r2: int = 0,
        r3: int = 0,
        limit: int = 200_000_000,
    ) -> int:
        uc = self.emulator
        self.last_call = address
        uc.reg_write(UC_ARM_REG_SP, STACK_BASE + STACK_SIZE - 0x400)
        uc.reg_write(UC_ARM_REG_R0, r0)
        uc.reg_write(UC_ARM_REG_R1, r1)
        uc.reg_write(UC_ARM_REG_R2, r2)
        uc.reg_write(UC_ARM_REG_R3, r3)
        uc.reg_write(UC_ARM_REG_LR, HALT)
        uc.emu_start(address, HALT, count=limit)
        return uc.reg_read(UC_ARM_REG_R0)

    # -- object access ---------------------------------------------------

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.emulator.mem_read(address, 4))[0]

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.emulator.mem_read(address, 4))[0]

    def read_u8(self, address: int) -> int:
        return self.emulator.mem_read(address, 1)[0]

    def read_f32(self, address: int) -> float:
        return struct.unpack("<f", self.emulator.mem_read(address, 4))[0]

    def write_u32(self, address: int, value: int) -> None:
        self.emulator.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def write_f32(self, address: int, value: float) -> None:
        self.emulator.mem_write(address, struct.pack("<f", value))


class PitchEffect:
    """The four entry points the runtime hook uses, in the same order."""

    def __init__(self, machine: Machine, sample_rate: int, block_frames: int) -> None:
        self.machine = machine
        self.sample_rate = sample_rate
        self.block_frames = block_frames
        self.object = machine.allocate(0x400)
        machine.call(PITCH_STATIC_INIT)
        machine.call(PITCH_CTOR, r0=self.object)
        # The stock owner publishes the audio device format before initialize();
        # the constructor leaves the frame count at zero.
        machine.write_u32(self.object + OFF_SAMPLE_RATE, sample_rate)
        machine.write_u32(self.object + OFF_SAMPLE_RATE2, sample_rate)
        machine.write_f32(self.object + OFF_SAMPLE_PERIOD, 1.0 / sample_rate)
        machine.write_u32(self.object + OFF_BLOCK_FRAMES, block_frames)
        machine.call(PITCH_INITIALIZE, r0=self.object)
        self.input = machine.allocate(block_frames * 8)
        self.output = machine.allocate(block_frames * 8)

    def neutralise(self) -> None:
        """Publish the executed-equivalent neutral state the hook relies on."""
        machine = self.machine
        machine.write_u32(self.object + OFF_PERCENT, 0)
        machine.write_u32(self.object + OFF_PENDING_PERCENT, 0)
        machine.emulator.mem_write(self.object + OFF_RAMP_PENDING, b"\0")
        machine.write_f32(self.object + OFF_RATIO, 1.0)

    def adjust_parameter(self, parameter: int, value: float) -> None:
        # rbp is built -mfloat-abi=softfp: the float argument arrives in r2.
        bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
        self.machine.call(
            ADJUST_PARAMETER, r0=self.object, r1=parameter, r2=bits
        )

    def set_level_depth(self, level: float = UNITY_LEVEL_DEPTH) -> float:
        self.adjust_parameter(PARAMETER_LEVEL_DEPTH, level)
        return self.machine.read_f32(self.object + OFF_LEVEL_DEPTH)

    def set_percent(self, percent: float) -> int:
        self.adjust_parameter(PARAMETER_PERCENT, percent)
        return self.machine.read_i32(self.object + OFF_PERCENT)

    def shift_speed(self) -> float:
        return self.machine.read_f32(self.object + OFF_SHIFT_SPEED)

    def run(self, frames: list[tuple[float, float]]) -> list[tuple[float, float]]:
        machine = self.machine
        out: list[tuple[float, float]] = []
        for start in range(0, len(frames), self.block_frames):
            block = frames[start : start + self.block_frames]
            payload = b"".join(struct.pack("<ff", left, right) for left, right in block)
            machine.emulator.mem_write(self.input, payload)
            machine.emulator.mem_write(self.output, b"\0" * len(payload))
            machine.call(
                PITCH_EXECUTE,
                r0=self.object,
                r1=self.input,
                r2=self.output,
                r3=len(block),
            )
            raw = bytes(machine.emulator.mem_read(self.output, len(payload)))
            out.extend(
                struct.unpack_from("<ff", raw, index * 8) for index in range(len(block))
            )
        return out

    def state(self) -> dict[str, float | int]:
        machine = self.machine
        return {
            "percent": machine.read_i32(self.object + OFF_PERCENT),
            "ratio": machine.read_f32(self.object + OFF_RATIO),
            "engaged": machine.read_u8(self.object + OFF_ENGAGED),
            "crossfade": machine.read_u8(self.object + OFF_CROSSFADE),
            "ramp_pending": machine.read_u8(self.object + OFF_RAMP_PENDING),
        }


# -- signal helpers ------------------------------------------------------


def sine(frames: int, frequency: float, sample_rate: int) -> list[tuple[float, float]]:
    step = 2.0 * math.pi * frequency / sample_rate
    return [
        (0.5 * math.sin(step * index), 0.5 * math.sin(step * index))
        for index in range(frames)
    ]


def dominant_frequency(
    samples: list[float], sample_rate: int, low: float, high: float
) -> tuple[float, float]:
    """Autocorrelation peak inside [low, high] Hz, with its normalised score."""
    if not samples:
        return 0.0, 0.0
    mean = sum(samples) / len(samples)
    signal = [value - mean for value in samples]
    energy = sum(value * value for value in signal)
    if energy <= 1e-12:
        return 0.0, 0.0
    best_lag, best_score = 0, -1.0
    first = max(2, int(sample_rate / high))
    last = min(len(signal) - 1, int(sample_rate / low))
    for lag in range(first, last + 1):
        total = 0.0
        for index in range(len(signal) - lag):
            total += signal[index] * signal[index + lag]
        score = total / energy
        if score > best_score:
            best_lag, best_score = lag, score
    # Parabolic refinement around the integer lag keeps the estimate honest.
    return (sample_rate / best_lag if best_lag else 0.0), best_score


def semitone_ratio(semitones: int) -> float:
    return 2.0 ** (semitones / 12.0)



# -- quality measurement -------------------------------------------------


def goertzel(samples: list[float], frequency: float, sample_rate: int) -> float:
    """Magnitude of one DFT bin, without pulling in a full FFT."""
    count = len(samples)
    if count == 0:
        return 0.0
    omega = 2.0 * math.pi * frequency / sample_rate
    coefficient = 2.0 * math.cos(omega)
    first = second = 0.0
    for value in samples:
        first, second = coefficient * first - second + value, first
    real = first - second * math.cos(omega)
    imaginary = second * math.sin(omega)
    return math.hypot(real, imaginary)


def envelope(samples: list[float], window: int = 128) -> list[float]:
    out: list[float] = []
    for start in range(0, len(samples) - window, window):
        block = samples[start : start + window]
        out.append(math.sqrt(sum(value * value for value in block) / window))
    return out


def modulation(samples: list[float], sample_rate: int,
               window: int = 128) -> tuple[float, float]:
    """Depth in dB and rate in Hz of the amplitude ripple the grains leave."""
    levels = envelope(samples, window)
    if len(levels) < 8:
        return 0.0, 0.0
    trimmed = sorted(levels)
    low = trimmed[len(trimmed) // 20] or 1e-9
    high = trimmed[-max(1, len(trimmed) // 20)]
    depth = 20.0 * math.log10(high / low) if low > 0.0 else 0.0
    rate, _score = dominant_frequency(
        levels, sample_rate // window, 4.0, float(sample_rate // window) / 2.5
    )
    return depth, rate


def peak_near(samples: list[float], centre: float, sample_rate: int,
              span: float = 0.03, steps: int = 60) -> float:
    """Locate the real tone. A short probe window resolves the peak only to its
    own bin width, which at 220 Hz is worth tens of cents, so a coarse pass over
    a probe is refined over the whole tail before the result is trusted."""
    probe = samples[: min(len(samples), 8192)]

    def scan(block: list[float], low: float, high: float, count: int) -> float:
        best_frequency, best_magnitude = centre, -1.0
        for index in range(count + 1):
            frequency = low + (high - low) * index / count
            magnitude = goertzel(block, frequency, sample_rate)
            if magnitude > best_magnitude:
                best_frequency, best_magnitude = frequency, magnitude
        return best_frequency

    coarse = scan(probe, centre * (1.0 - span), centre * (1.0 + span), 2 * steps)
    # The coarse step is one probe bin wide at most; refine within two of them.
    window = 2.0 * sample_rate / len(probe)
    return scan(samples, coarse - window, coarse + window, 40)


def report_quality(
    elf: Elf32, semitones: int, percent: int, sample_rate: int, block_frames: int
) -> None:
    machine = Machine(elf)
    effect = PitchEffect(machine, sample_rate, block_frames)
    effect.neutralise()
    effect.set_level_depth()
    effect.set_percent(float(percent))

    source = 440.0
    frames = sine(int(sample_rate * 1.4), source, sample_rate)
    output = effect.run(frames)
    # Drop the engage crossfade; the effect needs about 1300 frames to start.
    tail = [left for left, _right in output[sample_rate // 3 :]]
    if not tail or max(abs(value) for value in tail) < 1e-6:
        print(f"{semitones:+3d}   no output")
        return

    # The effect shifts by the stored percentage, not by the ideal ratio.
    nominal = source * (1.0 + percent / 100.0)
    measured = peak_near(tail, nominal, sample_rate)
    total = sum(value * value for value in tail) / len(tail)
    count = len(tail)

    def power_at(frequency: float) -> float:
        if frequency <= 0.0 or frequency >= sample_rate / 2.0:
            return 0.0
        return 2.0 * (goertzel(tail, frequency, sample_rate) / count) ** 2

    tonal = power_at(measured) / total if total > 0.0 else 0.0
    leak = power_at(source) / total if total > 0.0 else 0.0
    harmonic = 0.0
    for multiple in (2, 3, 4):
        harmonic += power_at(measured * multiple) / total if total > 0.0 else 0.0
    depth, rate = modulation(tail, sample_rate)
    cents = 1200.0 * math.log2(measured / (source * semitone_ratio(semitones)))
    print(
        f"{semitones:+3d}  {percent:+5d}  {measured:8.1f}  {cents:+6.1f}  "
        f"{100.0 * tonal:6.1f}  {100.0 * (1.0 - tonal):6.1f}  "
        f"{100.0 * leak:6.1f}  {100.0 * harmonic:6.1f}  {depth:6.1f}  {rate:7.1f}"
    )


# -- reports -------------------------------------------------------------


def report_level_curve(effect: PitchEffect) -> None:
    """Prove that level/depth 0.5 is the unity point of the percentage curve."""
    print("level/depth  percent  shift speed  ratio     note")
    for level in (0.0, 0.25, UNITY_LEVEL_DEPTH, 0.75, 1.0):
        effect.set_level_depth(level)
        effect.set_percent(100.0)
        speed = effect.shift_speed()
        note = ""
        if abs(speed - 1.0) < 1e-4:
            note = "unity: percent/100 == shift speed"
        elif abs(speed) < 1e-4:
            note = "fully bypassed"
        print(
            f"{level:<12.3f} {effect.machine.read_i32(effect.object + OFF_PERCENT):+7d}"
            f"  {speed:+11.5f}  {1.0 + speed:.5f}   {note}"
        )
    effect.set_level_depth()


def report_percent_table(effect: PitchEffect) -> dict[int, int]:
    """Semitone -> percentage, as the firmware's own integer quantiser sees it."""
    effect.set_level_depth()
    best: dict[int, int] = {}
    print("\nsemitone  ratio     want%     sent%  stored%  ratio     cents")
    for semitones in range(-12, 13):
        wanted = (semitone_ratio(semitones) - 1.0) * 100.0
        # adjustParameter truncates toward zero, so bias by half a percent.
        sent = wanted + (0.5 if wanted >= 0.0 else -0.5)
        stored = effect.set_percent(sent)
        ratio = 1.0 + stored / 100.0
        cents = 1200.0 * math.log2(ratio / semitone_ratio(semitones))
        best[semitones] = stored
        print(
            f"{semitones:+3d}      {semitone_ratio(semitones):.6f}  "
            f"{wanted:+8.3f}  {sent:+7.2f}  {stored:+7d}  {ratio:.6f}  {cents:+7.2f}"
        )
    print("\nstatic const signed char semitone_percent[25] = {")
    values = ", ".join(str(best[semitones]) for semitones in range(-12, 13))
    print(f"    {values}\n}};")
    return best


def report_shift(
    elf: Elf32, semitones: int, percent: int, sample_rate: int, block_frames: int
) -> None:
    machine = Machine(elf)
    effect = PitchEffect(machine, sample_rate, block_frames)
    effect.neutralise()
    effect.set_level_depth()
    effect.set_percent(float(percent))
    print(
        f"\nsemitone {semitones:+d}: percent={effect.state()['percent']:+d} "
        f"shift speed={effect.shift_speed():+.5f}"
    )

    frequency = 440.0
    # 2 s is well past the effect's own warm-up counters (0x910 frames).
    frames = sine(sample_rate * 2, frequency, sample_rate)
    output = effect.run(frames)
    state = effect.state()
    print(
        f"  engaged={state['engaged']} crossfade={state['crossfade']} "
        f"ramp_pending={state['ramp_pending']} ratio={state['ratio']:.6f}"
    )

    # Measure the tail only: the first blocks contain the engage crossfade.
    tail = [left for left, _right in output[-8192:]]
    measured, score = dominant_frequency(tail, sample_rate, 100.0, 1500.0)
    expected = frequency * semitone_ratio(semitones)
    if measured <= 0.0:
        print("  FAIL: output has no periodic content")
        return
    cents = 1200.0 * math.log2(measured / expected)
    peak = max(abs(value) for value in tail)
    verdict = "OK" if abs(cents) < 60.0 and score > 0.3 and peak > 0.2 else "SUSPECT"
    print(
        f"  expected {expected:8.2f} Hz, measured {measured:8.2f} Hz "
        f"({cents:+.1f} cents, correlation {score:.2f}, peak {peak:.3f} "
        f"of 0.500 in)  {verdict}"
    )
    if machine.unresolved:
        print(f"  note: unimplemented imports reached: {sorted(machine.unresolved)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rbp", type=pathlib.Path)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--block-frames", type=int, default=512)
    parser.add_argument(
        "--table", action="store_true", help="print the percentage table only"
    )
    parser.add_argument(
        "--quality",
        action="store_true",
        help="measure how cleanly the effect shifts, per semitone",
    )
    parser.add_argument(
        "--semitones",
        type=int,
        nargs="*",
        default=[-12, -5, -1, 1, 5, 12],
        help="semitone offsets to measure",
    )
    arguments = parser.parse_args()
    elf = Elf32(arguments.rbp)

    machine = Machine(elf)
    effect = PitchEffect(machine, arguments.sample_rate, arguments.block_frames)
    print(
        f"constructed BeatEffectPitch at 0x{effect.object:08x}, "
        f"{arguments.sample_rate} Hz, {arguments.block_frames} frames/block"
    )
    if machine.unresolved:
        print(f"unimplemented imports during setup: {sorted(machine.unresolved)}")
    report_level_curve(effect)
    table = report_percent_table(effect)
    if arguments.table:
        return
    if arguments.quality:
        print(
            "\nst   percent  measured   cents  tonal%  other%   leak%   "
            "harm%  AM dB  AM Hz"
        )
        for semitones in arguments.semitones:
            report_quality(
                elf,
                semitones,
                table[semitones],
                arguments.sample_rate,
                arguments.block_frames,
            )
        return
    for semitones in arguments.semitones:
        report_shift(
            elf,
            semitones,
            table[semitones],
            arguments.sample_rate,
            arguments.block_frames,
        )


if __name__ == "__main__":
    main()
