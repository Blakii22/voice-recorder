import time
import customtkinter as ctk

# Colour tokens
BG        = "#0d0d14"
SURFACE   = "#16162a"
SURFACE2  = "#1e1e33"
ACCENT    = "#5865f2"
TEXT      = "#e3e5e8"
MUTED     = "#72767d"

class ModelLoadingWindow(ctk.CTkToplevel):
    def __init__(self, parent, model_size: str):
        super().__init__(parent)
        self.title("VoiceNote — Loading Model")
        self.geometry("450x200")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        # self.overrideredirect(True)
        self.grab_set()

        self._start_time = time.time()
        self._last_downloaded = 0
        self._last_time = self._start_time

        f = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=16)
        f.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        self.lbl_head = ctk.CTkLabel(f, text=f"Loading Whisper model '{model_size}'...",
                                     font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT)
        self.lbl_head.pack(anchor="w", padx=20, pady=(20, 10))

        # Progress elements
        self.bar = ctk.CTkProgressBar(f, height=14, corner_radius=7, fg_color=SURFACE2, progress_color=ACCENT)
        self.bar.set(0.0)
        self.bar.pack(fill="x", padx=20, pady=(0, 10))

        # Details
        det_row = ctk.CTkFrame(f, fg_color="transparent")
        det_row.pack(fill="x", padx=20)
        self.lbl_status = ctk.CTkLabel(det_row, text="Initializing...", font=ctk.CTkFont(size=11), text_color=MUTED)
        self.lbl_status.pack(side="left")

        self.lbl_speed = ctk.CTkLabel(det_row, text="", font=ctk.CTkFont(size=11), text_color=MUTED)
        self.lbl_speed.pack(side="right")
        
        # To handle window closure properly
        self.protocol("WM_DELETE_WINDOW", lambda: None)

    def set_progress(self, downloaded: int, total: int):
        if total == 0:
            return
        
        now = time.time()
        dt = now - self._last_time
        if dt > 0.5:
            # compute speed
            bytes_diff = downloaded - self._last_downloaded
            speed_mb = (bytes_diff / (1024*1024)) / dt
            self.lbl_speed.configure(text=f"{speed_mb:.1f} MB/s")
            
            self._last_time = now
            self._last_downloaded = downloaded

        progress = downloaded / total
        self.bar.set(progress)
        
        mb_d = downloaded / (1024*1024)
        mb_t = total / (1024*1024)
        self.lbl_status.configure(text=f"Downloading: {mb_d:.1f}/{mb_t:.1f} MB")
        self.update()

    def set_status(self, text: str):
        self.lbl_status.configure(text=text)
        self.lbl_speed.configure(text="")
        self.bar.set(0) # set to indeterminate style by repeatedly calling step() if we wanted, but 0 is fine
        self.update()
