# JARVIS — Personal Desktop AI Assistant

A sophisticated, Iron Man-inspired desktop AI assistant for Windows featuring a real-time holographic HUD interface, voice-to-voice conversation, system automation, universal browser integration, and pluggable offline AI capabilities.

---

## 📌 Ownership, Attribution & Licensing

This project is a customized personal assistant fork developed and maintained by **Daxit Rathod**

- **Maintainer & Custom Enhancements**: **Daxit Rathod**
  - **Universal Browser Integration**: Dynamic multi-browser detection (Chrome, Edge, Brave, Firefox, Opera, etc.), session and user profile reuse (preventing repeated logins), and visit history tracking.
  - **Windows Path-Independent Architecture**: Resilient local launchers (`run.bat`, `run_silent.vbs`) and virtual environment path portability.
  - **Security & Data Sanitization**: Secure configuration templates (`api_keys.example.json`, `long_term.example.json`), strict git exclusion of private memory and credentials.
  - **Filesystem & Automation Reliability**: Verified file-creation tools, post-action checks, and comprehensive automated test suites.

## 📂 Project Directory Structure

```text
D:\My Assistant\
│
├── README.md                       # Project documentation, architecture & setup guide
├── LICENSE                         # CC BY-NC 4.0 license notice
├── requirements.txt                # Python package dependencies with OS platform markers
├── setup.py                        # One-time environment & Playwright browser installer
├── run.bat                         # Desktop launcher script (directly runs venv python)
├── run_silent.vbs                  # Background silent launcher (runs pythonw without terminal)
├── main.py                         # Application entry point & asyncio event loop orchestrator
├── ui.py                           # PyQt6 holographic HUD interface & 3D visualizer
│
├── actions/                        # The Assistant's Actions / Tools (auto-discovered)
│   ├── background_monitor.py       # Recurring background topic monitor
│   ├── browser_control.py          # Universal browser launcher & DOM automation
│   ├── code_helper.py              # Code analysis, debugging, and execution tools
│   ├── computer_control.py         # Media keys, volume, mouse, keyboard hotkeys
│   ├── computer_settings.py        # Windows settings toggles (Wi-Fi, Bluetooth, Dark mode)
│   ├── desktop.py                  # Window management and virtual desktop controls
│   ├── dev_agent.py                # Autonomous development & shell agent
│   ├── file_controller.py          # Safe file creation, reading, and folder management
│   ├── file_processor.py           # Document formatting & parsing (PDF, Word, Notebooks)
│   ├── flight_finder.py            # Flight search query tool
│   ├── game_updater.py             # Steam / game launcher commands
│   ├── open_app.py                 # Windows application launcher & process watcher
│   ├── proactive.py                # Proactive suggestions and morning brief
│   ├── reminder.py                 # System timer, alarm, and scheduled reminder tool
│   ├── screen_processor.py         # Screen capture and webcam vision analysis
│   ├── send_message.py             # WhatsApp and desktop messaging helper
│   ├── system_monitor.py           # CPU, RAM, GPU, battery, and disk statistics
│   ├── video_player.py             # Local and online media playback controls
│   ├── weather_report.py           # Live weather information tool
│   ├── web_search.py               # Grounded search (Google / DuckDuckGo fallback)
│   └── youtube_video.py            # YouTube search, playback, and transcript extraction
│
├── core/                           # System Core & Hardware Abstractions
│   ├── action_loader.py            # Discovers tool files in actions/ and builds schemas
│   ├── appidentity.py              # Cross-platform application alias resolution
│   ├── audio_devices.py            # Audio enumeration and hardware latency calibration
│   ├── avatar.py                   # 3D holographic sphere and avatar rendering
│   ├── avatar_mesh.py              # 3D polygon mesh transformations
│   ├── browser_manager.py          # Windows Registry browser detection & profile reuse
│   ├── confirm.py                  # On-screen confirmation gate for sensitive actions
│   ├── echo.py                     # Acoustic feedback & echo suppression
│   ├── face_model.obj              # 3D wireframe mesh asset
│   ├── gemini.py                   # Gemini client fallback ladder & quota manager
│   ├── hotkey.py                   # Global hotkey listener (Push-to-Talk)
│   ├── installer.py                # Dynamic pip dependency helper
│   ├── lazyimport.py               # Module proxy loader for rapid application startup
│   ├── llm_client.py               # Local OpenAI-compatible REST client
│   ├── outcome.py                  # Truthful action execution verification markers
│   ├── platform_support.py         # OS feature checks
│   ├── plugin_loader.py            # Plugin discovery and validator
│   ├── prompt.txt                  # Base system prompt with strict execution rules
│   ├── stt.py                      # Speech-to-text base interface
│   ├── tts.py                      # Text-to-speech base interface
│   ├── undo.py                     # Action undo stack for file and setting rollbacks
│   ├── viseme.py                   # Real-time audio spectrum & formant analyzer for mouth shape
│   └── wake_word.py                # Wake-word detector ("Hey Jarvis")
│
├── config/                         # Configuration & Secrets
│   ├── api_keys.json               # (Local only / gitignored) Live API keys & settings
│   ├── api_keys.example.json       # Clean template for git repository
│   └── jarvis.ico                  # Application icon for window and Desktop shortcut
│
├── memory/                         # Persistent Memory & History
│   ├── browser_history.json        # (Local only / gitignored) Browsing history for 'open_last'
│   ├── config_manager.py           # Settings reader/writer
│   ├── long_term.json              # (Local only / gitignored) Personal facts & user preferences
│   ├── long_term.example.json      # Clean memory schema template
│   └── memory_manager.py           # Memory query, search, and update functions
│
├── providers/                      # Pluggable Offline / Local AI Engines
│   ├── audio.py                    # Voice activity detection (VAD) & audio converters
│   ├── base.py                     # Provider interface contracts
│   ├── engine_pipeline.py          # Offline STT + Local LLM + TTS pipeline engine
│   ├── llm_openai.py               # Local LLM connector (Ollama, LM Studio, vLLM)
│   ├── registry.py                 # Provider discovery & lazy loading
│   ├── schema.py                   # Provider configuration schema
│   ├── stt_whisper.py              # Local Whisper STT provider (faster-whisper CPU)
│   ├── tts_elevenlabs.py           # ElevenLabs cloud TTS provider
│   ├── tts_piper.py                # Local Piper neural TTS provider (fast, offline)
│   ├── tts_system.py               # Windows SAPI / macOS native TTS provider
│   └── _tests.py                   # Provider unit test harness
│
├── dashboard/                      # Local Companion Web Dashboard
│   ├── server.py                   # FastAPI HTTPS local server (port 8001)
│   └── static/                     # Web dashboard frontend (AES-256-GCM encrypted)
│
├── plugins/                        # User extension plugins
│   └── _template.py                # Template for authoring custom plugins
│
├── tests/                          # Automated Verification Test Suite
│   ├── test_agent_integration.py   # End-to-end tool execution and safety tests
│   ├── test_browser_repair.py      # Browser automation and DOM typing tests
│   ├── test_filesystem_repair.py   # File controller and path handling tests
│   └── test_universal_browser.py   # Multi-browser detection and session reuse tests
│
└── logs/                           # Runtime Logs
    └── actions.log                 # Tool execution history and debug traces
```

