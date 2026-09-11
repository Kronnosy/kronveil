# Kronos Veil (KV)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GUI: PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52.svg?logo=qt&logoColor=white)](https://www.qt.io/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10_%2F_11-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Tests: 140 Passing](https://img.shields.io/badge/Tests-140_Passing-brightgreen.svg)]()

> **"Your chat. Your screen. Invisible to stream."**

**Kronos Veil** is a lightweight, private livestream chat overlay designed specifically for streamers with a single monitor. It renders chat transparently on top of full-screen borderless games and desktop applications while excluding the overlay window from OBS and screen capture using native Windows Desktop Window Manager (DWM) display affinity APIs.

---

## Key Features

- **OBS Capture Privacy:** Native Windows capture exclusion (`WDA_EXCLUDEFROMCAPTURE = 0x00000011`) excludes the chat from screen recorders and stream broadcasts.
- **Built-in Capture Test Mode:** Displays a high-contrast diagnostic banner so you can instantly verify in OBS whether the overlay is captured before going live.
- **Dual Operational Modes:**
  - **Edit Mode:** Drag, resize with bottom-right corner grip, adjust settings, and reposition chat anywhere on your monitors.
  - **Locked Mode:** Strips all borders and edit controls, displaying a minimal, unobtrusive HUD.
- **Optional Click-Through:** Mouse clicks pass straight through the overlay to underlying games (`WS_EX_TRANSPARENT`).
- **Global Hotkey Recovery:** Toggle between Edit Mode and Locked Mode with `Ctrl + Shift + F10` even when playing a game.
- **Persistent System Tray:** Never get locked out; control modes, privacy, and settings from the Windows taskbar notification area.
- **Streamer UI Studio & 1-Click Themes:** Real-time interactive Live Preview sandbox in Settings with 1-click broadcast themes (Cyberpunk Cyan, Obsidian Stealth, Frosted Slate, Neon Sunset, Retro Terminal) and Card, Bubble, or Clean message presentation styles.
- **In-Game Toast Deck & Mention Alerts:** Ephemeral, capture-protected floating notifications for OBS stream status, dropped frame spikes, and glowing streamer mention highlights.
- **Standalone Modular Mini-HUD Window:** An independent, capture-protected floating telemetry HUD showing live stream status, recording state, uptime, dynamic bitrate health gauge, and dropped frames warnings.
- **Stream Events Deck & Live Goal Bar:** Independent capture-protected floating widget tracking latest Follower, Subscriber, Bits, and Tips along with an animated live goal progress bar (tokenless demo cycle + optional StreamElements JWT).
- **Per-Game Auto-Switching Profiles:** Automatically shifts overlay, HUD, and widget positions and sizes depending on which game is focused (Valorant, CS2, League of Legends, or custom), powered by non-invasive Win32 ctypes window detection.
- **Emote & Badge Rendering Engine:** Built-in support for Twitch and 7TV popular emotes (KEKW, Pog, monkaS, etc.) and user badges (Broadcaster, Moderator, VIP, Sub), with background async downloading and LRU disk caching.
- **Chat Provider Architecture:**
  - **Local Demo Provider:** Simulates realistic viewer chat and reactions out of the box with zero setup or credentials required.
  - **Twitch Live Chat:** Direct SSL IRC connection (`irc.chat.twitch.tv:6697`) supporting anonymous read-only access—no developer account or OAuth tokens required for public channels.
  - **Kick Live Chat:** Direct Pusher WebSocket integration for real-time Kick.com chat without requiring API keys or authentication.
  - **YouTube Live Chat:** Architecture-ready integration via YouTube Data API v3.
