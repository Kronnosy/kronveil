# Kronos Veil (KV)

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
- **Chat Provider Architecture:**
  - **Local Demo Provider:** Simulates realistic viewer chat and reactions out of the box with zero setup or credentials required.
  - **Twitch Live Chat:** Direct SSL IRC connection (`irc.chat.twitch.tv:6697`) supporting anonymous read-only access—no developer account or OAuth tokens required for public channels.
  - **YouTube Live Chat:** Architecture-ready integration via YouTube Data API v3.
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
   git clone https://github.com/your-username/kronos-veil.git
   cd kronos-veil
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
kronos-veil/
├── main.py                     # Application entry point & CLI parser
├── requirements.txt            # Package dependencies
├── README.md                   # Documentation & OBS guidance
├── KronosVeil.spec             # PyInstaller standalone executable specification
│
├── kronos_veil/
│   ├── __init__.py             # Version and app metadata
│   ├── app.py                  # Core application orchestrator
│   ├── config.py               # JSON settings manager & multi-monitor recovery
│   ├── hotkeys.py              # Win32 RegisterHotKey background worker
│   ├── overlay.py              # Frameless transparent overlay & message widgets
│   ├── settings_window.py      # Modern dark HUD control panel
│   ├── tray.py                 # Windows system tray integration & menu
│   │
│   ├── windows/
│   │   ├── __init__.py
│   │   ├── capture_protection.py # SetWindowDisplayAffinity & WDA_EXCLUDEFROMCAPTURE
│   │   └── window_styles.py      # Win32 WS_EX_TRANSPARENT & HWND_TOPMOST
│   │
│   └── chat/
│       ├── __init__.py
│       ├── base.py             # ChatMessage dataclass & ChatProvider base
│       ├── demo.py             # Offline simulation chat generator
│       ├── twitch.py           # Anonymous SSL Twitch IRC provider
│       └── youtube.py          # YouTube Live Data API provider
│
├── assets/
│   └── icon.png                # High-DPI application icon
│
└── tests/                      # Automated test suite
    ├── conftest.py
    ├── test_capture_protection.py
    ├── test_chat_providers.py
    ├── test_config.py
    ├── test_hotkeys.py
    ├── test_overlay_logic.py
    ├── test_ui_windows.py
    └── test_window_styles.py
```

---

## License

MIT License. See LICENSE for details.
