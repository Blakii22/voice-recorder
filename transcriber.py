"""Speech-to-text via faster-whisper, loaded once at startup."""
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Global callback for tqdm interception
_progress_callback: Optional[Callable[[str, any], None]] = None

# Monkey-patch tqdm to intercept huggingface_hub downloads
import huggingface_hub.utils as hf_utils
import faster_whisper.utils as fw_utils
_orig_tqdm = hf_utils.tqdm

import time

class TqdmInterceptor(_orig_tqdm):
    def __init__(self, *args, **kwargs):
        kwargs["disable"] = False
        super().__init__(*args, **kwargs)
        self.disable = False
        self._last_emit_time = 0
        if _progress_callback and getattr(self, "unit", "") == "B":
            _progress_callback("desc", self.desc or "Downloading...")
            
    def update(self, n=1):
        super().update(n)
        if _progress_callback and getattr(self, "unit", "") == "B":
            now = time.time()
            if self.total and self.n >= self.total or (now - self._last_emit_time) > 0.2:
                self._last_emit_time = now
                _progress_callback("update", (self.n, self.total))

hf_utils.tqdm = TqdmInterceptor
fw_utils.disabled_tqdm = TqdmInterceptor


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

    def load_async(self, on_progress=None, on_ready=None, on_error=None):
        """Start loading the Whisper model in a background thread."""
        global _progress_callback
        _progress_callback = on_progress

        def _load():
            try:
                if on_progress:
                    on_progress("status", "Checking model files...")
                    
                logger.info(f"Loading faster-whisper [{self.model_size}] …")
                
                # First download/ensure model exists using huggingface hub
                from faster_whisper.utils import download_model
                
                download_model(self.model_size)
                
                if on_progress:
                    on_progress("status", "Loading model to memory...")
                
                from faster_whisper import WhisperModel
                try:
                    model = WhisperModel(
                        self.model_size, device="auto", compute_type="int8"
                    )
                except Exception as cuda_err:
                    logger.warning(f"GPU/CUDA load failed: {cuda_err}. Falling back to CPU...")
                    model = WhisperModel(
                        self.model_size, device="cpu", compute_type="int8"
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
            finally:
                global _progress_callback
                _progress_callback = None

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
            try:
                segments, _ = self._model.transcribe(
                    wav_path,
                    language=self.language,
                    beam_size=2,
                    vad_filter=True,
                    vad_parameters={
                        "min_silence_duration_ms": 300,
                        "max_speech_duration_s": 28.0
                    },
                    chunk_length=30,
                )
            except Exception as e:
                err_msg = str(e).lower()
                if "cublas" in err_msg or "cuda" in err_msg or "dnn" in err_msg:
                    logger.warning(f"CUDA/cuBLAS failed during inference ({e}). Hot-swapping model to CPU...")
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                    segments, _ = self._model.transcribe(
                        wav_path,
                        language=self.language,
                        beam_size=2,
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 300,
                            "max_speech_duration_s": 28.0
                        },
                        chunk_length=30,
                    )
                else:
                    raise

            return " ".join(seg.text.strip() for seg in segments).strip()
