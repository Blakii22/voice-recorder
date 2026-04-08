"""Speech-to-text via faster-whisper, loaded once at startup."""
import logging
import threading

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_size: str = "medium", language: str = "pl"):
        self.model_size = model_size
        self.language = language
        self._model = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._error: Exception | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_async(self, on_ready=None, on_error=None):
        """Start loading the Whisper model in a background thread."""

        def _load():
            try:
                logger.info(f"Loading faster-whisper [{self.model_size}] …")
                from faster_whisper import WhisperModel
                model = WhisperModel(
                    self.model_size, device="auto", compute_type="int8"
                )
                with self._lock:
                    self._model = model
                self._ready.set()
                logger.info("Model ready.")
                if on_ready:
                    on_ready()
            except Exception as exc:
                self._error = exc
                self._ready.set()          # unblock waiters even on error
                logger.error(f"Model load failed: {exc}")
                if on_error:
                    on_error(exc)

        threading.Thread(target=_load, daemon=True, name="WhisperLoader").start()

    def is_ready(self) -> bool:
        return self._model is not None

    def wait_until_ready(self, timeout: float = 180.0) -> bool:
        return self._ready.wait(timeout=timeout) and self._model is not None

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(self, wav_path: str) -> str:
        if not self.wait_until_ready(timeout=180.0):
            raise RuntimeError("Whisper model not available")

        with self._lock:
            segments, _ = self._model.transcribe(
                wav_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
