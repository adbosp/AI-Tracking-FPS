$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6.0"

if (-not (Test-Path -LiteralPath ".\yolo11n.pt")) {
    python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name "AI-Tracking-FPS" `
    --icon ".\icon.ico" `
    --add-data ".\icon.ico;." `
    --add-data ".\yolo11n.pt;." `
    --collect-all ultralytics `
    ".\person_tracker.py"

Write-Host "Build complete: dist\AI-Tracking-FPS.exe"
