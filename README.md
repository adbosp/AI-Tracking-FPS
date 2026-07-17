# AI Tracking FPS

Windows screen-based AI person tracker with FPS-style crosshair and configurable mouse assistance.

## Features

- Select any screen region and detect people with YOLO.
- Draw click-through tracking boxes over the selected area.
- Optional mouse tracking with independent lock-strength and movement-speed controls.
- Configurable global hotkeys and hold-to-track key.
- Four FPS crosshair styles centered on the primary display.
- Optional W/A/S/D Auto Move cycle.
- Vietnamese and English menu languages.
- Dark borderless UI and system-tray support.

## Run from source

Requires Python 3.11 or newer.

```powershell
python -m pip install -r requirements.txt
python person_tracker.py
```

The YOLO model is downloaded automatically on first use if `yolo11n.pt` is not already beside the script.

## Build the Windows application

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The packaged application is created at:

```text
dist\AI-Tracking-FPS.exe
```

The output is a self-contained, single-file Windows executable. End users do not need Python or any additional dependencies installed.

## Default hotkeys

| Action | Key |
|---|---|
| Show or hide the menu | F10 |
| Start or pause tracking | F8 |
| Toggle Auto Mouse | F9 |
| Hold Auto Mouse | Left Alt |

All hotkeys can be changed from the menu.