- **Multistream Unified Chat & Smart Filters (v1.2):** Connect to Twitch, Kick, and YouTube simultaneously into one unified chronological feed with platform badges (`TW`, `KICK`, `YT`), automatic bot command suppression (`!commands`), and rapid duplicate spam protection.
- **Mobile LAN Web Companion & Touch Stream Deck (v1.2):** Zero-app local HTTP + SSE server allowing any smartphone or tablet on the same Wi-Fi to serve as an interactive touch Stream Deck (lock toggle, click-through, OBS stream/record, scene switcher), real-time live chat reader, and telemetry display with instant QR camera pairing and PIN security.
- **Windows Auto-Start on Boot (v1.2):** Non-elevated auto-start registration via Windows HKCU Run registry key for background boot execution.
- **OBS Studio WebSocket v5 Integration:** Direct connection to OBS (`obs-websocket` 5.x) monitoring bitrate health and alerting on dropped frames in real-time.
- **Multi-Monitor Safe:** Automatically detects off-screen coordinates on startup and repositions within visible monitor bounds.
- **Zero Injections / Non-Invasive:** No DLL injection, no hooking, no game memory tampering, no anti-cheat triggers, and no administrator privileges required.

---

## ⚠️ Important Privacy Warning

> [!WARNING]
> **Always verify your OBS preview before going live.**
> 
> Windows `SetWindowDisplayAffinity(0x11)` instructs the Windows Desktop Window Manager (DWM) not to include the window in capture streams (such as Windows Graphics Capture and Window Capture).
> 
> However, capture behavior depends on your Windows version, graphics driver configuration, and OBS capture mode:
> - **Game Capture (Recommended):** Overlays on the desktop are never captured because Game Capture hooks the game engine directly.
> - **Window Capture:** Excluded when using the default "Windows Graphics Capture (WGC)" method.
> - **Display / Desktop Capture:** Depending on Windows build and GPU setup, full desktop capture may capture desktop overlays.
> 
> **Never assume universal invisibility.** Always use **Capture Test Mode** to confirm your OBS setup.

---

## System Requirements

- **Operating System:** Windows 10 Version 2004 (Build 19041+) or Windows 11.
- **Python:** Python 3.10+ (for running from source).
- **Display Mode:** Windowed or Borderless Fullscreen for games (Exclusive Fullscreen prevents desktop overlays from rendering).

---

## Quick Start (Running from Source)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Kronnosy/kronveil.git
   cd kronveil
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch Kronos Veil:**
   ```bash
   python main.py
   ```

### Command-Line Options

```bash
python main.py --help
python main.py --debug            # Enable verbose debug logging
python main.py --reset-position   # Force overlay to center of primary monitor
python main.py --config path.json # Use custom configuration file
```

---

## Building Standalone Windows Executable (.exe)

You can compile Kronos Veil into a single standalone Windows executable using PyInstaller:

```bash
pyinstaller KronosVeil.spec
```

The compiled `KronosVeil.exe` will be located in the `dist/` directory and can be run on any compatible Windows PC without Python installed.

---

## Overlay Controls & Hotkeys

| Action | Shortcut / Method | Description |
| :--- | :--- | :--- |
| **Toggle Lock / Edit Mode** | `Ctrl + Shift + F10` | Switches between draggable/resizable Edit Mode and minimal Locked Mode |
| **Toggle Click-Through** | `Ctrl + Shift + F11` | Pass mouse clicks through to background games |
| **Peek Chat** | `Ctrl + Shift + F9` | Temporarily brings overlay topmost |
| **Drag Overlay** | Click & Drag (Edit Mode) | Move overlay anywhere across connected monitors |
| **Resize Overlay** | Drag ◢ Grip (Edit Mode) | Resize chat box from the bottom-right corner |
| **System Tray Menu** | Right-click Tray Icon | Quick access to lock/unlock, settings, and recovery |

---

## OBS Studio Recommended Configuration

1. In OBS, add a **Game Capture** source targeting your game.
2. In Kronos Veil Settings (or Tray), toggle **Capture Test Mode**.
3. Verify that the bright yellow test banner appears on your monitor but **does not** appear in your OBS stream preview.
4. Turn off Test Mode and start streaming!

---

## Configuration (`settings.json`)

Settings are saved automatically in `%APPDATA%\KronosVeil\settings.json`.