---

## ⚡ How the Assistant Works: Input & Execution Flow

```text
                                 ┌───────────────────────────────────────┐
                                 │          User Voice / Text            │
                                 └───────────────────┬───────────────────┘
                                                     │
                                                     ▼
                                 ┌───────────────────────────────────────┐
                                 │ Microphone Stream (sounddevice)       │
                                 └───────────────────┬───────────────────┘
                                                     │
                          ┌──────────────────────────┴──────────────────────────┐
                          ▼                                                     ▼
           [ONLINE MODE: Gemini Live]                             [OFFLINE MODE: Local Pipeline]
           Bidirectional WebSocket audio stream                    Local Whisper STT (faster-whisper)
           models/gemini-3.1-flash-live-preview                   Local LLM via Ollama / LM Studio
                          │                                                     │
                          └──────────────────────────┬──────────────────────────┘
                                                     │
                                                     ▼
                                 ┌───────────────────────────────────────┐
                                 │ AI Decision & Tool Calling Gate       │
                                 └───────────────────┬───────────────────┘
                                                     │
                          ┌──────────────────────────┴──────────────────────────┐
                          │ (If tool call requested)                            │ (If direct speech)
                          ▼                                                     ▼
           ┌─────────────────────────────┐                       ┌─────────────────────────────┐
           │ Tool Execution (actions/)   │                       │ Audio Output Synthesis      │
           │ • browser_control           │                       │ • Gemini Audio Stream OR    │
           │ • file_controller           │                       │ • Local Piper / System SAPI │
           │ • open_app / settings       │                       └──────────────┬──────────────┘
           └──────────────┬──────────────┘                                      │
                          │                                                     ▼
                          ▼                                      ┌─────────────────────────────┐
           ┌─────────────────────────────┐                       │ Speaker Playback            │
           │ Verified Tool Outcome       │                       │ (viseme mouth sync in UI)   │
           │ Returns structured data     │                       └─────────────────────────────┘
           └──────────────┬──────────────┘
                          │
                          ▼
           AI speaks natural confirmation
```

