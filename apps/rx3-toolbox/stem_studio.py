#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""The vocal stems pane: generate RX3 sidecars from a Rekordbox export.

The pane carries only what preparing stems requires: an export, a playlist, a
destination, and how much quality to trade for speed. The separation runtime,
the model catalogue, and the per-architecture tuning live behind Advanced
options, and surface on their own only when the runtime is missing and nothing
can run without it.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tools.rx3_stems import estimate, provisioning, separation
from tools.rx3_stems.job import JobState, StemJob
from tools.rx3_stems.rekordbox import Collection, parse_collection
from tools.rx3_stems.separation import (
    CUSTOM_MODE,
    PRESETS,
    Catalogue,
    Model,
    Option,
    Settings,
)

import theme


# Above this, a run is long enough that being told so before it starts is worth
# one dialog; below it the confirmation would only be in the way. Saying it here
# rather than in a standing banner keeps the warning where it is acted on.
LONG_RUN_SECONDS = 600
WORKLOAD_NOTICE = "Keep the computer plugged in and awake, and close other heavy apps."
# Label column of every field row, in characters. One value, or nothing aligns.
FIELD = 14
# What a reflowing label loses to the padding around it: the pane's own padding
# on both sides, and the dialog tab's. Text is measured against the width it is
# actually given, so these only have to account for the chrome outside it.
PANE_INSET = 48
TAB_INSET = 64


