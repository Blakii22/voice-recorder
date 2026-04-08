"""
Three-step first-run setup wizard built with CustomTkinter.
  Step 1 — Speaker name
  Step 2 — Hotkey capture
  Step 3 — Audio device picker with live level meter + test
"""
import threading
import time
from typing import Optional

import customtkinter as ctk
import sounddevice as sd

from recorder import get_input_devices, validate_device, SAMPLE_RATE
from utils import serialize_key, format_key_name, is_dangerous_key


# ── Colour tokens ────────────────────────────────────────────────────────────
BG        = "#0d0d14"
SURFACE   = "#16162a"
SURFACE2  = "#1e1e33"
ACCENT    = "#5865f2"
ACCENT_H  = "#4752c4"
SUCCESS   = "#57f287"
WARNING   = "#faa81a"
DANGER    = "#ed4245"
TEXT      = "#e3e5e8"
MUTED     = "#72767d"
FONT_MAIN = ("Inter", 13)
FONT_H1   = ("Inter", 22, "bold")
FONT_H2   = ("Inter", 15, "bold")
FONT_SM   = ("Inter", 11)


class SetupWizard(ctk.CTk):
    """Runs the full setup wizard and stores the result in self.result."""

    STEPS = 3

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("VoiceNote — Setup")
        self.geometry("500x560")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # State
        self.result: Optional[dict] = None
        self._step = 0
        self._captured_key = None
        self._capturing_hotkey = False
        self._hotkey_listener = None
        self._level_stream = None
        self._level_value = 0.0
        self._monitor_active = False
        self._test_running = False

        self._build_chrome()
        self._build_steps()
        self._show_step(0)

    # ── Chrome (header + dots + nav) ─────────────────────────────────────────

    def _build_chrome(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG)
        hdr.pack(fill="x", padx=36, pady=(32, 0))
        ctk.CTkLabel(hdr, text="🎙️  VoiceNote", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(hdr, text="Quick setup — takes under a minute",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(anchor="w", pady=(2, 0))

        # Progress dots
        dot_row = ctk.CTkFrame(self, fg_color=BG)
        dot_row.pack(fill="x", padx=36, pady=(18, 0))
        self._dots = []
        inner = ctk.CTkFrame(dot_row, fg_color=BG)
        inner.pack(anchor="w")
        for i in range(self.STEPS):
            if i:
                ctk.CTkFrame(inner, width=32, height=2, fg_color=SURFACE2,
                             corner_radius=1).pack(side="left", padx=2)
            dot = ctk.CTkFrame(inner, width=14, height=14, corner_radius=7, fg_color=SURFACE2)
            dot.pack(side="left")
            self._dots.append(dot)

        # Content card
        self._card = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=16)
        self._card.pack(fill="both", expand=True, padx=36, pady=18)

        # Nav buttons
        nav = ctk.CTkFrame(self, fg_color=BG)
        nav.pack(fill="x", padx=36, pady=(0, 28))
        self._back_btn = ctk.CTkButton(
            nav, text="← Back", width=100, height=38,
            fg_color=SURFACE2, hover_color=SURFACE, text_color=MUTED,
            corner_radius=10, command=self._prev
        )
        self._back_btn.pack(side="left")
        self._next_btn = ctk.CTkButton(
            nav, text="Next →", width=130, height=38,
            fg_color=ACCENT, hover_color=ACCENT_H,
            corner_radius=10, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._next
        )
        self._next_btn.pack(side="right")

    # ── Step frames ──────────────────────────────────────────────────────────

    def _build_steps(self):
        self._frames: list[ctk.CTkFrame] = []
        for builder in [self._build_step1, self._build_step2, self._build_step3]:
            f = ctk.CTkFrame(self._card, fg_color=SURFACE, corner_radius=0)
            builder(f)
            self._frames.append(f)

    # Step 1 — name -----------------------------------------------------------

    def _build_step1(self, f: ctk.CTkFrame):
        ctk.CTkLabel(f, text="What's your name?", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=28, pady=(28, 4))
        ctk.CTkLabel(f, text="This will appear next to every transcription in Google Sheets.",
                     font=ctk.CTkFont(size=12), text_color=MUTED, wraplength=380,
                     justify="left").pack(anchor="w", padx=28)

        self._name_var = ctk.StringVar()
        self._name_entry = ctk.CTkEntry(
            f, textvariable=self._name_var, placeholder_text="e.g. Jan Kowalski",
            height=44, corner_radius=10, font=ctk.CTkFont(size=13),
            fg_color=SURFACE2, border_color=SURFACE2, border_width=1
        )
        self._name_entry.pack(fill="x", padx=28, pady=(16, 0))

        self._name_err = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                      text_color=DANGER)
        self._name_err.pack(anchor="w", padx=28, pady=(6, 0))

    # Step 2 — hotkey ---------------------------------------------------------

    def _build_step2(self, f: ctk.CTkFrame):
        ctk.CTkLabel(f, text="Set your push-to-talk key",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT
                     ).pack(anchor="w", padx=28, pady=(28, 4))
        ctk.CTkLabel(f,
                     text="Hold this key while speaking. Released = transcription starts.",
                     font=ctk.CTkFont(size=12), text_color=MUTED, wraplength=380,
                     justify="left").pack(anchor="w", padx=28)

        self._hotkey_btn = ctk.CTkButton(
            f, text="🎹  Click here, then press a key…",
            height=52, corner_radius=10, font=ctk.CTkFont(size=13),
            fg_color=SURFACE2, hover_color=SURFACE, text_color=TEXT,
            command=self._start_hotkey_capture
        )
        self._hotkey_btn.pack(fill="x", padx=28, pady=(20, 0))

        self._hotkey_label = ctk.CTkLabel(f, text="No key selected yet.",
                                          font=ctk.CTkFont(size=12), text_color=MUTED)
        self._hotkey_label.pack(anchor="w", padx=28, pady=(10, 0))

        self._hotkey_warn = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                         text_color=WARNING, wraplength=380, justify="left")
        self._hotkey_warn.pack(anchor="w", padx=28, pady=(4, 0))

        ctk.CTkLabel(f,
                     text="💡 Recommended: Right Ctrl, Scroll Lock, F9 — rarely conflicts with other shortcuts.",
                     font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=380,
                     justify="left").pack(anchor="w", padx=28, pady=(16, 0))

    # Step 3 — device ---------------------------------------------------------

    def _build_step3(self, f: ctk.CTkFrame):
        ctk.CTkLabel(f, text="Choose your microphone",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT
                     ).pack(anchor="w", padx=28, pady=(28, 4))
        ctk.CTkLabel(f, text="Select the input device you'll speak into.",
                     font=ctk.CTkFont(size=12), text_color=MUTED
                     ).pack(anchor="w", padx=28)

        # Device dropdown
        self._device_var = ctk.StringVar(value="")
        self._device_map: dict[str, int] = {}  # label → device index
        self._device_combo = ctk.CTkComboBox(
            f, variable=self._device_var, height=42, corner_radius=10,
            fg_color=SURFACE2, border_color=SURFACE2, dropdown_fg_color=SURFACE2,
            font=ctk.CTkFont(size=12), command=self._on_device_changed
        )
        self._device_combo.pack(fill="x", padx=28, pady=(14, 0))

        # Level meter
        meter_row = ctk.CTkFrame(f, fg_color=SURFACE)
        meter_row.pack(fill="x", padx=28, pady=(14, 0))
        ctk.CTkLabel(meter_row, text="Input level", font=ctk.CTkFont(size=11),
                     text_color=MUTED).pack(anchor="w")
        self._level_bar = ctk.CTkProgressBar(
            meter_row, height=12, corner_radius=6,
            fg_color=SURFACE2, progress_color=ACCENT
        )
        self._level_bar.set(0)
        self._level_bar.pack(fill="x", pady=(4, 0))

        self._level_status = ctk.CTkLabel(meter_row, text="—",
                                          font=ctk.CTkFont(size=11), text_color=MUTED)
        self._level_status.pack(anchor="w", pady=(4, 0))

        # Test button
        self._test_btn = ctk.CTkButton(
            f, text="▶  Test (2 s)", height=38, corner_radius=10,
            fg_color=SURFACE2, hover_color=SURFACE, text_color=TEXT,
            font=ctk.CTkFont(size=12), command=self._run_test
        )
        self._test_btn.pack(fill="x", padx=28, pady=(14, 0))

        self._test_result = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                         text_color=MUTED)
        self._test_result.pack(anchor="w", padx=28, pady=(6, 0))

    # ── Step navigation ──────────────────────────────────────────────────────

    def _show_step(self, step: int):
        for i, dot in enumerate(self._dots):
            dot.configure(fg_color=ACCENT if i <= step else SURFACE2)

        for i, frame in enumerate(self._frames):
            if i == step:
                frame.pack(fill="both", expand=True, padx=0, pady=0)
            else:
                frame.pack_forget()

        self._back_btn.configure(state="normal" if step > 0 else "disabled",
                                 text_color=TEXT if step > 0 else SURFACE2)

        if step == self.STEPS - 1:
            self._next_btn.configure(text="✓  Start App")
        else:
            self._next_btn.configure(text="Next →")

        # Activate step-specific logic
        if step == 2:
            self._populate_devices()
            self._start_level_monitor()
        else:
            self._stop_level_monitor()

    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._show_step(self._step)

    def _next(self):
        if self._step == 0:
            if not self._validate_name():
                return
        elif self._step == 1:
            if not self._validate_hotkey():
                return
        elif self._step == 2:
            if not self._validate_device():
                return
            self._finish()
            return

        self._step += 1
        self._show_step(self._step)

    # ── Validation ───────────────────────────────────────────────────────────

    def _validate_name(self) -> bool:
        name = self._name_var.get().strip()
        if not name:
            self._name_err.configure(text="⚠  Please enter your name.")
            return False
        if len(name) < 2:
            self._name_err.configure(text="⚠  Name is too short.")
            return False
        self._name_err.configure(text="")
        return True

    def _validate_hotkey(self) -> bool:
        if self._captured_key is None:
            self._hotkey_warn.configure(text="⚠  Please capture a hotkey first.",
                                        text_color=DANGER)
            return False
        self._hotkey_warn.configure(text="")
        return True

    def _validate_device(self) -> bool:
        label = self._device_var.get()
        if label not in self._device_map:
            self._test_result.configure(text="⚠  Please select a device.", text_color=DANGER)
            return False
        self._test_result.configure(text="")
        return True

    # ── Hotkey capture ───────────────────────────────────────────────────────

    def _start_hotkey_capture(self):
        if self._capturing_hotkey:
            return
        self._capturing_hotkey = True
        self._hotkey_btn.configure(text="🔴  Listening — press any key…",
                                   fg_color=DANGER, hover_color=DANGER)
        self._hotkey_label.configure(text="Waiting for key press…", text_color=MUTED)

        def _listen():
            from pynput import keyboard as kb
            captured = []

            def on_press(k):
                if not captured:
                    captured.append(k)
                return False  # stop listener

            with kb.Listener(on_press=on_press) as ls:
                ls.join()

            if captured:
                self.after(0, lambda: self._on_key_captured(captured[0]))

        threading.Thread(target=_listen, daemon=True, name="HotkeyCapture").start()

    def _on_key_captured(self, key):
        self._capturing_hotkey = False
        self._captured_key = key
        name = format_key_name(key)
        self._hotkey_btn.configure(
            text=f"✓  {name}  — click to change",
            fg_color=SUCCESS, hover_color="#45c96e", text_color="#0d0d14"
        )
        self._hotkey_label.configure(text=f"Selected: {name}", text_color=SUCCESS)
        if is_dangerous_key(key):
            self._hotkey_warn.configure(
                text=f"⚠  {name} is a common key that may interfere with normal typing. Consider choosing another.",
                text_color=WARNING
            )
        else:
            self._hotkey_warn.configure(text="")

    # ── Device handling ──────────────────────────────────────────────────────

    def _populate_devices(self):
        devs = get_input_devices()
        self._device_map = {f"{name}  (#{idx})": idx for idx, name in devs}
        labels = list(self._device_map.keys())
        self._device_combo.configure(values=labels)
        if labels:
            self._device_combo.set(labels[0])
            self._on_device_changed(labels[0])

    def _on_device_changed(self, label: str):
        self._stop_level_monitor()
        self._start_level_monitor()
        self._test_result.configure(text="")

    def _current_device_index(self) -> Optional[int]:
        label = self._device_var.get()
        return self._device_map.get(label)

    # ── Live level monitor ───────────────────────────────────────────────────

    def _start_level_monitor(self):
        idx = self._current_device_index()
        if idx is None:
            return
        self._monitor_active = True

        import numpy as np

        def _cb(indata, frames, t, status):
            self._level_value = float(np.sqrt(np.mean(indata ** 2)))

        try:
            self._level_stream = sd.InputStream(
                device=idx, channels=1, samplerate=SAMPLE_RATE,
                blocksize=1024, callback=_cb
            )
            self._level_stream.start()
            self._update_meter()
        except Exception as exc:
            self._level_status.configure(text=f"Cannot open: {exc}", text_color=DANGER)

    def _stop_level_monitor(self):
        self._monitor_active = False
        if self._level_stream:
            try:
                self._level_stream.stop()
                self._level_stream.close()
            except Exception:
                pass
            self._level_stream = None

    def _update_meter(self):
        if not self._monitor_active:
            return
        norm = min(1.0, self._level_value * 30)
        self._level_bar.set(norm)
        color = SUCCESS if norm > 0.05 else (WARNING if norm > 0.01 else MUTED)
        status = "Active" if norm > 0.05 else ("Faint signal" if norm > 0.01 else "Silent / no signal")
        self._level_status.configure(text=status, text_color=color)
        self.after(60, self._update_meter)

    # ── 2-second test ────────────────────────────────────────────────────────

    def _run_test(self):
        if self._test_running:
            return
        idx = self._current_device_index()
        if idx is None:
            return
        self._test_running = True
        self._test_btn.configure(state="disabled", text="⏱  Recording 2 s…")
        self._test_result.configure(text="", text_color=MUTED)

        import numpy as np

        def _test():
            try:
                audio = sd.rec(int(2 * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                               channels=1, dtype="float32", device=idx)
                sd.wait()
                rms = float(np.sqrt(np.mean(audio ** 2)))
                if rms > 0.008:
                    msg, col = f"✓  Sound detected (level {rms:.4f}) — microphone works!", SUCCESS
                elif rms > 0.001:
                    msg, col = f"⚠  Very faint signal (level {rms:.4f}). Check volume.", WARNING
                else:
                    msg, col = "✗  No sound detected. Is the microphone muted?", DANGER
            except Exception as e:
                msg, col = f"✗  Error: {e}", DANGER

            self.after(0, lambda: self._test_done(msg, col))

        threading.Thread(target=_test, daemon=True, name="MicTest").start()

    def _test_done(self, msg: str, color: str):
        self._test_running = False
        self._test_btn.configure(state="normal", text="▶  Test (2 s)")
        self._test_result.configure(text=msg, text_color=color)

    # ── Finish ───────────────────────────────────────────────────────────────

    def _finish(self):
        self._stop_level_monitor()
        dev_label = self._device_var.get()
        dev_idx = self._device_map.get(dev_label, 0)
        dev_name = dev_label.rsplit("  (#", 1)[0]  # strip index suffix

        self.result = {
            "speaker_name": self._name_var.get().strip(),
            "hotkey_str": serialize_key(self._captured_key),
            "audio_device_index": dev_idx,
            "audio_device_name": dev_name,
            "webhook_url": "https://[YOUR_N8N_SERVER_ADDRESS]/webhook/[YOUR_WEBHOOK_PATH]",
            "webhook_api_key": "[YOUR_API_KEY_HERE]",
            "model_size": "medium",
            "language": "pl",
        }
        self.destroy()

    def _on_close(self):
        self._stop_level_monitor()
        self.result = None
        self.destroy()
