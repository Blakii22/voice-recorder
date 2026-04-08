"""Audio recording via sounddevice."""
import logging
import tempfile
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000          # Whisper optimal
CHANNELS = 1
SILENCE_THRESHOLD = 0.002    # RMS; below this → consider silent
MIN_DURATION = 0.5            # seconds; shorter recordings are ignored


# ---------------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------------

def get_input_devices() -> list[tuple[int, str]]:
    """Return (index, name) for every input-capable device."""
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def validate_device(index: int) -> tuple[bool, str]:
    """Try opening a stream to verify the device works. Returns (ok, msg)."""
    try:
        devs = sd.query_devices()
        if index >= len(devs):
            return False, f"Device index {index} does not exist"
        if devs[index]["max_input_channels"] == 0:
            return False, f"'{devs[index]['name']}' has no input channels"
        with sd.InputStream(device=index, channels=CHANNELS, samplerate=SAMPLE_RATE, blocksize=512):
            pass
        return True, ""
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------

class AudioRecorder:
    def __init__(self, device_index: Optional[int] = None):
        self.device_index = device_index
        self.is_recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._start_time: float = 0.0

    # --- internal callback ---------------------------------------------------

    def _cb(self, indata, frames, t, status):
        if status:
            logger.warning(f"Stream: {status}")
        with self._lock:
            if self.is_recording:
                self._chunks.append(indata.copy())

    # --- public API ----------------------------------------------------------

    def start(self) -> tuple[bool, str]:
        """Open stream and begin recording. Returns (ok, error_msg)."""
        self._chunks = []
        self._start_time = time.time()
        try:
            self._stream = sd.InputStream(
                device=self.device_index,
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                callback=self._cb,
                blocksize=1024,
                latency="low",
            )
            self._stream.start()
            self.is_recording = True
            _beep(880, 80)
            return True, ""
        except Exception as exc:
            self.is_recording = False
            return False, str(exc)

    def stop(self) -> tuple[Optional[str], str]:
        """
        Stop recording, save WAV to a temp file.
        Returns (wav_path, status) where status is:
          "ok" | "too_short" | "silent" | "empty"
        """
        self.is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        _beep(440, 80)

        duration = time.time() - self._start_time
        if duration < MIN_DURATION:
            return None, "too_short"

        with self._lock:
            chunks = list(self._chunks)

        if not chunks:
            return None, "empty"

        audio = np.concatenate(chunks, axis=0)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < SILENCE_THRESHOLD:
            return None, "silent"

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wavfile.write(tmp.name, SAMPLE_RATE, audio)
        tmp.close()
        return tmp.name, "ok"


# ---------------------------------------------------------------------------
# Beep helper (Windows only; silent fail on other platforms)
# ---------------------------------------------------------------------------

def _beep(freq: int, duration_ms: int):
    try:
        import winsound
        winsound.Beep(freq, duration_ms)
    except Exception:
        pass