def reveal(path: pathlib.Path) -> None:
    """Show a generated directory in the platform file manager."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])


def readable(size: int) -> str:
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.1f} GB"
    return f"{size / 1024 ** 2:.0f} MB"


class AdvancedDialog(tk.Toplevel):
    """Runtime manager, model manager, and separation parameters."""

    def __init__(self, app: "StemStudioPane"):
        window = app.winfo_toplevel()
        super().__init__(window)
        self.app = app
        self.title("Advanced options")
        self.geometry("860x680")
        # Small enough to be usable on a 768-tall laptop screen; every tab
        # scrolls or reflows rather than clipping.
        self.minsize(520, 380)
        self.transient(window)
        self.busy = False
        self.status = tk.StringVar(value="")
        self.accelerator_choice = tk.StringVar()
        self._accelerator_labels: dict[str, str] = {}
        self.variables: dict[str, tuple[Option, tk.Variable]] = {}
        self._rows: dict[str, Model] = {}

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        self.runtime_tab = ttk.Frame(notebook, padding=16)
        self.models_tab = ttk.Frame(notebook, padding=16)
        self.parameters_tab = ttk.Frame(notebook, padding=16)
        notebook.add(self.runtime_tab, text="Runtime")
        notebook.add(self.models_tab, text="Models")
        notebook.add(self.parameters_tab, text="Model parameters")
        self._build_runtime_tab()
        self._build_models_tab()
        self._build_parameters_tab()

        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.pack(fill="x")
        theme.wrapping(
            ttk.Label(footer, textvariable=self.status, style="Muted.TLabel"), inset=120
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Close", command=self._close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._close)
        theme.follow_width(self)
        self.refresh()

    # Runtime tab

    def _build_runtime_tab(self) -> None:
        frame = self.runtime_tab
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Separation software", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.runtime_state = theme.wrapping(ttk.Label(frame), inset=TAB_INSET)
        self.runtime_state.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 2))
        self.runtime_location = theme.wrapping(
            ttk.Label(frame, style="Muted.TLabel"), inset=TAB_INSET
        )
        self.runtime_location.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ttk.Label(frame, text="Acceleration", width=16).grid(row=3, column=0, sticky="w")
        self.accelerator_box = ttk.Combobox(
            frame, textvariable=self.accelerator_choice, state="readonly", width=34
        )
        self.accelerator_box.grid(row=3, column=1, sticky="w")
        self.accelerator_box.bind("<<ComboboxSelected>>", self._accelerator_selected)
        self.acceleration_detail = theme.wrapping(
            ttk.Label(frame, style="Muted.TLabel"), inset=TAB_INSET
        )
        self.acceleration_detail.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 4))
        self.reinstall_notice = theme.wrapping(
            ttk.Label(frame, style="Warning.TLabel"), inset=TAB_INSET
        )
        self.reinstall_notice.grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 16))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w")
        self.install_button = ttk.Button(buttons, text="Install", command=self._install)
        self.install_button.pack(side="left")
        self.uninstall_button = ttk.Button(buttons, text="Uninstall", command=self._uninstall)
        self.uninstall_button.pack(side="left", padx=(8, 0))

        theme.wrapping(ttk.Label(
            frame,
            text=(
                "A private Python environment holding the separator. Uninstalling "
                "removes it and keeps the downloaded models."
            ),
            style="Muted.TLabel",
        ), inset=TAB_INSET).grid(row=7, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def _accelerator_selected(self, _event=None) -> None:
        key = self._accelerator_labels.get(self.accelerator_choice.get(), provisioning.AUTOMATIC)
        if key != self.app.settings.accelerator:
            self.app.apply_settings(self.app.settings.with_accelerator(key))
            # A preset names a trade-off, and which model expresses it depends
            # on which inference runtime this build accelerates. Changing the
            # accelerator can therefore change the model without changing the
            # preset the operator chose.
            self.app.reconcile_preset()
        self.refresh()

    def _install(self) -> None:
        acceleration = provisioning.resolve_acceleration(self.app.settings.accelerator)
        if not messagebox.askyesno(
            "Install the separation software ?",
            f"audio-separator, PyTorch ({acceleration.label}) and FFmpeg go into\n"
            f"{provisioning.data_directory()}\n\n"
            "Needs an internet connection and 1.5 GB of disk. Continue?",
            parent=self,
        ):
            return
        self._run(
            lambda report: provisioning.provision(
                progress=report, accelerator=self.app.settings.accelerator
            ),
            "Installing the separation runtime...",
        )

    def _uninstall(self) -> None:
        if not messagebox.askyesno(
            "Remove the separation software?",
            f"Deletes\n{provisioning.data_directory() / 'software'}\n\n"
            "Models are kept. Separation stops working until you install again. "
            "Continue?",
            parent=self,
        ):
            return
        self._run(provisioning.uninstall, "Removing the separation runtime...")

    # Models tab

    def _build_models_tab(self) -> None:
        frame = self.models_tab
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Separation models", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        theme.wrapping(ttk.Label(
            frame,
            text=(
                "Only the model in use is downloaded. Choosing another fetches it on "
                "first use and switches Quality to Custom."
            ),
            style="Muted.TLabel",
        ), inset=TAB_INSET).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        columns = ("state", "sdr", "architecture", "filename")
        self.models_view = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        # Only the model name grows: the other three hold values of a known
        # size, and widening them would just push the name out of view.
        for column, heading, width, stretch in (
            ("state", "Local", 130, False), ("sdr", "Vocal SDR", 90, False),
            ("architecture", "Architecture", 110, False), ("filename", "Model", 260, True),
        ):
            self.models_view.heading(column, text=heading)
            self.models_view.column(
                column, width=width, minwidth=70, stretch=stretch, anchor="w"
            )
        self.models_view.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.models_view.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.models_view.configure(yscrollcommand=scrollbar.set)
        self.models_view.bind("<<TreeviewSelect>>", lambda _event: self._update_model_buttons())

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.use_button = ttk.Button(buttons, text="Use this model", command=self._use_model)
        self.use_button.pack(side="left")
        self.download_button = ttk.Button(buttons, text="Download", command=self._download_model)
        self.download_button.pack(side="left", padx=(8, 0))
        self.delete_button = ttk.Button(buttons, text="Delete", command=self._delete_model)
        self.delete_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Refresh list", command=self._refresh_catalogue).pack(
            side="left", padx=(8, 0)
        )
        self.models_summary = theme.wrapping(
            ttk.Label(frame, style="Muted.TLabel"), inset=TAB_INSET
        )
        self.models_summary.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _selected_model(self) -> Model | None:
        selection = self.models_view.selection()
        return self._rows.get(selection[0]) if selection else None

    def _use_model(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        self.app.apply_settings(self.app.settings.with_model(model.filename))
        self.refresh()

    def _download_model(self) -> None:
        model = self._selected_model()
        runtime = self.app.runtime
        if model is None or runtime.separator is None:
            return
        self._run(
            lambda report: separation.download_model(runtime, model, progress=report),
            f"Downloading {model.filename}...",
        )

    def _delete_model(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        runtime = self.app.runtime
        if model.filename == self.app.settings.model and not messagebox.askyesno(
            "Delete the model in use ?",
            f"{model.filename} is in use and would be downloaded again on the next "
            "run. Delete anyway?",
            parent=self,
        ):
            return
        freed = separation.delete_model(runtime.models, model)
        self.app.log(f"Deleted {model.filename} ({readable(freed)} freed).")
        self.refresh()

    def _refresh_catalogue(self) -> None:
        self.status.set("Loading the model list...")
        self.app.load_catalogue(refresh=True, done=self.refresh)

    # Parameters tab

    def _build_parameters_tab(self) -> None:
        frame = self.parameters_tab
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self.parameters_header = theme.wrapping(ttk.Label(frame), inset=TAB_INSET)
        self.parameters_header.grid(row=0, column=0, sticky="w", pady=(0, 12))
        # VR alone contributes eleven options with their help text, which does
        # not fit any window this dialog is allowed to be.
        self.parameters_scroll = theme.ScrollFrame(frame)
        self.parameters_scroll.grid(row=1, column=0, sticky="nsew")
        self.parameters_body = self.parameters_scroll.body
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text="Apply", command=self._apply_parameters).pack(side="left")
        ttk.Button(buttons, text="Restore defaults", command=self._restore_parameters).pack(
            side="left", padx=(8, 0)
        )

    def _build_parameter_rows(self) -> None:
        for child in self.parameters_body.winfo_children():
            child.destroy()
        self.variables.clear()
        settings = self.app.settings
        architecture = self.app.catalogue.architecture_of(settings.model)
        self.parameters_header.configure(text=(
            f"{settings.model} · {architecture or 'architecture unknown, common options only'}"
            "\nApplying a change switches Quality to Custom."
        ))
        for title, options in settings.options(architecture):
            group = ttk.LabelFrame(self.parameters_body, text=title, padding=12)
            group.pack(fill="x", pady=(0, 12))
            group.columnconfigure(1, weight=1)
            for index, option in enumerate(options):
                self._option_row(group, index * 2, option, settings)
        theme.reflow(self)

    def _option_row(self, parent: ttk.Frame, row: int, option: Option, settings: Settings) -> None:
        value = settings.value(option)
        if option.kind == "flag":
            variable: tk.Variable = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(parent, text=option.label, variable=variable).grid(
                row=row, column=0, columnspan=2, sticky="w"
            )
        else:
            variable = tk.StringVar(value=str(value))
            ttk.Label(parent, text=option.label, width=26).grid(row=row, column=0, sticky="w")
            ttk.Entry(parent, textvariable=variable, width=14).grid(row=row, column=1, sticky="w")
        # Indented under its control, inside a group box, inside the scroller.
        theme.wrapping(
            ttk.Label(parent, text=option.help, style="Muted.TLabel"), inset=TAB_INSET + 90
        ).grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=(20, 0), pady=(0, 8))
        self.variables[option.name] = (option, variable)

    def _restore_parameters(self) -> None:
        for option, variable in self.variables.values():
            variable.set(option.default if option.kind == "flag" else str(option.default))

    def _apply_parameters(self) -> None:
        settings = self.app.settings
        for option, variable in self.variables.values():
            raw = variable.get()
            try:
                value = bool(raw) if option.kind == "flag" else option.parse(str(raw))
                option.validate(value)
            except ValueError as error:
                messagebox.showerror("Invalid value", f"{option.label}: {error}", parent=self)
                return
            settings = settings.with_value(option, value)
        self.app.apply_settings(settings)
        self.status.set("Separation parameters saved.")
        self.refresh()

    # Shared state

    def _run(self, work, message: str) -> None:
        """Run a long task, keeping the dialog responsive and buttons disabled."""
        self.busy = True
        self._update_buttons()
        self.status.set(message)
        self.app.log(message)

        def worker() -> None:
            try:
                work(lambda text: self.after(0, self.status.set, text))
            except Exception as error:  # Tk must receive worker failures on its own thread.
                self.after(0, self._finished, str(error))
            else:
                self.after(0, self._finished, None)

        threading.Thread(target=worker, daemon=True).start()

    def _finished(self, error: str | None) -> None:
        self.busy = False
        self.app.refresh_runtime()
        if error:
            self.status.set("Failed.")
            self.app.log(error)
            messagebox.showerror("Operation failed", error, parent=self)
        else:
            self.app.log(self.status.get())
        self.refresh()
        if self.app.runtime.ready and not self.app.catalogue.models:
            self._refresh_catalogue()

    def refresh(self) -> None:
        runtime = self.app.runtime
        settings = self.app.settings

        pairs = provisioning.available_accelerations()
        self._accelerator_labels = {label: key for key, label in pairs}
        self.accelerator_box.configure(values=[label for _, label in pairs])
        self.accelerator_choice.set(next(
            (label for key, label in pairs if key == settings.accelerator), pairs[0][1]
        ))
        acceleration = provisioning.resolve_acceleration(settings.accelerator)
        self.acceleration_detail.configure(text=acceleration.detail)

        installed = provisioning.installed_accelerator()
        if not runtime.ready:
            state = "Not installed."
            location = str(runtime.environment)
        elif not runtime.managed:
            state = "Provided by an installation already on this computer."
            location = f"{runtime.separator} - not managed here, so it cannot be removed."
        else:
            state = (
                f"Installed for {provisioning.ACCELERATIONS[installed].label}."
                if installed else "Installed."
            )
            location = str(runtime.separator)
        self.runtime_state.configure(text=state)
        self.runtime_location.configure(text=location)

        mismatch = provisioning.needs_reinstall(settings.accelerator, runtime)
        self.reinstall_notice.configure(text=(
            f"The runtime was installed for {provisioning.ACCELERATIONS[installed].label} and needs "
            f"reinstallation to run on {acceleration.label}."
            if mismatch and installed else ""
        ))
        self.install_button.configure(
            text="Reinstall" if mismatch
            else "Install or repair" if runtime.managed else "Install"
        )

        self._fill_models()
        self._build_parameter_rows()
        self._update_buttons()

    def _fill_models(self) -> None:
        selected = self._selected_model()
        self.models_view.delete(*self.models_view.get_children())
        self._rows.clear()
        models = self.app.catalogue.models
        directory = self.app.runtime.models
        downloaded = 0
        for model in models:
            local = model.is_downloaded(directory)
            downloaded += 1 if local else 0
            in_use = model.filename == self.app.settings.model
            state = f"✓ {readable(model.size(directory))}" if local else "not downloaded"
            row = self.models_view.insert("", "end", values=(
                ("● in use · " if in_use else "") + state,
                f"{model.vocal_sdr:.2f}" if model.vocal_sdr is not None else "-",
                model.architecture,
                model.filename,
            ))
            self._rows[row] = model
            if selected is not None and model.filename == selected.filename:
                self.models_view.selection_set(row)
                self.models_view.see(row)
        if not models:
            self.models_summary.configure(
                text="No model list. Install the runtime, then Refresh list."
            )
        else:
            total = sum(m.size(directory) for m in models if m.is_downloaded(directory))
            self.models_summary.configure(
                text=f"{len(models)} vocal models · {downloaded} downloaded · {readable(total)} on disk"
            )

    def _update_buttons(self) -> None:
        state = "disabled" if self.busy else "normal"
        runtime = self.app.runtime
        self.accelerator_box.configure(state="disabled" if self.busy else "readonly")
        self.install_button.configure(state=state)
        self.uninstall_button.configure(
            state="disabled" if self.busy or not runtime.managed else "normal"
        )
        self._update_model_buttons()

    def _update_model_buttons(self) -> None:
        model = self._selected_model()
        local = model.is_downloaded(self.app.runtime.models) if model else False
        ready = self.app.runtime.ready
        self.use_button.configure(state="normal" if model and not self.busy else "disabled")
        self.download_button.configure(
            state="normal" if model and ready and not local and not self.busy else "disabled"
        )
        self.delete_button.configure(
            state="normal" if model and local and not self.busy else "disabled"
        )

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo("Busy", "Wait for the current task to finish.", parent=self)
            return
        self.app.advanced = None
        self.destroy()


class StemStudioPane(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.runtime = provisioning.detect()
        self.settings = separation.load_settings(
            provisioning.data_directory() / separation.SETTINGS_NAME
        )
        self.catalogue = Catalogue()
        self.collection: Collection | None = None
        self.job: StemJob | None = None
        self.advanced: AdvancedDialog | None = None
        self.xml_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.playlist_choice = tk.StringVar()
        self.setup_status = tk.StringVar()
        self.mode_choice = tk.StringVar(value=self.settings.mode)
        self.status = tk.StringVar(value="Choose a Rekordbox XML export to begin.")
        self._playlist_labels: dict[str, str] = {}
        self._forecast = estimate.Forecast()
        # The status line is shared, so it has to know who is speaking.
        self._running = False
        self._build_interface()
        theme.follow_width(self)
        self.refresh_runtime()
        self.load_catalogue()

    # Interface construction

    def _build_interface(self) -> None:
        """Four fields, one status line, one button.

        Everything the operator has to decide sits in one aligned column. What
        the run is doing is one line, not four scattered labels, and anything
        explanatory belongs where it is acted on rather than on screen at all
        times.
        """
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(7, weight=1)
        self.container = container

        # Shown only while separation cannot run at all.
        self.setup_frame = ttk.LabelFrame(container, text="Separation software", padding=10)
        self.setup_frame.columnconfigure(0, weight=1)
        theme.wrapping(
            ttk.Label(self.setup_frame, textvariable=self.setup_status), inset=PANE_INSET + 140
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            self.setup_frame, text="Set up...", command=self.open_advanced
        ).grid(row=0, column=1, padx=(12, 0))

        theme.path_row(container, 1, "Rekordbox XML", self.xml_path, self._choose_xml, width=FIELD)

        playlist_row = ttk.Frame(container)
        playlist_row.grid(row=2, column=0, sticky="ew", pady=3)
        playlist_row.columnconfigure(1, weight=1)
        ttk.Label(playlist_row, text="Playlist", width=FIELD).grid(row=0, column=0, sticky="w")
        self.playlist_box = ttk.Combobox(
            playlist_row, textvariable=self.playlist_choice, state="disabled"
        )
        self.playlist_box.grid(row=0, column=1, sticky="ew", padx=8)
        self.playlist_box.bind("<<ComboboxSelected>>", self._playlist_selected)
        ttk.Button(playlist_row, text="Reload", command=self._load_collection).grid(row=0, column=2)

        theme.path_row(container, 3, "Output", self.output_path, self._choose_output, width=FIELD)
        self._build_quality_row(container, 4)

        progress = ttk.Frame(container)
        progress.grid(row=5, column=0, sticky="ew", pady=(18, 0))
        progress.columnconfigure(0, weight=1)
        self.overall = ttk.Progressbar(progress, maximum=100)
        self.overall.grid(row=0, column=0, sticky="ew")
        self.track = ttk.Progressbar(progress, maximum=100)
        self.track.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        # One line for the whole state of things: the forecast before a run,
        # the position and time left during one, the outcome after.
        theme.wrapping(
            ttk.Label(progress, textvariable=self.status), inset=PANE_INSET
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(container)
        buttons.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(buttons, text="Generate stems", command=self._start_job)
        self.start_button.grid(row=0, column=0, sticky="ew", ipady=6)
        self.cancel_button = ttk.Button(
            buttons, text="Cancel", command=self._cancel_job, state="disabled"
        )
        self.cancel_button.grid(row=0, column=1, padx=(8, 0), ipady=6)

        log_frame = ttk.Frame(container)
        log_frame.grid(row=7, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_view = tk.Text(log_frame, height=6, wrap="word", state="disabled")
        self.log_view.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_view.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_view.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(container)
        footer.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(1, weight=1)
        self.reveal_button = ttk.Button(
            footer, text="Show output", command=self._reveal_output, state="disabled"
        )
        self.reveal_button.grid(row=0, column=0, sticky="w")
        self.footer_detail = theme.wrapping(
            ttk.Label(footer, style="Muted.TLabel"), inset=PANE_INSET + 260
        )
        self.footer_detail.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Button(footer, text="Advanced...", command=self.open_advanced).grid(
            row=0, column=2, sticky="e"
        )

    def _build_quality_row(self, parent: ttk.Frame, row: int) -> None:
        """One more row in the same column, not a boxed section of its own."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=3)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Quality", width=FIELD).grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(frame)
        choices.grid(row=0, column=1, sticky="w", padx=8)
        for index, preset in enumerate((*PRESETS, None)):
            ttk.Radiobutton(
                choices,
                text=preset.label if preset else "Custom",
                value=preset.key if preset else CUSTOM_MODE,
                variable=self.mode_choice, command=self._mode_selected,
            ).grid(row=0, column=index, sticky="w", padx=(0, 16))
        self.mode_summary = theme.wrapping(
            ttk.Label(frame, style="Muted.TLabel"), inset=PANE_INSET + FIELD * 9
        )
        self.mode_summary.grid(row=1, column=1, sticky="w", padx=8, pady=(2, 0))

    def restyle(self, colors: theme.Palette) -> None:
        """Recolour what ttk styles cannot reach after an appearance change."""
        theme.restyle_text(self.log_view, colors)

    def log(self, message: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", message + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    # Shared state

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.mode_choice.set(settings.mode)
        separation.save_settings(
            provisioning.data_directory() / separation.SETTINGS_NAME, settings
        )
        self.refresh_runtime()

    def _mode_selected(self) -> None:
        """Switch preset, or hand the operator over to Advanced options."""
        chosen = self.mode_choice.get()
        if chosen == CUSTOM_MODE:
            if self.settings.mode != CUSTOM_MODE:
                self.apply_settings(self.settings.as_custom())
            self.open_advanced()
            return
        preset = separation.preset(chosen)
        if preset is not None:
            self.apply_settings(separation.apply_preset(
                self.settings, preset, self.catalogue,
                prefers_torch=self._prefers_torch(),
            ))
            if self.advanced is not None and self.advanced.winfo_exists():
                self.advanced.refresh()

    def reconcile_preset(self) -> None:
        """Re-derive a preset's model once the catalogue can confirm it.

        Before the runtime is installed there is no catalogue, so a preset
        resolves to its first candidate on faith. When the real list arrives
        the choice is made again, which is also what picks up a model that was
        renamed or withdrawn upstream, and what follows a change of accelerator
        to the variant that expresses the preset on the new one.
        """
        preset = separation.preset(self.settings.mode)
        if preset is None or not self.catalogue.models:
            return
        resolved = separation.apply_preset(
            self.settings, preset, self.catalogue,
            prefers_torch=self._prefers_torch(),
        )
        if resolved != self.settings:
            self.apply_settings(resolved)

    def _prefers_torch(self) -> bool:
        """Whether this machine's build accelerates PyTorch but not ONNX."""
        return provisioning.resolve_acceleration(self.settings.accelerator).prefers_torch

    def refresh_runtime(self) -> None:
        """Show the setup panel only while separation cannot run at all."""
        self.runtime = provisioning.detect()
        if self.runtime.ready:
            self.setup_frame.grid_forget()
        else:
            self.setup_status.set(self.runtime.summary)
            self.setup_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._describe_mode()
        self._describe_footer()
        self._describe_forecast()

    def _describe_mode(self) -> None:
        preset = separation.preset(self.settings.mode)
        self.mode_summary.configure(
            text=preset.summary if preset else "Set by hand in Advanced options."
        )

    def _describe_footer(self) -> None:
        """The model in use, and only what is wrong with it."""
        model = self.catalogue.by_filename(self.settings.model)
        parts = [self.settings.model]
        if model is not None and not model.is_downloaded(self.runtime.models):
            parts.append("downloads on first use")
        if provisioning.needs_reinstall(self.settings.accelerator, self.runtime):
            parts.append("runtime needs reinstallation")
        self.footer_detail.configure(text=" · ".join(parts))

    # Duration estimate

    def _estimator(self) -> estimate.Estimator:
        return estimate.estimator_for(
            provisioning.data_directory() / estimate.THROUGHPUT_NAME,
            self.catalogue.architecture_of(self.settings.model),
            provisioning.resolve_acceleration(self.settings.accelerator).key,
        )

    def _selected_playlist(self):
        playlist_id = self._playlist_labels.get(self.playlist_choice.get())
        if self.collection is None or playlist_id is None:
            return None
        return self.collection.playlist(playlist_id)

    def _describe_forecast(self) -> None:
        """Put what this playlist will cost on the shared status line.

        Only while idle: during a run that line is reporting the run, which is
        the more useful answer to the same question.
        """
        if self._running:
            return
        playlist = self._selected_playlist()
        if playlist is None or not playlist.tracks:
            self._forecast = estimate.Forecast()
            self.status.set("Choose an export and a playlist.")
            return
        self._forecast = estimate.forecast(playlist.tracks, self._estimator())
        parts = [self._forecast.summary]
        if playlist.missing_count:
            parts.append(f"{playlist.missing_count} missing")
        self.status.set(" · ".join(part for part in parts if part))

    def open_advanced(self) -> None:
        if self.advanced is not None and self.advanced.winfo_exists():
            self.advanced.lift()
            self.advanced.focus_set()
            return
        self.advanced = AdvancedDialog(self)

    # Model catalogue

    def load_catalogue(self, refresh: bool = False, done=None) -> None:
        if self.runtime.separator is None:
            self._show_catalogue(Catalogue(), None, done)
            return
        threading.Thread(
            target=self._catalogue_worker, args=(refresh, done), daemon=True
        ).start()

    def _catalogue_worker(self, refresh: bool, done) -> None:
        try:
            catalogue = separation.load_catalogue(
                self.runtime,
                provisioning.data_directory() / separation.CATALOGUE_NAME,
                refresh=refresh,
            )
        except Exception as error:  # Tk must receive worker failures on its own thread.
            self.after(0, self._show_catalogue, Catalogue(), str(error), done)
        else:
            self.after(0, self._show_catalogue, catalogue, None, done)

    def _show_catalogue(self, catalogue: Catalogue, error: str | None, done=None) -> None:
        self.catalogue = catalogue
        if error:
            self.log(f"Model list unavailable: {error}")
        self.reconcile_preset()
        self._describe_mode()
        self._describe_footer()
        self._describe_forecast()
        if done is not None:
            done()

    # Collection and paths

    def _choose_xml(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose the Rekordbox XML export",
            filetypes=[("Rekordbox XML export", "*.xml"), ("All files", "*")],
        )
        if selected:
            self.xml_path.set(selected)
            self._load_collection()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose the USB drive or output folder", mustexist=True
        )
        if selected:
            self.output_path.set(selected)

    def _output_directory(self) -> pathlib.Path | None:
        """Validate the destination, reporting why it cannot be used.

        An empty field would otherwise resolve to the working directory, which
        is the read-only volume root for an application launched from a
        desktop shell.
        """
        window = self.winfo_toplevel()
        raw = self.output_path.get().strip()
        if not raw:
            messagebox.showerror(
                "No output folder", "Choose the output folder or the USB drive to write to.",
                parent=window,
            )
            return None
        output = pathlib.Path(raw).expanduser()
        if not output.is_dir():
            messagebox.showerror(
                "Output not found", f"{output} is not an existing folder or mounted drive.",
                parent=window,
            )
            return None
        if not os.access(output, os.W_OK):
            messagebox.showerror(
                "Output not writable", f"{output} cannot be written to. Choose another folder.",
                parent=window,
            )
            return None
        return output

    def _load_collection(self) -> None:
        window = self.winfo_toplevel()
        path = pathlib.Path(self.xml_path.get()).expanduser()
        if not path.is_file():
            messagebox.showerror(
                "Export not found", "Choose an existing Rekordbox XML export.", parent=window
            )
            return
        try:
            collection = parse_collection(path)
        except Exception as error:
            messagebox.showerror("Export cannot be read", str(error), parent=window)
            return
        self.collection = collection
        self._playlist_labels = {
            playlist.label: playlist.playlist_id for playlist in collection.playlists
        }
        labels = list(self._playlist_labels)
        self.playlist_box.configure(values=labels, state="readonly" if labels else "disabled")
        self.playlist_choice.set(labels[0] if labels else "")
        self.log(
            f"Loaded {path} - {collection.track_count} tracks in the collection, "
            f"{len(collection.playlists)} playlists"
        )
        self._playlist_selected()

    def _playlist_selected(self, _event=None) -> None:
        """Report the selected playlist, not the whole collection."""
        if self.collection is not None:
            self._describe_forecast()

    # Job control

    def _confirm_long_run(self) -> bool:
        """Warn before a run long enough to tie the machine up for a while."""
        seconds = self._forecast.seconds
        if seconds is None or seconds < LONG_RUN_SECONDS:
            return True
        rough = "" if self._forecast.measured else " (rough)"
        return messagebox.askyesno(
            "This will take a while",
            f"{self._forecast.tracks} tracks, {estimate.format_duration(seconds)}"
            f"{rough}.\n\n{WORKLOAD_NOTICE}\n\nStart?",
            parent=self.winfo_toplevel(),
        )

    def _start_job(self) -> None:
        window = self.winfo_toplevel()
        if self.collection is None:
            messagebox.showerror(
                "No export loaded", "Load a Rekordbox XML export first.", parent=window
            )
            return
        playlist = self._selected_playlist()
        if playlist is None:
            messagebox.showerror(
                "No playlist selected", "Select a playlist to process.", parent=window
            )
            return
        output = self._output_directory()
        if output is None:
            return
        self.refresh_runtime()
        if not self.runtime.ready:
            messagebox.showerror("Runtime missing", self.runtime.summary, parent=window)
            self.open_advanced()
            return
        if provisioning.needs_reinstall(self.settings.accelerator, self.runtime) and not messagebox.askyesno(
            "Runtime needs reinstallation",
            "The runtime was installed for another processor type (CPU or GPU). Separation will run on the "
            "installed one until it is reinstalled.\n\nContinue anyway ?",
            parent=window,
        ):
            self.open_advanced()
            return
        if not self._confirm_long_run():
            return

        acceleration = provisioning.resolve_acceleration(self.settings.accelerator)
        self.job = StemJob(
            self.runtime,
            self.collection,
            playlist,
            output,
            settings=self.settings,
            architecture=self.catalogue.architecture_of(self.settings.model),
            acceleration=acceleration,
            estimator=self._estimator(),
            observer=lambda state: self.after(0, self._job_progress, state),
        )
        self._running = True
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.reveal_button.configure(state="disabled")
        self.log(f"{output / 'RX3_STEMS'} · {self.settings.model} · {acceleration.label}")
        threading.Thread(target=self._job_worker, daemon=True).start()

    def _job_worker(self) -> None:
        assert self.job is not None
        model = self.catalogue.by_filename(self.settings.model)
        if model is not None and not model.is_downloaded(self.runtime.models):
            self.after(0, self.status.set, f"Downloading {model.filename}...")
            try:
                separation.download_model(
                    self.runtime, model,
                    progress=lambda text: self.after(0, self.status.set, text),
                )
            except Exception as error:
                self.after(0, self._model_download_failed, str(error))
                return
        state = self.job.run()
        self.after(0, self._job_finished, state)

    def _model_download_failed(self, error: str) -> None:
        self._running = False
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.status.set("The model could not be downloaded.")
        self.log(error)
        messagebox.showerror("Model unavailable", error, parent=self.winfo_toplevel())

    def _job_progress(self, state: JobState) -> None:
        self.overall["value"] = state.progress
        self.track["value"] = state.track_progress
        # `position`, not `completed`: this sits beside the name of the track
        # being worked on, and answers which one it is.
        position = f"{state.position}/{state.total}" if state.position else ""
        remaining = (
            f"{estimate.format_duration(state.eta_seconds)} left"
            if state.eta_seconds else ""
        )
        self.status.set(" · ".join(
            part for part in (position, state.current, state.stage, remaining) if part
        ))

    def _cancel_job(self) -> None:
        if self.job is not None:
            self.cancel_button.configure(state="disabled")
            self.status.set("Cancelling...")
            self.job.cancel()

    def _job_finished(self, state: JobState) -> None:
        window = self.winfo_toplevel()
        self._running = False
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if self.job is not None:
            # What this machine measured is worth more than the seeded table,
            # and is what makes the next run's estimate meaningful.
            estimate.remember(
                provisioning.data_directory() / estimate.THROUGHPUT_NAME,
                self.job.estimator,
            )
        self.refresh_runtime()
        for result in state.results:
            verb = "kept" if result.status == "existing" else "created"
            self.log(f"{verb}: {result.sidecar} ({result.size} bytes)")
        for failure in state.errors:
            self.log(f"failed: {failure.track} - {failure.error}")
        for notice in state.notices:
            self.log(f"note: {notice}")
        if state.output is not None:
            self.reveal_button.configure(state="normal")
        if state.state == "failed":
            self.status.set("Failed.")
            messagebox.showerror("Generation failed", state.fatal, parent=window)
            return
        if state.state == "cancelled":
            self.status.set("Cancelled · finished stems kept.")
            return
        summary = f"{len(state.results)} stems in {estimate.format_duration(state.elapsed_seconds)}"
        if state.errors:
            summary += f" · {len(state.errors)} failed"
        self.status.set(summary)
        messagebox.showinfo(
            "Done",
            f"{summary}.\n\nCopy RX3_STEMS to the root of the Rekordbox USB drive.",
            parent=window,
        )

    def _reveal_output(self) -> None:
        if self.job is not None and self.job.state.output is not None:
            reveal(self.job.state.output)