Available configurations:
- `overlay_x`, `overlay_y`, `overlay_width`, `overlay_height`: Geometry.
- `overlay_opacity` (0.1 to 1.0): Overall transparency.
- `background_opacity` (0.0 to 1.0): Chat container background darkness.
- `font_size`, `message_spacing`, `text_shadow`: Typography settings.
- `max_messages`, `message_lifetime_sec`, `fade_duration_sec`: Message scroll & fade timing.
- `capture_protection`: Toggle `WDA_EXCLUDEFROMCAPTURE`.
- `chat_provider`: `"demo"`, `"twitch"`, or `"youtube"`.
- `twitch_channel`: Target channel name for Twitch IRC.

---

## Testing

Execute the automated test suite with pytest:

```bash
pytest -v
```

---

## Architecture & Project Structure

```text
kronveil/
├── main.py                     # Application entry point & CLI parser
├── requirements.txt            # Package dependencies
├── README.md                   # Documentation & OBS guidance
├── LICENSE                     # MIT License
├── KronosVeil.spec             # PyInstaller standalone executable specification
│
├── kronos_veil/
│   ├── __init__.py             # Version and app metadata
│   ├── app.py                  # Core application orchestrator
│   ├── autostart.py            # Windows HKCU Run auto-start manager
│   ├── config.py               # JSON settings manager & multi-monitor recovery
│   ├── event_deck.py           # Stream Events Deck & live goal progress bar
│   ├── hotkeys.py              # Win32 RegisterHotKey background listener
│   ├── hud.py                  # Modular Mini-HUD telemetry window
│   ├── overlay.py              # Frameless transparent overlay & message widgets
│   ├── profiles.py             # Per-game auto-switching profiles & window detector
│   ├── question_deck.py        # Smart Q&A Deck window for audience questions
│   ├── settings_window.py      # Streamer UI Studio & configuration dialog
│   ├── themes.py               # 1-Click broadcast theme presets
│   ├── toast.py                # In-game notification toast alerts
│   ├── tray.py                 # Windows system tray integration & menu
│   │
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── aggregator.py       # Multistream unified chat aggregator
│   │   ├── base.py             # ChatMessage dataclass & ChatProvider base
│   │   ├── demo.py             # Offline simulation chat generator
│   │   ├── emotes.py           # Twitch & 7TV emote resolution and LRU caching
│   │   ├── filters.py          # Bot suppression & duplicate spam filters
│   │   ├── hype.py             # Chat velocity analyzer & OBS auto-clip trigger
│   │   ├── kick.py             # Pusher WebSocket Kick.com chat provider
│   │   ├── questions.py        # Natural language question detector
│   │   ├── twitch.py           # Anonymous SSL Twitch IRC provider
│   │   └── youtube.py          # YouTube Live Data API provider
│   │
│   ├── gsi/
│   │   ├── __init__.py
│   │   ├── clutch_manager.py   # CS2 Clutch Silence auto-dimming logic
│   │   ├── installer.py        # CS2 cfg generator and auto-installer
│   │   ├── models.py           # Valve GSI telemetry data models
│   │   └── server.py           # Zero-injection local GSI HTTP server
│   │
│   ├── obs/
│   │   ├── __init__.py
│   │   └── client.py           # OBS Studio WebSocket v5 client & telemetry
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── companion.py        # Mobile LAN HTTP + SSE Web Companion server
│   │   ├── qr.py               # Pure-Python SVG QR pairing code generator
│   │   └── templates/
│   │       └── index.html      # Touch-friendly Stream Deck mobile web app
│   │
│   └── windows/
│       ├── __init__.py
│       ├── capture_protection.py # WDA_EXCLUDEFROMCAPTURE manager
│       └── window_styles.py      # Win32 WS_EX_TRANSPARENT & HWND_TOPMOST
│
├── assets/
│   └── icon.png                # High-DPI application icon
│
└── tests/                      # Automated test suite (140 tests)
```

---

## License

MIT License. See LICENSE for details.
