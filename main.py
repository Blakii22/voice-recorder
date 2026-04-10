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
import os
import threading
from pathlib import Path
from typing import Optional

# PyInstaller --windowed sets sys.stdout and sys.stderr to None.
# TQDM and other libraries crash trying to write to them. Mock them here.
class _DummyStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False

if sys.stdout is None: sys.stdout = _DummyStream()
if sys.stderr is None: sys.stderr = _DummyStream()
if getattr(sys, "__stdout__", None) is None: sys.__stdout__ = _DummyStream()
if getattr(sys, "__stderr__", None) is None: sys.__stderr__ = _DummyStream()

import customtkinter as ctk

from recorder import AudioRecorder, validate_device
from sender import send_transcription
from transcriber import Transcriber
from tray_app import TrayApp
from utils import deserialize_key
from i18n import t, set_language, get_language, subscribe, unsubscribe
from ui.loading_screen import ModelLoadingWindow

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import paths
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(paths.LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("main")

CONFIG_PATH = paths.CONFIG_PATH

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
    """Simple settings editor: name, model size, language."""
    win = ctk.CTkToplevel(root)
    win.geometry("480x480")
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

    labels = {}

    btn_row = ctk.CTkFrame(win, fg_color=BG)
    btn_row.pack(side="bottom", fill="x", padx=28, pady=(10, 28))

    scroll_f = ctk.CTkScrollableFrame(win, fg_color=BG, scrollbar_button_color=S2)
    scroll_f.pack(fill="both", expand=True, padx=0, pady=0)

    def row(key, widget_factory):
        f = ctk.CTkFrame(scroll_f, fg_color=BG)
        f.pack(fill="x", padx=16, pady=(0, 14))
        lbl = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=12), text_color=MUTED)
        lbl.pack(anchor="w")
        labels[key] = lbl
        w = widget_factory(f)
        w.pack(fill="x", pady=(4, 0))
        return w

    lbl_title_main = ctk.CTkLabel(scroll_f, text="", font=ctk.CTkFont(size=18, weight="bold"),
                                  text_color=TEXT)
    lbl_title_main.pack(anchor="w", padx=16, pady=(20, 20))

    kw = dict(height=40, corner_radius=10, fg_color=S2, border_color=S2, font=ctk.CTkFont(size=12))

    name_e = row("settings_speaker", lambda p: ctk.CTkEntry(p, **kw))
    
    model_cb = row("settings_model", lambda p: ctk.CTkComboBox(
        p, values=["tiny", "base", "small", "medium", "large-v3"],
        height=40, corner_radius=10, fg_color=S2, border_color=S2,
        dropdown_fg_color=S2, font=ctk.CTkFont(size=12)))
        
    LANG_MAP = {"pl": "Polski 🇵🇱", "uk": "Українська 🇺🇦", "en": "English 🇬🇧"}
    INV_LANG_MAP = {v: k for k, v in LANG_MAP.items()}
    
    def on_lang_change(val):
        code = INV_LANG_MAP.get(val, "pl")
        set_language(code)

    lang_cb = row("settings_lang", lambda p: ctk.CTkComboBox(
        p, values=list(LANG_MAP.values()),
        height=40, corner_radius=10, fg_color=S2, border_color=S2,
        dropdown_fg_color=S2, font=ctk.CTkFont(size=12), command=on_lang_change))

    # Mode dropdown removed as we now support dual simultaneous binds!

    name_e.insert(0, config.get("speaker_name", ""))
    model_cb.set(config.get("model_size", "medium"))
    current_lang = get_language()
    lang_cb.set(LANG_MAP.get(current_lang, LANG_MAP["pl"]))
    # Mode logic removed
    btn_cancel = ctk.CTkButton(btn_row, text="", width=100, height=38, corner_radius=10,
                  fg_color=S2, hover_color=S2, text_color=MUTED,
                  command=lambda: (win.grab_release(), win.destroy()))
    btn_cancel.pack(side="left")
    
    btn_save = ctk.CTkButton(btn_row, text="", width=120, height=38, corner_radius=10,
                  fg_color=ACCENT, font=ctk.CTkFont(size=13, weight="bold"))
    btn_save.pack(side="right")

    # Local hotkey state for settings dialog
    from utils import format_key_name, serialize_key, deserialize_key, is_dangerous_key
    settings_state = {
        "ptt": deserialize_key(config.get("hotkey_ptt_str", config.get("hotkey_str", ""))),
        "toggle": deserialize_key(config.get("hotkey_toggle_str", ""))
    }

    def _build_hk_row(parent, dict_key, title_key):
        hk_f = ctk.CTkFrame(parent, fg_color=BG)
        hk_f.pack(fill="x", padx=16, pady=(0, 14))
        lbl_hk = ctk.CTkLabel(hk_f, text=t(title_key), font=ctk.CTkFont(size=12), text_color=MUTED)
        lbl_hk.pack(anchor="w")
        current_val = settings_state[dict_key]
        current_name = format_key_name(current_val) if current_val else t("step2_no_key")
        
        btn_hotkey = ctk.CTkButton(
            hk_f, text=t("step2_change", name=current_name), height=40, corner_radius=10,
            fg_color=S2, hover_color=SURFACE, text_color=TEXT, font=ctk.CTkFont(size=12)
        )
        
        def _start_hotkey_capture():
            btn_hotkey.configure(text=t("step2_listening"), fg_color=ACCENT)
            def _listen():
                from pynput import keyboard as kb
                captured = []
                def on_press(key):
                    if key != kb.Key.esc and key not in captured:
                        captured.append(key)
                def on_release(key):
                    if captured:
                        return False
                with kb.Listener(on_press=on_press, on_release=on_release) as ls:
                    ls.join()
                if captured:
                    win.after(0, lambda: _on_hotkey_captured(tuple(captured)))
            import threading
            threading.Thread(target=_listen, daemon=True).start()

        def _on_hotkey_captured(key):
            settings_state[dict_key] = key
            name = format_key_name(key)
            btn_hotkey.configure(text=t("step2_change", name=name), fg_color=S2)

        btn_hotkey.configure(command=_start_hotkey_capture)
        btn_hotkey.pack(fill="x", pady=(4, 0))

    _build_hk_row(scroll_f, "ptt", "settings_ptt")
    _build_hk_row(scroll_f, "toggle", "settings_toggle")

    def _update_texts():
        win.title(t("settings_title"))
        lbl_title_main.configure(text=t("settings_header"))
        for key, lbl in labels.items():
            lbl.configure(text=t(key))
        btn_cancel.configure(text=t("settings_cancel"))
        btn_save.configure(text=t("settings_save"))

    subscribe(_update_texts)
    _update_texts()

    def _save():
        unsubscribe(_update_texts)
        config["speaker_name"] = name_e.get().strip()
        config["model_size"] = model_cb.get()
        config["ui_language"] = INV_LANG_MAP.get(lang_cb.get(), "pl")
        
        # Dual config saves
        if settings_state["ptt"]:
            config["hotkey_ptt_str"] = serialize_key(settings_state["ptt"])
        if settings_state["toggle"]:
            config["hotkey_toggle_str"] = serialize_key(settings_state["toggle"])
            
        save_config(config)
        on_saved()
        win.grab_release()
        win.destroy()
        
    def _cancel():
        # Revert language preview
        set_language(config.get("ui_language", "pl"))
        unsubscribe(_update_texts)
        win.grab_release()
        win.destroy()
        
    btn_cancel.configure(command=_cancel)
    btn_save.configure(command=_save)
    win.protocol("WM_DELETE_WINDOW", _cancel)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    if config:
        set_language(config.get("ui_language", "pl"))
    else:
        set_language("pl")

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # ── Phase 1: first-run wizard ──────────────────────────────────────────

    if not config or not config.get("speaker_name"):
        from ui.setup_wizard import SetupWizard
        wizard = SetupWizard()
        wizard.mainloop()
        config = wizard.result
        if not config:
            logger.info("Setup cancelled — exiting.")
            sys.exit(0)
        save_config(config)
        # Apply the selected language immediately
        set_language(config.get("ui_language", "pl"))

    # ── Phase 2: validate stored device ────────────────────────────────────
    device_index: int = config.get("audio_device_index", 0)
    ok, err = validate_device(device_index)
    if not ok:
        logger.warning(f"Stored device #{device_index} failed: {err}")

    # ── Phase 3: hidden CTk root (keeps tkinter alive) ─────────────────────
    root = ctk.CTk()
    root.withdraw()
    root.title(t("tray_idle"))

    # Start tray in background thread
    action_q: queue.Queue = queue.Queue()
    tray = TrayApp(action_q)
    tray_thread = threading.Thread(target=tray.run, daemon=True, name="TrayThread")
    tray_thread.start()
    
    # ── Phase 3.5: Check for updates silently in background
    from updater import check_for_updates
    check_for_updates(root)

    recorder = AudioRecorder(device_index)

    # ── Phase 4: load transcriber and show loading window ──────────────────
    loading_win = ModelLoadingWindow(root, config.get("model_size", "medium"))

    transcriber = Transcriber(config.get("model_size", "medium"),
                              "pl") # Always use polish for whisper recognition as requested initially or update?

    def _on_progress(event_type, data):
        # Must schedule GUI updates on the main thread
        if event_type == "status":
            root.after(0, lambda d=data: loading_win.set_status(d))
        elif event_type == "desc":
            root.after(0, lambda d=data: loading_win.set_status(d))
        elif event_type == "update":
            downloaded, total = data
            root.after(0, lambda d=downloaded, t=total: loading_win.set_progress(d, t))

    def _model_ready():
        root.after(0, loading_win.destroy)
        tray.set_state("idle")
        logger.info("Model ready — app idle.")

    def _model_error(exc):
        root.after(0, lambda: loading_win.set_status(f"Error: {exc}"))
        tray.set_state("error")
        logger.error(f"Model load error: {exc}")

    # Start transcriber background load
    transcriber.load_async(on_progress=_on_progress, on_ready=_model_ready, on_error=_model_error)

    # Show device error dialog on startup if device is bad
    if not ok:
        root.after(500, lambda: _prompt_device(root, config, recorder))

    # ── Hotkey listener ────────────────────────────────────────────────────
    def _load_hk_state():
        return {
            "ptt": set(deserialize_key(config.get("hotkey_ptt_str", config.get("hotkey_str", ""))) or []),
            "toggle": set(deserialize_key(config.get("hotkey_toggle_str", "")) or [])
        }
    hk_state = _load_hk_state()

    _recording_active = threading.Event()
    pressed_keys = set()
    _toggle_active = [False]
    
    def _stop_and_process():
        _recording_active.clear()
        wav_path, status = recorder.stop()

        if status == "too_short":
            tray.set_state("idle")
            return
        if status in ("silent", "empty"):
            tray.set_state("idle")
            tray.notify(t("tray_idle"), t("tray_no_audio"))
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
                tray.notify(t("tray_idle"), t("tray_error", exc=str(exc)[:40]))
                return
            finally:
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

            send_transcription(
                speaker=config["speaker_name"],
                text=text,
                on_success=lambda: tray.set_state("sent"),
                on_failure=lambda e: (
                    tray.set_state("idle"),
                    tray.notify(t("tray_idle"), t("tray_saved_fail", e=str(e)[:40])),
                ),
            )
            # Return to idle after a short pause
            threading.Timer(2.5, lambda: tray.set_state("idle")).start()

        threading.Thread(target=_pipeline, daemon=True, name="Pipeline").start()

    def _on_press(key):
        if key not in pressed_keys:
            pressed_keys.add(key)
            
        target_ptt = hk_state["ptt"]
        target_toggle = hk_state["toggle"]

        # 1. Toggle Mode Activation
        if target_toggle and target_toggle.issubset(pressed_keys):
            if _recording_active.is_set():
                if _toggle_active[0]:
                    _toggle_active[0] = False
                    _stop_and_process()
            else:
                if not transcriber.is_ready():
                    tray.notify(t("tray_idle"), t("tray_loading"))
                    return
                _toggle_active[0] = True
                _recording_active.set()
                ok2, err2 = recorder.start()
                if not ok2:
                    _recording_active.clear()
                    _toggle_active[0] = False
                    logger.warning(f"Recording start failed: {err2}")
                    root.after(0, lambda: _prompt_device(root, config, recorder))
                    return
                tray.set_state("recording")
        
        # 2. PTT Activation
        elif target_ptt and target_ptt.issubset(pressed_keys):
            if not _recording_active.is_set() and not _toggle_active[0]:
                if not transcriber.is_ready():
                    tray.notify(t("tray_idle"), t("tray_loading"))
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
        if key in pressed_keys:
            pressed_keys.remove(key)
            
        target_ptt = hk_state["ptt"]
        if target_ptt and not target_ptt.issubset(pressed_keys):
            if _recording_active.is_set() and not _toggle_active[0]:
                _stop_and_process()

    from pynput import keyboard as kb
    listener = kb.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
    logger.info(f"Listener initialized with configs.")

    # ── Phase 5: tray action loop (runs on main thread via after()) ────────
    def _process_actions():
        try:
            while True:
                action = action_q.get_nowait()
                if action == "open_settings":
                    def _on_settings_saved():
                        logger.info("Settings saved.")
                        # Reload hotkey
                        hk_state["target"] = deserialize_key(config.get("hotkey_str", ""))
                        hk_state["mode"] = config.get("recording_mode", "ptt")
                    open_settings_window(root, config, on_saved=_on_settings_saved)
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
    try:
        main()
    except Exception as e:
        import traceback
        try:
            import paths
            with open(paths.CRASH_LOG_PATH, "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass # Failsafe
        raise
