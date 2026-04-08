"""System tray icon with state-based colour coding."""
import logging
import queue
import threading
from typing import Callable

from PIL import Image, ImageDraw
import pystray

logger = logging.getLogger(__name__)

# Colour per state
_COLORS = {
    "loading":      "#5865f2",   # blue-purple
    "idle":         "#72767d",   # grey
    "recording":    "#ed4245",   # red
    "transcribing": "#faa81a",   # amber
    "sent":         "#57f287",   # green
    "error":        "#ed4245",   # red
}

_LABELS = {
    "loading":      "VoiceNote — Loading model…",
    "idle":         "VoiceNote — Ready",
    "recording":    "VoiceNote — Recording…",
    "transcribing": "VoiceNote — Transcribing…",
    "sent":         "VoiceNote — Sent ✓",
    "error":        "VoiceNote — Error",
}


def _make_icon_image(state: str) -> Image.Image:
    size = 64
    color = _COLORS.get(state, "#72767d")
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Mic capsule
    d.rounded_rectangle([20, 4, 44, 38], radius=12, fill=color)
    # Mic stand arc
    d.arc([10, 20, 54, 52], start=0, end=180, fill=color, width=4)
    # Stand post + base
    d.line([32, 52, 32, 60], fill=color, width=4)
    d.line([22, 60, 42, 60], fill=color, width=4)

    # Pulse ring on recording
    if state == "recording":
        d.ellipse([4, 4, 60, 60], outline=color, width=2)

    return img


class TrayApp:
    def __init__(self, action_queue: queue.Queue):
        self._queue = action_queue
        self._state = "loading"
        self._icon: pystray.Icon | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_state(self, state: str):
        self._state = state
        if self._icon:
            self._icon.icon = _make_icon_image(state)
            self._icon.title = _LABELS.get(state, "VoiceNote")

    def notify(self, title: str, message: str):
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def run(self):
        """Blocking — call from a dedicated thread."""
        menu = pystray.Menu(
            pystray.MenuItem("Open Settings", self._on_settings),
            pystray.MenuItem("View Log", self._on_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            "voicenote",
            _make_icon_image("loading"),
            "VoiceNote — Loading…",
            menu=menu,
        )
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _on_settings(self, icon, item):
        self._queue.put("open_settings")

    def _on_log(self, icon, item):
        self._queue.put("open_log")

    def _on_quit(self, icon, item):
        self._queue.put("quit")
