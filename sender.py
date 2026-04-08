"""Sends transcriptions to the n8n webhook; falls back to local CSV."""
import csv
import logging
import threading
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
LOG_PATH = Path("log.csv")

_PLACEHOLDER_MARKER = "[YOUR_N8N_SERVER_ADDRESS]"


def _ensure_csv_headers():
    if not LOG_PATH.exists():
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp", "speaker", "text", "sent_to_n8n"])


def _append_csv(speaker: str, text: str, timestamp: str, sent: bool):
    _ensure_csv_headers()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([timestamp, speaker, text, "yes" if sent else "no"])


def send_transcription(
    speaker: str,
    text: str,
    webhook_url: str,
    api_key: str = "",
    on_success=None,
    on_failure=None,
):
    """Post transcription to n8n in a background thread."""

    def _run():
        ts = datetime.now().isoformat(timespec="seconds")
        payload = {"speaker": speaker, "text": text, "timestamp": ts}

        # Skip if placeholder not yet configured
        if not webhook_url or _PLACEHOLDER_MARKER in webhook_url:
            logger.warning("Webhook URL not configured — saving locally only.")
            _append_csv(speaker, text, ts, sent=False)
            if on_failure:
                on_failure("Webhook URL not configured")
            return

        headers = {"Content-Type": "application/json"}
        if api_key and "[YOUR_API_KEY_HERE]" not in api_key:
            headers["X-API-Key"] = api_key

        try:
            r = httpx.post(webhook_url, json=payload, headers=headers, timeout=10.0)
            r.raise_for_status()
            logger.info(f"Sent ✓  {speaker}: {text[:60]!r}")
            _append_csv(speaker, text, ts, sent=True)
            if on_success:
                on_success()
        except Exception as exc:
            logger.error(f"Webhook failed: {exc}")
            _append_csv(speaker, text, ts, sent=False)
            if on_failure:
                on_failure(str(exc))

    threading.Thread(target=_run, daemon=True, name="WebhookSender").start()
