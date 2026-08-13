#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""The USB runtime pane: build a versioned RX3 `autoexec.bin`."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tools.rx3_runtime.build import (
    available_versions,
    build_runtime,
    dependent_closure,
    discover_patches,
    repository_root,
    required_closure,
)

import theme


# The pane's own padding on both sides, which reflowing text sits inside.
PANE_INSET = 56


class ModGeneratorPane(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.root_resources = repository_root()
        self.key_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="Choose the patches, your RX3 key, and the USB drive.")
        self.firmware = tk.StringVar()
        self.patch_variables: dict[str, tk.BooleanVar] = {}
        self._patches: list = []
        self._propagating = False
        self.patch_frame: ttk.Frame
        self.build_button: ttk.Button
        self.progress: ttk.Progressbar
        self._build_interface()
        theme.follow_width(self)
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
        container.rowconfigure(4, weight=1)

        ttk.Label(container, text="Build an RX3 modding USB", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        theme.wrapping(ttk.Label(
            container,
            text="Nothing is installed permanently on the player. Power cycling without the modded USB disables all mods.",
        ), inset=PANE_INSET).grid(row=1, column=0, sticky="w", pady=(4, 20))

        version_row = ttk.Frame(container)
        version_row.grid(row=2, column=0, sticky="ew")
        ttk.Label(version_row, text="Firmware version:").pack(side="left")
        self.version_box = ttk.Combobox(version_row, textvariable=self.firmware, state="readonly", width=12)
        self.version_box.pack(side="left", padx=(10, 0))
        self.version_box.bind("<<ComboboxSelected>>", lambda _event: self._load_patches())

        ttk.Label(container, text="Features", style="Section.TLabel").grid(
            row=3, column=0, sticky="w", pady=(22, 8)
        )
        self.patch_scroll = theme.ScrollFrame(container)
        self.patch_scroll.grid(row=4, column=0, sticky="nsew")
        self.patch_frame = self.patch_scroll.body
        self.patch_frame.columnconfigure(0, weight=1)

        ttk.Separator(container).grid(row=5, column=0, sticky="ew", pady=18)
        theme.path_row(container, 6, "RX3 encryption key", self.key_path, self._choose_key)
        theme.path_row(container, 7, "USB drive or output folder", self.output_path, self._choose_output)

        theme.wrapping(ttk.Label(
            container,
            text="Existing mods will be replaced.",
        ), inset=PANE_INSET).grid(row=8, column=0, sticky="w", pady=(8, 18))

        self.progress = ttk.Progressbar(container, mode="indeterminate")
        self.progress.grid(row=9, column=0, sticky="ew")
        theme.wrapping(
            ttk.Label(container, textvariable=self.status), inset=PANE_INSET
        ).grid(row=10, column=0, sticky="w", pady=(8, 16))
        self.build_button = ttk.Button(container, text="Mod your RX3 !", command=self._start_build)
        self.build_button.grid(row=11, column=0, sticky="ew", ipady=8)

    def _load_patches(self) -> None:
        for child in self.patch_frame.winfo_children():
            child.destroy()
        self.patch_variables.clear()
        self._patches = discover_patches(self.root_resources, self.firmware.get())
        # Internal modules are shown so the selection is not a partial account
        # of what gets built, but they are never the operator's to tick: they
        # follow whatever depends on them.
        for row, patch in enumerate(self._patches):
            variable = tk.BooleanVar(value=patch.default)
            self.patch_variables[patch.patch_id] = variable
            box = ttk.Checkbutton(
                self.patch_frame,
                text=patch.name if patch.selectable else f"{patch.name} (required)",
                variable=variable,
                state="normal" if patch.selectable else "disabled",
            )
            box.grid(row=row * 2, column=0, sticky="w")
            description = patch.description
            if not patch.selectable:
                dependents = sorted(
                    other.name
                    for other in self._patches
                    if patch.patch_id in other.requires
                )
                description = f"{description} Added automatically by {', '.join(dependents)}."
            theme.wrapping(ttk.Label(
                self.patch_frame, text=description, style="Muted.TLabel",
            ), inset=PANE_INSET + 40).grid(
                row=row * 2 + 1, column=0, sticky="w", padx=(24, 0), pady=(0, 8)
            )
        for patch_id, variable in self.patch_variables.items():
            variable.trace_add(
                "write", lambda *_args, identifier=patch_id: self._propagate(identifier)
            )
        self._synchronise_internal()
        theme.reflow(self)

    def _propagate(self, identifier: str) -> None:
        """Keep the ticked set consistent with the manifests' `requires`.

        Ticking a module pulls in what it needs; unticking one drops whatever
        would be left needing it. Both directions run under a guard because
        each assignment fires this same trace.
        """
        if self._propagating:
            return
        self._propagating = True
        try:
            variable = self.patch_variables[identifier]
            if variable.get():
                affected = required_closure(self._patches, [identifier])
                wanted = True
            else:
                affected = dependent_closure(self._patches, [identifier])
                wanted = False
            for other in affected - {identifier}:
                if self.patch_variables[other].get() != wanted:
                    self.patch_variables[other].set(wanted)
            self._synchronise_internal()
        finally:
            self._propagating = False

    def _synchronise_internal(self) -> None:
        """An internal module is ticked exactly when something needs it."""
        selectable = {
            patch.patch_id
            for patch in self._patches
            if patch.selectable and self.patch_variables[patch.patch_id].get()
        }
        needed = required_closure(self._patches, selectable)
        for patch in self._patches:
            if patch.selectable:
                continue
            variable = self.patch_variables[patch.patch_id]
            if variable.get() != (patch.patch_id in needed):
                variable.set(patch.patch_id in needed)

    def _choose_key(self) -> None:
        selected = filedialog.askopenfilename(title="Choose the RX3 encryption key")
        if selected:
            self.key_path.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Choose the USB drive or output folder", mustexist=True)
        if selected:
            self.output_path.set(selected)

    def _start_build(self) -> None:
        window = self.winfo_toplevel()
        # Internal modules are ticked for display only; the resolver refuses
        # them as a direct selection and adds them back transitively.
        selectable = {patch.patch_id for patch in self._patches if patch.selectable}
        selected = [
            patch_id
            for patch_id, variable in self.patch_variables.items()
            if variable.get() and patch_id in selectable
        ]
        key = pathlib.Path(self.key_path.get()).expanduser()
        output = pathlib.Path(self.output_path.get()).expanduser()
        if not selected:
            messagebox.showerror(
                "No feature selected", "Select at least one feature to build.", parent=window
            )
            return
        if not key.is_file():
            messagebox.showerror(
                "Key not found", "Choose an existing RX3 encryption key file.", parent=window
            )
            return
        if not output.is_dir():
            messagebox.showerror(
                "Output not found", "Choose an existing folder or mounted USB drive.", parent=window
            )
            return
        destination = output / "autoexec.bin"
        if destination.exists() and not messagebox.askyesno(
            "Replace autoexec.bin?", f"{destination} already exists. Replace it?", parent=window
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
        window = self.winfo_toplevel()
        self.progress.stop()
        self.build_button.configure(state="normal")
        self.version_box.configure(state="readonly")
        if error:
            self.status.set("Build failed.")
            messagebox.showerror("Build failed", error, parent=window)
            return
        self.status.set(f"Ready: {result.output}")
        messagebox.showinfo(
            "Runtime ready",
            f"autoexec.bin was written to:\n{result.output}\n\n"
            "Eject the USB drive cleanly before inserting it into the RX3.",
            parent=window,
        )


def self_test() -> None:
    """Exercise embedded resources and the complete portable build path."""
    root = repository_root()
    versions = available_versions(root)
    if not versions:
        raise RuntimeError("No embedded firmware definitions")
    firmware = versions[-1]
    patches = [patch for patch in discover_patches(root, firmware) if patch.selectable]
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
