"""
VoiceNote — push-to-talk recorder → faster-whisper → n8n → Google Sheets
Entry point.
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from recorder import AudioRecorder, validate_device
from sender import send_transcription
from transcriber import Transcriber
from tray_app import TrayApp
from utils import deserialize_key

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

CONFIG_PATH = Path("config.json")

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> Optional[dict]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error(f"Failed to read config: {exc}")
    return None


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    logger.info(f"Config saved → {CONFIG_PATH}")


# ---------------------------------------------------------------------------
# Settings dialog (opened from tray → "Open Settings")
# ---------------------------------------------------------------------------

def open_settings_window(root: ctk.CTk, config: dict, on_saved):
    """Simple settings editor: name, webhook URL, API key, model size."""
    win = ctk.CTkToplevel(root)
    win.title("VoiceNote — Settings")
    win.geometry("480x500")
    win.resizable(False, False)
    win.configure(fg_color="#0d0d14")
    win.grab_set()
    win.focus_force()

    BG      = "#0d0d14"
    SURFACE = "#16162a"
    S2      = "#1e1e33"
    ACCENT  = "#5865f2"
    TEXT    = "#e3e5e8"
    MUTED   = "#72767d"

    def row(label, widget_factory):
        f = ctk.CTkFrame(win, fg_color=BG)
        f.pack(fill="x", padx=28, pady=(0, 14))
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=12), text_color=MUTED).pack(anchor="w")
        w = widget_factory(f)
        w.pack(fill="x", pady=(4, 0))
        return w

    ctk.CTkLabel(win, text="Settings", font=ctk.CTkFont(size=18, weight="bold"),
                 text_color=TEXT).pack(anchor="w", padx=28, pady=(28, 20))

    kw = dict(height=40, corner_radius=10, fg_color=S2, border_color=S2,
              font=ctk.CTkFont(size=12))

    name_e   = row("Speaker name",    lambda p: ctk.CTkEntry(p, **kw))
    url_e    = row("n8n Webhook URL", lambda p: ctk.CTkEntry(p, **kw))
    key_e    = row("API Key",         lambda p: ctk.CTkEntry(p, show="•", **kw))
    model_cb = row("Model size", lambda p: ctk.CTkComboBox(
        p, values=["tiny", "base", "small", "medium", "large-v3"],
        height=40, corner_radius=10, fg_color=S2, border_color=S2,
        dropdown_fg_color=S2, font=ctk.CTkFont(size=12)))

    name_e.insert(0,   config.get("speaker_name", ""))
    url_e.insert(0,    config.get("webhook_url", ""))
    key_e.insert(0,    config.get("webhook_api_key", ""))
    model_cb.set(      config.get("model_size", "medium"))

    def _save():
        config["speaker_name"]   = name_e.get().strip()
        config["webhook_url"]    = url_e.get().strip()
        config["webhook_api_key"]= key_e.get().strip()
        config["model_size"]     = model_cb.get()
        save_config(config)
        on_saved()
        win.grab_release()
        win.destroy()

    btn_row = ctk.CTkFrame(win, fg_color=BG)
    btn_row.pack(fill="x", padx=28, pady=(10, 28))
    ctk.CTkButton(btn_row, text="Cancel", width=100, height=38, corner_radius=10,
                  fg_color=S2, hover_color=S2, text_color=MUTED,
                  command=lambda: (win.grab_release(), win.destroy())).pack(side="left")
    ctk.CTkButton(btn_row, text="Save", width=120, height=38, corner_radius=10,
                  fg_color=ACCENT, font=ctk.CTkFont(size=13, weight="bold"),
                  command=_save).pack(side="right")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # ── Phase 1: first-run wizard ──────────────────────────────────────────
    config = load_config()

    if not config or not config.get("speaker_name"):
        from ui.setup_wizard import SetupWizard
        wizard = SetupWizard()
        wizard.mainloop()
        config = wizard.result
        if not config:
            logger.info("Setup cancelled — exiting.")
            sys.exit(0)
        save_config(config)

    # ── Phase 2: validate stored device ────────────────────────────────────
    device_index: int = config.get("audio_device_index", 0)
    ok, err = validate_device(device_index)
    if not ok:
        logger.warning(f"Stored device #{device_index} failed: {err}")
        # We'll handle this below via the hidden root + dialog

    # ── Phase 3: start services ────────────────────────────────────────────
    transcriber = Transcriber(config.get("model_size", "medium"),
                              config.get("language", "pl"))

    action_q: queue.Queue = queue.Queue()
    tray = TrayApp(action_q)

    # Start tray in background thread
    tray_thread = threading.Thread(target=tray.run, daemon=True, name="TrayThread")
    tray_thread.start()

    recorder = AudioRecorder(device_index)

    # Load model async; update tray when ready
    def _model_ready():
        tray.set_state("idle")
        logger.info("Model ready — app idle.")

    def _model_error(exc):
        tray.set_state("error")
        logger.error(f"Model load error: {exc}")

    transcriber.load_async(on_ready=_model_ready, on_error=_model_error)

    # ── Phase 4: hidden CTk root (keeps tkinter alive for dialogs) ─────────
    root = ctk.CTk()
    root.withdraw()
    root.title("VoiceNote")

    # Show device error dialog on startup if device is bad
    if not ok:
        root.after(500, lambda: _prompt_device(root, config, recorder))

    # ── Hotkey listener ────────────────────────────────────────────────────
    target_key = deserialize_key(config.get("hotkey_str", ""))
    if target_key is None:
        logger.error("No valid hotkey in config — please re-run setup.")
        sys.exit(1)

    _recording_active = threading.Event()

    def _on_press(key):
        if key == target_key and not _recording_active.is_set():
            if not transcriber.is_ready():
                tray.notify("VoiceNote", "Model still loading, please wait…")
                return
            _recording_active.set()
            ok2, err2 = recorder.start()
            if not ok2:
                _recording_active.clear()
                logger.warning(f"Recording start failed: {err2}")
                root.after(0, lambda: _prompt_device(root, config, recorder))
                return
            tray.set_state("recording")

    def _on_release(key):
        if key == target_key and _recording_active.is_set():
            _recording_active.clear()
            wav_path, status = recorder.stop()

            if status == "too_short":
                tray.set_state("idle")
                return
            if status in ("silent", "empty"):
                tray.set_state("idle")
                tray.notify("VoiceNote", "No audio detected — check your microphone.")
                root.after(0, lambda: _prompt_device(root, config, recorder))
                return

            tray.set_state("transcribing")

            def _pipeline():
                try:
                    text = transcriber.transcribe(wav_path)
                    logger.info(f"Transcribed: {text[:80]!r}")
                except Exception as exc:
                    logger.error(f"Transcription failed: {exc}")
                    tray.set_state("error")
                    tray.notify("VoiceNote", f"Transcription error: {exc}")
                    return
                finally:
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass

                send_transcription(
                    speaker=config["speaker_name"],
                    text=text,
                    webhook_url=config.get("webhook_url", ""),
                    api_key=config.get("webhook_api_key", ""),
                    on_success=lambda: tray.set_state("sent"),
                    on_failure=lambda e: (
                        tray.set_state("idle"),
                        tray.notify("VoiceNote", f"Saved locally (webhook error: {e})"),
                    ),
                )
                # Return to idle after a short pause
                threading.Timer(2.5, lambda: tray.set_state("idle")).start()

            threading.Thread(target=_pipeline, daemon=True, name="Pipeline").start()

    from pynput import keyboard as kb
    listener = kb.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
    logger.info(f"Hotkey registered: {config.get('hotkey_str')}")

    # ── Phase 5: tray action loop (runs on main thread via after()) ────────
    def _process_actions():
        try:
            while True:
                action = action_q.get_nowait()
                if action == "open_settings":
                    open_settings_window(root, config,
                                         on_saved=lambda: logger.info("Settings saved."))
                elif action == "open_log":
                    try:
                        os.startfile("log.csv")
                    except Exception:
                        pass
                elif action == "quit":
                    listener.stop()
                    tray.stop()
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(100, _process_actions)

    root.after(100, _process_actions)
    root.mainloop()
    logger.info("VoiceNote exited.")


# ---------------------------------------------------------------------------
# Device re-picker helper
# ---------------------------------------------------------------------------

def _prompt_device(root: ctk.CTk, config: dict, recorder: AudioRecorder):
    """Show DeviceDialog; if confirmed, update config and recorder."""
    from ui.device_dialog import DeviceDialog
    dlg = DeviceDialog(root, error_message=f"Device '{config.get('audio_device_name', '')}' is unavailable.")
    root.wait_window(dlg)

    if dlg.selected_index is not None:
        config["audio_device_index"] = dlg.selected_index
        recorder.device_index = dlg.selected_index
        save_config(config)
        logger.info(f"Device switched to index {dlg.selected_index}")


if __name__ == "__main__":
    main()
