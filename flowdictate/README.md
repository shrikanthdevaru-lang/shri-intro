# 🎙 FlowDictate

> **Hold a key. Speak. Release. Polished text appears instantly — in any app.**

FlowDictate is a macOS menu-bar voice dictation app built for Apple Silicon.  
It works like Wispr Flow: hold `Right ⌘`, dictate, release, and Claude-cleaned text is pasted at your cursor — in any application, anywhere on your Mac.

---

## Features

| Feature | Detail |
|---|---|
| **Global hotkey** | Hold Right ⌘ to record (works in any app) |
| **Cloud transcription** | OpenAI Whisper API (`whisper-1`) |
| **Local / offline mode** | `faster-whisper` on CPU, zero data leaves your Mac |
| **LLM cleanup** | Claude Haiku cleans filler words and fixes punctuation |
| **Context-aware** | Adjusts tone for Messages, Mail, VS Code, Notes, etc. |
| **Custom dictionary** | SQLite store — words fed to Whisper for better accuracy |
| **Transcription history** | Last 10 results, click to re-paste |
| **Floating overlay** | Animated pill shows Recording → Transcribing states |
| **Privacy first** | Temp audio deleted immediately; clipboard restored in 2 s |

---

## Prerequisites

- macOS 13 Ventura or later (Apple Silicon recommended)
- **Python 3.12+** — install via [python.org](https://www.python.org/downloads/) or `brew install python@3.12`
- **Homebrew** — [brew.sh](https://brew.sh)
- `portaudio` (required by sounddevice): `brew install portaudio`

---

## Installation

```bash
# 1. Clone / download the project
cd ~/flowdictate

# 2. Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your API keys
cp .env.example .env
open -e .env   # or use any text editor
```

Edit `.env` and add your keys:

```dotenv
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## macOS Permissions

FlowDictate needs two permissions (granted **once** in System Settings):

### 1. Accessibility (for global hotkey + Cmd+V injection)
`System Settings → Privacy & Security → Accessibility`  
Add your Terminal app **and** Python (`.venv/bin/python3`).

### 2. Microphone
`System Settings → Privacy & Security → Microphone`  
Add your Terminal app.

> **Tip**: If pasting doesn't work, make sure the app you're pasting into also has Accessibility permission, or use `System Events` permission.

---

## Running FlowDictate

```bash
source .venv/bin/activate
python main.py
```

A 🎙 icon appears in your menu bar. FlowDictate is now running.

### First-time setup — grant permissions when prompted
macOS will ask for Accessibility and Microphone permissions. After granting them, restart FlowDictate.

---

## Usage

| Action | What happens |
|---|---|
| Hold `Right ⌘` | Recording starts — animated overlay appears |
| Speak | Dictate naturally; overlay shows waveform |
| Release `Right ⌘` | Transcription begins — spinner overlay shows |
| *(auto)* | Cleaned text is pasted at your cursor |

### Workflow example

1. Open any app (Messages, Mail, VS Code, Notes…)
2. Click where you want text
3. Hold `Right ⌘`, say your text, release
4. Watch polished text appear instantly

---

## Menu Bar Options

| Item | Action |
|---|---|
| **Mode: Cloud ✓ / Local ✓** | Toggle between OpenAI Whisper and local faster-whisper |
| **Edit Dictionary…** | Add / remove / search custom words |
| **History** | Re-paste any of the last 10 transcriptions |
| **Preferences…** | Change hotkey, mode, cleanup toggle, local model size |
| **Quit** | Exit FlowDictate |

---

## Adding Custom Words to the Dictionary

Custom words are sent to Whisper as a vocabulary prompt, improving recognition of proper nouns, technical terms, and unusual words.

### Via the UI
1. Click `🎙` in the menu bar → **Edit Dictionary…**
2. Type a word in the text box at the bottom
3. Press Enter or click **Add Word**

### Pre-seeded words
The dictionary comes with these defaults:
- Bagalkot, Siddarameshwara, Sanskrit, Vachana, Lingayata, Basavanna

### Programmatically
```python
from dictionary import VocabularyDB
db = VocabularyDB()
db.add_word("Kubernetes")
db.add_word("WWDC")
```

---

## Keyboard Shortcut Customisation

Edit `Preferences…` → **Hotkey key name** and enter any pynput key name:

| Key | Value to enter |
|---|---|
| Right ⌘ (default) | `right_cmd` |
| Left ⌘ | `left_cmd` |
| F13 | `f13` |
| F14 | `f14` |
| Right Option | `right_alt` |

Or edit `.env` directly:

```dotenv
HOTKEY=f13
```

Restart FlowDictate for changes to take effect.

---

## Transcription Modes

### Cloud mode (default)
- Uses OpenAI `whisper-1` API
- Requires `OPENAI_API_KEY`
- Fastest, highest accuracy
- Falls back to local automatically if no internet or API error

### Local mode (offline / privacy)
- Uses `faster-whisper` with `turbo` model (recommended for M-series)
- Zero audio data leaves your Mac
- First use downloads the model (~800 MB for turbo)
- Toggle via menu bar: **Mode: Local ✓**
- Change model size in Preferences → **Local model size**

Available model sizes (trade-off: speed vs accuracy):
`tiny` → `base` → `small` → `medium` → `large-v3` → `turbo`

---

## LLM Cleanup

Claude Haiku post-processes every transcript to:
- Remove filler words (`um`, `uh`, `like`, `you know`…)
- Fix punctuation and capitalisation
- Fix grammar while preserving your natural voice
- Apply context-appropriate formatting (casual for Messages, formal for Mail, etc.)

**Disable cleanup**: `Preferences… → LLM cleanup → uncheck`  
**API key required**: `ANTHROPIC_API_KEY` in `.env`  
**Timeout**: 8 seconds — falls back to raw transcript if exceeded

---

## Privacy

- Audio is recorded to `/tmp/flowdictate/` and **deleted immediately** after transcription
- Transcription content is **never logged** — only metadata (duration, word count, latency)
- Clipboard is restored to its previous content 2 seconds after injection
- Local mode sends **no data** to any server

---

## Configuration Reference

All settings can be set in `.env`:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key for cloud Whisper |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key for Claude cleanup |
| `HOTKEY` | `right_cmd` | pynput key name for push-to-talk |
| `DEFAULT_MODE` | `cloud` | `cloud` or `local` |
| `WHISPER_LOCAL_MODEL` | `turbo` | faster-whisper model size |
| `CLEANUP_ENABLED` | `true` | Enable/disable LLM cleanup |
| `HISTORY_SIZE` | `10` | Number of transcriptions to keep |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Hotkey not working | Grant Accessibility permission in System Settings |
| Mic not recording | Grant Microphone permission; check `sounddevice` device list |
| Text not pasting | Check Accessibility permission for the target app |
| API error | Verify API keys in `.env`; check internet connection |
| Local model slow | Use `tiny` or `base` model in Preferences |
| "Module not found" | Activate venv: `source .venv/bin/activate` |

### Debug mode
```bash
LOG_LEVEL=DEBUG python main.py
```

---

## Architecture

```
main.py          ← rumps menu bar + orchestration
├── hotkey.py    ← pynput global key listener (daemon thread)
├── recorder.py  ← sounddevice mic capture (callback thread)
├── transcriber.py ← OpenAI Whisper / faster-whisper
├── cleaner.py   ← Anthropic Claude haiku post-processing
├── injector.py  ← clipboard + Cmd+V text injection
├── overlay.py   ← Tkinter floating pill animation
├── context.py   ← pyobjc frontmost app detection
├── dictionary.py ← SQLite custom vocabulary + Tkinter UI
└── config.py    ← all settings from .env
```

---

## License

MIT — free to use, modify, and distribute.
