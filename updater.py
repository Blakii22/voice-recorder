import httpx
import threading
import logging
import webbrowser
from pathlib import Path
import customtkinter as ctk
from i18n import t

logger = logging.getLogger(__name__)

def check_for_updates(root: ctk.CTk):
    """
    Checks the GitHub API to see if a newer version of the app exists.
    If yes, triggers a popup on the main thread.
    """
    def _run():
        try:
            # 1. Read current version
            version_path = Path("version.txt")
            if not version_path.exists():
                return
            
            with open(version_path, "r", encoding="utf-8") as f:
                current_ver = f.read().strip()
                
            if not current_ver:
                return

            # 2. Fetch latest version from GitHub
            url = "https://api.github.com/repos/Blakii22/voice-recorder/releases/latest"
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code != 200:
                    return
                data = res.json()
                
            remote_ver = data.get("tag_name", "").strip()
            if not remote_ver:
                return

            # Note: A simple string check assuming standard format v0.5.1 vs v0.5.2
            # For complex versions, 'packaging.version' is better, but this suffices.
            if remote_ver != current_ver and remote_ver > current_ver:
                logger.info(f"Update available: {remote_ver} (Current: {current_ver})")
                root.after(1000, lambda: _show_update_popup(root, remote_ver))

        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")

    threading.Thread(target=_run, daemon=True, name="UpdaterThread").start()


def _show_update_popup(root: ctk.CTk, new_version: str):
    """Display a popup giving the user the option to download the update."""
    win = ctk.CTkToplevel(root)
    win.geometry("400x200")
    win.resizable(False, False)
    win.configure(fg_color="#0d0d14")
    win.title(t("update_title"))
    win.attributes("-topmost", True)
    win.grab_set()
    win.focus_force()

    BG      = "#0d0d14"
    S2      = "#1e1e33"
    ACCENT  = "#5865f2"
    TEXT    = "#e3e5e8"
    MUTED   = "#72767d"

    lbl_title = ctk.CTkLabel(win, text=t("update_title"), font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT)
    lbl_title.pack(anchor="w", padx=28, pady=(24, 8))

    desc_text = t("update_desc", version=new_version)
    lbl_desc = ctk.CTkLabel(win, text=desc_text, font=ctk.CTkFont(size=12), text_color=MUTED, wraplength=340, justify="left")
    lbl_desc.pack(anchor="w", padx=28, pady=(0, 24))

    btn_row = ctk.CTkFrame(win, fg_color=BG)
    btn_row.pack(fill="x", padx=28, pady=(0, 20))

    def _open_url():
        webbrowser.open("https://github.com/Blakii22/voice-recorder/releases/latest")
        win.destroy()

    btn_no = ctk.CTkButton(btn_row, text=t("update_no"), width=100, height=38, corner_radius=10,
                           fg_color=S2, hover_color=S2, text_color=MUTED,
                           command=win.destroy)
    btn_no.pack(side="left")

    btn_yes = ctk.CTkButton(btn_row, text=t("update_yes"), width=120, height=38, corner_radius=10,
                            fg_color=ACCENT, font=ctk.CTkFont(size=13, weight="bold"),
                            command=_open_url)
    btn_yes.pack(side="right")