1. **Audio Capture**: Your microphone streams PCM audio via `sounddevice` to the active engine.
2. **AI Reasoning**: The AI listens continuously. If you ask a conversational question, it replies immediately. If you ask it to perform an action (open a browser, create a file, launch an app), it issues a structured tool call.
3. **Action Dispatch**: `core/action_loader.py` dynamically dispatches the request to the matching tool inside `actions/`.
4. **Verified Execution**: The tool verifies that the real-world action succeeded (e.g., verifying the file exists on disk or the browser launched) and returns outcome data.
5. **Speech & Visuals**: Audio response streams to your speakers while `core/viseme.py` analyzes frequencies in real time to animate the holographic HUD visualizer.

---

## 🚀 Installation & Quick Start

### 1. Prerequisites
- **Operating System**: Windows 10 or 11 (64-bit).
- **Python**: Version **3.11** to **3.13** installed.

### 2. Setup
Open PowerShell or Command Prompt, navigate to the folder, and run the automated setup:

```bat
git clone https://github.com/dakshit157/personal-assistant.git "D:\My Assistant"
cd "D:\My Assistant"
python setup.py
```

`setup.py` will install all required Python packages for your operating system and configure the Playwright browser binaries.

### 3. Configure Your API Key
Copy the example configuration file:

```bat
copy config\api_keys.example.json config\api_keys.json
```

Open `config\api_keys.json` in any text editor and paste your free Gemini API key:
```json
{
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "assistant_name": "JARVIS",
    "voice_name": "Puck"
}
```
*(You can get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey). Your key stays strictly local and is never committed to git.)*

### 4. Running the Assistant
You can launch JARVIS in two ways:
- **Normal Console Mode**: Double-click `run.bat` (shows console logs + holographic HUD).
- **Silent Mode**: Double-click `run_silent.vbs` (runs purely in the background without a command prompt window).

---

## 🔒 Operating Modes: Online vs. Offline

You can switch between high-speed Cloud Mode and 100% Private Offline Mode in `config/api_keys.json` or through the on-screen settings drawer (⚙):

| Feature | Online Mode (Gemini Live) | Offline Mode (Local Pipeline) |
| :--- | :--- | :--- |
| **Voice-to-Voice Latency** | ~200ms ultra-low latency streaming | ~1-3s (depends on local hardware) |
| **Speech-to-Text (STT)** | Gemini Live audio stream | Local **Whisper** (`faster-whisper` on CPU) |
| **Language Model (LLM)** | Gemini 3.1 Flash Live | Local **Ollama** / **LM Studio** / **llama.cpp** |
| **Voice Synthesis (TTS)** | Gemini Cloud Audio / ElevenLabs | Local **Piper Neural TTS** / Windows SAPI |
| **Internet Requirement** | Required | **None** (zero data leaves your PC) |
| **File Operations & Tools**| Fully supported | Fully supported |
| **Universal Browser Launcher**| Fully supported | Fully supported |
| **Live Web Search** | Grounded Google Search & DuckDuckGo | Disabled (offline notice given) |

---

## 🧪 Automated Tests

The project includes unit and integration test suites covering all critical functionality:

```bat
python -m unittest tests/test_universal_browser.py
python -m unittest tests/test_filesystem_repair.py
python -m unittest tests/test_browser_repair.py
python -m unittest tests/test_agent_integration.py
```
*(All 23 test suites verify multi-browser detection, profile preservation, safe file handling, and truthfulness gates.)*

---
