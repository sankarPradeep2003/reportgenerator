## Report Generator - Cross-Platform Flask App

A Flask web application that automates report generation using Playwright. Works on **Windows** and **macOS**.

### Setup

#### Windows
1) Create/activate venv and install deps:
```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

2) Run the app:
```powershell
python app.py
```

#### macOS
1) Create/activate venv and install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Run the app:
```bash
python app.py
```

Open `http://127.0.0.1:8000`, enter a URL, and click "Open in Chrome".

### Auto-login via Playwright (optional)
To enable auto-login (fill username/password automatically), install Playwright browsers:

**Windows:**
```powershell
python -m playwright install chromium
```

**macOS:**
```bash
python3 -m playwright install chromium
```

Then, in the form, also fill the User ID and Password. The app will open Chromium and attempt to fill common username/password fields and click Sign in. For reliability, share your portal's exact labels/selectors so we can hardcode them.

### Notes
- **Cross-platform support**: The app automatically detects your operating system and uses the appropriate paths.
- **Chrome detection**: The app searches for Chrome in standard installation locations:
  - **Windows:**
  - `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
  - `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`
  - **macOS:**
    - `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
    - `~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- **Downloads directory**: Files are automatically saved to your Downloads folder:
  - **Windows**: `%USERPROFILE%\Downloads`
  - **macOS**: `~/Downloads`
- If Chrome is installed elsewhere, update `find_chrome_exe()` in `app.py`.

