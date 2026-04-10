"""Shared utility functions."""
from pynput import keyboard as kb


# ---------------------------------------------------------------------------
# Hotkey serialisation
# ---------------------------------------------------------------------------

def serialize_single_key(key) -> str:
    """Convert a single pynput key to a string."""
    if isinstance(key, kb.Key):
        return f"Key.{key.name}"
    elif isinstance(key, kb.KeyCode):
        if key.char is not None:
            return f"char:{key.char}"
        else:
            return f"vk:{key.vk}"
    return str(key)


def serialize_key(key) -> str:
    """Convert key or collection of keys to JSON-safe string."""
    if isinstance(key, (list, tuple, set)):
        return "|".join(serialize_single_key(k) for k in key)
    return serialize_single_key(key)


def deserialize_single_key(key_str: str):
    """Convert string to single pynput key."""
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


def deserialize_key(key_str: str):
    """Convert stored string back to tuple of keys."""
    if not key_str:
        return tuple()
    parts = key_str.split("|")
    keys = []
    for p in parts:
        k = deserialize_single_key(p)
        if k is not None:
            keys.append(k)
    return tuple(keys)


def format_single_key_name(key) -> str:
    """Return a human-readable label for a single pynput key."""
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


def format_key_name(key) -> str:
    if not key:
        return "—"
    if isinstance(key, (list, tuple, set)):
        return " + ".join(format_single_key_name(k) for k in key)
    return format_single_key_name(key)


DANGEROUS_KEYS = {
    kb.Key.esc, kb.Key.enter, kb.Key.backspace,
    kb.Key.tab, kb.Key.space,
}


def is_dangerous_key(key) -> bool:
    if isinstance(key, (list, tuple, set)):
        if len(key) == 1:
            return key[0] in DANGEROUS_KEYS if isinstance(key, (list, tuple)) else next(iter(key)) in DANGEROUS_KEYS
        return False
    return key in DANGEROUS_KEYS
