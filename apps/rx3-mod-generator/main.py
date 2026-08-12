#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Tkinter interface for building a versioned RX3 USB runtime."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.rx3_runtime.build import (
    available_versions,
    build_runtime,
    discover_patches,
    repository_root,
)


class ToolkitBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RX3 Mod Generator")
        self.geometry("760x680")
        self.minsize(680, 600)
        self.root_resources = repository_root()
        self.key_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="Choose the patches, your RX3 key, and the USB drive.")
        self.firmware = tk.StringVar()
        self.patch_variables: dict[str, tk.BooleanVar] = {}
        self.patch_frame: ttk.Frame
        self.build_button: ttk.Button
        self.progress: ttk.Progressbar
        self._build_interface()
        versions = available_versions(self.root_resources)
        if not versions:
            raise RuntimeError("No versioned RX3 patches were found")
        self.firmware.set(versions[-1])
        self.version_box.configure(values=versions)
        self._load_patches()

    def _build_interface(self) -> None:
        container = ttk.Frame(self, padding=24)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Build an RX3 USB runtime", font=("TkDefaultFont", 20, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            container,
            text="Nothing is installed permanently on the player. Power cycling restores stock behavior.",
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(4, 20))

        version_row = ttk.Frame(container)
        version_row.grid(row=2, column=0, sticky="ew")
        ttk.Label(version_row, text="RX3 firmware:").pack(side="left")
        self.version_box = ttk.Combobox(version_row, textvariable=self.firmware, state="readonly", width=12)
        self.version_box.pack(side="left", padx=(10, 0))
        self.version_box.bind("<<ComboboxSelected>>", lambda _event: self._load_patches())

        ttk.Label(container, text="Features", font=("TkDefaultFont", 12, "bold")).grid(
            row=3, column=0, sticky="w", pady=(22, 8)
        )
        self.patch_frame = ttk.Frame(container)
        self.patch_frame.grid(row=4, column=0, sticky="ew")
        self.patch_frame.columnconfigure(0, weight=1)

        ttk.Separator(container).grid(row=5, column=0, sticky="ew", pady=18)
        self._path_row(container, 6, "RX3 encryption key", self.key_path, self._choose_key)
        self._path_row(container, 7, "Output folder or USB drive", self.output_path, self._choose_output)

        ttk.Label(
            container,
            text="The key is read locally and is never copied to the output. Existing autoexec.bin will be replaced.",
            wraplength=680,
        ).grid(row=8, column=0, sticky="w", pady=(8, 18))

        self.progress = ttk.Progressbar(container, mode="indeterminate")
        self.progress.grid(row=9, column=0, sticky="ew")
        ttk.Label(container, textvariable=self.status, wraplength=680).grid(
            row=10, column=0, sticky="w", pady=(8, 16)
        )
        self.build_button = ttk.Button(container, text="Build autoexec.bin", command=self._start_build)
        self.build_button.grid(row=11, column=0, sticky="ew", ipady=8)

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, command) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=4)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=label, width=25).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=variable).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Choose…", command=command).grid(row=0, column=2)

    def _load_patches(self) -> None:
        for child in self.patch_frame.winfo_children():
            child.destroy()
        self.patch_variables.clear()
        for row, patch in enumerate(discover_patches(self.root_resources, self.firmware.get())):
            variable = tk.BooleanVar(value=patch.default)
            self.patch_variables[patch.patch_id] = variable
            box = ttk.Checkbutton(self.patch_frame, text=patch.name, variable=variable)
            box.grid(row=row * 2, column=0, sticky="w")
            ttk.Label(self.patch_frame, text=patch.description, foreground="#555555", wraplength=650).grid(
                row=row * 2 + 1, column=0, sticky="w", padx=(24, 0), pady=(0, 8)
            )

    def _choose_key(self) -> None:
        selected = filedialog.askopenfilename(title="Choose the RX3 encryption key")
        if selected:
            self.key_path.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Choose the USB drive or output folder", mustexist=True)
        if selected:
            self.output_path.set(selected)

    def _start_build(self) -> None:
        selected = [patch_id for patch_id, variable in self.patch_variables.items() if variable.get()]
        key = pathlib.Path(self.key_path.get()).expanduser()
        output = pathlib.Path(self.output_path.get()).expanduser()
        if not selected:
            messagebox.showerror("No feature selected", "Select at least one feature to build.")
            return
        if not key.is_file():
            messagebox.showerror("Key not found", "Choose an existing RX3 encryption key file.")
            return
        if not output.is_dir():
            messagebox.showerror("Output not found", "Choose an existing folder or mounted USB drive.")
            return
        destination = output / "autoexec.bin"
        if destination.exists() and not messagebox.askyesno(
            "Replace autoexec.bin?", f"{destination} already exists. Replace it?"
        ):
            return

        self.build_button.configure(state="disabled")
        self.version_box.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Starting build…")
        thread = threading.Thread(
            target=self._build_worker,
            args=(self.firmware.get(), selected, key, output),
            daemon=True,
        )
        thread.start()

    def _build_worker(self, firmware: str, selected: list[str], key: pathlib.Path, output: pathlib.Path) -> None:
        try:
            result = build_runtime(
                firmware,
                selected,
                key,
                output,
                root=self.root_resources,
                progress=lambda message: self.after(0, self.status.set, message),
            )
        except Exception as error:  # Tk must receive worker failures on its own thread.
            self.after(0, self._build_finished, None, str(error))
        else:
            self.after(0, self._build_finished, result, None)

    def _build_finished(self, result, error: str | None) -> None:
        self.progress.stop()
        self.build_button.configure(state="normal")
        self.version_box.configure(state="readonly")
        if error:
            self.status.set("Build failed.")
            messagebox.showerror("Build failed", error)
            return
        self.status.set(f"Ready: {result.output}")
        messagebox.showinfo(
            "Runtime ready",
            f"autoexec.bin was written to:\n{result.output}\n\n"
            "Eject the USB drive cleanly before inserting it into the RX3.",
        )


def self_test() -> None:
    """Exercise embedded resources and the complete portable build path."""
    root = repository_root()
    versions = available_versions(root)
    if not versions:
        raise RuntimeError("No embedded firmware definitions")
    firmware = versions[-1]
    patches = discover_patches(root, firmware)
    with tempfile.TemporaryDirectory(prefix="rx3-mod-generator-self-test-") as directory:
        directory = pathlib.Path(directory)
        key = directory / "test.key"
        key.write_bytes(b"0123456789012345678901234567890\n")
        result = build_runtime(
            firmware,
            [patch.patch_id for patch in patches if patch.default],
            key,
            directory,
            root=root,
        )
        if not result.output.is_file():
            raise RuntimeError("Portable build did not create autoexec.bin")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    app = ToolkitBuilderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
