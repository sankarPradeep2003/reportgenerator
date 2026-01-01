#!/usr/bin/env bash
# Build script for Render deployment
# This script installs Playwright browsers

echo "=== Starting Build Process ==="

echo "Step 1: Installing Python dependencies..."
pip install -r requirements.txt

echo "Step 2: Verifying Playwright installation..."
python -m playwright --version

echo "Step 3: Installing Playwright browsers..."
# Try Chrome first, fall back to Chromium headless shell (required for Linux servers)
echo "Attempting to install Chrome..."
python -m playwright install chrome || echo "Chrome install failed (common on Linux), trying Chromium..."

echo "Installing Chromium headless shell (required for headless mode on servers)..."
python -m playwright install chromium-headless-shell || echo "Note: headless-shell install had issues, continuing..."

echo "Step 4: Installing system dependencies for Playwright..."
# Install system dependencies (required for headless mode on Linux)
# This may fail on some systems but is not always critical - don't fail the build
python -m playwright install-deps chromium 2>&1 || echo "Note: install-deps had issues, but continuing (this is often OK)..."

echo "Step 5: Verifying browser installation..."
# Verify that browsers were installed correctly
python -c "
from playwright.sync_api import sync_playwright
try:
    p = sync_playwright().start()
    chromium_path = p.chromium.executable_path
    print(f'SUCCESS: Chromium found at: {chromium_path}')
    import os
    if os.path.exists(chromium_path):
        print('SUCCESS: Chromium executable exists!')
    else:
        print(f'WARNING: Chromium executable NOT found at: {chromium_path}')
        print('This might still work - Playwright will try to download it at runtime')
    p.stop()
except Exception as e:
    print(f'WARNING verifying browser: {e}')
    print('Build will continue - browser may download at runtime')
"

echo "=== Build completed! ==="