def self_test() -> None:
    """Exercise runtime detection and the complete generation path off-line."""
    provisioning.detect()
    provisioning.available_accelerations()
    provisioning.resolve_acceleration()
    provisioning.installed_accelerator()
    try:
        # Exercises the frozen-application branch of interpreter discovery. A
        # host without Python is a supported state, so it is not a failure.
        provisioning.host_python()
    except provisioning.ProvisioningError:
        pass
    with tempfile.TemporaryDirectory(prefix="rx3-stem-studio-self-test-") as directory:
        root = pathlib.Path(directory)
        audio = root / "Artist - Track.aiff"
        audio.write_bytes(b"fixture")
        xml = root / "rekordbox.xml"
        xml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="1">'
            f'<TRACK TrackID="1" Name="Track" Artist="Artist" TotalTime="123" '
            f'Location="{audio.as_uri()}"/>'
            '</COLLECTION><PLAYLISTS><NODE Type="0" Name="ROOT">'
            '<NODE Type="1" Name="RX3 Stems" Entries="1"><TRACK Key="1"/></NODE>'
            '</NODE></PLAYLISTS></DJ_PLAYLISTS>',
            encoding="utf-8",
        )
        collection = parse_collection(xml)
        if collection.track_count != 1 or len(collection.playlists) != 1:
            raise RuntimeError("Embedded Rekordbox parsing is broken")
        output = root / "export"
        (output / "RX3_STEMS").mkdir(parents=True)
        (output / "RX3_STEMS/Artist - Track.rx3stem").write_bytes(b"x" * 128)
        state = StemJob(
            provisioning.detect(), collection, collection.playlists[0], output
        ).run()
        if state.state != "done" or state.results[0].status != "existing":
            raise RuntimeError(f"Generation self-test did not resume: {state.state}")
        if state.position != 1 or state.total != 1:
            raise RuntimeError("Generation self-test reported the wrong track position")
        if not (output / "rx3-stems-manifest.json").is_file():
            raise RuntimeError("Generation self-test did not write a manifest")
        # The quality presets must resolve to something runnable even with no
        # catalogue, which is the state before the runtime is installed.
        for preset in PRESETS:
            for prefers_torch in (False, True):
                resolved = separation.apply_preset(
                    Settings(), preset, Catalogue(), prefers_torch=prefers_torch
                )
                if not resolved.model or resolved.mode != preset.key:
                    raise RuntimeError(f"Preset {preset.key} did not resolve to a model")
