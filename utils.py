"""Shared utility functions."""
from pynput import keyboard as kb


# ---------------------------------------------------------------------------
# Hotkey serialisation
# ---------------------------------------------------------------------------

def serialize_key(key) -> str:
    """Convert a pynput key object to a JSON-safe string."""
    if isinstance(key, kb.Key):
        return f"Key.{key.name}"
    elif isinstance(key, kb.KeyCode):
        if key.char is not None:
            return f"char:{key.char}"
        else:
            return f"vk:{key.vk}"
    return str(key)


def deserialize_key(key_str: str):
    """Convert a stored string back to a pynput key object."""
    if not key_str:
        return None
    if key_str.startswith("Key."):
        try:
            return getattr(kb.Key, key_str[4:])
        except AttributeError:
            return None
    elif key_str.startswith("char:"):
        return kb.KeyCode.from_char(key_str[5:])
    elif key_str.startswith("vk:"):
        try:
            return kb.KeyCode.from_vk(int(key_str[3:]))
        except (ValueError, TypeError):
            return None
    return None


def format_key_name(key) -> str:
    """Return a human-readable label for a pynput key."""
    if key is None:
        return "—"
    if isinstance(key, kb.Key):
        _map = {
            "ctrl_r": "Right Ctrl", "ctrl_l": "Left Ctrl",
            "shift_r": "Right Shift", "shift_l": "Left Shift",
            "alt_r": "Right Alt", "alt_l": "Left Alt",
            "cmd": "Win Key", "cmd_r": "Right Win Key",
            "caps_lock": "Caps Lock", "scroll_lock": "Scroll Lock",
            "num_lock": "Num Lock", "pause": "Pause/Break",
            "print_screen": "Print Screen", "insert": "Insert",
            "delete": "Delete", "home": "Home", "end": "End",
            "page_up": "Page Up", "page_down": "Page Down",
            "up": "↑ Up", "down": "↓ Down",
            "left": "← Left", "right": "→ Right",
            "enter": "Enter", "backspace": "Backspace",
            "tab": "Tab", "esc": "Escape", "space": "Space",
        }
        for i in range(1, 13):
            _map[f"f{i}"] = f"F{i}"
        return _map.get(key.name, key.name.replace("_", " ").title())
    elif isinstance(key, kb.KeyCode):
        if key.char is not None:
            return key.char.upper()
        return f"Key(vk={key.vk})"
    return str(key)


DANGEROUS_KEYS = {
    kb.Key.esc, kb.Key.enter, kb.Key.backspace,
    kb.Key.tab, kb.Key.space,
}


def is_dangerous_key(key) -> bool:
    return key in DANGEROUS_KEYS
