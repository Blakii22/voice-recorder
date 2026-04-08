# VoiceNote 🎙️

Push-to-talk voice recorder → automatic transcription (faster-whisper) → Google Sheets via n8n.

---

## Requirements

- Python 3.10+
- Windows (tested on 10/11)
- A CUDA GPU is optional but speeds up transcription significantly

---

## Installation

```bash
cd voice-recorder
pip install -r requirements.txt
```

> **First run downloads the Whisper model** (~1.5 GB for `medium`). This happens once automatically.

---

## Running

```bash
python main.py
```

On first launch a setup wizard walks you through:
1. Your name (appears in Google Sheets)
2. Your push-to-talk hotkey
3. Your microphone

After setup the app lives in the **system tray**. Hold your hotkey to record, release to transcribe and send.

---

## Configuring n8n

### 1. Set up the webhook URL and API key

Open `config.json` (created after first run) and fill in:

```json
{
  "webhook_url": "https://YOUR_N8N_SERVER/webhook/YOUR_WEBHOOK_ID",
  "webhook_api_key": "YOUR_SECRET_KEY"
}
```

Or open Settings from the tray icon.

### 2. Create the n8n workflow

In your n8n instance:

1. **Add a Webhook node**
   - Method: `POST`
   - Authentication: `Header Auth`
   - Header name: `X-API-Key`
   - Header value: *(same key as above)*
   - Copy the webhook URL into `config.json`

2. **Add a Google Sheets node** → *Append Row*
   - Spreadsheet: *(your sheet)*
   - Sheet: *(your tab)*
   - Column mapping:
     | n8n field | Column |
     |-----------|--------|
     | `{{$json.speaker}}` | A (Speaker) |
     | `{{$json.text}}` | B (Transcription) |
     | `{{$json.timestamp}}` | C (Time) |

3. **Activate the workflow.**

### Payload sent by VoiceNote

```json
{
  "speaker": "Jan Kowalski",
  "text": "Transkrypcja nagranego zdania…",
  "timestamp": "2026-04-08T14:30:00"
}
```

---

## Offline fallback

If the webhook is unreachable every transcription is still saved to **`log.csv`** in the app folder:

| timestamp | speaker | text | sent_to_n8n |
|-----------|---------|------|-------------|
| 2026-04-08T14:30:00 | Jan Kowalski | Transkrypcja… | no |

Open it from *Tray → View Log*.

---

## Changing settings later

Right-click the tray icon → **Open Settings** to change your name, webhook URL, API key, or model size.

To re-run the audio device wizard, delete `config.json` and restart.

---

## Model sizes (accuracy vs speed)

| Model | RAM | Speed (CPU) | Polish accuracy |
|-------|-----|-------------|-----------------|
| tiny | 1 GB | Very fast | Low |
| small | 2 GB | Fast | Good |
| **medium** (default) | 5 GB | OK | Very good |
| large-v3 | 10 GB | Slow on CPU | Best |

Change via Settings or edit `config.json` → `"model_size"`.

---

## Troubleshooting

**App asks for device every time** — the USB mic was assigned a different index. Select it again in the dialog.

**No sound detected** — check that the mic is not muted in Windows sound settings.

**Transcription is slow** — switch to a smaller model or use a machine with a GPU.

**Webhook errors** — check n8n logs; verify the URL and API key match exactly.
