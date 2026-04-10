# VoiceNote 🎙️

Push-to-talk voice recorder → automatic transcription (faster-whisper) → Google Sheets via n8n.
Designed as an internal company tool, fully localized and configured out-of-the-box.

---

## Features

- **Instant Localization**: Fully supports Polish, Ukrainian, and English. Change languages on the fly instantly from the setup menu or system tray.
- **Dual Hotkey Modes**: Set both a **Push-to-Talk** hotkey (hold to record) AND a **Toggle** hotkey (click start, click stop) running simultaneously on the exact same app.
- **Auto Update Checker**: Background watcher automatically checks GitHub for newer releases and drops an un-intrusive popup if your build is outdated.
- **Zero-Permission I/O Validation**: The entire app runs flawlessly without needing System Administrator permissions natively off any drive by locally mirroring logs and settings straight to `C:\Users\[User]\Documents\VoiceNote\`.
- **Smart Hardware Fail-safes**: Deep runtime CUDA swap testing dynamically routes high-performance GPU tasks to the standard CPU securely on older machines or machines missing driver toolkits.
- **Static API Configuration**: Webhook endpoints are heavily hardcoded into the source application so users do not have to manually configure them.
- **Offline Fallback**: If the server is unreachable, locally tracked transcriptions are safely dropped into a local `log.csv` file.

---

## Requirements

- Python 3.10+
- Windows (tested on 10/11)
- A CUDA GPU is optional but speeds up transcription significantly

---

## Installation

Just download the latest **`VoiceNote setup.exe`** from the [GitHub Releases](../../releases/latest) page and run the installer.

> **First run downloads the Whisper model** (~1.5 GB for `medium`). This happens once automatically and you will see a download progress screen displaying the MB/s speed.

---

## Running Locally

```bash
py main.py
```

On first launch, a highly visual setup wizard walks you through:
1. **Language Check**: Choose between PL / UK / EN.
2. **Your Name**: Appears in Google Sheets transcriptions.
3. **Your Macros**: Supports distinct binds for Push-To-Talk and Toggle recording modes!
4. **Your Microphone**: Fast realtime DB verification.

After setup, the app lives out of the way in the **Windows System Tray**.

---

## Compiling for Distribution

To distribute this to your company's machines, install it as an instantly-booting compiled folder using PyInstaller rather than a standalone `.exe`.

1. Install PyInstaller: `py -m pip install pyinstaller`
2. Fetch the path of your customtkinter library: `py -c "import customtkinter; import site; print(customtkinter.__file__)"`
3. Compile the app into the `dist/main` folder using this exact fully resolved build command (ensuring ONNX, version trackers, and UI tools are bundled correctly): 
   ```bash
   py -m PyInstaller --noconfirm --onedir --windowed --collect-data faster_whisper --add-data "C:\Users\YOUR_USERNAME\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\customtkinter;customtkinter/" --add-data "version.txt;." main.py
   ```
4. Use **Inno Setup** to wrap the resulting `dist/main` folder into an automated installation wizard!

---

## Configuring the n8n Hook

### 1. Set up the webhook URL and API key

Unlike older versions, the webhook configuration is statically compiled into the source codebase (`sender.py`) to prevent user error. 

```python
N8N_WEBHOOK_URL = "https://YOUR_N8N_SERVER/webhook/YOUR_WEBHOOK_ID"
N8N_API_KEY = "YOUR_SECRET_KEY"
```

### 2. Create the n8n workflow

In your n8n instance:

1. **Add a Webhook node**
   - Method: `POST`
   - Authentication: `Header Auth`
   - Header name: `X-API-Key`
   - Header value: *(match the secret key from `sender.py`)*

2. **Add a Google Sheets node** → *Append Row*
   - Spreadsheet: *(your sheet)*
   - Sheet: *(your tab)*
   - Column mapping:
     | n8n field | Column |
     |-----------|--------|
     | `{{$json.speaker}}` | A (Speaker) |
     | `{{$json.text}}` | B (Transcription) |
     | `{{$json.timestamp}}` | C (Time) |

---

## Changing settings later

Right-click the VoiceNote tray icon → **Open Settings** to change your name, model size, hotkeys, or interface language seamlessly without rebooting the app.

---

## Model sizes (accuracy vs speed)

| Model | RAM | Speed (CPU) | Polish accuracy |
|-------|-----|-------------|-----------------|
| tiny | 1 GB | Very fast | Low |
| small | 2 GB | Fast | Good |
| **medium** (default) | 5 GB | OK | Very good |
| large-v3 | 10 GB | Slow on CPU | Best |

---

## Troubleshooting

**Data and Config files are "missing"?**
All user modifications, debug logs (`voicenote.log`, `crash_log.txt`), and offline fallbacks (`log.csv`) are safely walled off in your `Documents\VoiceNote` folder!

**App asks for device every time** — the USB mic was assigned a different index. Select it again in the dialog.

**No sound detected** — check that the mic is not muted in Windows sound settings.

**Transcription is slow** — switch to a smaller `small` model in Settings or use a machine with a GPU.

**Webhook errors** — check n8n logs; verify your constants in `sender.py` match perfectly.
