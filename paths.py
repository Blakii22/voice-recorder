import os
from pathlib import Path

APP_DIR = Path.home() / "Documents" / "VoiceNote"

# Create the folder if it doesn't exist to prevent IO errors
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = APP_DIR / "config.json"
LOG_CSV_PATH = APP_DIR / "log.csv"
LOG_FILE_PATH = APP_DIR / "voicenote.log"
CRASH_LOG_PATH = APP_DIR / "crash_log.txt"
