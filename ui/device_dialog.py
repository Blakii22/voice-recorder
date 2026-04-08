"""
Device error / repicker dialog.
Shown when the configured audio device fails or produces silence.
"""
import threading
from typing import Optional

import customtkinter as ctk
import sounddevice as sd
import numpy as np

from recorder import get_input_devices, SAMPLE_RATE

BG      = "#0d0d14"
SURFACE = "#16162a"
SURFACE2= "#1e1e33"
ACCENT  = "#5865f2"
ACCENT_H= "#4752c4"
SUCCESS = "#57f287"
WARNING = "#faa81a"
DANGER  = "#ed4245"
TEXT    = "#e3e5e8"
MUTED   = "#72767d"


class DeviceDialog(ctk.CTkToplevel):
    """
    Modal dialog for selecting a replacement audio device.
    Opens on device error; returns new device index via self.selected_index.
    """

    def __init__(self, parent, error_message: str = ""):
        super().__init__(parent)
        self.title("Microphone Problem")
        self.geometry("460x420")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.grab_set()            # modal
        self.focus_force()

        self.selected_index: Optional[int] = None
        self._device_map: dict[str, int] = {}
        self._level_stream = None
        self._level_value = 0.0
        self._monitor_active = False

        self._build(error_message)
        self._populate_devices()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build(self, error_message: str):
        # Error banner
        banner = ctk.CTkFrame(self, fg_color="#2a1a1a", corner_radius=10)
        banner.pack(fill="x", padx=24, pady=(24, 0))
        ctk.CTkLabel(banner, text="⚠  Microphone not responding",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=DANGER
                     ).pack(anchor="w", padx=16, pady=(12, 4))
        if error_message:
            ctk.CTkLabel(banner, text=error_message, font=ctk.CTkFont(size=11),
                         text_color=WARNING, wraplength=380, justify="left"
                         ).pack(anchor="w", padx=16, pady=(0, 12))

        # Device picker
        ctk.CTkLabel(self, text="Choose a different microphone:",
                     font=ctk.CTkFont(size=12), text_color=TEXT
                     ).pack(anchor="w", padx=24, pady=(20, 4))

        self._device_var = ctk.StringVar()
        self._combo = ctk.CTkComboBox(
            self, variable=self._device_var, height=42, corner_radius=10,
            fg_color=SURFACE2, border_color=SURFACE2, dropdown_fg_color=SURFACE2,
            font=ctk.CTkFont(size=12), command=self._on_device_changed
        )
        self._combo.pack(fill="x", padx=24)

        # Level meter
        meter_f = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=10)
        meter_f.pack(fill="x", padx=24, pady=(16, 0))
        ctk.CTkLabel(meter_f, text="Live input level",
                     font=ctk.CTkFont(size=11), text_color=MUTED
                     ).pack(anchor="w", padx=14, pady=(10, 2))
        self._bar = ctk.CTkProgressBar(
            meter_f, height=12, corner_radius=6, fg_color=SURFACE2, progress_color=ACCENT
        )
        self._bar.set(0)
        self._bar.pack(fill="x", padx=14, pady=(0, 4))
        self._status_lbl = ctk.CTkLabel(meter_f, text="—",
                                        font=ctk.CTkFont(size=11), text_color=MUTED)
        self._status_lbl.pack(anchor="w", padx=14, pady=(0, 10))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color=BG)
        btn_row.pack(fill="x", padx=24, pady=(20, 24))
        ctk.CTkButton(btn_row, text="Cancel", width=100, height=38, corner_radius=10,
                      fg_color=SURFACE2, hover_color=SURFACE2, text_color=MUTED,
                      command=self._cancel).pack(side="left")
        ctk.CTkButton(btn_row, text="Use this device", width=160, height=38,
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._confirm).pack(side="right")

    # ── Devices ──────────────────────────────────────────────────────────────

    def _populate_devices(self):
        devs = get_input_devices()
        self._device_map = {f"{name}  (#{idx})": idx for idx, name in devs}
        labels = list(self._device_map.keys())
        self._combo.configure(values=labels)
        if labels:
            self._combo.set(labels[0])
            self._on_device_changed(labels[0])

    def _on_device_changed(self, label: str):
        self._stop_monitor()
        self._start_monitor()

    def _current_index(self) -> Optional[int]:
        return self._device_map.get(self._device_var.get())

    # ── Level monitor ────────────────────────────────────────────────────────

    def _start_monitor(self):
        idx = self._current_index()
        if idx is None:
            return
        self._monitor_active = True

        def _cb(indata, frames, t, status):
            self._level_value = float(np.sqrt(np.mean(indata ** 2)))

        try:
            self._level_stream = sd.InputStream(
                device=idx, channels=1, samplerate=SAMPLE_RATE,
                blocksize=1024, callback=_cb
            )
            self._level_stream.start()
            self._tick()
        except Exception as exc:
            self._status_lbl.configure(text=f"Cannot open: {exc}", text_color=DANGER)

    def _stop_monitor(self):
        self._monitor_active = False
        if self._level_stream:
            try:
                self._level_stream.stop()
                self._level_stream.close()
            except Exception:
                pass
            self._level_stream = None

    def _tick(self):
        if not self._monitor_active:
            return
        norm = min(1.0, self._level_value * 30)
        self._bar.set(norm)
        color  = SUCCESS if norm > 0.05 else (WARNING if norm > 0.01 else MUTED)
        status = "Active" if norm > 0.05 else ("Faint signal" if norm > 0.01 else "Silent / no signal")
        self._status_lbl.configure(text=status, text_color=color)
        self.after(60, self._tick)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _confirm(self):
        self.selected_index = self._current_index()
        self._stop_monitor()
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.selected_index = None
        self._stop_monitor()
        self.grab_release()
        self.destroy()
